"""Case-caption shortening and practice-area tagging for data briefs.

CourtListener captions arrive in every register at once — "In The Interest Of
J.e., Minor Child, R.e., Mother Vs. State Of Iowa" — and a figure label has
room for "In re J.E.". The rules here were tuned against the actual top-50
most-cited Iowa cases (the fixture in tests/test_briefs_names.py pins all
fifty), so they are deliberately narrow: they normalise the caption shapes
that occur, and anything unrecognised passes through unchanged so a refresh
can never silently mangle a new case — it shows up verbatim in the JSON diff
and earns either a rule or an override.

Categories are editorial, not doctrinal: the three-way split exists because
the bubble-chart palette is validated for exactly three hues (see
DATA_BRIEFS.md, design standards).
"""

from __future__ import annotations

import re

# Explicit overrides, keyed by the exact caption. For captions the general
# rules would get wrong (reporter suffixes, full-name party strings, d/b/a
# tails). Extend this table — don't loosen the rules — when a refresh
# surfaces a new misfit.
OVERRIDES: dict[str, str] = {
    "Meier v. SENECAUT III": "Meier v. Senecaut",
    "Lynn G. Lamasters Vs. State of Iowa": "Lamasters v. State",
    (
        "Brenda J. Alcala v. Marriott International, Inc. and Courtyard "
        "Management Corporation D/B/A Quad Cities Courtyard by Marriott"
    ): "Alcala v. Marriott Int'l",
    # The mockup's table also carried a Castro entry; that case sits outside
    # the current top fifty, so the exact caption must be read off the corpus
    # when it next surfaces rather than guessed here.
}

# Generational suffixes stripped when reducing a party to a surname.
_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}

_INTEREST_RE = re.compile(r"^in\s+the\s+interests?\s+of\s+", re.IGNORECASE)
_IN_RE_RE = re.compile(r"^in\s+re\s+", re.IGNORECASE)
_MARRIAGE_RE = re.compile(r"^in\s+re\s+(?:the\s+)?marriage\s+of\s+", re.IGNORECASE)
_STATE_V_RE = re.compile(r"^state\s+of\s+iowa\s+vs?\.\s+", re.IGNORECASE)


def _surname(party: str) -> str:
    """Last word of a party name, minus generational suffixes."""
    words = [w for w in party.strip().rstrip(",").split() if w]
    while words and words[-1].lower().rstrip(",") in _SUFFIXES:
        words.pop()
    return words[-1] if words else party.strip()


def _first_party(text: str) -> str:
    """Text up to the first co-party separator ("and", "&", or a comma)."""
    for sep in (" and ", " & "):
        idx = text.lower().find(sep)
        if idx != -1:
            text = text[:idx]
    return text.split(",")[0].strip()


def shorten(caption: str) -> str:
    """Reduce a full case caption to its citable short form."""
    caption = " ".join(caption.split())
    if caption in OVERRIDES:
        return OVERRIDES[caption]

    m = _MARRIAGE_RE.match(caption)
    if m:
        rest = caption[m.end() :]
        # "… McDermott Upon the Petition of Rachel A. McDermott" — the
        # petition tail restates a party; drop it before picking the surname.
        rest = re.split(r"\s+upon\s+the\s+petition\s+of\s+", rest, flags=re.IGNORECASE)[0]
        return f"In re Marriage of {_surname(_first_party(rest))}"

    m = _INTEREST_RE.match(caption)
    if m:
        # The initials token: up to the first co-party ("A.B. & S.B.",
        # "M.W. and Z.W.") or descriptor comma. Source casing is unreliable
        # ("J.e.") so the initials are uppercased.
        return f"In re {_first_party(caption[m.end():]).upper()}"

    m = _IN_RE_RE.match(caption)
    if m:
        return f"In re {caption[m.end():].strip().upper()}"

    m = _STATE_V_RE.match(caption)
    if m:
        return f"State v. {_surname(caption[m.end():])}"

    return caption


# The three-hue editorial split. Family is tested before criminal because
# juvenile captions can end in "Vs. State Of Iowa" and still be family cases.
CATEGORIES = {
    "family": {"label": "Family & juvenile", "color": "#8a3ffc"},
    "criminal": {"label": "Criminal & postconviction", "color": "#1192e8"},
    "civil": {"label": "Civil & procedure", "color": "#ee5396"},
}


