"""PR3/PR5: annotate caselaw decisions with a treatment flag.

Writes ``Node.source_metadata["treatment"]`` (a ``TreatmentResult.as_metadata()``
dict) on every Iowa **decision** that a citing opinion treats negatively —
overruled / abrogated / superseded / disapproved. ``retrieve_context`` reads that
cache (one indexed lookup) so a passage can carry its good-law status.

Efficient **inverted** scan (v1): most opinions never treat anything negatively,
so we do NOT walk all 76K targets. We pull only the citing opinions whose body
contains a negative stem (a single regex prefilter), and for each, run the v1
phrase classifier against the targets it cites (its outgoing CASELAW_GRAPH edges).

    python manage.py annotate_treatment             # v1 phrase scan, full rebuild
    python manage.py annotate_treatment --dry-run    # report, write nothing
    python manage.py annotate_treatment --limit 500  # cap citing opinions (smoke)

**PR5 — ``--llm`` (v2 refinement).** v1 is high-recall and over-flags (a negative
stem near a DIFFERENT case's cite; intent it can't read). With ``--llm`` each v1
candidate gets a second-pass LLM read of the citing **paragraph** + the target's
identity + the citing court level; the model confirms / relabels / rejects. To
keep cost bounded the pass is gated by citation **depth** (``--llm-min-depth``)
and capped (``--llm-limit``), and it acts only when the model is **confident**
(``--llm-min-confidence``): a confident negative refines the flag (``source=llm``),
a confident rejection drops a v1 false positive, an uncertain read leaves the v1
advisory flag untouched.

    python manage.py annotate_treatment --llm --llm-min-depth 2 --llm-limit 1000

Idempotent: clears the existing ``treatment`` key on every decision first (a node
that is no longer treated negatively must lose its stale flag), then writes the
freshly computed flags. Only severity >= ``--min-severity`` (default 3) is
persisted — absence of the key means "no negative treatment found".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

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
    _STATUS_BY_SEVERITY,
    TreatmentResult,
    _cite_anchors,
    classify_in_sentences,
    normalized_sentences,
)

# Shared with the classifier (and guaranteed by test_treatment to be a superset
# of its stems) so a re-run can never miss a negative-bearing opinion and thereby
# drop a real flag during the clear-stale phase.
_STEM_PREFILTER = PREFILTER_SQL_REGEX
_CHUNK = 500  # citing opinions per progress tick


@dataclass
class _Cand:
    """One target's best treatment candidate, carrying enough to (a) write the
    flag and (b) run the optional v2 LLM refinement (citing opinion + depth)."""

    severity: int
    label: str
    excerpt: str
    by_name: str
    citing_node_id: int | None = None
    depth: int = 1
    source: str = "graph_phrase"
    confidence: float = 0.0

    def result(self) -> TreatmentResult:
        conf = self.confidence or (0.65 if self.severity >= 5 else 0.55)
        return TreatmentResult(
            status=_STATUS_BY_SEVERITY.get(self.severity, "caution"),
            severity=self.severity,
            label=self.label,
            by_citation=self.by_name,
            excerpt=self.excerpt,
            source=self.source,
            confidence=conf,
        )


def _court_level(md: dict | None) -> int | None:
    """Best-effort Iowa court authority level from a decision's metadata."""
    md = md or {}
    cid = (md.get("court_id") or "").lower()
    name = (md.get("court_name") or "").lower()
    if "ctapp" in cid or "appeal" in name:
        return 2
    if cid == "iowa" or "supreme" in name:
        return 1
    return None


