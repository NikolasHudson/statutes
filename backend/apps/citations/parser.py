"""Iowa Code citation parser.

Recognizes the citation forms attorneys actually type:

    "Iowa Code § 714.16"
    "Iowa Code section 714.16(2)(a)"
    "I.C. § 714.16"
    "I.C. 714"
    "section 1.4"
    "§ 714.16(2)(a)(1)"
    "714.16"
    "714.16(2)(a)"
    "Chapter 232"
    "Iowa R. Civ. P. 1.303"      (court rules, by reporter)
    "Iowa Ct. R. 32:1.7"
    "rule 1.421(4)"
    "Iowa Admin. Code r. 441—65.2"   (admin code, em-dash agency—rule form)
    "441 IAC 65.2(3)"                (admin code, official inline form)
    "441—65.2"                       (em, en, or plain hyphen all accepted)

Rule of thumb: be liberal in what we accept (case-insensitive, optional
section sigil, optional spaces around dots) but strict about what we
return — every parsed citation has a normalized chapter, section_number
(or None for chapter-only), and a list of subdivision tokens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Citation:
    chapter: str  # always present, e.g. "714" or "12C"
    section: str | None  # e.g. "714.16" — None for chapter-only citations
    subdivisions: tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""
    # Set when the citation FORM itself names the corpus: the em-dash
    # agency—rule shape is unambiguously the Iowa Admin. Code
    # ("iowa-admin-code"). None for the dotted/colon forms, which are
    # resolved against whatever source the caller passes.
    source_hint: str | None = None

    @property
    def is_chapter_only(self) -> bool:
        return self.section is None

    @property
    def section_path(self) -> str | None:
        """Materialized path used by Node.path. None if chapter-only."""
        return self.section

    @property
    def chapter_path(self) -> str:
        return self.chapter

    def render(self, style: str = "long") -> str:
        body = self.section or self.chapter
        for sub in self.subdivisions:
            body += f"({sub})"
        if self.source_hint == "iowa-admin-code":
            if style == "long":
                prefix = "Iowa Admin. Code r. " if self.section else "Iowa Admin. Code ch. "
                return prefix + body
            if style == "short":
                prefix = "IAC r. " if self.section else "IAC ch. "
                return prefix + body
            return body
        if style == "long":
            prefix = "Iowa Code § " if self.section else "Iowa Code ch. "
            return prefix + body
        if style == "short":
            prefix = "I.C. § " if self.section else "I.C. ch. "
            return prefix + body
        return body


_SIGIL_TOKEN_RE = re.compile(
    r"""
    \s*
    (?:
        iowa\ code                # "Iowa Code"
      # --- Iowa Admin. Code sigils (must precede I.C., whose optional dots
      # would otherwise nibble the "IA" of a bare "IAC") ---
      | iowa\s+admin(?:\.|istrative)?\s*code
      | \biac\b
      | i\.?\s*c\.?               # I.C.
      # --- Iowa rule reporter prefixes (court rules are cited by reporter,
      # not "Iowa Code §"). Also lets our own rendered "Iowa Ct. R. 1.303"
      # round-trip back through lookup. ---
      | iowa\s+ct\.?\s*r\.?                      # Iowa Ct. R.
      | iowa\s+r\.?\s*civ\.?\s*p\.?              # Iowa R. Civ. P.
      | iowa\s+r\.?\s*crim\.?\s*p\.?             # Iowa R. Crim. P.
      | iowa\s+r\.?\s*app\.?\s*p\.?              # Iowa R. App. P.
      | iowa\s+r\.?\s*evid\.?                    # Iowa R. Evid.
      | iowa\s+rs?\.?\s*(?:of\s+)?prof(?:'l|essional)?\.?\s*conduct
      | iowa\s+rules?\s+of\s+(?:civil|criminal|appellate)\s+procedure
      | iowa\s+rules?\s+of\s+evidence
      | iowa\s+rules?\s+of\s+professional\s+conduct
      | §§?                       # § or §§
      | sec(?:tion|s\.?|\.)?      # section / sec. / secs.
      | ch(?:apter|\.)?           # chapter / ch.
      | rules?\.?                 # "rule" / "rules" / "rule."
      | r\.                       # bare "R."
    )
    \s*
    """,
    re.IGNORECASE | re.VERBOSE,
)

_BODY_RE = re.compile(
    r"""
    (?P<chapter>\d+[A-Z]?)
    (?:
        # Separator is "." for the Iowa Code / most rules (714.16, 1.303)
        # but ":" for the Rules of Professional Conduct (32:1.7). The rule
        # number after a colon is itself dotted ("1.10"), so allow dots in
        # ``rest``. We capture the separator and keep it in the path because
        # Node.path stores the colon verbatim ("32:1.7").
        \s*(?P<sep>[.:])\s*(?P<rest>\w[\w.]*)
    )?
    (?P<subs>(?:\s*\([^)]+\))*)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SUB_RE = re.compile(r"\(\s*([^)\s]+)\s*\)")

# --- Iowa Admin. Code body forms. Node.path stores the em-dash shape
# ("441—65.2" = agency 441, chapter 65, rule 2); readers type em dash, en
# dash, or plain hyphen interchangeably, so accept all three and normalize
# to the em dash. A dotless rest ("441—65") is a chapter reference. The
# parenthetical after a rule number is captured as subdivisions verbatim —
# whether it is a subrule index or the enabling statute is a resolution
# question (they share the syntax), not a parsing one.
_IAC_BODY_RE = re.compile(
    r"""
    (?P<agency>\d+)\s*[—–-]\s*
    (?P<rest>\d+(?:\.\d+)?)
    (?P<subs>(?:\s*\([^)]+\))*)
    \s*$
    """,
    re.VERBOSE,
)

