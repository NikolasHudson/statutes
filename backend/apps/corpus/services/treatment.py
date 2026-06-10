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
# West history-chain shorthand: "Brecher v. Brown, 17 N.W.2d 377 (1945),
# overruled, Ehlers v. Iowa Warehouse Co., 188 N.W.2d 368". The comma after the
# stem stands for "by" — the PRECEDING cite is the overruled case and the case
# that FOLLOWS is the overruler. A stem is in this form when it is immediately
# followed by a comma; combined with a reporter cite shortly BEFORE the stem
# (the victim's cite), the target after the stem is the agent and must NOT be
# flagged. Genuine prose ("Smith, 1 N.W.2d 2, overruled [target]") has no comma
# after the verb, so it still flags.
_COMMA_AFTER = re.compile(r"\s*,")
# Narrative-agent pattern: "In [target], 188 N.W.2d 368, 369 (Iowa 1971), this
# court overruled a line of prior cases" — the citing opinion is describing what
# the TARGET case did (the target is the overruler). Matches when the ONLY
# material between the target cite and the stem is pincite pages / a court-year
# paren / a court subject ("this court", "the court", "we"). A relative pronoun
# ("[cite], which we overruled") breaks the match, so a genuine object-position
# target still flags; the guard further requires a PAST-tense stem ("-ed") —
# a citing court overruling the target in the same breath writes the present
# ("having reconsidered [cite], we overrule it"), while past tense after the
# cite narrates what the target case itself did.
_NARRATIVE_SUBJECT = re.compile(
    r"^[\s\d,–—-]*(?:\([^)]{0,40}\))?[\s,]*"
    r"(?:this\s+court|the\s+(?:\w+\s+)?court|we)\s+"
    r"(?:expressly\s+|specifically\s+|effectively\s+)?$",
    re.I,
)
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

# Sentence segmentation. We scan ONLY the cite's own sentence for a negative stem,
# so the stem and the target cite must co-occur in one sentence ("expressly
# overruling PPH 2018"; "PPH 2018 … is overruled"). A looser char window
# mis-attributes a stem from an adjacent sentence (a different case, or "the court
# overruled the objection") to the target.
#
# Segmenting court-opinion ``body_text`` is two-step. (1) NORMALIZE: PDF text
# extraction injects ``\n\n`` (and hyphen line-wraps "rea-\n\nsons") MID-sentence,
# so "in overruling\n\nMadden v. City of Iowa City, 848 N.W.2d 40" gets the
# overrule stem and the reporter cite torn into different "lines". Naive
# newline-splitting therefore SILENTLY DROPS real overrulings (this exact case:
# Bankers Trust → Madden). We repair the soft hyphenation and collapse ALL
# whitespace to single spaces first. (2) SPLIT on sentence punctuation, skipping
# periods inside legal abbreviations so a caption between the stem and the cite
# ("overruling Madden v. City of Iowa City, 848 N.W.2d 40") is not chopped.
#
# The abbreviation handling is deliberately NOT a flat "v."-like set (an earlier
# version was, and it MERGED two real sentences — "...we overrule Acme Co. The
# plaintiff cites [target]" — mis-attributing the overrule to [target], a
# false-positive "this case is dead" flag, the exact harm this module guards). Two
# classes: (A) abbreviations that NEVER end a sentence (titles, "v.", cite-internal
# single letters) — always non-terminal; (B) entity / citation SUFFIXES
# ("Co."/"Inc."/"No."/"App.") that legitimately end a party name AND can end a
# sentence — non-terminal only when the next token CONTINUES the clause (lowercase
# / digit / "("), terminal when it starts a Capitalized new sentence. "Iowa" is in
# NEITHER (so "...of Iowa. We reaffirm X" splits correctly; "(Iowa 2014)" never
# matches _SENT_END because the period is inside the paren after the year).
_WRAP_HYPHEN = re.compile(r"(?<=[a-z])-\s*\n+\s*(?=[a-z])")  # soft-hyphen wrap only
_WS = re.compile(r"\s+")
_SENT_END = re.compile(r"[.?;]\s")
_TRAIL_WORD = re.compile(r"([A-Za-z0-9]+)\)?$")
# Another reporter cite between a stem and the target cite means the stem belongs
# to that OTHER case (or it is a string-cite list) — not negative treatment of the
# target. Catches the "newline cite-block collapses to one sentence" false positive.
_CITE_IN_SPAN = re.compile(r"\d{1,4}\s+[A-Z][A-Za-z0-9.\s]{0,12}?[A-Za-z.]\s+\d")
# (A) never a sentence end.
_ABBREV_ALWAYS = frozenset({
    "v", "vs", "mr", "mrs", "ms", "dr", "prof", "rev", "st", "mt",
    "n", "w", "e", "s", "u", "f", "cf", "eg", "ie",
})
# (B) entity / citation suffixes — terminal only before a Capitalized new sentence.
_ABBREV_SUFFIX = frozenset({
    "co", "inc", "corp", "ltd", "llc", "lp", "bros", "assn", "dept", "div",
    "ct", "cts", "app", "ed", "eds", "supp", "fed", "vol", "etc", "al", "id",
    "ch", "sec", "art", "para", "p", "pp", "no", "nos", "jr", "sr", "a",
})


def _normalize_body(text: str) -> str:
    """Repair PDF soft-hyphen line wraps (lowercase-``-``\\n-lowercase only, so page
    ranges "33-\\n34" and date spans "2014-\\n2016" survive intact), then collapse
    all whitespace (incl. the mid-sentence ``\\n\\n`` PDF extraction injects)."""
    if not text:
        return text
    return _WS.sub(" ", _WRAP_HYPHEN.sub("", text))


