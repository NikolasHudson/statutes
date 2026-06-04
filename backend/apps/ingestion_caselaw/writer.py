"""Write parsed caselaw into the corpus tables (the only DB-mutating module).

Two streaming passes, batched and idempotent:

1. ``write_decisions_batch`` — upserts decision (cluster) container Nodes and,
   when present, a head-matter NodeVersion on the decision node. Returns a
   ``{cluster_id: (node_pk, date_filed)}`` cache so the opinion pass can re-link
   without re-querying.
2. ``write_opinions_batch`` — upserts opinion child Nodes and their body
   NodeVersions under the cached decision node.

The command records ONE summary ``IngestionRun`` (``record_write_run``) at the
end — durability of the data comes from the per-batch ``@transaction.atomic``
commits, not from the run row, so a single consolidated run keeps the metrics
coherent instead of fragmenting one row per batch.

Idempotency: ``load_open_version_hashes`` preloads ``{path: open content_hash}``
once at the start (cheap — strings only, no bodies). Per record we compare and
either skip (unchanged), close-and-recreate (amended), or create (added). The
``uniq_open_nodeversion_per_node_hash`` partial constraint (migration 0010) is
the DB backstop. Heading is always saved on the Node *before* its NodeVersion is
inserted, because the ``search_vector`` BEFORE INSERT trigger reads
``Node.heading`` (weight A). NodeVersions are auto-APPROVED (bulk public data,
no human review), unlike the Iowa Code writer's PENDING.
"""

from __future__ import annotations

import datetime as dt
import json

from django.db import transaction
from django.utils import timezone

from apps.corpus.models import Node, NodeType, NodeVersion, ReviewStatus, Source

from .models import IngestionRun
from .parser import ParsedDecision, ParsedOpinion

IOWA_JURISDICTION_SLUG = "iowa"
IOWA_CASELAW_SOURCE_SLUG = "iowa-caselaw"


def get_iowa_caselaw_source() -> Source:
    return Source.objects.select_related("jurisdiction").get(
        jurisdiction__slug=IOWA_JURISDICTION_SLUG, slug=IOWA_CASELAW_SOURCE_SLUG
    )


def get_node_types(source: Source) -> dict[str, NodeType]:
    return {nt.key: nt for nt in NodeType.objects.filter(source=source)}


def load_open_version_hashes(source: Source) -> dict[str, str]:
    """Preload {node.path: content_hash} for every currently-open version of
    this source. Strings only (no bodies), so it is cheap even for a large
    corpus. Used to classify each record added/amended/unchanged without a
    per-record query."""
    return {
        path: content_hash
        for path, content_hash in NodeVersion.objects.filter(
            node__source=source, effective_to__isnull=True
        ).values_list("node__path", "content_hash")
    }


# ---------------------------------------------------------------------------
# Node upserts (heading saved before any NodeVersion is created)
# ---------------------------------------------------------------------------

def ensure_decision_node(
    source: Source, decision_type: NodeType, parsed: ParsedDecision
) -> tuple[Node, bool]:
    node, created = Node.objects.get_or_create(
        source=source,
        path=parsed.path,
        defaults={
            "node_type": decision_type,
            "parent": None,
            "ordinal": str(parsed.cl_cluster_id),
            "heading": parsed.heading,
            "source_metadata": parsed.source_metadata,
        },
    )
    if not created:
        dirty = False
        if node.heading != parsed.heading:
            node.heading = parsed.heading
            dirty = True
        if node.source_metadata != parsed.source_metadata:
            node.source_metadata = parsed.source_metadata
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata"])
    return node, created


def ensure_opinion_node(
    source: Source, opinion_type: NodeType, parent_pk: int, parsed: ParsedOpinion
) -> tuple[Node, bool]:
    node, created = Node.objects.get_or_create(
        source=source,
        path=parsed.path,
        defaults={
            "node_type": opinion_type,
            "parent_id": parent_pk,
            "ordinal": parsed.ordinal,
            "heading": parsed.heading,
            "source_metadata": parsed.source_metadata,
        },
    )
    if not created:
        dirty = False
        if node.heading != parsed.heading:
            node.heading = parsed.heading
            dirty = True
        if node.source_metadata != parsed.source_metadata:
            node.source_metadata = parsed.source_metadata
            dirty = True
        if node.parent_id != parent_pk:
            node.parent_id = parent_pk
            dirty = True
        if dirty:
            node.save(update_fields=["heading", "source_metadata", "parent"])
    return node, created