def categorize(caption: str) -> str:
    """family | criminal | civil, from the raw caption."""
    c = " ".join(caption.split()).lower()
    if c.startswith("in re ") or _INTEREST_RE.match(c):
        return "family"
    if re.match(r"^state(\s+of\s+iowa)?\s+vs?\.\s", c) or re.search(
        r"\bvs?\.\s+state(\s+of\s+iowa)?$", c
    ):
        return "criminal"
    return "civil"


# ---------------------------------------------------------------------------
# U.S. Supreme Court cases (figure 2)
# ---------------------------------------------------------------------------

# Federal citations in opinion text carry no case name, so display names,
# in-bubble labels, decision years, and doctrine categories live here, keyed
# by the official U.S. Reports cite. The export command FAILS if a top-ranked
# cite is missing from this table — a refresh that surfaces a new case is
# supposed to stop and make a human add the entry (the diff is the review).
SCOTUS_CATEGORIES = {
    "counsel": {"label": "Counsel, pleas & fair trial", "color": "#8a3ffc"},
    "police": {"label": "Police, search & interrogation", "color": "#1192e8"},
    "dueproc": {"label": "Due process, sentencing & civil", "color": "#ee5396"},
}

# (volume, page) -> (display name, in-bubble label, year, category)
SCOTUS_CASES: dict[tuple[int, int], tuple[str, str, int, str]] = {
    (466, 668): ("Strickland v. Washington", "Strickland", 1984, "counsel"),
    (384, 436): ("Miranda v. Arizona", "Miranda", 1966, "police"),
    (400, 25): ("North Carolina v. Alford", "Alford", 1970, "counsel"),
    (392, 1): ("Terry v. Ohio", "Terry", 1968, "police"),
    (373, 83): ("Brady v. Maryland", "Brady", 1963, "counsel"),
    (367, 643): ("Mapp v. Ohio", "Mapp", 1961, "police"),
    (412, 218): ("Schneckloth v. Bustamonte", "Schneckloth", 1973, "police"),
    (408, 471): ("Morrissey v. Brewer", "Morrissey", 1972, "dueproc"),
    (560, 48): ("Graham v. Florida", "Graham", 2010, "dueproc"),
    (418, 539): ("Wolff v. McDonnell", "Wolff", 1974, "dueproc"),
    (424, 319): ("Mathews v. Eldridge", "Mathews", 1976, "dueproc"),
    (371, 471): ("Wong Sun v. United States", "Wong Sun", 1963, "police"),
    (304, 458): ("Johnson v. Zerbst", "Zerbst", 1938, "counsel"),
    (372, 335): ("Gideon v. Wainwright", "Gideon", 1963, "counsel"),
    (389, 347): ("Katz v. United States", "Katz", 1967, "police"),
    (397, 358): ("In re Winship", "In re Winship", 1970, "dueproc"),
    (284, 299): ("Blockburger v. United States", "Blockburger", 1932, "counsel"),
    (543, 551): ("Roper v. Simmons", "Roper", 2005, "dueproc"),
    (395, 238): ("Boykin v. Alabama", "Boykin", 1969, "counsel"),
    (386, 18): ("Chapman v. California", "Chapman", 1967, "counsel"),
    (422, 806): ("Faretta v. California", "Faretta", 1975, "counsel"),
    (476, 79): ("Batson v. Kentucky", "Batson", 1986, "counsel"),
    (474, 52): ("Hill v. Lockhart", "Hill v. Lockhart", 1985, "counsel"),
    (407, 514): ("Barker v. Wingo", "Barker", 1972, "counsel"),
    (541, 36): ("Crawford v. Washington", "Crawford", 2004, "counsel"),
    (567, 460): ("Miller v. Alabama", "Miller", 2012, "dueproc"),
    (403, 443): ("Coolidge v. New Hampshire", "Coolidge", 1971, "police"),
    (384, 757): ("Schmerber v. California", "Schmerber", 1966, "police"),
    (411, 792): ("McDonnell Douglas Corp. v. Green", "McDonnell Douglas", 1973, "dueproc"),
    (517, 806): ("Whren v. United States", "Whren", 1996, "police"),
}

# A bare official cite at the start of the reference text, tolerating a
# trailing pincite (", 687") or parallel-cite tail. "Id. at 687"-style
# references never match — by design, they were already counted at the
# opinion's first full cite (and if not, undercounting is the documented
# conservative direction).
US_CITE_RE = re.compile(r"^(\d{1,3}) U\.S\. (\d{1,4})($|[,\s])")


def parse_us_cite(external_text: str) -> tuple[int, int] | None:
    """(volume, page) from a raw external reference, or None."""
    m = US_CITE_RE.match(external_text.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))