class Command(BaseCommand):
    help = "Compute treatment flags onto caselaw decisions (v1 phrase scan; --llm v2)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=None,
                            help="Cap the number of citing opinions scanned (smoke).")
        parser.add_argument("--min-severity", type=int, default=3,
                            help="Persist flags at or above this severity (default 3).")
        parser.add_argument("--llm", action="store_true",
                            help="PR5: refine v1 candidates with an LLM second pass.")
        parser.add_argument("--llm-model", default=None,
                            help="Model for the v2 pass (default: service default).")
        parser.add_argument("--llm-limit", type=int, default=None,
                            help="Cap candidates sent to the LLM (deepest first).")
        parser.add_argument("--llm-min-depth", type=int, default=1,
                            help="Only classify candidates whose citation depth >= this.")
        parser.add_argument("--llm-min-confidence", type=float, default=None,
                            help="Confidence at/above which the LLM may override v1.")

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

        best: dict[int, _Cand] = {}
        scanned = 0
        for citing_node, body in citing_qs:
            scanned += 1
            if opts["limit"] and scanned > opts["limit"]:
                break
            if scanned % _CHUNK == 0:
                self.stdout.write(f"  …{scanned:,} citing opinions scanned, "
                                  f"{len(best):,} targets flagged")
            citing_name = ""
            # outgoing graph edges → the targets this opinion cites (+ depth)
            cited: list[tuple[int, int]] = []  # (target decision id, depth)
            for to_node, weight in (
                CrossReference.objects.filter(
                    source=CrossReferenceSource.CASELAW_GRAPH,
                    from_version__node_id=citing_node,
                ).values_list("to_node_id", "weight")
            ):
                dec = opinion_to_decision.get(to_node)
                if dec is not None:
                    cited.append((dec, max(1, weight or 1)))
            if not cited:
                continue
            citing_dec = opinion_to_decision.get(citing_node)
            citing_name = self._name_of(citing_dec)
            # Normalize the citing body ONCE (the expensive step), then scan it
            # against every target it cites — re-normalizing per target/anchor is a
            # large, needless cost on opinions that cite hundreds of cases.
            sentences = normalized_sentences(body)
            for dec, depth in cited:
                anchors = decision_anchors.get(dec)
                if not anchors:
                    continue
                found = classify_in_sentences(sentences, anchors)
                if found is None:
                    continue
                severity, label = found[0], found[1]
                # NB: no citing-court authority gate. The citing court is often
                # only *reporting* a higher court's overruling ("[target],
                # overruled by [Supreme case]"), so its level says nothing about
                # validity; the agent/patient + negation guards carry precision.
                if severity < min_sev:
                    continue
                # Aggregate by MAX severity across all citing opinions. v1's
                # known limit (one mis-attributed sentence can flag a good case)
                # is exactly what --llm refines away.
                cur = best.get(dec)
                if cur is None or severity > cur.severity:
                    best[dec] = _Cand(
                        severity=severity, label=label, excerpt=found[2],
                        by_name=citing_name, citing_node_id=citing_node, depth=depth,
                    )

        self.stdout.write(
            f"Scanned {scanned:,} negative-bearing opinions → "
            f"{len(best):,} decisions flagged (sev>={min_sev})."
        )
        self._severity_dist(best)

        if opts["llm"]:
            self._refine_with_llm(best, opinion_to_decision, opts)
            self._severity_dist(best, prefix="  after v2:")

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: nothing written."))
            self._sample(best)
            return

        self._write(src_id, best)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote treatment on {len(best):,} decisions."))
        self._sample(best)

    # ------------------------------------------------------------------
    # PR5 v2 refinement
    # ------------------------------------------------------------------
    def _get_classifier(self, model):
        from apps.corpus.services.treatment_llm import (
            OpenAITreatmentClassifier,
            default_treatment_classifier,
        )
        if model:
            return OpenAITreatmentClassifier(model=model)
        return default_treatment_classifier()

    def _refine_with_llm(self, best, opinion_to_decision, opts):
        from apps.corpus.services.treatment_llm import (
            DEFAULT_MIN_CONFIDENCE,
            paragraph_around,
        )

        classifier = self._get_classifier(opts["llm_model"])
        if classifier is None:
            self.stdout.write(self.style.WARNING(
                "  --llm: no OpenAI key / classifier; skipping v2 (v1 flags kept)."))
            return
        min_conf = opts["llm_min_confidence"]
        if min_conf is None:
            min_conf = DEFAULT_MIN_CONFIDENCE
        min_depth = opts["llm_min_depth"]

        cands = sorted(
            ((dec, c) for dec, c in best.items() if c.depth >= min_depth),
            key=lambda x: x[1].depth, reverse=True,
        )
        if opts["llm_limit"]:
            cands = cands[: opts["llm_limit"]]
        self.stdout.write(
            f"  --llm: classifying {len(cands):,} candidates "
            f"(depth>={min_depth}, conf>={min_conf})…"
        )

        # Batch the per-candidate fetches.
        dec_ids = [dec for dec, _ in cands]
        citing_ids = [c.citing_node_id for _, c in cands if c.citing_node_id]
        target_md = {
            pk: (md, heading)
            for pk, md, heading in Node.objects.filter(pk__in=dec_ids).values_list(
                "pk", "source_metadata", "heading"
            )
        }
        bodies = dict(
            NodeVersion.objects.filter(
                node_id__in=citing_ids, effective_to__isnull=True
            ).values_list("node_id", "body_text")
        )
        citing_dec_ids = {
            opinion_to_decision.get(cid) for cid in citing_ids
        }
        citing_md = dict(
            Node.objects.filter(pk__in=[c for c in citing_dec_ids if c])
            .values_list("pk", "source_metadata")
        )

        confirmed = relabeled = dropped = kept = failed = 0
        for i, (dec, c) in enumerate(cands, 1):
            if i % 100 == 0:
                self.stdout.write(f"    …{i:,}/{len(cands):,} classified")
            tmd, theading = target_md.get(dec, ({}, ""))
            tmd = tmd or {}
            tname = tmd.get("case_name") or theading or ""
            tcites = [x for x in (tmd.get("citations") or [])
                      if "LEXIS" not in x and " WL " not in x]
            level = _court_level(citing_md.get(opinion_to_decision.get(c.citing_node_id)))
            para = paragraph_around(bodies.get(c.citing_node_id, ""), c.excerpt)
            v = classifier.classify(
                target_name=tname,
                target_citation=tcites[0] if tcites else "",
                citing_name=c.by_name,
                citing_court_level=level,
                paragraph=para,
            )
            if v.error:
                failed += 1  # API failure — v1 flag kept, but NOT a verdict
                continue
            if v.confidence < min_conf:
                kept += 1  # uncertain — leave the v1 advisory flag as-is
                continue
            if v.is_negative:
                best[dec] = replace(
                    c, severity=v.severity, label=v.label,
                    excerpt=v.evidence or c.excerpt, source="llm",
                    confidence=v.confidence,
                )
                confirmed += 1
                if v.label != c.label or v.severity != c.severity:
                    relabeled += 1
            else:
                del best[dec]  # confident rejection of a v1 false positive
                dropped += 1

        self.stdout.write(
            f"  --llm: {confirmed:,} confirmed ({relabeled:,} relabeled), "
            f"{dropped:,} dropped as false positives, {kept:,} left as v1 (uncertain), "
            f"{failed:,} API failures (v1 kept, unclassified)."
        )
        if failed:
            self.stdout.write(self.style.WARNING(
                f"  --llm: {failed:,} candidates were NOT classified — re-run to cover them."))

    # ------------------------------------------------------------------
    def _severity_dist(self, best: dict[int, _Cand], prefix: str = "  severity:"):
        dist = Counter(c.severity for c in best.values())
        self.stdout.write(
            prefix + " " + "  ".join(f"{s}:{dist[s]}" for s in sorted(dist, reverse=True))
        )

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

    def _write(self, src_id, best: dict[int, _Cand]):
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
            for dec_id, cand in best.items():
                node = Node.objects.only("id", "source_metadata").get(pk=dec_id)
                node.source_metadata["treatment"] = cand.result().as_metadata()
                node.save(update_fields=["source_metadata"])

    def _sample(self, best: dict[int, _Cand], k: int = 12):
        self.stdout.write("  sample flags:")
        for dec_id, c in list(best.items())[:k]:
            nm = self._name_of(dec_id)[:36]
            self.stdout.write(
                f"    [{c.severity} {c.label:22s} {c.source:11s}] {nm:36s} ← {c.by_name[:24]}"
            )
            self.stdout.write(f"         “{c.excerpt[:120]}”")