def _upsert_version(
    node: Node,
    *,
    body_text: str,
    effective_from: dt.date,
    enacted_by: str,
    content_hash: str,
    open_hashes: dict[str, str],
) -> str:
    """Idempotent open-version upsert keyed on (node.path, content_hash).

    Returns 'unchanged' | 'amended' | 'added'. Updates ``open_hashes`` in place
    so a repeat path within the same run is recognized as unchanged.
    """
    prior = open_hashes.get(node.path)
    if prior == content_hash:
        return "unchanged"
    if prior is not None:
        # Amend = a data correction (cases are immutable). Supersede the prior
        # text as of the detection date and start the corrected version then,
        # so the timeline has no zero-duration or overlapping rows. The original
        # (added) version keeps its natural filing date as effective_from.
        status = "amended"
        close_date = timezone.now().date()
        NodeVersion.objects.filter(node=node, effective_to__isnull=True).update(
            effective_to=close_date
        )
        version_effective_from = close_date
    else:
        status = "added"
        version_effective_from = effective_from
    NodeVersion.objects.create(
        node=node,
        body_text=body_text,
        effective_from=version_effective_from,
        effective_to=None,
        enacted_by=enacted_by,
        content_hash=content_hash,
        embedding_source_hash="",
        review_status=ReviewStatus.APPROVED,
    )
    open_hashes[node.path] = content_hash
    return status


# ---------------------------------------------------------------------------
# Batch writers (each its own transaction → "stop halfway → keep half").
# Run accounting is the command's job (one consolidated run), so the writers
# return counts only.
# ---------------------------------------------------------------------------

@transaction.atomic
def write_decisions_batch(
    batch: list[ParsedDecision],
    source: Source,
    types: dict[str, NodeType],
    open_hashes: dict[str, str],
) -> tuple[dict, dict]:
    decision_type = types["decision"]
    counts = {
        "decisions_created": 0,
        "head_added": 0, "head_amended": 0, "head_unchanged": 0,
    }
    cache: dict[int, tuple[int, dt.date | None]] = {}
    for parsed in batch:
        node, created = ensure_decision_node(source, decision_type, parsed)
        counts["decisions_created"] += int(created)
        eff = parsed.date_filed
        cache[parsed.cl_cluster_id] = (node.pk, eff)
        if parsed.has_head_matter and eff is not None:
            status = _upsert_version(
                node,
                body_text=parsed.head_matter_text,
                effective_from=eff,
                enacted_by="",
                content_hash=parsed.head_matter_content_hash,
                open_hashes=open_hashes,
            )
            counts[f"head_{status}"] += 1
    return counts, cache


@transaction.atomic
def write_opinions_batch(
    batch: list[ParsedOpinion],
    source: Source,
    types: dict[str, NodeType],
    decision_cache: dict[int, tuple[int, dt.date | None]],
    open_hashes: dict[str, str],
) -> dict:
    opinion_type = types["opinion"]
    counts = {
        "opinions_created": 0,
        "op_added": 0, "op_amended": 0, "op_unchanged": 0,
        "empty_body": 0, "orphan_skipped": 0, "skipped_no_date": 0,
    }
    for parsed in batch:
        entry = decision_cache.get(parsed.cl_cluster_id)
        if entry is None:
            # Opinion whose decision was not written (filtered/different run).
            counts["orphan_skipped"] += 1
            continue
        node_pk, eff = entry
        op_node, created = ensure_opinion_node(source, opinion_type, node_pk, parsed)
        counts["opinions_created"] += int(created)
        if not parsed.body_text.strip():
            counts["empty_body"] += 1  # node is a container; no version
            continue
        if eff is None:
            counts["skipped_no_date"] += 1
            continue
        status = _upsert_version(
            op_node,
            body_text=parsed.body_text,
            effective_from=eff,
            enacted_by=f"Decided {eff.isoformat()}",
            content_hash=parsed.content_hash,
            open_hashes=open_hashes,
        )
        counts[f"op_{status}"] += 1
    return counts


def record_write_run(*, totals: dict, issues: dict[str, int],
                     last_cluster_id: int | None) -> IngestionRun:
    """Record ONE summary IngestionRun for a whole write (both passes).

    ``nodes_added`` counts *Nodes* created (decisions + opinions), matching the
    "nodes" semantics of the Iowa Code writer; the per-version add/amend/
    unchanged tallies live in ``log``. Validation issue counts are persisted to
    ``validation_errors`` for auditability.
    """
    return IngestionRun.objects.create(
        raw=None,
        phase="write",
        status="approved",  # caselaw auto-approves; no human review gate
        finished_at=timezone.now(),
        nodes_added=totals.get("decisions_created", 0) + totals.get("opinions_created", 0),
        nodes_amended=totals.get("head_amended", 0) + totals.get("op_amended", 0),
        nodes_repealed=0,
        nodes_unchanged=totals.get("head_unchanged", 0) + totals.get("op_unchanged", 0),
        last_cluster_id=last_cluster_id,
        validation_errors=[{"code": k, "count": v} for k, v in sorted(issues.items())],
        log=json.dumps(totals),
    )
