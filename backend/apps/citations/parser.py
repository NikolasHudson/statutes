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

    consumed = 0
    while True:
        m = _SIGIL_TOKEN_RE.match(raw, consumed)
        if not m:
            break
        consumed = m.end()
    body_text = raw[consumed:].strip()

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


# Used by find_all only. Order matters: try the most-specific forms first.
_ITER_RE = re.compile(
    r"""
    (?:
        (?:Iowa\ Code\s+)?
        (?:§§?|\bsec(?:tion|s\.?|\.)?\b|\bI\.?C\.?\b|\bch(?:apter|\.)?\b)
        \s*
    )?
    \d+[A-Z]?(?:\.\w+)?(?:\s*\([^)]+\))*
    """,
    re.IGNORECASE | re.VERBOSE,
)
