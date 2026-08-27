"""Where a drawing goes on a screen, and how big, how tilted, which way round.

Held in fractions of the screen and in degrees rather than in pixels, for three
reasons: it survives the phone being turned, it means the same thing on a
different device, and a scale of one can mean something recognisable - "as large
as it goes with a margin" - rather than a pixel count nobody can picture.

This lives in the library rather than in the desktop app because placing a
drawing is part of drawing it. The command line places shapes and text with the
same code the window places a photograph with.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

__all__ = ["Placement", "fit_to_screen", "place_on_screen"]


@dataclass(frozen=True)
class Placement:
    """Attributes:

    centre: Where the middle of the drawing lands, 0 to 1 across the screen.
    scale: Multiplier on the size it would have if fitted, so 1.0 is as large
        as it goes with a margin.
    rotation: Degrees clockwise.
    flip_x: Mirror left to right.
    flip_y: Mirror top to bottom.
    """

    centre: tuple[float, float] = (0.5, 0.5)
    scale: float = 1.0
    rotation: float = 0.0
    flip_x: bool = False
    flip_y: bool = False

    def moved(self, dx: float, dy: float) -> "Placement":
        return replace(self, centre=(self.centre[0] + dx, self.centre[1] + dy))

    def zoomed(self, factor: float, *, low: float = 0.05, high: float = 6.0) -> "Placement":
        return replace(self, scale=max(low, min(high, self.scale * factor)))

    def turned(self, degrees: float) -> "Placement":
        return replace(self, rotation=(self.rotation + degrees) % 360.0)

    def mirrored(self, *, horizontal: bool = False, vertical: bool = False) -> "Placement":
        return replace(self,
                       flip_x=self.flip_x != horizontal,
                       flip_y=self.flip_y != vertical)


def place_on_screen(paths, width: int, height: int,
                    placement: Placement | None = None, *, margin: float = 0.06):
    """Put *paths* on a screen of *width* x *height* as *placement* says.

    The base size is the one :func:`fit_to_screen` would choose, so a scale of
    one means the same thing whatever the drawing and whatever the phone.
    """
    placement = placement or Placement()
    points = [point for path in paths for point in path]
    if not points:
        return []

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    source_width = max(max_x - min_x, 1e-9)
    source_height = max(max_y - min_y, 1e-9)
    source_centre = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

    mirror_x = -1.0 if placement.flip_x else 1.0
    mirror_y = -1.0 if placement.flip_y else 1.0

    # Rotation happens about the drawing's own middle, so turning it does not
    # also throw it across the screen.
    angle = math.radians(placement.rotation)
    cos, sin = math.cos(angle), math.sin(angle)

    # Fit the rotated bounding box, not the upright one; a drawing turned
    # forty-five degrees needs more room than it did before, and without this it
    # would quietly grow past the edges of the screen.
    turned_width = abs(source_width * cos) + abs(source_height * sin)
    turned_height = abs(source_width * sin) + abs(source_height * cos)

    pad_x, pad_y = width * margin, height * margin
    base = min((width - 2 * pad_x) / turned_width, (height - 2 * pad_y) / turned_height)
    scale = base * placement.scale

    target_x = placement.centre[0] * width
    target_y = placement.centre[1] * height

    placed = []
    for path in paths:
        line = []
        for x, y in path:
            ox = (x - source_centre[0]) * mirror_x
            oy = (y - source_centre[1]) * mirror_y
            rx = ox * cos - oy * sin
            ry = ox * sin + oy * cos
            line.append((round(target_x + rx * scale), round(target_y + ry * scale)))
        placed.append(line)
    return placed


def fit_to_screen(paths, width: int, height: int, *, margin: float = 0.06):
    """Scale paths to fill the screen, keeping shape and a clear margin.

    The special case of :func:`place_on_screen` with nothing moved, kept as its
    own name because callers that have no interest in placement read better
    saying what they mean.
    """
    return place_on_screen(paths, width, height, Placement(), margin=margin)
