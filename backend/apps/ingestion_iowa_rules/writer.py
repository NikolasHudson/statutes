"""Apply a validated changeset to the corpus tables in a single transaction.

The writer is the only place in this app that mutates Node / NodeVersion. All
other modules are pure. If you find yourself writing to the corpus from the
parser, the differ, or a management command, push it through here instead.

The raw-input / ingestion-run audit trail is shared with the Iowa Code app —
``RawIngestion`` and ``IngestionRun`` are source-agnostic, so a reviewer sees
every ingest of every source in one admin list.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.corpus.models import Node, NodeType, NodeVersion, ReviewStatus, Source
from apps.ingestion_iowa_code.models import IngestionRun, RawIngestion

from .differ import Changeset
from .parser import ParsedChapter, ParsedRule, ParseResult

IOWA_JURISDICTION_SLUG = "iowa"
IOWA_COURT_RULES_SOURCE_SLUG = "iowa-court-rules"


def get_iowa_court_rules_source() -> Source:
    return Source.objects.select_related("jurisdiction").get(
        jurisdiction__slug=IOWA_JURISDICTION_SLUG,
        slug=IOWA_COURT_RULES_SOURCE_SLUG,
    )


def persist_raw_input(
    *,
    payload_bytes: bytes,
    source_kind: str,
    code_year: int,
    fetched_from: str = "",
    storage_dir: Path,
    notes: str = "",
) -> RawIngestion:
    """Write the raw bytes to ``storage_dir`` keyed by hash, dedupe via DB.

    Every NodeVersion can be traced back to a file on disk we never overwrite.
    ``code_year`` carries the edition year for Court Rules."""

    content_hash = hashlib.sha256(payload_bytes).hexdigest()

    existing = RawIngestion.objects.filter(content_hash=content_hash).first()
    if existing is not None:
        return existing

    storage_dir.mkdir(parents=True, exist_ok=True)
    target = storage_dir / f"{content_hash}.bin"
    if not target.exists():
        target.write_bytes(payload_bytes)

    return RawIngestion.objects.create(
        source_kind=source_kind,
        code_year=code_year,
        fetched_from=fetched_from,
        content_hash=content_hash,
        byte_size=len(payload_bytes),
        storage_path=str(target),
        notes=notes,
    )


@transaction.atomic
def apply_changeset(
    *,
    parsed: ParseResult,
    changeset: Changeset,
    raw: RawIngestion,
    effective_from: dt.date | None = None,
) -> IngestionRun:
    """Apply ``changeset`` and create an IngestionRun row.

    All NodeVersions are written with review_status='pending' — nothing
    becomes visible until a reviewer approves it via the admin. Defaults
    ``effective_from`` to the probe edition date."""

    effective_from = effective_from or parsed.edition_date
    source = get_iowa_court_rules_source()

    chapter_type = NodeType.objects.get(source=source, key="chapter")
    rule_type = NodeType.objects.get(source=source, key="rule")

    chapter_node_by_path = _ensure_chapter_nodes(
        source, chapter_type, parsed.chapters
    )

    nodes_added = 0
    nodes_amended = 0
    nodes_repealed = 0

    for change in changeset.rules_added:
        node = _ensure_rule_node(
            source=source,
            node_type=rule_type,
            parent=chapter_node_by_path[change.parsed.chapter],
            parsed=change.parsed,
        )
        _create_pending_version(node, change.parsed, effective_from)
        nodes_added += 1

    for change in changeset.rules_amended:
        node = _ensure_rule_node(
            source=source,
            node_type=rule_type,
            parent=chapter_node_by_path[change.parsed.chapter],
            parsed=change.parsed,
        )
        NodeVersion.objects.filter(
            node=node, effective_to__isnull=True
        ).update(effective_to=effective_from)
        _create_pending_version(node, change.parsed, effective_from)
        nodes_amended += 1

    for path in changeset.rules_repealed:
        try:
            node = Node.objects.get(source=source, path=path)
        except Node.DoesNotExist:
            continue
        NodeVersion.objects.filter(
            node=node, effective_to__isnull=True
        ).update(effective_to=effective_from)
        node.is_repealed = True
        node.save(update_fields=["is_repealed"])
        nodes_repealed += 1

    return IngestionRun.objects.create(
        raw=raw,
        finished_at=timezone.now(),
        status="pending",
        nodes_added=nodes_added,
        nodes_amended=nodes_amended,
        nodes_repealed=nodes_repealed,
        nodes_unchanged=len(changeset.rules_unchanged),
        validation_errors=[],
        log=json.dumps(changeset.summary()),
    )


def _ensure_chapter_nodes(
    source: Source,
    chapter_type: NodeType,
    chapters: tuple[ParsedChapter, ...],
) -> dict[str, Node]:
    """Create/update a Node per chapter — including reserved and zero-rule
    chapters, so the structure is complete and lookups never 404. Chapters do
    not carry NodeVersions in this flow; their heading/metadata is mutable."""
    out: dict[str, Node] = {}
    for ch in chapters:
        meta = _chapter_metadata(ch)
        node, _ = Node.objects.get_or_create(
            source=source,
            path=ch.path,
            defaults={
                "node_type": chapter_type,
                "parent": None,
                "ordinal": ch.number,
                "heading": ch.title,
                "source_metadata": meta,
                "is_repealed": ch.reserved,
            },
        )
        dirty = False
        if node.heading != ch.title:
            node.heading = ch.title
            dirty = True
        if node.source_metadata != meta:
            node.source_metadata = meta
            dirty = True
        if node.is_repealed != ch.reserved:
            node.is_repealed = ch.reserved
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "is_repealed"])
        out[ch.path] = node
    return out


def _chapter_metadata(ch: ParsedChapter) -> dict:
    return {
        "chapter_pdf_url": ch.chapter_pdf_url,
        "reserved": ch.reserved,
        "page_count": ch.page_count,
        "parse_notes": list(ch.parse_notes),
    }


def _ensure_rule_node(
    *, source: Source, node_type: NodeType, parent: Node, parsed: ParsedRule
) -> Node:
    meta = _rule_metadata(parsed)
    node, created = Node.objects.get_or_create(
        source=source,
        path=parsed.path,
        defaults={
            "node_type": node_type,
            "parent": parent,
            "ordinal": parsed.ordinal,
            "heading": parsed.heading,
            "source_metadata": meta,
        },
    )
    if not created:
        dirty = False
        if node.heading != parsed.heading:
            node.heading = parsed.heading
            dirty = True
        if node.source_metadata != meta:
            node.source_metadata = meta
            dirty = True
        if node.is_repealed:
            # Rule reappeared in input — un-repeal it. The new version below
            # restarts the clock.
            node.is_repealed = False
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "is_repealed"])
    return node


def _rule_metadata(parsed: ParsedRule) -> dict:
    return {
        "division": parsed.division,
        "history_brackets": list(parsed.history_brackets),
        "has_comment": bool(parsed.comment_text.strip()),
    }


def _create_pending_version(
    node: Node, parsed: ParsedRule, effective_from: dt.date
) -> NodeVersion:
    return NodeVersion.objects.create(
        node=node,
        body_text=parsed.combined_text,
        effective_from=effective_from,
        effective_to=None,
        enacted_by=parsed.history_brackets[0] if parsed.history_brackets else "",
        content_hash=parsed.content_hash,
        embedding_source_hash="",
        review_status=ReviewStatus.PENDING,
    )
