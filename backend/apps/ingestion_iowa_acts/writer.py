"""Write one scraped session of Iowa Acts into the corpus tables.

Acts are frozen documents — an enrolled bill's text never changes after
publication — so unlike the Code/IAC writers there is no amendment/repeal
flow: the writer is a single idempotent pass. Re-ingesting a session no-ops
on content hash; a hash MISMATCH on an already-approved section is reported,
never silently overwritten (it means the parser changed, and a reviewer
should look).

Node shape (see IOWA_ACTS_INGESTION_PLAN.md): session → chapter → section.
Only sections carry NodeVersions. Section metadata carries both edge
channels: ``edges`` (parser lead-ins, localized to this section) and
``affects`` (the legislature's sections-amended table rows for this bill
section — authoritative actions + effective dates).
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

IOWA_JURISDICTION_SLUG = "iowa"
IOWA_ACTS_SOURCE_SLUG = "iowa-acts"


def get_iowa_acts_source() -> Source:
    return Source.objects.select_related("jurisdiction").get(
        jurisdiction__slug=IOWA_JURISDICTION_SLUG,
        slug=IOWA_ACTS_SOURCE_SLUG,
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
    """Identical contract to the other ingestion apps: content-hash keyed
    blob on disk + a deduped RawIngestion row."""
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


def session_path(year: int, session: int, label: str) -> str:
    """"2024" for regular sessions; extra sessions get an X suffix keyed by
    the legislature's own session number ("2023X3")."""
    if "extra" in label.lower():
        return f"{year}X{session}"
    return str(year)


def _default_effective(year: int) -> dt.date:
    """Iowa Const. art. III §26 default: July 1 following enactment."""
    return dt.date(year, 7, 1)


@transaction.atomic
def apply_session(payload: dict, raw: RawIngestion) -> IngestionRun:
    """Write one ``scrape_session`` payload. Returns the pending run."""
    source = get_iowa_acts_source()
    session_type = NodeType.objects.get(source=source, key="session")
    chapter_type = NodeType.objects.get(source=source, key="chapter")
    section_type = NodeType.objects.get(source=source, key="section")

    year = payload["year"]
    label = payload.get("label", "Regular GA")
    spath = session_path(year, payload["session"], label)

    # The amended table, grouped by (bill, act-section-number) for the
    # per-section ``affects`` attach, and by bill for chapter-level rows.
    by_bill_section: dict[tuple[str, int], list[dict]] = {}
    by_bill: dict[str, list[dict]] = {}
    for row in payload.get("amended", []):
        bill = row["bill"]
        by_bill.setdefault(bill, []).append(row)
        for sec in row.get("bill_sections") or []:
            by_bill_section.setdefault((bill, sec), []).append(row)

    session_node, _ = Node.objects.get_or_create(
        source=source,
        path=spath,
        defaults={
            "node_type": session_type,
            "ordinal": spath,
            "heading": f"{year} — {payload['ga']}th G.A., {label or 'Regular Session'}",
            "source_metadata": {
                "ga": payload["ga"],
                "session": payload["session"],
                "ssid": payload["ssid"],
            },
        },
    )

    added = unchanged = mismatched = 0
    issues: list[str] = []

    for ch in payload["chapters"]:
        ch_path = f"{spath}.{ch['chapter']}"
        gov_rows = by_bill.get(ch["bill"], [])
        ch_meta = {
            "bill": ch["bill"],
            "ga": ch["ga"],
            "session": ch["session"],
            "enrolled_rtf": ch.get("enrolled_rtf", False),
            "gov_action": gov_rows[0]["gov_action"] if gov_rows else "",
            "gov_date": gov_rows[0]["gov_date"] if gov_rows else None,
        }
        chapter_node, created = Node.objects.get_or_create(
            source=source,
            path=ch_path,
            defaults={
                "node_type": chapter_type,
                "parent": session_node,
                "ordinal": str(ch["chapter"]),
                "heading": ch.get("title") or ch.get("act_title", ""),
                "source_metadata": ch_meta,
            },
        )
        if not created and chapter_node.source_metadata != ch_meta:
            chapter_node.source_metadata = ch_meta
            chapter_node.save(update_fields=["source_metadata"])

        for sec in ch.get("sections", []):
            sec_path = f"{ch_path}.{sec['number']}"
            affects = by_bill_section.get((ch["bill"], sec["number"]), [])
            body = sec["body_text"]
            content_hash = hashlib.sha256(body.encode()).hexdigest()
            # eff_date is usually ISO but the table also says "Multiple",
            # "Varies", etc. — those rows keep their verbatim value in
            # ``affects``; only parseable dates drive effective_from.
            eff_dates = []
            for r in affects:
                try:
                    eff_dates.append(dt.date.fromisoformat(r.get("eff_date") or ""))
                except ValueError:
                    pass
            effective = min(eff_dates) if eff_dates else _default_effective(year)

            node, _ = Node.objects.get_or_create(
                source=source,
                path=sec_path,
                defaults={
                    "node_type": section_type,
                    "parent": chapter_node,
                    "ordinal": str(sec["number"]),
                    "heading": sec["heading"],
                    "source_metadata": {
                        "kind": sec["kind"],
                        "edges": sec["edges"],
                        "affects": affects,
                    },
                },
            )

            current = node.versions.order_by("-effective_from").first()
            if current is None:
                NodeVersion.objects.create(
                    node=node,
                    body_text=body,
                    effective_from=effective,
                    content_hash=content_hash,
                    review_status=ReviewStatus.PENDING,
                    enacted_by=f"{ch['bill']} (GA {ch['ga']})",
                )
                added += 1
            elif current.content_hash == content_hash:
                unchanged += 1
            else:
                mismatched += 1
                issues.append(
                    f"{sec_path}: text hash differs from existing version "
                    f"(review_status={current.review_status}) — not overwritten"
                )

    return IngestionRun.objects.create(
        raw=raw,
        finished_at=timezone.now(),
        status="pending",
        nodes_added=added,
        nodes_amended=0,
        nodes_repealed=0,
        nodes_unchanged=unchanged,
        validation_errors=issues,
        log=json.dumps(
            {
                "session": spath,
                "chapters": len(payload["chapters"]),
                "sections_added": added,
                "sections_unchanged": unchanged,
                "hash_mismatches": mismatched,
                "amended_rows": len(payload.get("amended", [])),
            }
        ),
    )
