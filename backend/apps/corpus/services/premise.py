"""PR6: verify a USER-asserted case holding against the opinion (anti-anchoring).

The dangerous failure the slip-and-fall prompt exposed: a user *states* what a
case holds ("Madden v. City of Iowa City confirmed that local liability-shifting
ordinances are perfectly valid"), the model anchors on that confident premise and
parrots it, and the post-answer claim-NLI misses it (the answer is hedged →
"partial", and the retrieved chunk is background law). The fix has to intercept
the premise BEFORE the model drafts.

This module: (1) deterministically extracts case-holding *premises* from the
user's text — a sentence that names a case AND asserts what it held; (2) retrieves
that case and (3) checks the premise against the opinion text with the existing
``semantic_support`` NLI. A ``contradicted`` or ``partial`` verdict becomes a
finding the chat layer turns into a pre-answer caution + a user advisory.

Mirrors the treatment v1→v2 split: a cheap, precise deterministic gate generates
candidates; the LLM only verifies. Flag-gated (``RAG_PREMISE_CHECK``), no-op
without a key or without an injected checker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.corpus.services import semantic_support
from apps.corpus.services.answer import (
    _normalize_for_match,
    _passage_anchors,
    _split_sentences,
    _TREATMENT_CUE_RE,
)
from apps.corpus.services.search import extract_citations

# At most this many premises verified per turn (cost ceiling; pathological inputs
# naming many cases are bounded). Deepest-asserted first is not meaningful here,
# so it is just first-N in reading order.
MAX_PREMISES = 3

# A case caption: "Party1 v. Party2", each side a capitalized run with a few
# connectors. Greedy enough to grab "City of Iowa City", bounded so it stops at
# the first lowercase non-connector ("confirmed", "held").
_CAPTION_RE = re.compile(
    # Party 1 must not START with a sentence-opener / preposition that merely
    # PRECEDES the caption ("Under Madden v. …"); excluding it keeps the leading
    # word out of the captured name AND leaves it visible to _prep_before.
    r"\b(?!(?:Under|Per|In|On|See|The|And|But|Or|Pursuant|According|Given|Cf|"
    r"For|To|By|Of|From|With|Here|Where|When|However|Thus|Therefore)\s)"
    r"([A-Z][\w.'&-]+(?:\s+(?:of|the|and|&|for|[A-Z][\w.'&-]+)){0,5})"
    r"\s+vs?\.?\s+"
    r"([A-Z][\w.'&-]+(?:\s+(?:of|the|and|&|for|[A-Z][\w.'&-]+)){0,5})"
)

# Verbs that ATTRIBUTE A HOLDING to a case. Kept tight: "discusses"/"addresses"/
# "cites" are NOT here (they don't assert a holding, so an incidental mention is
# not a premise). Must occur AFTER the case anchor and near it (see _bind).
_ASSERT_VERB_RE = re.compile(
    r"\b(?:held|holds|holding|confirmed|confirms|establish(?:ed|es)?|"
    r"stands?\s+for|ruled|rules|found|finds|conclud(?:ed|es)|"
    r"require[sd]?|mandate[sd]?|recogniz(?:ed|es)|made\s+(?:it\s+)?clear|"
    r"settled|says?\s+that|provides?\s+that|means?\s+that)\b",
    re.I,
)

# Hedges that mean the user is NOT confidently asserting the holding (so there is
# no anchor to neutralize). "overruled/abrogated/..." (the treatment cues) also
# mean the user is engaging with the case's status, not asserting it as good law.
_HEDGE_RE = re.compile(
    r"\b(?:arguably|allegedly|i\s+think|might\s+have|may\s+have|possibly|perhaps|"
    r"did\s+not\s+hold|does\s+not\s+hold|didn'?t\s+hold|i'?m\s+not\s+sure|"
    r"i\s+believe|not\s+certain|unsure)\b",
    re.I,
)

# The assertion verb must sit within this many chars AFTER a case anchor to be
# bound to it (same clause), so "the statute requires X; see Smith v. Jones" does
# not fire (verb precedes the anchor) and a far-away verb in a long sentence is
# not mis-attributed.
_BIND_WINDOW = 130

# A case introduced as AUTHORITY for a proposition — "Under Madden, …", "Per X",
# "Pursuant to Y" — asserts a holding without a verb like "held". The NLI verdict
# (supported/no_claim → silent) is the precision backstop, so this can broaden
# recall without producing false warnings. NB "in" is deliberately excluded — it
# is too common in non-holding references ("In Smith, the plaintiff argued …").
_HOLDING_PREP_RE = re.compile(r"\b(?:under|per|pursuant\s+to|according\s+to)\s+$", re.I)


@dataclass
class Premise:
    sentence: str          # the verbatim user sentence asserting the holding
    query: str             # retrieval query for the case (cite preferred)
    case_label: str        # human label (caption, else cite)
    anchors: list[str]     # normalized caption + cites, for the retrieval guard


@dataclass
class PremiseFinding:
    case_label: str
    sentence: str          # the user's asserted premise
    # FIDELITY axis (LLM NLI): is the premise a faithful reading of the case?
    verdict: str           # "contradicted" | "partial" | "supported" | "unchecked" | ...
    evidence: str          # verbatim span from the opinion
    # CURRENCY axis (deterministic, PR7): is the case still GOOD LAW? Orthogonal to
    # fidelity — a premise can be a *perfect* reading of an OVERRULED case (the
    # Madden/Bankers Trust trap), which fidelity-NLI alone scores ``supported`` and
    # waves through. Sourced from the retrieved passage's PR3 ``TreatmentFlag``.
    currency: str = "unknown"        # "good" | "caution" | "negative" | "unknown"
    treating_case: str = ""          # the case that treated it (TreatmentFlag.by_citation)
    treatment_label: str = ""        # "overruled" | "abrogated" | "superseded" | ...
    treatment_evidence: str = ""     # verbatim treating sentence (the evidence)

    @property
    def fidelity_bad(self) -> bool:
        from apps.corpus.services import semantic_support
        return self.verdict in (semantic_support.CONTRADICTED, semantic_support.PARTIAL)

    @property
    def currency_bad(self) -> bool:
        return self.currency in ("negative", "caution")


def _anchors_in(sentence: str) -> tuple[list[tuple[str, int, int]], list[tuple[str, int]]]:
    """Return ([(caption, start, end)], [(cite, start)]) found in ``sentence``."""
    captions = [(m.group(0), m.start(), m.end()) for m in _CAPTION_RE.finditer(sentence)]
    cites: list[tuple[str, int]] = []
    for c in extract_citations(sentence):
        m = re.search(re.escape(c), sentence)
        if m:
            cites.append((c, m.start()))
    return captions, cites


def _bind(sentence: str, anchor_ends: list[int]) -> bool:
    """True when an assertion verb sits just after one of the anchor end offsets."""
    for vm in _ASSERT_VERB_RE.finditer(sentence):
        for ae in anchor_ends:
            if 0 <= vm.start() - ae <= _BIND_WINDOW:
                return True
    return False


def _prep_before(sentence: str, anchor_starts: list[int]) -> bool:
    """True when a case anchor is introduced by a holding-preposition ("Under X")."""
    return any(
        _HOLDING_PREP_RE.search(sentence[max(0, s - 20):s]) for s in anchor_starts
    )


def extract_premises(text: str) -> list[Premise]:
    """Deterministically pull case-holding premises from ``text``. A sentence
    qualifies iff it names a case (caption or reporter cite) AND attributes a
    holding to it — either an assertion verb after the name ("Madden … confirmed
    that") OR the name introduced as authority for a proposition ("Under Madden,
    …") — and it is not hedged / not about the case's treatment. The NLI verdict
    is the precision backstop (a correct premise verifies as supported → silent),
    so extraction favors recall over a too-narrow verb list."""
    out: list[Premise] = []
    seen: set[str] = set()
    for sent in _split_sentences(text):
        if _HEDGE_RE.search(sent) or _TREATMENT_CUE_RE.search(sent):
            continue
        captions, cites = _anchors_in(sent)
        if not captions and not cites:
            continue
        anchor_ends = [e for _, _, e in captions] + [s + len(c) for c, s in cites]
        anchor_starts = [s for _, s, _ in captions] + [s for _, s in cites]
        if not (_bind(sent, anchor_ends) or _prep_before(sent, anchor_starts)):
            continue
        caption = captions[0][0] if captions else ""
        cite_texts = [c for c, _ in cites]
        label = caption or (cite_texts[0] if cite_texts else "")
        if not label:
            continue
        key = _normalize_for_match(label)
        if key in seen:
            continue
        seen.add(key)
        anchors = [_normalize_for_match(caption)] if caption else []
        anchors += [_normalize_for_match(c) for c in cite_texts]
        cleaned = " ".join(sent.split()).strip()
        out.append(Premise(
            sentence=cleaned,
            # Retrieval query = the whole assertion (case anchor + the asserted
            # topic), NOT just the caption: the name/cite lanes still pin the right
            # case at rank 1, but the topical words make the chunk-aware excerpt
            # surface the RELEVANT holding instead of an arbitrary chunk (the bug
            # that made the live check miss Madden — it pulled a preemption chunk).
            query=cleaned,
            case_label=label.strip(),
            anchors=[a for a in anchors if a],
        ))
        if len(out) >= MAX_PREMISES:
            break
    return out


def _overlaps(premise: Premise, passage) -> bool:
    """The retrieved passage is the asserted case iff one of the premise's
    normalized anchors and one of the passage's anchors are substrings of each
    other (caption containment — "madden v. city of iowa city" inside the full
    "beth a. madden v. city of iowa city" — or a shared reporter cite)."""
    pa = _passage_anchors(passage)
    for a in premise.anchors:
        for b in pa:
            if a and b and (a in b or b in a):
                return True
    return False


def check_premises(
    text: str,
    *,
    source_slug: str | None = None,
    checker=None,
    retrieve_fn=None,
    currency: bool = True,
) -> list[PremiseFinding]:
    """Extract → retrieve → check the named case on TWO orthogonal axes:

    * **Currency** (deterministic, always runs): is the case still good law? Read
      straight off the retrieved passage's PR3 ``TreatmentFlag`` — no LLM. This is
      the axis the fidelity check is structurally blind to: a *faithful* reading
      of an OVERRULED case (Madden/Bankers Trust) scores ``supported`` on fidelity
      and would otherwise pass silently.
    * **Fidelity** (LLM NLI, only when a ``checker`` is supplied): does the case
      actually hold what the user says? ``contradicted``/``partial`` → finding.

    A finding is emitted when EITHER axis is bad. ``currency=False`` disables the
    currency axis (so ``RAG_CURRENCY_CHECK`` is honored even when fidelity is on).
    ``retrieve_fn`` is injectable for tests; in production it auto-binds to
    ``retrieve_context`` (whose passages already carry ``treatment``).
    ``checker=None`` runs currency-only — the chat layer passes a real checker only
    when ``RAG_PREMISE_CHECK`` is on and a key resolves one, but currency
    (``RAG_CURRENCY_CHECK``) needs no key. ``source_slug`` is accepted for call-shape
    symmetry but ignored: premises are case-holding assertions, so retrieval is
    always scoped to ``iowa-caselaw``."""
    premises = extract_premises(text)
    if not premises:
        return []
    if retrieve_fn is None:
        from apps.corpus.services.retrieval import retrieve_context as retrieve_fn

    findings: list[PremiseFinding] = []
    for p in premises:
        try:
            ctx = retrieve_fn(
                p.query, source_slug="iowa-caselaw", candidate_pool=60,
                display_limit=6, rerank=True, enrich_bodies=True,
                excerpt_budget_top=9000, excerpt_budget_rest=4000, top_hits_full=2,
            )
        except Exception:  # noqa: BLE001 — retrieval failure must not break the turn
            continue
        # Pick the retrieved passage that actually IS the asserted case (anchor
        # overlap) — NOT just rank 1. The query is topical (name + holding) so a
        # different, more on-topic case can outrank the named one; we must check
        # against the case the user named, or stay silent if it isn't retrieved.
        passage = next(
            (pg for pg in ctx.passages if not p.anchors or _overlaps(p, pg)),
            None,
        )
        if passage is None:
            continue

        # --- Currency axis (deterministic): the flag is RIGHT THERE on the passage.
        flag = getattr(passage, "treatment", None)
        currency_status = getattr(flag, "status", "unknown") or "unknown"
        treating_case = getattr(flag, "by_citation", "") or ""
        treatment_label = getattr(flag, "label", "") or ""
        treatment_evidence = getattr(flag, "excerpt", "") or ""

        # --- Fidelity axis (LLM NLI): only when a checker is available.
        verdict_str, evidence = "unchecked", ""
        source_text = passage.excerpt or passage.snippet
        if checker is not None and source_text:
            try:
                v = checker.check_claims([p.sentence], source_text)[0]
                verdict_str, evidence = v.verdict, v.evidence
            except Exception:  # noqa: BLE001 — NLI failure must not break the turn
                pass

        # Emit on EITHER axis. Fidelity asymmetry (vs the post-answer claim-NLI): a
        # user premise that OVERSTATES a holding (partial) is also an anchor worth
        # neutralizing, so partial warns. Currency: negative (overruled/abrogated/
        # superseded) or caution (overruled-on-other-grounds) both warn.
        fidelity_bad = verdict_str in (semantic_support.CONTRADICTED, semantic_support.PARTIAL)
        currency_bad = currency and currency_status in ("negative", "caution")
        if fidelity_bad or currency_bad:
            findings.append(PremiseFinding(
                case_label=p.case_label, sentence=p.sentence,
                verdict=verdict_str, evidence=evidence,
                currency=currency_status, treating_case=treating_case,
                treatment_label=treatment_label, treatment_evidence=treatment_evidence,
            ))
    return findings


def render_premise_caution(findings: list[PremiseFinding]) -> str:
    """The pre-answer system message that stops the model anchoring on a bad
    premise. Each finding may flag two orthogonal problems — the case is no longer
    GOOD LAW (currency) and/or the premise MISREADS the case (fidelity) — and the
    message instructs the model to correct first, then answer under current law."""
    if not findings:
        return ""
    lines = []
    for f in findings:
        if f.currency_bad:
            # Currency is the load-bearing correction: the premise may be a
            # perfectly faithful reading, but it rests on a case that is dead law.
            who = f.treating_case or "a later Iowa decision"
            verb = (f.treatment_label or "negatively treated").replace("-", " ")
            ev = (f.treatment_evidence or "").strip()
            ev_txt = f' Treating-court language: "{ev[:200].rstrip()}".' if ev else ""
            severity_word = "OVERRULED / no longer good law" if f.currency == "negative" \
                else "treated with CAUTION (qualified on another point)"
            lines.append(
                f"- The user's argument rests on **{f.case_label}**, which has been "
                f"{verb} by {who} — it is {severity_word}. The user's reading may even "
                f"be FAITHFUL to what that case once held; that does not matter, "
                f"because the case is no longer authority. Do NOT analyze the question "
                f"on the premise that this case states current law.{ev_txt}"
            )
        if f.fidelity_bad:
            how = ("the retrieved opinion text CONTRADICTS this"
                   if f.verdict == semantic_support.CONTRADICTED
                   else "the retrieved opinion text supports only a NARROWER point — "
                        "the user's statement overstates it")
            ev = f.evidence.strip()
            ev_txt = f' Opinion text: "{ev[:200].rstrip()}".' if ev else ""
            lines.append(
                f'- The user asserts that **{f.case_label}** {f.sentence!r}, but {how}.'
                f"{ev_txt}"
            )
    return (
        "PREMISE CHECK — the user's question rests on one or more named cases, and "
        "those premises did NOT hold up when checked against the corpus (the case "
        "is no longer good law, and/or the stated holding misreads the opinion). Do "
        "NOT accept the user's characterization and do NOT answer on top of it. For "
        "each item below: (1) independently read the case via search_statutes; "
        "(2) LEAD your answer by stating plainly that the premise is bad — name the "
        "overruling/treating case and what changed; then (3) answer the user's "
        "underlying question under the CURRENT rule (downstream strategy built on "
        "the bad premise is moot — say so and redirect to what actually controls):\n"
        + "\n".join(lines)
    )


def finding_dicts(findings: list[PremiseFinding]) -> list[dict]:
    """Serialize for the verify report / advisory (additive). Existing keys
    (``case``/``asserted``/``verdict``/``evidence``) unchanged; the currency axis
    is additive (``currency``/``treating_case``/``treatment_label``)."""
    return [
        {"case": f.case_label, "asserted": f.sentence,
         "verdict": f.verdict, "evidence": f.evidence,
         "currency": f.currency, "treating_case": f.treating_case,
         "treatment_label": f.treatment_label,
         "treatment_evidence": f.treatment_evidence}
        for f in findings
    ]
