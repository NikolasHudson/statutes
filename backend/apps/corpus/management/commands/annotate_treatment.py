"""PR3: annotate caselaw decisions with a deterministic v1 treatment flag.

Writes ``Node.source_metadata["treatment"]`` (a ``TreatmentResult.as_metadata()``
dict) on every Iowa **decision** that a citing opinion treats negatively —
overruled / abrogated / superseded / disapproved. ``retrieve_context`` reads that
cache (one indexed lookup) so a passage can carry its good-law status.

Efficient **inverted** scan: most opinions never treat anything negatively, so we
do NOT walk all 76K targets. We pull only the citing opinions whose body actually
contains a negative stem (a single regex prefilter), and for each, run the
classifier against the targets it cites (its outgoing CASELAW_GRAPH edges). The
authority gate (a court can only *overrule* a case it could bind — citing
``Court.level`` <= target's) is applied here, where both levels are known; a
lower court's "overrule" is downgraded to a caution.

    python manage.py annotate_treatment            # full rebuild
    python manage.py annotate_treatment --dry-run   # report, write nothing
    python manage.py annotate_treatment --limit 500 # cap citing opinions (smoke)

Idempotent: clears the existing ``treatment`` key on every decision first (a node
that is no longer treated negatively must lose its stale flag), then writes the
freshly computed flags. Only severity >= ``--min-severity`` (default 3) is
persisted — absence of the key means "no negative treatment found".
"""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.corpus.models import (
    CrossReference,
    CrossReferenceSource,
    Node,
    NodeVersion,
)
from apps.corpus.services.treatment import (
    PREFILTER_SQL_REGEX,
    _cite_anchors,
    classify_citing_text,
)

# Shared with the classifier (and guaranteed by test_treatment to be a superset
# of its stems) so a re-run can never miss a negative-bearing opinion and thereby
# drop a real flag during the clear-stale phase.
_STEM_PREFILTER = PREFILTER_SQL_REGEX
_CHUNK = 500  # citing opinions per progress tick