def _is_boundary(text: str, dot_idx: int, next_char: str) -> bool:
    """Does the ``[.?;]`` at ``dot_idx`` end a sentence? Yes, unless the word it
    terminates is an abbreviation: class (A) never ends a sentence; class (B) ends
    one only when ``next_char`` starts a Capitalized new sentence.

    Looks back only a bounded window (the trailing token is at most a few chars):
    slicing the FULL prefix (``text[:dot_idx]``) and searching it per boundary is
    O(n) each → O(n²) over a long opinion body, the cause of a pathological
    annotation slowdown."""
    m = _TRAIL_WORD.search(text[max(0, dot_idx - 24):dot_idx])
    if m is None:
        return True
    w = m.group(1).lower()
    if w in _ABBREV_ALWAYS:
        return False
    if w in _ABBREV_SUFFIX:
        return next_char.isupper()
    return True


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _SENT_END.finditer(text):
        nxt = text[m.end()] if m.end() < len(text) else ""
        if _is_boundary(text, m.start(), nxt):
            out.append(text[start:m.start() + 1])
            start = m.end()
    if start < len(text):
        out.append(text[start:])
    return out


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


def normalized_sentences(body: str) -> list[str]:
    """Normalize a citing opinion body (repair PDF hyphen wraps, collapse the
    mid-sentence ``\\n\\n`` PDF extraction injects) and split it abbreviation-aware
    into sentences. This is the EXPENSIVE step (two full-body regex passes), so do
    it ONCE per body — the batch annotator scans the same body against many target
    cites, and re-normalizing per (target, anchor) is a large, needless cost."""
    if not body:
        return []
    return _split_sentences(_normalize_body(body))


def classify_in_sentences(
    sentences: list[str], target_anchors: list[str]
) -> tuple[int, str, str] | None:
    """Scan PRE-NORMALIZED sentences (from :func:`normalized_sentences`) for the
    most-severe negative treatment of the target. Same logic and guards as
    :func:`classify_citing_text`, but reuses one normalization across the many
    targets a single citing opinion cites (the hot batch path)."""
    if not sentences or not target_anchors:
        return None
    best: tuple[int, str, str] | None = None
    for anchor in target_anchors:
        alen = len(anchor)
        for sent in sentences:
            apos = sent.find(anchor)
            if apos == -1:
                continue
            for stem, severity, label in _NEG_STEMS:
                for m in stem.finditer(sent):
                    # Proximity: the stem must sit next to THIS cite, not a
                    # different case mentioned elsewhere in a long sentence.
                    if not (apos - _PROX <= m.start() <= apos + alen + _PROX):
                        continue
                    # Guard 0: "overruled [...] by [target]" — the target is the
                    # OVERRULER (agent), not the overruled. Stem before the cite
                    # with a linking "by" → skip.
                    if m.end() <= apos and _AGENT_BY.search(sent[m.end():apos]):
                        continue
                    # Guard 0a: West history-chain comma form — "X, 17 N.W.2d
                    # 377 (1945), overruled, [target]": the comma stands for
                    # "by", so the target FOLLOWING the stem is the OVERRULER
                    # of the cite preceding it. Both marks required (comma
                    # right after the stem AND a reporter cite shortly before
                    # it) so prose overrulings still flag.
                    if (
                        m.end() <= apos
                        and _COMMA_AFTER.match(sent, m.end())
                        and _CITE_IN_SPAN.search(sent[max(0, m.start() - 45):m.start()])
                    ):
                        continue
                    # Guard 0b: "[target] (overruling X)" — a gerund AFTER the cite
                    # is a parenthetical describing what the target DID (agent).
                    # ("overruling [target]" keeps the stem BEFORE the cite.)
                    if m.start() > apos and m.group().lower().endswith("ing"):
                        continue
                    # Guard 0d: "In [target], this court overruled <others>" —
                    # a PAST-tense stem after the cite with only pincite/paren
                    # + a court subject between them: the citing opinion
                    # narrates what the TARGET case did (target is the agent).
                    if (
                        m.start() > apos
                        and m.group().lower().endswith("ed")
                        and _NARRATIVE_SUBJECT.match(sent[apos + alen:m.start()])
                    ):
                        continue
                    # Guard 1: ruling noun right after → "overruled the objection".
                    if _RULING_NOUN.match(sent[m.end():m.end() + 40].lstrip()):
                        continue
                    # Guard 2: negation/hypothetical/party-request before the stem.
                    if _NEGATION_BEFORE.search(sent[max(0, m.start() - 60):m.start()]):
                        continue
                    # Guard 2b: another reporter cite BETWEEN the stem and the
                    # target cite → the stem belongs to that other case (or this is
                    # a string-cite list / a whitespace-collapsed cite block, not a
                    # single treatment statement). Defends precision after sentence
                    # normalization joined newline-separated cite stacks.
                    between = (sent[m.end():apos] if m.end() <= apos
                               else sent[apos + alen:m.start()])
                    if _CITE_IN_SPAN.search(between):
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


def classify_citing_text(
    citing_body: str, target_anchors: list[str]
) -> tuple[int, str, str] | None:
    """Scan one citing opinion (raw body) for negative treatment of the target.

    Returns ``(severity, label, sentence)`` for the most-severe negative stem
    found within ``_PROX`` chars of a target-cite occurrence (and in its
    sentence), or ``None``. Convenience wrapper that normalizes the body then
    delegates to :func:`classify_in_sentences`; the batch path should call
    :func:`normalized_sentences` once and :func:`classify_in_sentences` per target."""
    if not citing_body or not target_anchors:
        return None
    return classify_in_sentences(normalized_sentences(citing_body), target_anchors)


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
