"""Circle packing + in-bubble label fitting for data-brief figures.

Pure geometry, no Django. Ported from the brief 001 mockup pipeline; the
constants are load-bearing design decisions (see DATA_BRIEFS_PLAN.md §1c) —
change them and the published figures change.

Coordinate system: viewBox pixels, origin top-left, (cx, cy) circle centers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Gap between neighbouring bubble rims, in viewBox px, before fit-scaling.
# The design spec's hard minimum is 2px; packing at 3 leaves headroom so the
# fit-scale never takes a gap below spec.
PAD = 3.0
# Viewbox inset the packed cloud is scaled into.
MARGIN = 10.0
# Candidate positions are tried every 2 degrees around each placed circle.
STEP_DEG = 2
# IBM Plex Sans 600: mean glyph advance ≈ 0.55em (names).
ADV_SANS = 0.55
# IBM Plex Mono 400: fixed advance 0.6em (count line).
ADV_MONO = 0.6
# Label lines sit on a grid of 1.12em centred on the bubble centre.
LINE_STEP = 1.12
# Count line font-size relative to the name line.
COUNT_FS = 0.74
# Horizontal slack between a text line's end and the bubble rim.
CHORD_INSET = 4.0
FS_MIN = 10.5
FS_STEP = 0.75


@dataclass
class Bubble:
    """One mark: sized by ``weight``, positioned by :func:`pack`."""

    key: str            # stable identifier (rank as str is fine)
    weight: float       # cites — area is proportional to this
    name: str           # short display name (label candidate)
    count_text: str     # preformatted count, e.g. "1,502"
    label_name: str | None = None  # explicit in-bubble label (SCOTUS surnames)
    x: float = 0.0
    y: float = 0.0
    r: float = 0.0
    label: list[str] = field(default_factory=list)
    fs: float = 0.0
    count_label: bool = False


def pack(bubbles: list[Bubble], width: float, height: float, fill: float) -> None:
    """Position ``bubbles`` (mutating x/y/r) inside ``width``×``height``.

    Greedy tangent placement: circles in descending weight order; each new
    circle tries candidate positions every STEP_DEG degrees around every
    placed circle at tangent distance + PAD, and takes the valid position
    closest to the centre under an ellipse-weighted norm (so the cloud
    matches the viewBox aspect instead of coming out round).
    """
    if not bubbles:
        return
    order = sorted(bubbles, key=lambda b: (-b.weight, b.key))
    # Radii from the fill ratio: sum(pi r^2) = fill * W * H.
    k = math.sqrt(fill * width * height / (math.pi * sum(b.weight for b in order)))
    for b in order:
        b.r = k * math.sqrt(b.weight)

    aspect = width / height
    placed: list[Bubble] = []
    for b in order:
        if not placed:
            b.x, b.y = 0.0, 0.0
            placed.append(b)
            continue
        best = None
        best_norm = math.inf
        for anchor in placed:
            d = anchor.r + b.r + PAD
            for deg in range(0, 360, STEP_DEG):
                a = math.radians(deg)
                x = anchor.x + d * math.cos(a)
                y = anchor.y + d * math.sin(a)
                # tiny epsilon: the anchor's own tangent distance is exact,
                # so float noise must not invalidate it
                if any(
                    math.hypot(x - p.x, y - p.y) < p.r + b.r + PAD - 1e-9
                    for p in placed
                ):
                    continue
                norm = (x / aspect) ** 2 + y**2
                if norm < best_norm:
                    best_norm = norm
                    best = (x, y)
        assert best is not None  # a far-enough tangent point always exists
        b.x, b.y = best
        placed.append(b)

    _fit(bubbles, width, height)


def _fit(bubbles: list[Bubble], width: float, height: float) -> None:
    """Uniformly scale + translate the cloud into the viewBox with MARGIN."""
    x0 = min(b.x - b.r for b in bubbles)
    x1 = max(b.x + b.r for b in bubbles)
    y0 = min(b.y - b.r for b in bubbles)
    y1 = max(b.y + b.r for b in bubbles)
    s = min((width - 2 * MARGIN) / (x1 - x0), (height - 2 * MARGIN) / (y1 - y0), 1.0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for b in bubbles:
        b.x = (b.x - cx) * s + width / 2
        b.y = (b.y - cy) * s + height / 2
        b.r *= s


def check_invariants(bubbles: list[Bubble], width: float, height: float) -> None:
    """Raise AssertionError unless the layout honours the design spec."""
    for i, a in enumerate(bubbles):
        assert a.r > 0
        assert a.x - a.r >= MARGIN - 1e-6 and a.x + a.r <= width - MARGIN + 1e-6
        assert a.y - a.r >= MARGIN - 1e-6 and a.y + a.r <= height - MARGIN + 1e-6
        for b in bubbles[i + 1 :]:
            gap = math.hypot(a.x - b.x, a.y - b.y) - a.r - b.r
            assert gap >= 2.0 - 1e-6, f"gap {gap:.2f}px between {a.key} and {b.key}"


# ---------------------------------------------------------------------------
# Label fitting
# ---------------------------------------------------------------------------


def _half_width(text: str, fs: float, adv: float) -> float:
    return 0.5 * len(text) * adv * fs


def _chord(r: float, dy: float) -> float:
    """Half-chord of the circle at vertical offset dy, minus the inset."""
    if abs(dy) >= r:
        return 0.0
    return math.sqrt(r * r - dy * dy) - CHORD_INSET


def _lines_fit(lines: list[tuple[str, float, float]], r: float, fs: float) -> bool:
    """lines: (text, fs, advance). Positions come from the 1.12em grid."""
    n = len(lines)
    for i, (text, line_fs, adv) in enumerate(lines):
        dy = (i - (n - 1) / 2) * LINE_STEP * fs
        if _half_width(text, line_fs, adv) > _chord(r, dy):
            return False
    return True


def _wrap2(name: str) -> list[str] | None:
    """Balanced two-line wrap: the space split minimising the longer line."""
    words = name.split(" ")
    if len(words) < 2:
        return None
    best = None
    best_w = math.inf
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        w = max(len(a), len(b))
        if w < best_w:
            best_w = w
            best = [a, b]
    return best


def fit_label(b: Bubble, fs_max: float) -> None:
    """Choose label lines + font size for one bubble (mutates it).

    Tries, at each size from clamp(0.27·r) down in 0.75 steps: the name on
    one line with the count beneath, then wrapped over two lines with the
    count; then — last resort — the unwrapped name alone (no count, no
    wrap: a wrapped count-less label was judged too busy for a small
    bubble). Bubbles that fit nothing stay unlabeled — the tooltip and the
    table carry them (selective labels are the spec, not a bug).
    """
    name = b.label_name or b.name
    # "In re Marriage of X" may drop the "In re" inside the bubble only.
    if name.startswith("In re Marriage of "):
        name = name[len("In re ") :]

    fs0 = min(max(0.27 * b.r, FS_MIN), fs_max)
    candidates = [[name]]
    wrapped = _wrap2(name)
    if wrapped:
        candidates.append(wrapped)

    for with_count, cands in ((True, candidates), (False, [[name]])):
        fs = fs0
        while fs >= FS_MIN - 1e-9:
            for cand in cands:
                lines = [(t, fs, ADV_SANS) for t in cand]
                if with_count:
                    lines = lines + [(b.count_text, COUNT_FS * fs, ADV_MONO)]
                if _lines_fit(lines, b.r, fs):
                    b.label = cand
                    b.fs = round(fs, 2)
                    b.count_label = with_count
                    return
            fs -= FS_STEP
    b.label = []
    b.fs = 0.0
    b.count_label = False
