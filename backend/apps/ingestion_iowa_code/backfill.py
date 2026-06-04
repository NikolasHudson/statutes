"""Insert an *older* Iowa Code edition behind the data already in the store.

The forward ingest path (``differ`` + ``writer``) assumes the incoming edition
is the newest one: it closes the current open version and opens a new one. A
prior edition is the opposite — it has to slot in *behind* whatever is already
loaded, without disturbing the current (and already-embedded) versions.

This module does exactly that, and is written to be re-runnable so editions can
be loaded one after another, each further back in time:

    register the current edition (e.g. 2026)  ->  backfill 2025  ->  backfill 2024 ...

For each section in the incoming (older) edition Y, sitting behind the node's
current *earliest* known version at date ``D_next``:

* unchanged (content_hash matches the earliest version) -> backdate that
  version's ``effective_from`` to ``D_Y``. One fact, a longer validity
  interval; no duplicate row, no new embedding.
* changed -> insert a historical version ``[D_Y, D_next)`` carrying the old
  text. The newer version is left untouched (embedding preserved).
* present in Y but with no node at all (repealed/removed since) -> create the
  node + a version ``[D_Y, D_next)`` and mark it repealed.
* in the store but absent from Y (added after Y) -> left alone; it already
  resolves to "absent" at ``D_Y`` because its earliest version starts later.

Nothing here writes embeddings: historical editions are for diffing/display,
not semantic search, so ``embedding`` stays NULL on backfilled rows.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from django.db import transaction

from apps.corpus.models import Node, NodeType, NodeVersion, ReviewStatus, Source

from .parser import ParsedChapter, ParsedSection, ParseResult, _hash, _normalize_body
from .writer import _section_metadata


def _body_fingerprint(body_text: str) -> str:
    """Hash of the *current* normalized body.

    We deliberately recompute rather than trust ``NodeVersion.content_hash``:
    some stored hashes predate later normalization changes and no longer match
    their own ``body_text``, which would make unchanged sections look amended.
    The body text itself reproduces exactly from a re-scrape, so it is the
    reliable basis for edition-to-edition comparison.
    """
    return _hash(_normalize_body(body_text))


@dataclass
class BackfillReport:
    year: int
    as_of: str
    next_as_of: str
    sections_seen: int = 0
    unchanged_backdated: int = 0
    changed_inserted: int = 0
    repealed_between_created: int = 0
    added_after_skipped: int = 0
    chapters_created: int = 0
    already_present: int = 0  # idempotent re-run: version already at D_Y

    def as_dict(self) -> dict:
        return asdict(self)


def backfill_edition(
    *,
    parsed: ParseResult,
    source: Source,
    as_of: dt.date,
    next_as_of: dt.date,
    review_status: str = ReviewStatus.APPROVED,
    dry_run: bool = False,
) -> BackfillReport:
    """Slot the older edition ``parsed`` into the timeline behind ``next_as_of``.

    ``as_of`` is this (older) edition's point-in-time date; ``next_as_of`` is
    the as-of date of the edition immediately newer than it (used to close
    historical versions of nodes that no longer exist). Must satisfy
    ``as_of < next_as_of``.
    """

    if as_of >= next_as_of:
        raise ValueError(
            f"as_of ({as_of}) must be strictly before next_as_of ({next_as_of})"
        )

    report = BackfillReport(
        year=parsed.code_year, as_of=as_of.isoformat(), next_as_of=next_as_of.isoformat()
    )

    with transaction.atomic():
        chapter_type = NodeType.objects.get(source=source, key="chapter")
        section_type = NodeType.objects.get(source=source, key="section")

        existing_nodes: dict[str, Node] = {
            n.path: n
            for n in Node.objects.filter(source=source).select_related("node_type")
        }
        earliest = _earliest_versions(source)

        chapter_nodes = _ensure_chapter_nodes(
            source, chapter_type, parsed.chapters, existing_nodes, report, dry_run
        )

        parsed_section_paths: set[str] = set()
        parsed_chapter_paths = {ch.path for ch in parsed.chapters}

        for section in parsed.iter_sections():
            parsed_section_paths.add(section.path)
            report.sections_seen += 1
            node = existing_nodes.get(section.path)

            if node is None:
                # Existed in edition Y, absent from every later edition we hold.
                _create_repealed_between(
                    source=source,
                    node_type=section_type,
                    parent=chapter_nodes[section.chapter],
                    parsed=section,
                    as_of=as_of,
                    next_as_of=next_as_of,
                    review_status=review_status,
                    report=report,
                    dry_run=dry_run,
                )
                continue

            ev = earliest.get(node.id)
            if ev is None:
                # Node with no versions (shouldn't happen for sections). Treat
                # like a fresh historical insert closing at next_as_of.
                _insert_historical(
                    node, section, as_of, next_as_of, review_status, report, dry_run
                )
                continue

            if ev.effective_from <= as_of:
                # Already extends back to (or past) this edition — nothing to do.
                report.already_present += 1
                continue

            if _body_fingerprint(ev.body_text) == section.content_hash:
                report.unchanged_backdated += 1
                if not dry_run:
                    ev.effective_from = as_of
                    ev.save(update_fields=["effective_from"])
            else:
                _insert_historical(
                    node, section, as_of, ev.effective_from, review_status, report, dry_run
                )

        # Sections present now but absent from edition Y were added after Y.
        for path, node in existing_nodes.items():
            if node.node_type.key != "section":
                continue
            chapter_prefix = path.split(".", 1)[0]
            if chapter_prefix in parsed_chapter_paths and path not in parsed_section_paths:
                report.added_after_skipped += 1

        if dry_run:
            transaction.set_rollback(True)

    return report


def _earliest_versions(source: Source) -> dict[int, NodeVersion]:
    """Map node_id -> its earliest (oldest effective_from) version."""
    out: dict[int, NodeVersion] = {}
    qs = (
        NodeVersion.objects.filter(node__source=source)
        .order_by("node_id", "effective_from", "id")
    )
    for nv in qs:
        # ordered ascending, so the first seen per node is the earliest
        if nv.node_id not in out:
            out[nv.node_id] = nv
    return out


def _ensure_chapter_nodes(
    source: Source,
    chapter_type: NodeType,
    chapters: tuple[ParsedChapter, ...],
    existing_nodes: dict[str, Node],
    report: BackfillReport,
    dry_run: bool,
) -> dict[str, Node]:
    """Return chapter Node per chapter path, creating only the missing ones.

    Unlike the forward writer, we never overwrite an existing chapter's heading
    or metadata: the current edition's values must win.
    """
    out: dict[str, Node] = {}
    for ch in chapters:
        node = existing_nodes.get(ch.path)
        if node is None:
            report.chapters_created += 1
            if dry_run:
                # Build an unsaved stand-in so section inserts can reference it;
                # in dry-run nothing is persisted anyway.
                node = Node(
                    source=source,
                    node_type=chapter_type,
                    parent=None,
                    ordinal=ch.number,
                    path=ch.path,
                    heading=ch.title,
                )
            else:
                node = Node.objects.create(
                    source=source,
                    node_type=chapter_type,
                    parent=None,
                    ordinal=ch.number,
                    path=ch.path,
                    heading=ch.title,
                    source_metadata={
                        "chapter_html_url": ch.chapter_html_url,
                        "chapter_pdf_url": ch.chapter_pdf_url,
                    },
                )
                existing_nodes[ch.path] = node
        out[ch.path] = node
    return out


def _create_repealed_between(
    *,
    source: Source,
    node_type: NodeType,
    parent: Node,
    parsed: ParsedSection,
    as_of: dt.date,
    next_as_of: dt.date,
    review_status: str,
    report: BackfillReport,
    dry_run: bool,
) -> None:
    report.repealed_between_created += 1
    if dry_run:
        return
    node = Node.objects.create(
        source=source,
        node_type=node_type,
        parent=parent,
        ordinal=parsed.number.split(".", 1)[1],
        path=parsed.path,
        heading=parsed.heading,
        source_metadata=_section_metadata(parsed),
        is_repealed=True,
    )
    _write_version(node, parsed, as_of, next_as_of, review_status)


def _insert_historical(
    node: Node,
    parsed: ParsedSection,
    as_of: dt.date,
    effective_to: dt.date,
    review_status: str,
    report: BackfillReport,
    dry_run: bool,
) -> None:
    report.changed_inserted += 1
    if dry_run:
        return
    _write_version(node, parsed, as_of, effective_to, review_status)


def _write_version(
    node: Node,
    parsed: ParsedSection,
    effective_from: dt.date,
    effective_to: dt.date | None,
    review_status: str,
) -> NodeVersion:
    return NodeVersion.objects.create(
        node=node,
        body_text=parsed.body_text,
        effective_from=effective_from,
        effective_to=effective_to,
        enacted_by=parsed.history_brackets[0] if parsed.history_brackets else "",
        content_hash=parsed.content_hash,
        embedding_source_hash="",
        embedding=None,
        review_status=review_status,
    )