# The official inline form ("441 IAC 65.2(3)") puts the sigil BETWEEN agency
# and rule, so the leading-sigil stripper never sees it.
_IAC_INLINE_RE = re.compile(
    r"""
    ^\s*(?P<agency>\d+)\s+iac\s+
    (?P<rest>\d+(?:\.\d+)?)
    (?P<subs>(?:\s*\([^)]+\))*)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _iac_citation(m: re.Match, raw: str) -> Citation:
    agency, rest = m["agency"], m["rest"]
    chapter = f"{agency}—{rest.split('.', 1)[0]}"
    subdivisions = tuple(_SUB_RE.findall(m["subs"] or ""))
    return Citation(
        chapter=chapter,
        section=f"{agency}—{rest}" if "." in rest else None,
        subdivisions=subdivisions,
        raw=raw,
        source_hint="iowa-admin-code",
    )

_CHAPTER_TRIGGER_RE = re.compile(
    r"\b(ch(?:apter|\.)?)\b", re.IGNORECASE
)


class CitationParseError(ValueError):
    pass


def parse(text: str) -> Citation:
    """Parse a single citation string. Raises CitationParseError on failure."""
    if not text or not text.strip():
        raise CitationParseError("empty citation")

    raw = text.strip()
    forced_chapter_only = bool(_CHAPTER_TRIGGER_RE.search(raw))

    inline = _IAC_INLINE_RE.match(raw)
    if inline:
        return _iac_citation(inline, raw)

    consumed = 0
    while True:
        m = _SIGIL_TOKEN_RE.match(raw, consumed)
        if not m:
            break
        consumed = m.end()
    body_text = raw[consumed:].strip()

    # The dash form is unambiguously the Iowa Admin. Code — try it before the
    # dotted-body fallback would misread "441—65.2" as bare chapter "441".
    iac = _IAC_BODY_RE.match(body_text)
    if iac:
        return _iac_citation(iac, raw)

    body_match = _BODY_RE.match(body_text)
    if not body_match:
        raise CitationParseError(f"could not parse {raw!r}")

    chapter = body_match["chapter"]
    sep = body_match["sep"]
    rest = body_match["rest"]
    subs_text = body_match["subs"] or ""

    if forced_chapter_only and rest is None:
        return Citation(chapter=chapter, section=None, subdivisions=(), raw=raw)

    if rest is None:
        # Bare "714" with no chapter sigil is ambiguous. Convention: with no
        # explicit "chapter" trigger, treat it as a chapter reference.
        return Citation(chapter=chapter, section=None, subdivisions=(), raw=raw)

    section = f"{chapter}{sep}{rest}"
    subdivisions = tuple(_SUB_RE.findall(subs_text))
    return Citation(
        chapter=chapter, section=section, subdivisions=subdivisions, raw=raw
    )


def find_all(text: str) -> list[Citation]:
    """Find every citation-shaped substring in ``text``.

    Used by cross-reference extraction. The probe JSON's referred_to_in is
    already structured, but section bodies contain free-form refs ("section
    1.1", "as defined in chapter 232") we will want to capture later."""
    out: list[Citation] = []
    for match in _ITER_RE.finditer(text):
        try:
            out.append(parse(match.group(0)))
        except CitationParseError:
            continue
    return out


# Used by find_all and (re-exported into lookups.py) by citation_links,
# validate_citations, and verify_quotes. Order matters: try the most-specific
# forms first.
#
# The body separator must stay in sync with ``_BODY_RE``: the Iowa Code and
# most rules join chapter and section with a dot ("714.16", "1.303"), but the
# Rules of Professional Conduct use a colon ("32:1.10", "51:2.11"). The colon
# branch deliberately requires a *dotted* rest ("32:1.10", never "32:5") so it
# captures the court-rule form as ONE token instead of splitting it into "32"
# + "1.10" — while still not matching a bare time like "9:30" (rest "30" has
# no dot). It is purely additive: text with no colon-citations scans exactly
# as before.
_ITER_RE = re.compile(
    r"""
    (?:
        (?:Iowa\ Code\s+)?
        (?:§§?|\bsec(?:tion|s\.?|\.)?\b|\bI\.?C\.?\b|\bch(?:apter|\.)?\b)
        \s*
    )?
    \d+[A-Z]?
    (?:
        # Iowa Admin. Code forms. In free text only the em/en dash counts and
        # the rule part must be dotted ("441—65.2") — a plain hyphen or a
        # dotless rest would swallow every numeric range ("2023-24",
        # "chapters 135—137"). Explicit lookups take those via parse().
        \s*[—–]\s*\d+\.\w+   # em-dash form: 441—65.2
      | \s+IAC\s+\d+\.\w+    # official inline form: 441 IAC 65.2
      | :\s*\d+(?:\.\w+)+    # court-rule colon form: 32:1.10, 51:2.11
      | \.\w+               # dotted form: 714.16, 1.303
    )?
    (?:\s*\([^)]+\))*
    """,
    re.IGNORECASE | re.VERBOSE,
)
