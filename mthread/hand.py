"""Make a machine-drawn path look like something a hand did.

A traced image gives away its origin immediately, and not because the lines are
wrong. They are too right: every point sits exactly on the geometry, corners are
mathematically sharp, points are evenly spaced, every stroke starts precisely
where the line begins and stops precisely where it ends, and the strokes arrive
in whatever order the contour finder happened to produce.

A hand does none of that:

- **It rounds corners.** Wrist and finger joints cannot turn a corner in zero
  time; the pen cuts it.
- **It speeds up and slows down.** Slow leaving the paper, fast through the
  middle of a long line, slow again into a tight curve and at the end. On a
  device where every point costs the same amount of time to send, that velocity
  profile *is* the spacing between points - so it can be reproduced simply by
  putting points closer together where the pen would have been slow.
- **It wobbles**, in a slow drift rather than per-point static, with a much
  smaller tremor on top.
- **It overshoots and undershoots.** Strokes start a fraction late and end a
  fraction long, and shapes do not close exactly.
- **It draws in a sensible order**, moving to whatever is nearest rather than
  jumping across the page and back.

:func:`simulate` does all of it, driven by one ``amount`` dial, so callers do
not have to understand any of the above to use it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

__all__ = ["HandSettings", "simulate", "reorder_strokes"]

Point = tuple[float, float]
Path = list[Point]


@dataclass(frozen=True)
class HandSettings:
    """Every knob :func:`simulate` has, in the units it thinks in.

    The defaults describe a steady hand drawing on a phone-sized screen. Scaling
    them all together is what ``amount`` does; reach for the individual fields
    when one aspect specifically is wrong.

    Attributes:
        spacing: Target distance between sent points, in pixels, at full speed.
            Smaller is smoother and slower - and on devices without raw touch
            access, points are the entire cost of a drawing.
        tremor: Amplitude of the slow wobble along a stroke, in pixels.
        micro: Amplitude of the per-point noise, in pixels.
        smoothing: Corner rounding, 0 to 1.
        corner_radius: The most, in pixels, a corner is allowed to be cut by.
        ease: How much slower the pen is at the ends of a stroke than in the
            middle. 0 is a constant speed.
        curvature_drag: How much a tight curve slows the pen down.
        overshoot: How far, in pixels, a stroke runs past its end.
        entry_gap: How far, in pixels, a stroke starts short of its beginning.
        reorder: Draw strokes nearest-first instead of in contour order.
        max_points: Hard ceiling per stroke, so a pathological path cannot turn
            into thousands of touch events.
    """

    spacing: float = 18.0
    tremor: float = 1.1
    micro: float = 0.35
    smoothing: float = 0.6
    corner_radius: float = 11.0
    ease: float = 0.65
    curvature_drag: float = 0.7
    overshoot: float = 2.5
    entry_gap: float = 1.5
    reorder: bool = True
    max_points: int = 220

    def scaled(self, amount: float) -> "HandSettings":
        """Turn the single ``amount`` dial into a full set of settings.

        Not everything scales the same way. Wobble and overshoot scale linearly
        with how unsteady the hand is; spacing tightens only a little, because
        halving it doubles what the drawing costs; smoothing and easing saturate,
        since a hand can only round a corner so far.
        """
        return replace(
            self,
            spacing=max(6.0, self.spacing / (1 + 0.25 * amount)),
            tremor=self.tremor * amount,
            micro=self.micro * amount,
            smoothing=min(1.0, self.smoothing * (0.6 + 0.4 * amount)),
            corner_radius=self.corner_radius * (0.7 + 0.3 * amount),
            ease=min(0.9, self.ease * (0.6 + 0.4 * amount)),
            overshoot=self.overshoot * amount,
            entry_gap=self.entry_gap * amount,
        )


# --------------------------------------------------------------------- helpers


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _chaikin(points: Path, strength: float, radius: float) -> Path:
    """Round the corners off a polyline.

    One Chaikin pass replaces every corner with the two points a quarter and
    three quarters along its arms, which is the cheapest convincing way to say
    "a pen went round this rather than through it". *strength* interpolates
    between the original corner and the rounded one, so the effect is dialable.
    """
    if len(points) < 3 or strength <= 0:
        return list(points)

    # The cut ratio is the dial. At 0 the new points sit on the old corners and
    # nothing changes; at 0.25 this is textbook Chaikin. Blending the result
    # back against the input instead would need the two polylines matched point
    # for point, and matching them by index skews the shape wherever the
    # segments are uneven - which is every traced contour.
    ratio = 0.25 * min(strength, 1.0)

    out: Path = [points[0]]
    for first, second in zip(points, points[1:]):
        # Cap the cut in pixels as well as in proportion. A wrist rounds a
        # corner over a centimetre or so whatever the lines meeting there are
        # like; a purely proportional cut chamfers a long edge into a hexagon.
        length = _distance(first, second) or 1.0
        t = min(ratio, radius / length)
        out.append((first[0] + (second[0] - first[0]) * t,
                    first[1] + (second[1] - first[1]) * t))
        out.append((first[0] + (second[0] - first[0]) * (1 - t),
                    first[1] + (second[1] - first[1]) * (1 - t)))
    out.append(points[-1])
    return out


def _curvature(points: Path) -> list[float]:
    """Per-vertex turn, from 0 (straight on) to 1 (doubling back)."""
    values = [0.0] * len(points)
    for index in range(1, len(points) - 1):
        before, here, after = points[index - 1], points[index], points[index + 1]
        ax, ay = here[0] - before[0], here[1] - before[1]
        bx, by = after[0] - here[0], after[1] - here[1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-6 or lb < 1e-6:
            continue
        cosine = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        values[index] = math.acos(cosine) / math.pi
    return values


def _resample(points: Path, settings: HandSettings) -> Path:
    """Walk the polyline, placing points closer together where a pen is slower.

    This is the velocity profile. Every point sent to the device costs the same
    time, so the spacing between them is exactly how fast the pen appears to be
    moving: dense at the ends and through corners, sparse along a long straight.
    """
    if len(points) < 2:
        return list(points)

    segments = [_distance(a, b) for a, b in zip(points, points[1:])]
    total = sum(segments)
    if total < 1e-6:
        return [points[0], points[-1]]

    curvature = _curvature(points)
    cumulative = [0.0]
    for length in segments:
        cumulative.append(cumulative[-1] + length)

    def at(distance: float) -> tuple[Point, float]:
        """Point at *distance* along the polyline, and the local curvature."""
        index = 0
        while index < len(segments) - 1 and cumulative[index + 1] < distance:
            index += 1
        span = segments[index] or 1e-6
        t = max(0.0, min(1.0, (distance - cumulative[index]) / span))
        a, b = points[index], points[index + 1]
        turn = max(curvature[index], curvature[min(index + 1, len(curvature) - 1)])
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), turn

    out: Path = []
    travelled = 0.0
    while travelled < total and len(out) < settings.max_points:
        point, turn = at(travelled)
        out.append(point)

        # Slow near both ends of the stroke, and through tight curves.
        u = travelled / total
        envelope = 1.0 - settings.ease * (1.0 - max(0.0, math.sin(math.pi * u)) ** 0.7)
        drag = 1.0 / (1.0 + settings.curvature_drag * turn * 6.0)
        step = settings.spacing * max(0.15, envelope * drag)
        travelled += max(step, 1.0)

    out.append(points[-1])
    return out


def _tremor(points: Path, settings: HandSettings, rng: random.Random) -> Path:
    """A slow drift along the stroke, plus a little static on top.

    Independent per-point noise looks like a bad scan, not like a hand. The slow
    component is what reads as muscle, so it carries most of the amplitude.
    """
    if settings.tremor <= 0 and settings.micro <= 0:
        return points

    phase_x, phase_y = rng.uniform(0, math.tau), rng.uniform(0, math.tau)
    freq_x = rng.uniform(0.10, 0.30)
    freq_y = rng.uniform(0.10, 0.30)
    amplitude = settings.tremor * rng.uniform(0.7, 1.3)

    out: Path = []
    for index, (x, y) in enumerate(points):
        out.append((
            x + math.sin(phase_x + index * freq_x) * amplitude + rng.gauss(0, settings.micro),
            y + math.cos(phase_y + index * freq_y) * amplitude + rng.gauss(0, settings.micro),
        ))
    return out


def _ends(points: Path, settings: HandSettings, rng: random.Random) -> Path:
    """Start a fraction late and finish a fraction long.

    A pen touches down after the line has notionally begun and lifts after it
    has ended, which is why hand-drawn shapes never quite close and hand-drawn
    corners always have a little tail.
    """
    if len(points) < 2:
        return points

    out = list(points)

    if settings.entry_gap > 0:
        (x1, y1), (x2, y2) = out[0], out[1]
        length = _distance((x1, y1), (x2, y2)) or 1.0
        gap = min(rng.uniform(0.2, 1.0) * settings.entry_gap, length * 0.4)
        out[0] = (x1 + (x2 - x1) / length * gap, y1 + (y2 - y1) / length * gap)

    if settings.overshoot > 0:
        (x1, y1), (x2, y2) = out[-2], out[-1]
        length = _distance((x1, y1), (x2, y2)) or 1.0
        extra = rng.uniform(0.3, 1.0) * settings.overshoot
        out.append((x2 + (x2 - x1) / length * extra, y2 + (y2 - y1) / length * extra))

    return out


def reorder_strokes(paths, start: Point = (0.0, 0.0)):
    """Put the strokes in the order a person would draw them.

    Nearest-neighbour from wherever the pen last was, and a stroke is reversed
    when its far end is the closer one - nobody lifts the pen, crosses the page
    and comes back to start a line they were already standing on. It also means
    the pauses between strokes can follow the distance travelled.
    """
    remaining = [list(path) for path in paths if len(path) >= 2]
    ordered = []
    pen = start

    while remaining:
        best_index, best_cost, best_flip = 0, float("inf"), False
        for index, path in enumerate(remaining):
            head = _distance(pen, path[0])
            tail = _distance(pen, path[-1])
            if head <= tail:
                cost, flip = head, False
            else:
                cost, flip = tail, True
            if cost < best_cost:
                best_index, best_cost, best_flip = index, cost, flip

        path = remaining.pop(best_index)
        if best_flip:
            path.reverse()
        ordered.append(path)
        pen = path[-1]

    return ordered


def simulate(paths, amount: float = 1.0, seed: int | None = None,
             settings: HandSettings | None = None):
    """Redraw *paths* the way a hand would have.

    Args:
        amount: 0 returns the paths untouched. 1.0 is a steady hand; 2 to 3 is
            a careless one. Everything scales from here.
        seed: Fixes the randomness, so the same picture can be drawn twice.
        settings: Full control, when the single dial is not enough. ``amount``
            still scales whatever is passed.

    Returns:
        A new list of paths. Point counts change - that is the velocity profile
        - so callers that care about cost should re-estimate afterwards.
    """
    if amount <= 0:
        return paths

    rng = random.Random(seed)
    config = (settings or HandSettings()).scaled(amount)

    ordered = reorder_strokes(paths) if config.reorder else [list(p) for p in paths if len(p) >= 2]

    out = []
    for path in ordered:
        shaped = _chaikin(path, config.smoothing, config.corner_radius)
        shaped = _resample(shaped, config)
        shaped = _tremor(shaped, config, rng)
        shaped = _ends(shaped, config, rng)
        if len(shaped) >= 2:
            out.append(shaped)
    return out
