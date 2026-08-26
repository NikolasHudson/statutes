"""Caption shortening + categorisation — DB-free, table-driven.

The big table is the actual top fifty most-cited Iowa cases (captions as
they appear in the corpus). It exists so a rules change that would alter any
published short name fails loudly here first — the fifty are on a public
page, so this table is effectively a regression contract with the site.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.marketing.briefs.names import categorize, parse_us_cite, shorten

# (full caption, expected short name, expected category)
TOP_FIFTY = [
    ("In Re P.L.", "In re P.L.", "family"),
    ("In The Interest Of D.W., Minor Child, A.M.W., Mother", "In re D.W.", "family"),
    ("Meier v. SENECAUT III", "Meier v. Senecaut", "civil"),
    ("In the Interest of C.B.", "In re C.B.", "family"),
    ("In the Interest of A.M., Minor Child, A.M., Father", "In re A.M.", "family"),
    ("In the Interest of A.B. & S.B., Minor Children, S.B., Father", "In re A.B.", "family"),
    ("In The Interest Of J.e., Minor Child, R.e., Mother Vs. State Of Iowa", "In re J.E.", "family"),
    ("State v. Formaro", "State v. Formaro", "criminal"),
    ("In the Interest of M.W. and Z.W., Minor Children, R.W., Mother", "In re M.W.", "family"),
    ("Ledezma v. State", "Ledezma v. State", "criminal"),
    ("State v. Straw", "State v. Straw", "criminal"),
    ("In Re the Marriage of Hansen", "In re Marriage of Hansen", "family"),
    ("Lynn G. Lamasters Vs. State of Iowa", "Lamasters v. State", "criminal"),
    ("State of Iowa v. Allen Bradley Clay", "State v. Clay", "criminal"),
    ("In Re the Marriage of Winter", "In re Marriage of Winter", "family"),
    ("In RE the Marriage of Rachel A. McDermott and Stephen J. McDermott Upon the Petition of Rachel A. McDermott", "In re Marriage of McDermott", "family"),
    ("In the Interest of H.S. And S.N., Minor Children, V.R., Mother", "In re H.S.", "family"),
    ("State v. Maxwell", "State v. Maxwell", "criminal"),
    ("State v. Graves", "State v. Graves", "criminal"),
    ("In the Interest of J.S. & N.S., Minor Children, A.S., Mother", "In re J.S.", "family"),
    ("State v. Bruegger", "State v. Bruegger", "criminal"),
    ("In Re the Marriage of Sullins", "In re Marriage of Sullins", "family"),
    ("In Re the Marriage of Okland", "In re Marriage of Okland", "family"),
    ("State of Iowa v. Dontay Dakwon Sanford", "State v. Sanford", "criminal"),
    ("Brenda J. Alcala v. Marriott International, Inc. and Courtyard Management Corporation D/B/A Quad Cities Courtyard by Marriott", "Alcala v. Marriott Int'l", "civil"),
    ("Hyler v. Garner", "Hyler v. Garner", "civil"),
    ("In Re the Marriage of Frederici", "In re Marriage of Frederici", "family"),
    ("In the Interest of L.T., A.T., and D.T., Minor Children", "In re L.T.", "family"),
    ("In the Interest of T.S. and K.G., Minor Children, L.G., Mother, K.G., Father of K.G.", "In re T.S.", "family"),
    ("In the Interest of S.R.", "In re S.R.", "family"),
    ("In the Interest of C.K.", "In re C.K.", "family"),
    ("In the Interests of A.C.", "In re A.C.", "family"),
    ("In the Interest of C.H.", "In re C.H.", "family"),
    ("In the Interest of A.A.G.", "In re A.A.G.", "family"),
    ("DeVoss v. State", "DeVoss v. State", "criminal"),
    ("In the Interest of L.L.", "In re L.L.", "family"),
    ("State v. Shanahan", "State v. Shanahan", "criminal"),
    ("State v. Lyle", "State v. Lyle", "criminal"),
    ("State of Iowa v. Randall Lee Pals", "State v. Pals", "criminal"),
    ("State v. Carroll", "State v. Carroll", "criminal"),
    ("State of Iowa v. Craig Anthony Finney", "State v. Finney", "criminal"),
    ("State of Iowa v. Kelvin Plain Sr.", "State v. Plain", "criminal"),
    ("State v. Turner", "State v. Turner", "criminal"),
    ("In Re Marriage of Fennelly & Breckenfelder", "In re Marriage of Fennelly", "family"),
    ("In Re the Marriage of Vrban", "In re Marriage of Vrban", "family"),
    ("State of Iowa v. Donald James Hill", "State v. Hill", "criminal"),
    ("State v. Ellis", "State v. Ellis", "criminal"),
    ("State v. Fountain", "State v. Fountain", "criminal"),
    ("State v. Johnson", "State v. Johnson", "criminal"),
    ("In the Interest of D.S.", "In re D.S.", "family"),
]


class ShortenTableTests(SimpleTestCase):
    def test_top_fifty(self):
        for full, short, _cat in TOP_FIFTY:
            self.assertEqual(shorten(full), short, full)

    def test_unrecognised_captions_pass_through(self):
        # The safety property: no rule may silently mangle a shape it does
        # not understand — new shapes surface verbatim in the JSON diff.
        for caption in (
            "Estate of Representative Payee Gray v. Somewhere",
            "City of Des Moines v. Ames",
            "Iowa Supreme Court Attorney Disciplinary Board v. Example",
        ):
            self.assertEqual(shorten(caption), caption)

    def test_suffix_stripping(self):
        self.assertEqual(shorten("State of Iowa v. Kelvin Plain Sr."), "State v. Plain")
        self.assertEqual(
            shorten("State of Iowa vs. John Example Jr."), "State v. Example"
        )


class CategorizeTableTests(SimpleTestCase):
    def test_top_fifty(self):
        for full, _short, cat in TOP_FIFTY:
            self.assertEqual(categorize(full), cat, full)

    def test_juvenile_appeal_against_state_is_family(self):
        # "In The Interest Of J.e. ... Vs. State Of Iowa" must not be
        # classified criminal just because the State is a party.
        self.assertEqual(
            categorize("In The Interest Of J.e., Minor Child Vs. State Of Iowa"),
            "family",
        )


class ParseUsCiteTests(SimpleTestCase):
    def _check(self, text, expected):
        self.assertEqual(parse_us_cite(text), expected, text)

    def test_table(self):
        self._check("466 U.S. 668", (466, 668))
        self._check("466 U.S. 668, 687", (466, 668))       # pincite normalised
        self._check("466 U.S. 668, 104 S. Ct. 2052", (466, 668))
        self._check("392 U.S. 1 (1968)", (392, 1))
        self._check("Strickland, 466 U.S. at 687", None)   # at-cite: counted once already
        self._check("466 U.S. at 687", None)
        self._check("104 S. Ct. 2052", None)               # parallel reporter only
        self._check("Iowa Code section 232.116", None)
        self._check("", None)
