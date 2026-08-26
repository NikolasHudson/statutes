"""Packing + label-fitting invariants — DB-free, pure geometry.

The weights below are the real citation counts behind figure 1 of brief 001,
so the invariant tests exercise the exact size distribution the published
chart carries. The pinned label cases are taken from the approved mockup:
they encode wrap decisions ("State v. / Sanford" but "State / v. Lyle") that
came out of design review, not chance.
"""

from __future__ import annotations

import math

from django.test import SimpleTestCase

from apps.marketing.briefs.packing import (
    MARGIN,
    Bubble,
    check_invariants,
    fit_label,
    pack,
)

# Figure 1's actual citing-opinion counts, rank 1..50.
FIG1_CITES = [
    1502, 1325, 1234, 1124, 1120, 1049, 805, 733, 680, 645,
    596, 591, 480, 473, 396, 394, 380, 372, 361, 349,
    332, 331, 326, 322, 315, 296, 288, 283, 282, 279,
    272, 269, 267, 263, 261, 260, 251, 247, 246, 246,
    240, 239, 238, 238, 237, 237, 229, 226, 224, 223,
]

W, H, FILL = 1000, 660, 0.54


def _packed():
    bubbles = [
        Bubble(key=str(i + 1), weight=c, name=f"Case {i + 1}", count_text=f"{c:,}")
        for i, c in enumerate(FIG1_CITES)
    ]
    pack(bubbles, W, H, FILL)
    return bubbles


class PackInvariantTests(SimpleTestCase):
    def test_no_overlap_min_gap(self):
        # Independent of check_invariants: every pair keeps the 2px design
        # minimum between rims.
        bubbles = _packed()
        for i, a in enumerate(bubbles):
            for b in bubbles[i + 1 :]:
                gap = math.hypot(a.x - b.x, a.y - b.y) - a.r - b.r
                self.assertGreaterEqual(gap, 2.0 - 1e-6, f"{a.key}/{b.key}")

    def test_in_bounds_with_margin(self):
        for b in _packed():
            self.assertGreaterEqual(b.x - b.r, MARGIN - 1e-6)
            self.assertGreaterEqual(b.y - b.r, MARGIN - 1e-6)
            self.assertLessEqual(b.x + b.r, W - MARGIN + 1e-6)
            self.assertLessEqual(b.y + b.r, H - MARGIN + 1e-6)

    def test_deterministic(self):
        # Re-running the export against unchanged data must yield an empty
        # git diff, so the layout may not depend on iteration chance.
        a, b = _packed(), _packed()
        for x, y in zip(a, b):
            self.assertEqual((x.x, x.y, x.r), (y.x, y.y, y.r))

    def test_area_proportional_to_weight(self):
        bubbles = _packed()
        k = bubbles[0].r**2 / bubbles[0].weight
        for b in bubbles:
            self.assertAlmostEqual(b.r**2 / b.weight, k, places=6)

    def test_own_checker_agrees(self):
        check_invariants(_packed(), W, H)

    def test_empty_and_single(self):
        pack([], W, H, FILL)  # no crash
        one = [Bubble(key="1", weight=100, name="Only", count_text="100")]
        pack(one, W, H, FILL)
        check_invariants(one, W, H)


def _fit(name, r, count, fs_max=19.0, label_name=None):
    b = Bubble(key="t", weight=1, name=name, count_text=count, label_name=label_name)
    b.r = r
    fit_label(b, fs_max)
    return b


class FitLabelTests(SimpleTestCase):
    """Each case pins a bubble from the approved mockup at its real radius."""

    def test_big_bubble_single_line(self):
        b = _fit("In re P.L.", 85.06, "1,502")
        self.assertEqual(b.label, ["In re P.L."])
        self.assertEqual(b.fs, 19.0)
        self.assertTrue(b.count_label)

    def test_balanced_wrap_prefers_shorter_max_line(self):
        # "State v. Sanford" splits after "v." (max line 8 beats 10)…
        self.assertEqual(_fit("State v. Sanford", 39.38, "322").label, ["State v.", "Sanford"])
        # …while "State v. Lyle" splits before it (max line 7 beats 8).
        self.assertEqual(_fit("State v. Lyle", 34.49, "247").label, ["State", "v. Lyle"])

    def test_marriage_drops_in_re_inside_bubble_only(self):
        b = _fit("In re Marriage of Winter", 43.67, "396")
        self.assertEqual(b.label, ["Marriage", "of Winter"])

    def test_too_small_stays_unlabeled(self):
        # Rank 27 of the real figure: neither wrapped-with-count nor the
        # single-line fallback fits — tooltip and table carry it.
        b = _fit("In re Marriage of Frederici", 37.24, "288")
        self.assertEqual(b.label, [])
        self.assertFalse(b.count_label)

    def test_explicit_label_name_wins(self):
        b = _fit("Strickland v. Washington", 165.66, "1,250", fs_max=20.0, label_name="Strickland")
        self.assertEqual(b.label, ["Strickland"])
        self.assertEqual(b.fs, 20.0)

    def test_count_line_present_on_all_labeled(self):
        # The design never shows a name without its count unless nothing
        # else fits; at these mockup radii the count always made it.
        for name, r, count in (
            ("In re P.L.", 85.06, "1,502"),
            ("State v. Sanford", 39.38, "322"),
            ("In re D.S.", 32.77, "223"),
        ):
            b = _fit(name, r, count)
            self.assertTrue(b.count_label, name)
