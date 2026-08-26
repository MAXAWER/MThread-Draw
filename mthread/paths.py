"""Tidy up the polylines an edge detector produces, before anything draws them.

``findContours`` does not return strokes, it returns fragments. A single line in
a picture comes back as a handful of pieces that happen to end where the next
one begins, plus a scattering of two-point specks from noise. Drawing that
faithfully is both slower and worse-looking than it needs to be: every fragment
costs a pen lift, and every speck costs a full press-move-release for a mark
nobody can see.

Joining the fragments back into strokes is the one change that improves speed
and quality at the same time.
"""

from __future__ import annotations

import math

__all__ = ["join_strokes", "drop_specks", "simplify", "stroke_length", "tidy"]


def stroke_length(path) -> float:
    """Total length along a polyline, in pixels."""
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def drop_specks(paths, min_length: float = 8.0, min_points: int = 2):
    """Throw away fragments too small to be worth a pen stroke.

    A two-point speck four pixels long is invisible in the result but costs the
    same press, move and release as a real line - and on a device without raw
    touch access, that is a tenth of a second each.
    """
    return [path for path in paths
            if len(path) >= min_points and stroke_length(path) >= min_length]


def join_strokes(paths, tolerance: float = 6.0):
    """Reconnect fragments whose ends meet, into longer strokes.

    Greedy and endpoint-only: take a fragment, then keep attaching whichever
    unused fragment starts (or ends, in which case it is reversed) within
    *tolerance* of where the current one stopped. That is enough to put a
    contour back together, because the fragments really do share endpoints -
    they were split by the tracer, not by the picture.

    Args:
        tolerance: How far apart two ends can be and still be treated as the
            same point. A pixel or two covers rounding; much more starts joining
            lines that were genuinely separate.
    """
    fragments = [list(path) for path in paths if len(path) >= 2]
    if not fragments:
        return []

    used = [False] * len(fragments)
    joined = []

    for index, fragment in enumerate(fragments):
        if used[index]:
            continue
        used[index] = True
        current = fragment

        extended = True
        while extended:
            extended = False
            tail = current[-1]
            for other, candidate in enumerate(fragments):
                if used[other]:
                    continue
                if math.dist(tail, candidate[0]) <= tolerance:
                    current = current + candidate[1:]
                elif math.dist(tail, candidate[-1]) <= tolerance:
                    current = current + list(reversed(candidate))[1:]
                else:
                    continue
                used[other] = True
                extended = True
                break

        joined.append(current)

    return joined


def tidy(paths, *, join_tolerance: float = 6.0, min_length: float = 8.0):
    """Join what belongs together, then drop what is left over and too small.

    In that order: a speck sitting between two fragments is worth keeping if it
    joins them into one stroke, and only worth dropping once it turns out to be
    on its own.
    """
    if join_tolerance > 0:
        paths = join_strokes(paths, join_tolerance)
    if min_length > 0:
        paths = drop_specks(paths, min_length)
    return paths


def simplify(path, epsilon: float = 1.2):
    """Douglas-Peucker: drop points that were on the line anyway.

    A skeleton is one point per pixel, which is far more than a stroke needs -
    and on a device every point costs time. Keeping only the points that carry
    the shape typically removes four fifths of them and changes nothing visible.
    """
    if len(path) < 3 or epsilon <= 0:
        return list(path)

    keep = [False] * len(path)
    keep[0] = keep[-1] = True
    stack = [(0, len(path) - 1)]

    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = path[start], path[end]
        dx, dy = x2 - x1, y2 - y1
        span = math.hypot(dx, dy)

        worst, worst_index = 0.0, None
        for index in range(start + 1, end):
            x, y = path[index]
            if span < 1e-9:
                distance = math.hypot(x - x1, y - y1)
            else:
                distance = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / span
            if distance > worst:
                worst, worst_index = distance, index

        if worst_index is not None and worst > epsilon:
            keep[worst_index] = True
            stack.append((start, worst_index))
            stack.append((worst_index, end))

    return [point for point, kept in zip(path, keep) if kept]
