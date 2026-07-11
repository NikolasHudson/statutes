"""Materialize act→Code edges and statute-supersession notes from Iowa Acts.

    python manage.py backfill_acts_code_edges
    python manage.py backfill_acts_code_edges --dry-run

Every ingested act section carries the legislature's own sections-amended
rows in ``source_metadata["affects"]`` (action, effective date, governor's
action) plus the parser's lead-in ``edges``. This walks every current
approved act-section version and writes:

1. **CrossReference edges** (source=``act_affects``): one per distinct
   affected Code reference — INTERNAL when the ref resolves to an
   ``iowa-code`` Node (dotted sections and bare chapters are both Node
   paths), EXTERNAL with the verbatim ref otherwise (New Code sections not
   yet in our edition, unparseable refs). Delete-and-rebuild per version,
   same idempotency contract as the other backfills.

2. **Supersession notes** (CaseResearchNote kind=``act_supersession``): for
   a **Repeal** row whose target Code node our corpus still carries as live
   (``is_repealed=False``), an adverse note is upserted on the Code node —
   the statute-side Madden trap: the section reads as good law in our
   edition but a signed session law has repealed it. Notes surface inside
   tool results next to the section text (corpus_tools._node_dict), so the
   assistant warns WITH the authority. Deterministic and sourced from the
   legislature's table, hence ``corpus_verified=True``; review still starts
   PENDING so the attorney queue sees each one once.
"""

from __future__ import annotations

import datetime as dt

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.corpus.models import (
    CaseResearchNote,
    CrossReference,
    CrossReferenceKind,
    CrossReferenceSource,
    Node,
    NodeVersion,
    ReviewStatus,
    Source,
)
from apps.corpus.services.corpus_tools import acts_citation


class Command(BaseCommand):
    help = "Write act-section → Iowa Code CrossReference edges + supersession notes."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        acts = Source.objects.filter(slug="iowa-acts").first()
        iowa_code = Source.objects.filter(slug="iowa-code").first()
        if acts is None or iowa_code is None:
            self.stderr.write(self.style.ERROR("need both iowa-acts and iowa-code sources"))
            return

        versions = (
            NodeVersion.objects.filter(
                node__source=acts,
                node__node_type__key="section",
                effective_to__isnull=True,
                review_status=ReviewStatus.APPROVED,
            )
            .select_related("node")
            .order_by("node__path")
        )

        # Resolve every distinct ref corpus-wide in one query. The amended
        # table's refs are Iowa Code Node paths already: dotted sections
        # ("2.69", "455B.171") and — for chapter_only rows — bare chapters.
        per_version: list[tuple[NodeVersion, list[dict]]] = []
        wanted: set[str] = set()
        for version in versions.iterator():
            meta = version.node.source_metadata or {}
            rows = list(meta.get("affects") or [])
            seen_refs = {r["code_ref"] for r in rows if r.get("code_ref")}
            # Parser edges localize refs the table missed for this section
            # (rare; the table is the authority on action/eff_date).
            for e in meta.get("edges") or []:
                ref = e.get("code_ref")
                if ref and ref not in seen_refs:
                    rows.append(
                        {
                            "code_ref": ref,
                            "action": e.get("action", ""),
                            "eff_date": None,
                            "chapter_only": e.get("action") == "repeal_chapter",
                        }
                    )
                    seen_refs.add(ref)
            if rows:
                per_version.append((version, rows))
                wanted.update(r["code_ref"] for r in rows if r.get("code_ref"))

        target_by_path = {
            n.path: n
            for n in Node.objects.filter(source=iowa_code, path__in=wanted)
        }

        stats = {"versions": 0, "internal": 0, "external": 0, "notes": 0}
        now = timezone.now()

        for version, rows in per_version:
            stats["versions"] += 1
            # One edge per distinct ref; keep the first row per ref (the
            # table lists subunit-level rows we collapse to the section).
            by_ref: dict[str, dict] = {}
            for r in rows:
                ref = r.get("code_ref")
                if ref and ref not in by_ref:
                    by_ref[ref] = r

            refs = [
                (ref, target_by_path.get(ref), row) for ref, row in by_ref.items()
            ]
            stats["internal"] += sum(1 for _, n, _ in refs if n)
            stats["external"] += sum(1 for _, n, _ in refs if not n)

            if not dry_run:
                with transaction.atomic():
                    CrossReference.objects.filter(
                        from_version=version,
                        source=CrossReferenceSource.ACT_AFFECTS,
                    ).delete()
                    CrossReference.objects.bulk_create(
                        [
                            CrossReference(
                                from_version=version,
                                to_node=node,
                                external_text="" if node else f"Iowa Code {ref}",
                                kind=CrossReferenceKind.INTERNAL
                                if node
                                else CrossReferenceKind.EXTERNAL,
                                source=CrossReferenceSource.ACT_AFFECTS,
                            )
                            for ref, node, _ in refs
                        ]
                    )

            # Supersession notes: signed repeals of sections we still list
            # as live. Two true-positive shapes, everything else skipped:
            #   (a) the repeal POSTDATES our section's current text — the
            #       genuinely stale window between sessions and editions;
            #   (b) our node is an empty repealed stub (the edition already
            #       dropped the text but the node still resolves as live).
            # An old repeal against a section with real current text means
            # the section was later recreated — noting it would be a false
            # alarm (e.g. § 256.9, "repealed" 2019, fully live today).
            for ref, node, row in refs:
                if node is None or node.is_repealed:
                    continue
                if row.get("action") not in ("Repeal", "repeal", "repeal_chapter"):
                    continue
                gov = (row.get("gov_action") or "").lower()
                if gov and "veto" in gov and "item" not in gov:
                    continue
                cur = (
                    node.versions.filter(effective_to__isnull=True)
                    .order_by("-effective_from")
                    .first()
                )
                body_empty = not (cur.body_text.strip() if cur else "")
                postdates = False
                try:
                    eff_d = dt.date.fromisoformat(row.get("eff_date") or "")
                    postdates = cur is not None and eff_d >= cur.effective_from
                except ValueError:
                    pass
                if not (postdates or body_empty):
                    continue
                cite = acts_citation(version.node.path)
                eff = row.get("eff_date")
                eff_txt = f", effective {eff}" if eff else ""
                evidence = (
                    f"REPEALED BY SESSION LAW: this section was repealed by "
                    f"{cite}{eff_txt}. This Code edition's text predates the "
                    f"repeal — do not rely on it as current law."
                )
                stats["notes"] += 1
                if dry_run:
                    self.stdout.write(f"note: {ref} ← {cite}{eff_txt}")
                    continue
                CaseResearchNote.objects.update_or_create(
                    node=node,
                    kind=CaseResearchNote.Kind.ACT_SUPERSESSION,
                    defaults={
                        "status": CaseResearchNote.Status.ADVERSE,
                        "adverse_kind": "superseded_by_statute",
                        "claimed_by": cite,
                        "evidence": evidence,
                        "source_url": "",
                        "corpus_verified": True,
                        "corpus_matches": [version.node.path],
                        "model": "acts_amended_table",
                        "checked_at": now,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'would write' if dry_run else 'wrote'} edges for "
                f"{stats['versions']} act sections: {stats['internal']} internal, "
                f"{stats['external']} external; {stats['notes']} supersession notes"
            )
        )