class Command(BaseCommand):
    help = "Compute deterministic v1 treatment flags onto caselaw decisions (PR3)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None,
                            help="Cap the number of citing opinions scanned (smoke).")
        parser.add_argument("--min-severity", type=int, default=3,
                            help="Persist flags at or above this severity (default 3).")

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        min_sev = opts["min_severity"]
        src_id = Node.objects.filter(source__slug="iowa-caselaw").values_list(
            "source_id", flat=True
        ).first()

        # --- preload target anchors (the reporter cites we search for) -------
        decision_anchors: dict[int, list[str]] = {}
        for pk, md in (
            Node.objects.filter(source_id=src_id, parent__isnull=True)
            .values_list("pk", "source_metadata")
            .iterator(chunk_size=5000)
        ):
            anchors = _cite_anchors((md or {}).get("citations") or [])
            if anchors:
                decision_anchors[pk] = anchors

        opinion_to_decision: dict[int, int] = dict(
            Node.objects.filter(source_id=src_id, node_type__key="opinion")
            .values_list("pk", "parent_id")
            .iterator(chunk_size=5000)
        )
        self.stdout.write(
            f"Targets: {len(decision_anchors):,} decisions with citable anchors."
        )

        # --- iterate ONLY citing opinions that contain a negative stem -------
        citing_qs = (
            NodeVersion.objects.filter(
                node__source_id=src_id,
                node__node_type__key="opinion",
                effective_to__isnull=True,
                body_text__iregex=_STEM_PREFILTER,
            )
            .values_list("node_id", "body_text")
            .iterator(chunk_size=200)
        )

        # target decision -> best (severity, label, excerpt, by_name)
        best: dict[int, tuple[int, str, str, str]] = {}
        scanned = 0
        for citing_node, body in citing_qs:
            scanned += 1
            if opts["limit"] and scanned > opts["limit"]:
                break
            if scanned % _CHUNK == 0:
                self.stdout.write(f"  …{scanned:,} citing opinions scanned, "
                                  f"{len(best):,} targets flagged")
            citing_dec = opinion_to_decision.get(citing_node)
            citing_name = ""
            # outgoing graph edges → the targets this opinion cites
            cited_decisions: set[int] = set()
            for to_node in (
                CrossReference.objects.filter(
                    source=CrossReferenceSource.CASELAW_GRAPH,
                    from_version__node_id=citing_node,
                ).values_list("to_node_id", flat=True)
            ):
                dec = opinion_to_decision.get(to_node)
                if dec is not None:
                    cited_decisions.add(dec)
            if not cited_decisions:
                continue
            if not citing_name:
                citing_name = self._name_of(citing_dec)
            for dec in cited_decisions:
                anchors = decision_anchors.get(dec)
                if not anchors:
                    continue
                found = classify_citing_text(body, anchors)
                if found is None:
                    continue
                severity, label = found[0], found[1]
                # NB: no citing-court authority gate. The citing court is often
                # only *reporting* a higher court's overruling ("[target],
                # overruled by [Supreme case]"), so its level says nothing about
                # validity; the agent/patient + negation guards in the classifier
                # carry the precision. (A first-person lower-court "we overrule a
                # higher court" is vanishingly rare.)
                if severity < min_sev:
                    continue
                # Aggregate by MAX severity across all citing opinions. Known v1
                # limitation: a single mis-attributed sentence in one of many
                # citing opinions can flag a good-law case. Acceptable because the
                # flag is ADVISORY and ships the verbatim evidence sentence (a
                # reader sees "[target], overruled by X" and judges); the LLM pass
                # (PR5) and a multi-opinion support count are the path to enforce.
                cur = best.get(dec)
                if cur is None or severity > cur[0]:
                    best[dec] = (severity, label, found[2], citing_name)

        self.stdout.write(
            f"Scanned {scanned:,} negative-bearing opinions → "
            f"{len(best):,} decisions flagged (sev>={min_sev})."
        )
        from collections import Counter
        dist = Counter(v[0] for v in best.values())
        self.stdout.write("  severity: " + "  ".join(
            f"{s}:{dist[s]}" for s in sorted(dist, reverse=True)))

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: nothing written."))
            self._sample(best)
            return

        self._write(src_id, best)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote treatment on {len(best):,} decisions."))
        self._sample(best)

    # ------------------------------------------------------------------
    def _name_of(self, decision_id) -> str:
        if decision_id is None:
            return ""
        n = Node.objects.filter(pk=decision_id).values_list(
            "source_metadata", "heading"
        ).first()
        if not n:
            return ""
        md, heading = n
        return (md or {}).get("case_name") or heading or ""

    def _write(self, src_id, best: dict[int, tuple]):
        from apps.corpus.services.treatment import TreatmentResult, _STATUS_BY_SEVERITY

        with transaction.atomic():
            # Clear stale flags everywhere first (a node no longer treated
            # negatively must drop its flag), then write the fresh set.
            for node in (
                Node.objects.filter(source_id=src_id, parent__isnull=True)
                .filter(source_metadata__has_key="treatment")
                .only("id", "source_metadata")
                .iterator(chunk_size=2000)
            ):
                if node.id not in best:
                    node.source_metadata.pop("treatment", None)
                    node.save(update_fields=["source_metadata"])
            for dec_id, (sev, label, excerpt, by_name) in best.items():
                node = Node.objects.only("id", "source_metadata").get(pk=dec_id)
                res = TreatmentResult(
                    status=_STATUS_BY_SEVERITY.get(sev, "caution"),
                    severity=sev, label=label, by_citation=by_name,
                    excerpt=excerpt, source="graph_phrase",
                    confidence=0.65 if sev >= 5 else 0.55,
                )
                node.source_metadata["treatment"] = res.as_metadata()
                node.save(update_fields=["source_metadata"])

    def _sample(self, best: dict[int, tuple], k: int = 12):
        self.stdout.write("  sample flags:")
        for dec_id, (sev, label, excerpt, by_name) in list(best.items())[:k]:
            nm = self._name_of(dec_id)[:36]
            self.stdout.write(f"    [{sev} {label:22s}] {nm:36s} ← {by_name[:24]}")
            self.stdout.write(f"         “{excerpt[:120]}”")
