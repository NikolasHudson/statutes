"""Parse an enrolled Iowa bill (RTF) into act sections + Code-edge captures.

Phase 0 scope: the section grammar and amendatory lead-in extraction,
grounded in the measured structure of GA 90 enrolled bills (see
IOWA_ACTS_INGESTION_PLAN.md). The writer/differ integration lands with the
full ingestion app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rtf import Run, full_text_with_markers, resulting_text, tokenize

# "Section 1." opens a bill; every later head is "Sec. N.". Requiring the
# 3-space indent the publisher uses would be brittle; requiring the head to
# start its line is not.
_SECTION_HEAD_RE = re.compile(r"^\s*(?:Section|Sec\.)\s+(?P<num>\d+)\.\s*", re.MULTILINE)

_TITLE_RE = re.compile(
    r"^(?P<bill>[HS]F\s*\d+)\s*\(LSB[^)]*\)", re.MULTILINE
)

# A Code section token: 462A.17A, 161A.4, 2.69 …
_CODE_SEC = r"\d+[A-Z]{0,2}\.\d+[A-Z]{0,2}"

# Amendatory lead-ins, most specific first. Each yields (action, code refs).
_LEADIN_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "new_section",
        re.compile(rf"^NEW SECTION\.\s+(?P<refs>{_CODE_SEC})\s+(?P<heading>[^\n]*)"),
    ),
    (
        "repeal",
        re.compile(
            rf"^Sections?\s+(?P<refs>{_CODE_SEC}(?:\s*(?:,|and)\s*{_CODE_SEC})*)"
            r"[^\n]*?,\s*Code\s+(?P<code_year>\d{4})[^\n]*?,\s*(?:is|are)\s+repealed"
        ),
    ),
    (
        "repeal_chapter",
        re.compile(
            r"^Chapters?\s+(?P<refs>\d+[A-Z]{0,2}(?:\s*(?:,|and)\s*\d+[A-Z]{0,2})*)"
            r"\s*,\s*Code\s+(?P<code_year>\d{4})\s*,\s*(?:is|are)\s+repealed"
        ),
    ),
    (
        "amend_add",
        re.compile(
            rf"^Sections?\s+(?P<refs>{_CODE_SEC})[^\n]*?Code\s+(?P<code_year>\d{{4}})"
            r"[^\n]*?(?:is|are) amended by adding"
        ),
    ),
    (
        "amend_strike",
        re.compile(
            rf"^Sections?\s+(?P<refs>{_CODE_SEC})[^\n]*?Code\s+(?P<code_year>\d{{4}})"
            r"[^\n]*?(?:is|are) amended by striking"
        ),
    ),
    (
        "amend",
        re.compile(
            rf"^Sections?\s+(?P<refs>{_CODE_SEC})[^\n]*?Code\s+(?P<code_year>\d{{4}})"
            r"[^\n]*?(?:is|are) amended to read"
        ),
    ),
]

# An optional ALL-CAPS label ahead of a lead-in ("REPEAL.  Sections 2.69 and
# 3.20, Code 2024, are repealed."). Stripped before matching; kept as the
# heading fallback.
_CAPS_LABEL_RE = re.compile(r"^(?P<label>[A-Z][A-Z\d '’—-]{2,80}?)\.\s+(?=\S)")

_BOILERPLATE_RE = re.compile(
    r"^(?P<kind>EFFECTIVE DATE|RETROACTIVE APPLICABILITY|APPLICABILITY|"
    r"CODE EDITOR DIRECTIVE|TRANSITION)[S.\s—-]"
)

_CODE_SEC_FINDER = re.compile(_CODE_SEC)

# Signature/certification trailer — everything from the Speaker line on.
_TRAILER_RE = re.compile(
    r"\n\s*_{3,}[^\n]*\n|\n\s*(?:Speaker of the House|President of the Senate)\b"
)


@dataclass
class ActEdge:
    code_ref: str  # Iowa Code section ("2.69") the act section touches
    action: str  # new_section | repeal | amend | amend_add | amend_strike
    code_year: str | None  # the "Code 2024" edition named in the lead-in


@dataclass
class ParsedActSection:
    number: int
    heading: str  # NEW SECTION heading, boilerplate kind, or first code ref
    kind: str  # edge action, "boilerplate:<KIND>", or "other"
    body_text: str  # strike-resolved, lead-in included
    edges: list[ActEdge] = field(default_factory=list)


@dataclass
class ParsedAct:
    bill: str  # "HF2485" (whitespace stripped)
    title: str  # the RELATING TO … line
    sections: list[ParsedActSection] = field(default_factory=list)


def parse_enrolled_rtf(data: bytes) -> ParsedAct:
    runs = tokenize(data)
    text = resulting_text(runs)

    # Cut the signature trailer so it doesn't ride the last section's body.
    m = _TRAILER_RE.search(text)
    if m:
        text = text[: m.start()]

    bill = ""
    tm = _TITLE_RE.search(text)
    if tm:
        bill = re.sub(r"\s+", "", tm.group("bill"))

    # Title = first ALL-CAPS block before the enacting clause.
    title = ""
    enact = text.find("BE IT ENACTED")
    if enact != -1:
        head = text[:enact]
        title = " ".join(
            line.strip()
            for line in head.splitlines()
            if line.strip() and not _TITLE_RE.match(line)
        ).strip()

    # Act sections are strictly sequential (Section 1., Sec. 2., …). A head
    # whose number doesn't continue the sequence is quoted text, not a
    # boundary — joint resolutions embed a proposed constitutional
    # amendment whose own text begins "Section 1.", and amendatory bodies
    # can quote section heads too.
    heads = [
        h
        for h in _SECTION_HEAD_RE.finditer(text)
        if int(h.group("num")) < 10_000
    ]
    in_seq: list[re.Match] = []
    for h in heads:
        if int(h.group("num")) == len(in_seq) + 1:
            in_seq.append(h)

    sections: list[ParsedActSection] = []
    for i, h in enumerate(in_seq):
        start = h.end()
        end = in_seq[i + 1].start() if i + 1 < len(in_seq) else len(text)
        body = text[h.start() : end].strip()
        after_head = text[start:end].strip()
        sections.append(_classify(int(h.group("num")), after_head, body))
    return ParsedAct(bill=bill, title=title, sections=sections)


def _classify(number: int, after_head: str, body: str) -> ParsedActSection:
    bp = _BOILERPLATE_RE.match(after_head)
    if bp:
        kind = bp.group("kind")
        return ParsedActSection(
            number=number, heading=kind.title(), kind=f"boilerplate:{kind}", body_text=body
        )

    # "REPEAL.  Sections 2.69 and 3.20, Code 2024, are repealed." — the label
    # is presentation, the lead-in behind it is the signal. NEW SECTION is
    # itself a lead-in, so don't strip it.
    stripped = after_head
    label = _CAPS_LABEL_RE.match(after_head)
    if label and not after_head.startswith("NEW SECTION"):
        stripped = after_head[label.end() :]

    for action, pat in _LEADIN_PATTERNS:
        m = pat.match(after_head) or (label and pat.match(stripped))
        if not m:
            continue
        refs = (
            re.findall(r"\d+[A-Z]{0,2}", m.group("refs"))
            if action == "repeal_chapter"
            else _CODE_SEC_FINDER.findall(m.group("refs"))
        )
        code_year = m.groupdict().get("code_year")
        edges = [ActEdge(code_ref=r, action=action, code_year=code_year) for r in refs]
        heading = (
            m.group("heading").strip().rstrip(".")
            if action == "new_section"
            else refs[0]
            if refs
            else ""
        )
        return ParsedActSection(
            number=number, heading=heading, kind=action, body_text=body, edges=edges
        )

    return ParsedActSection(
        number=number,
        heading=after_head.split("\n", 1)[0][:120].strip(),
        kind="other",
        body_text=body,
    )
