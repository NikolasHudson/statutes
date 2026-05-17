"""Apply a validated changeset to the corpus tables in a single transaction.

The writer is the only place in this app that mutates Node / NodeVersion. All
other modules are pure. If you find yourself writing to the corpus from the
parser, the differ, or a management command, push it through here instead.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.corpus.models import (
    Jurisdiction,
    Node,
    NodeType,
    NodeVersion,
    ReviewStatus,
    Source,
)

from .differ import Changeset
from .models import IngestionRun, RawIngestion
from .parser import ParsedChapter, ParsedSection, ParseResult


IOWA_JURISDICTION_SLUG = "iowa"
IOWA_CODE_SOURCE_SLUG = "iowa-code"


def get_iowa_code_source() -> Source:
    return Source.objects.select_related("jurisdiction").get(
        jurisdiction__slug=IOWA_JURISDICTION_SLUG, slug=IOWA_CODE_SOURCE_SLUG
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

    The point is auditability: every NodeVersion can be traced back to a
    file on disk that we never overwrite."""

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
    becomes visible until a reviewer approves it via the admin."""

    effective_from = effective_from or timezone.now().date()
    source = get_iowa_code_source()

    chapter_type = NodeType.objects.get(source=source, key="chapter")
    section_type = NodeType.objects.get(source=source, key="section")

    chapter_node_by_path = _ensure_chapter_nodes(
        source, chapter_type, parsed.chapters
    )

    nodes_added = 0
    nodes_amended = 0
    nodes_repealed = 0

    for change in changeset.sections_added:
        node = _ensure_section_node(
            source=source,
            node_type=section_type,
            parent=chapter_node_by_path[change.parsed.chapter],
            parsed=change.parsed,
        )
        _create_pending_version(node, change.parsed, effective_from)
        nodes_added += 1

    for change in changeset.sections_amended:
        node = _ensure_section_node(
            source=source,
            node_type=section_type,
            parent=chapter_node_by_path[change.parsed.chapter],
            parsed=change.parsed,
        )
        NodeVersion.objects.filter(
            node=node, effective_to__isnull=True
        ).update(effective_to=effective_from)
        _create_pending_version(node, change.parsed, effective_from)
        nodes_amended += 1

    for path in changeset.sections_repealed:
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
        nodes_unchanged=len(changeset.sections_unchanged),
        validation_errors=[],
        log=json.dumps(changeset.summary()),
    )


def _ensure_chapter_nodes(
    source: Source,
    chapter_type: NodeType,
    chapters: tuple[ParsedChapter, ...],
) -> dict[str, Node]:
    out: dict[str, Node] = {}
    for ch in chapters:
        node, _ = Node.objects.get_or_create(
            source=source,
            path=ch.path,
            defaults={
                "node_type": chapter_type,
                "parent": None,
                "ordinal": ch.number,
                "heading": ch.title,
                "source_metadata": {
                    "chapter_html_url": ch.chapter_html_url,
                    "chapter_pdf_url": ch.chapter_pdf_url,
                },
            },
        )
        # Update heading/metadata if it changed (chapter heading is
        # not append-only — chapters do not have NodeVersions in this
        # ingest flow).
        dirty = False
        if node.heading != ch.title:
            node.heading = ch.title
            dirty = True
        new_meta = {
            "chapter_html_url": ch.chapter_html_url,
            "chapter_pdf_url": ch.chapter_pdf_url,
        }
        if node.source_metadata != new_meta:
            node.source_metadata = new_meta
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata"])
        out[ch.path] = node
    return out


def _ensure_section_node(
    *, source: Source, node_type: NodeType, parent: Node, parsed: ParsedSection
) -> Node:
    node, created = Node.objects.get_or_create(
        source=source,
        path=parsed.path,
        defaults={
            "node_type": node_type,
            "parent": parent,
            "ordinal": parsed.number.split(".", 1)[1],
            "heading": parsed.heading,
            "source_metadata": _section_metadata(parsed),
        },
    )
    if not created:
        dirty = False
        if node.heading != parsed.heading:
            node.heading = parsed.heading
            dirty = True
        new_meta = _section_metadata(parsed)
        if node.source_metadata != new_meta:
            node.source_metadata = new_meta
            dirty = True
        if node.is_repealed:
            # Section reappeared in input — un-repeal it. The new version
            # below will start the clock again.
            node.is_repealed = False
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "is_repealed"])
    return node


def _section_metadata(parsed: ParsedSection) -> dict:
    return {
        "history_brackets": list(parsed.history_brackets),
        "acts_citations": list(parsed.acts_citations),
        "referred_to_in": list(parsed.referred_to_in),
        "citation_pdf_url": parsed.citation_pdf_url,
        "citation_html_url": parsed.citation_html_url,
        "source_rtf_url": parsed.source_rtf_url,
    }


def _create_pending_version(
    node: Node, parsed: ParsedSection, effective_from: dt.date
) -> NodeVersion:
    return NodeVersion.objects.create(
        node=node,
        body_text=parsed.body_text,
        effective_from=effective_from,
        effective_to=None,
        enacted_by=parsed.history_brackets[0] if parsed.history_brackets else "",
        content_hash=parsed.content_hash,
        embedding_source_hash="",
        review_status=ReviewStatus.PENDING,
    )


def _ensure_jurisdiction() -> Jurisdiction:
    return Jurisdiction.objects.get(slug=IOWA_JURISDICTION_SLUG)
