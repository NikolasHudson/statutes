"""Deterministic v1 good-law / treatment classifier (no LLM).

Given a target decision and the opinions that cite it (the **incoming**
CASELAW_GRAPH edges), decide whether any citing court treated it negatively —
overruled, abrogated, superseded, disapproved, distinguished — and emit a
``TreatmentFlag``-shaped dict to cache on the cited decision's
``source_metadata["treatment"]``. ``retrieve_context`` reads that cache.

Why this is hard, and how v1 stays precise (a false *negative*-treatment flag is
its own harm — it tells a lawyer a good case is dead). Calibrated on real Iowa
opinion language, the dominant false positives are:

* **"the court overruled the objection"** — a trial-court evidentiary ruling, not
  case treatment. By far the most common ``overrul`` string in opinions.
* **"overruled on other grounds by X"** — the cited case is still good law for the
  point it is cited for; only a *different* holding was disturbed.
* **negation / hypothetical** — "did not purport to overrule", "decline to
  overrule", "ought to be overruled" (a dissent's wish, not a holding).
* **party requests** — "asked the court to overrule", "request that ... be
  overruled".

The structural defense is **target-anchoring**: we only look for a negative stem
inside a tight window around the place where the citing opinion actually cites
*this target* (by its reporter citation). "overruled the objection" never sits
next to the target's reporter cite, so it is excluded for free. On top of that we
apply explicit negation / "on other grounds" / "by statute" guards.

Phrase-only flags are advisory by design (real citators miss ~1/3 and over-flag
some); ``confidence`` reflects that, and PR4 decides enforcement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Court-authority levels (Court.level): lower number = higher authority. Only a
# court whose level is <= the target's can *overrule* it; a lower court can still
# criticize/distinguish (informative, but not an invalidation).
SUPREME, APPELLATE = 1, 2


# Negative-treatment stems, most-severe first. severity: 0 good .. 5 invalidated.
# Each entry: (compiled stem, severity, label).
#
# Scoped to the high-precision *invalidation* signals — the dangerous failure
# mode is "overruled law cited as good law", which is severity 4-5. We
# deliberately DROP "distinguished"/"limited"/"criticized": empirically (over the
# 250 most-cited Iowa cases) those are dominated by ordinary legal analysis
# ("we distinguish on the facts", "statute of limitations", "limited purpose")
# and flag good law as bad. A separate, lower-confidence "discussed/distinguished"
# tier can come back with the LLM pass (PR5), which can read intent.
_NEG_STEMS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"\boverrul(?:e|ed|es|ing)\b", re.I), 5, "overruled"),
    (re.compile(r"\babrogat(?:e|ed|es|ing|ion)\b", re.I), 5, "abrogated"),
    # "supersede(d)" but NOT "supersedeas" (the bond term) — \b after the stem.
    (re.compile(r"\bsupersed(?:e|ed|es|ing)\b", re.I), 5, "superseded"),
    (re.compile(r"\brepudiat(?:e|ed|es|ing)\b", re.I), 5, "repudiated"),
    (re.compile(r"\bdisapprov(?:e|ed|es|ing|al)\b", re.I), 4, "disapproved"),
    (re.compile(r"\bno longer (?:good law|controlling|the law|valid)\b", re.I), 4, "no-longer-good-law"),
    (re.compile(r"\bdeclin\w*\s+to\s+(?:follow|extend)\b", re.I), 4, "declined-to-follow"),
]

# Postgres (``~*``) prefilter for the annotate_treatment inverted scan: an
# opinion whose body matches this MIGHT treat something negatively, so it is worth
# running the precise classifier on. It MUST be a strict SUPERSET of everything
# ``_NEG_STEMS`` can match (broad ``\w*`` roots, ``\y`` = Postgres word boundary):
# the re-run clears every stale flag before rewriting, so an opinion the
# classifier WOULD flag but the prefilter MISSED would silently drop a real
# "overruled" flag — the exact dangerous failure mode. Over-matching is harmless
# (the classifier then rejects e.g. "supersedeas"). ``test_treatment`` asserts the
# superset property against every stem.
PREFILTER_SQL_REGEX = (
    r"\y(overrul\w*|abrogat\w*|supersed\w*|repudiat\w*|disapprov\w*|"
    r"no longer (good law|controlling|the law|valid)|"
    r"declin\w* to (follow|extend))\y"
)


# A negation/hypothetical/party-request immediately governing the stem flips it
# from "treated negatively" to "explicitly NOT". Scanned in the text just BEFORE
# the stem (within ~60 chars).
_NEGATION_BEFORE = re.compile(
    r"\b(?:"
    r"declin\w+|refus\w+|decid\w+\s+not|do(?:es)?\s+not|did\s+not|"
    r"need\s+not|will\s+not|would\s+not|cannot|can\s?not|should\s+not|"
    r"not\s+(?:be|purport\w*|mean|intend\w*|at\s+liberty|free|empowered|authoriz\w*|permitted)|"
    r"(?:no|without)\s+(?:authority|power|occasion|reason)\s+to|"
    r"ought\s+to\s+be|may\s+be|might\s+be|probably\s+(?:ought|should)|"
    r"ask\w*|request\w*|urg\w*|invit\w*|whether\s+to|reluctan\w*"
    r")\b",
    re.I,
)
# "overruled on (the) other grounds" / "in part" — the cited case survives for
# its cited holding; downgrade to a caution about a *different* point.
_OTHER_GROUNDS = re.compile(r"on\s+(?:the\s+)?other\s+grounds|in\s+part", re.I)
# "overruled [...] by [target]" — the target is the OVERRULER, not the overruled.
# When a negative stem precedes the target cite with a "by" linking them, the
# target is the agent and must NOT be flagged.
_AGENT_BY = re.compile(r"\bby\b", re.I)
# superseded/overruled BY STATUTE is a distinct (still-negative) label.
_BY_STATUTE = re.compile(r"by\s+statute|legislativ\w*|amend\w*\s+the\s+statute", re.I)
# "overruled the objection / overruling a motion / overruled his motion to
# suppress": a trial-court ruling, never case treatment. The determiner is
# OPTIONAL ("overruling objection" appears bare), and the match is run on the
# lstripped text right after the stem.
_RULING_NOUN = re.compile(
    r"(?:(?:the|its|our|your|my|his|her|their|that|this|an?|"
    r"appell\w+|defendant\w*|plaintiff\w*|state\w*|counsel\w*)(?:['’]s)?\s+)?"
    r"(?:objection|motion|demurrer|exception|request|defense)s?\b",
    re.I,
)

# Stem must fall within this many chars of the target-cite occurrence (inside the
# same sentence). Real negative treatment sits adjacent to the cite ("[cite],
# overruled by X"; "expressly overruling [cite]"); a stem farther off in a
# multi-clause sentence is usually about a *different* case mentioned alongside.
_PROX = 70

_STATUS_BY_SEVERITY = {5: "negative", 4: "caution", 3: "caution", 0: "good"}

# Sentence boundaries used to isolate the cite's own sentence. We scan ONLY that
# sentence for a negative stem, so the stem and the target cite must co-occur in
# one sentence ("expressly overruling PPH 2018"; "PPH 2018 … is overruled"). A
# looser char window mis-attributes a stem from an adjacent sentence (often about
# a different case, or "the court overruled the objection") to the target.
_SENT_SPLIT = re.compile(r"(?<=[.?;])\s+|\n+")


@dataclass
class TreatmentResult:
    """What the classifier found for one target, ready to cache as a dict."""

    status: str          # good | caution | negative | unknown
    severity: int        # 0 good .. 5 invalidated
    label: str           # overruled | distinguished | superseded-by-statute | ...
    by_citation: str     # the citing case that did it (case name / cite)
    excerpt: str         # verbatim citing sentence (the evidence)
    source: str          # "graph_phrase" | "history" | "none"
    confidence: float

    def as_metadata(self) -> dict:
        return {
            "status": self.status,
            "severity": self.severity,
            "label": self.label,
            "by_citation": self.by_citation,
            "excerpt": self.excerpt,
            "source": self.source,
            "confidence": self.confidence,
        }


_UNKNOWN = TreatmentResult("unknown", 0, "", "", "", "none", 0.0)


def _cite_anchors(citations: list[str]) -> list[str]:
    """The ``"<volume> <reporter>"`` prefix of each reporter cite — the anchor we
    search for in a citing body. The prefix (not the full cite) catches the short
    pincite forms a citing opinion actually uses ("778 N.W.2d at 40") as well as
    the first full cite ("778 N.W.2d 33"). Vendor cites (LEXIS/WL) are skipped."""
    out: list[str] = []
    for c in citations or []:
        if not c or "LEXIS" in c or " WL " in c:
            continue
        m = re.match(r"\s*(\d{1,4}\s+[A-Z][A-Za-z0-9.\s]*?[A-Za-z.])\s+\d", c)
        if m:
            anchor = " ".join(m.group(1).split())
            if anchor not in out:
                out.append(anchor)
    return out


def _sentences_with(text: str, anchor: str):
    """Yield ``(sentence, anchor_offset_within_sentence)`` for every sentence of
    ``text`` that contains ``anchor`` (the target cite). Offset is into the
    *normalized* (whitespace-collapsed) sentence that is returned."""
    start = text.find(anchor)
    seen: set[int] = set()
    while start != -1:
        lo = 0
        for m in _SENT_SPLIT.finditer(text, 0, start):
            lo = m.end()
        m = _SENT_SPLIT.search(text, start)
        hi = m.start() if m else len(text)
        if lo not in seen:
            seen.add(lo)
            sent = " ".join(text[lo:hi].split())
            apos = sent.find(anchor)
            if apos != -1:
                yield sent, apos
        start = text.find(anchor, start + 1)


def classify_citing_text(
    citing_body: str, target_anchors: list[str]
) -> tuple[int, str, str] | None:
    """Scan one citing opinion for negative treatment of the target.

    Returns ``(severity, label, sentence)`` for the most-severe negative stem
    found within ``_PROX`` chars of a target-cite occurrence (and in its
    sentence), or ``None``. Applies the negation / other-grounds / by-statute /
    ruling-noun guards. The returned sentence is the verbatim evidence.
    """
    if not citing_body or not target_anchors:
        return None
    best: tuple[int, str, str] | None = None
    for anchor in target_anchors:
        for sent, apos in _sentences_with(citing_body, anchor):
            for stem, severity, label in _NEG_STEMS:
                for m in stem.finditer(sent):
                    # Proximity: the stem must sit next to THIS cite, not a
                    # different case mentioned elsewhere in a long sentence.
                    if not (apos - _PROX <= m.start() <= apos + len(anchor) + _PROX):
                        continue
                    # Guard 0: "overruled [...] by [target]" — the target is the
                    # OVERRULER (agent), not the overruled. Stem before the cite
                    # with a linking "by" → skip.
                    if m.end() <= apos and _AGENT_BY.search(sent[m.end():apos]):
                        continue
                    # Guard 0b: "[target] (overruling X)" — a gerund AFTER the cite
                    # is a parenthetical describing what the target DID (agent).
                    # ("overruling [target]" keeps the stem BEFORE the cite.)
                    if m.start() > apos and m.group().lower().endswith("ing"):
                        continue
                    # Guard 1: ruling noun right after → "overruled the objection".
                    if _RULING_NOUN.match(sent[m.end():m.end() + 40].lstrip()):
                        continue
                    # Guard 2: negation/hypothetical/party-request before the stem.
                    if _NEGATION_BEFORE.search(sent[max(0, m.start() - 60):m.start()]):
                        continue
                    sev, lab = severity, label
                    # Guard 3: "on other grounds"/"in part" near the stem → the
                    # case survives for its cited holding; downgrade to a caution.
                    # ("overruled in relevant part on other grounds by X" puts the
                    # phrase a bit past the verb, so scan a wide tail.)
                    tail = sent[m.start():m.start() + 120]
                    if severity == 5 and _OTHER_GROUNDS.search(tail):
                        sev, lab = 3, f"{label}-on-other-grounds"
                    elif severity == 5 and _BY_STATUTE.search(tail):
                        lab = "superseded-by-statute"
                    if best is None or sev > best[0]:
                        best = (sev, lab, sent[:400])
    return best


def classify_target(
    target_citations: list[str],
    citing_opinions: list[dict],
) -> TreatmentResult:
    """Compute the treatment flag for one target decision.

    ``citing_opinions`` is a list of ``{"body": str, "court_level": int,
    "name": str, "depth": int}`` for each opinion that cites the target (its
    incoming CASELAW_GRAPH edges). The most-severe negative finding wins; an
    *overrule* (severity 5) is only credited when the citing court could actually
    overrule the target (``court_level <= target_level`` is enforced by the
    caller via ``min_overrule_level``)."""
    anchors = _cite_anchors(target_citations)
    if not anchors:
        return _UNKNOWN
    best: TreatmentResult | None = None
    for op in citing_opinions:
        found = classify_citing_text(op.get("body") or "", anchors)
        if found is None:
            continue
        sev, label, sentence = found
        if best is None or sev > best.severity:
            best = TreatmentResult(
                status=_STATUS_BY_SEVERITY.get(sev, "caution"),
                severity=sev,
                label=label,
                by_citation=op.get("name") or "",
                excerpt=sentence,
                source="graph_phrase",
                # Phrase-only: moderate confidence; an authority-gated overrule is
                # a notch higher than a lower-court criticism.
                confidence=0.65 if sev >= 5 else 0.55,
            )
    return best or TreatmentResult("good", 0, "", "", "", "graph_phrase", 0.4)
