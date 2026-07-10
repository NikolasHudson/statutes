"""Apply a validated changeset to the corpus tables in a single transaction.

The writer is the only place in this app that mutates Node / NodeVersion. All
other modules are pure. The raw-input / ingestion-run audit trail is shared
with the Iowa Code app — ``RawIngestion`` and ``IngestionRun`` are
source-agnostic — so a reviewer sees every ingest of every source in one list.

Three node levels: agency → chapter → rule. Only rules carry NodeVersions;
agency and chapter nodes are structural (heading/metadata mutable, no text
timeline), like Iowa Code chapters.
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
from .parser import ParsedAgency, ParsedChapter, ParsedRule, ParseResult

IOWA_JURISDICTION_SLUG = "iowa"
IOWA_ADMIN_CODE_SOURCE_SLUG = "iowa-admin-code"


def get_iowa_admin_code_source() -> Source:
    return Source.objects.select_related("jurisdiction").get(
        jurisdiction__slug=IOWA_JURISDICTION_SLUG,
        slug=IOWA_ADMIN_CODE_SOURCE_SLUG,
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
    """Write the raw bytes to ``storage_dir`` keyed by hash, dedupe via DB."""

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

    All NodeVersions are written review_status='pending' — nothing becomes
    visible until a reviewer approves it. A rule's own effective date (from its
    ARC bracket) wins; otherwise ``effective_from`` (defaulting to the probe
    pub_date)."""

    default_effective = effective_from or parsed.pub_date
    source = get_iowa_admin_code_source()

    agency_type = NodeType.objects.get(source=source, key="agency")
    chapter_type = NodeType.objects.get(source=source, key="chapter")
    rule_type = NodeType.objects.get(source=source, key="rule")

    agency_by_path = _ensure_agency_nodes(source, agency_type, parsed.agencies)
    chapter_by_path = _ensure_chapter_nodes(
        source, chapter_type, agency_by_path, parsed
    )

    nodes_added = nodes_amended = nodes_repealed = 0

    for change in changeset.rules_added:
        node = _ensure_rule_node(
            source=source, node_type=rule_type,
            parent=chapter_by_path[change.parsed.chapter_path], parsed=change.parsed,
        )
        _create_pending_version(node, change.parsed, default_effective)
        nodes_added += 1

    for change in changeset.rules_amended:
        node = _ensure_rule_node(
            source=source, node_type=rule_type,
            parent=chapter_by_path[change.parsed.chapter_path], parsed=change.parsed,
        )
        eff = change.parsed.effective_from or default_effective
        NodeVersion.objects.filter(node=node, effective_to__isnull=True).update(
            effective_to=eff
        )
        _create_pending_version(node, change.parsed, default_effective)
        nodes_amended += 1

    for path in changeset.rules_repealed:
        try:
            node = Node.objects.get(source=source, path=path)
        except Node.DoesNotExist:
            continue
        NodeVersion.objects.filter(node=node, effective_to__isnull=True).update(
            effective_to=default_effective
        )
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


def _ensure_agency_nodes(
    source: Source, agency_type: NodeType, agencies: tuple[ParsedAgency, ...]
) -> dict[str, Node]:
    out: dict[str, Node] = {}
    for ag in agencies:
        node, _ = Node.objects.get_or_create(
            source=source, path=ag.path,
            defaults={
                "node_type": agency_type, "parent": None,
                "ordinal": ag.agency, "heading": ag.name, "source_metadata": {},
            },
        )
        if ag.name and node.heading != ag.name:
            node.heading = ag.name
            node.save(update_fields=["heading"])
        out[ag.path] = node
    return out


def _ensure_chapter_nodes(
    source: Source,
    chapter_type: NodeType,
    agency_by_path: dict[str, Node],
    parsed: ParseResult,
) -> dict[str, Node]:
    """Create/update a Node per chapter, parented to its agency. Chapters carry
    no NodeVersion; heading/metadata are mutable."""
    out: dict[str, Node] = {}
    for ch in parsed.iter_chapters():
        meta = _chapter_metadata(ch)
        node, _ = Node.objects.get_or_create(
            source=source, path=ch.path,
            defaults={
                "node_type": chapter_type,
                "parent": agency_by_path[ch.agency],
                "ordinal": ch.number,
                "heading": ch.title,
                "source_metadata": meta,
                "is_repealed": ch.reserved,
            },
        )
        dirty = False
        if node.heading != ch.title:
            node.heading, dirty = ch.title, True
        if node.source_metadata != meta:
            node.source_metadata, dirty = meta, True
        if node.is_repealed != ch.reserved:
            node.is_repealed, dirty = ch.reserved, True
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "is_repealed"])
        out[ch.path] = node
    return out


def _chapter_metadata(ch: ParsedChapter) -> dict:
    return {
        "chapter_docx_url": ch.chapter_docx_url,
        "chapter_pdf_url": ch.chapter_pdf_url,
        "reserved": ch.reserved,
        "prior_agencies": list(ch.prior_agencies),
        "parse_notes": list(ch.parse_notes),
    }


def _ensure_rule_node(
    *, source: Source, node_type: NodeType, parent: Node, parsed: ParsedRule
) -> Node:
    meta = _rule_metadata(parsed)
    node, created = Node.objects.get_or_create(
        source=source, path=parsed.path,
        defaults={
            "node_type": node_type, "parent": parent,
            "ordinal": parsed.ordinal, "heading": parsed.heading,
            "source_metadata": meta,
        },
    )
    if not created:
        dirty = False
        if node.heading != parsed.heading:
            node.heading, dirty = parsed.heading, True
        if node.source_metadata != meta:
            node.source_metadata, dirty = meta, True
        if node.is_repealed:
            node.is_repealed, dirty = False, True  # reappeared — un-repeal
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "is_repealed"])
    return node


def _rule_metadata(parsed: ParsedRule) -> dict:
    return {
        "enabling_statutes": list(parsed.enabling_statutes),
        "history_brackets": list(parsed.history_brackets),
    }


def _create_pending_version(
    node: Node, parsed: ParsedRule, default_effective: dt.date
) -> NodeVersion:
    return NodeVersion.objects.create(
        node=node,
        body_text=parsed.body_text,
        effective_from=parsed.effective_from or default_effective,
        effective_to=None,
        enacted_by=parsed.history_brackets[0] if parsed.history_brackets else "",
        content_hash=parsed.content_hash,
        embedding_source_hash="",
        review_status=ReviewStatus.PENDING,
    )
