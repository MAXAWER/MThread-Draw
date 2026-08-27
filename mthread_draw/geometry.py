"""Pure coordinate maths shared by the canvas and the drawing thread.

Kept free of Tk so it can be unit tested without a display.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Sequence

__all__ = ["CanvasView", "Placement", "fit_to_screen", "place_on_screen", "place_paths"]


@dataclass(frozen=True)
class CanvasView:
    """The on-screen rectangle that stands in for the phone display.

    Attributes:
        origin: Canvas coordinates of the rectangle's top-left corner.
        size: Rectangle size in canvas pixels.
        screen: Real device resolution in pixels.
    """

    origin: tuple[float, float]
    size: tuple[float, float]
    screen: tuple[int, int]

    @property
    def ratio(self) -> tuple[float, float]:
        """Device pixels per canvas pixel, on each axis."""
        width, height = self.size
        if width <= 0 or height <= 0:
            raise ValueError("the phone rectangle has no area")
        return self.screen[0] / width, self.screen[1] / height

    def canvas_to_screen(self, x: float, y: float) -> tuple[float, float]:
        ratio_x, ratio_y = self.ratio
        return (x - self.origin[0]) * ratio_x, (y - self.origin[1]) * ratio_y

    def screen_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        ratio_x, ratio_y = self.ratio
        return self.origin[0] + x / ratio_x, self.origin[1] + y / ratio_y


def place_paths(
    paths: Sequence[Sequence[tuple[float, float]]],
    view: CanvasView,
    image_origin: tuple[float, float],
    image_scale: float,
    offset: tuple[float, float] = (0.0, 0.0),
    min_segment: float = 1.0,
) -> list[list[tuple[int, int]]]:
    """Convert preview-space paths into device pixel coordinates.

    Args:
        paths: Points in the coordinate space of the preview image.
        view: Where the phone rectangle sits on the canvas.
        image_origin: Canvas position of the preview image's top-left corner.
        image_scale: Zoom factor currently applied to the preview.
        offset: Manual calibration nudge, in device pixels.
        min_segment: Consecutive points closer than this (in device pixels) are
            collapsed, which trims redundant events without visible loss.
    """
    ratio_x, ratio_y = view.ratio
    base_x, base_y = view.canvas_to_screen(*image_origin)
    base_x += offset[0]
    base_y += offset[1]
    scale_x = image_scale * ratio_x
    scale_y = image_scale * ratio_y

    placed: list[list[tuple[int, int]]] = []
    for path in paths:
        points: list[tuple[int, int]] = []
        for x, y in path:
            point = (int(round(base_x + x * scale_x)), int(round(base_y + y * scale_y)))
            if points:
                previous = points[-1]
                if abs(point[0] - previous[0]) < min_segment and abs(point[1] - previous[1]) < min_segment:
                    continue
            points.append(point)
        if len(points) >= 2:
            placed.append(points)
    return placed


@dataclass(frozen=True)
class Placement:
    """Where a drawing goes on the screen, and how big and how tilted.

    Held in fractions of the screen rather than pixels so that it survives the
    phone being turned, and so the same numbers mean the same thing on a
    different device.

    Attributes:
        centre: Where the middle of the drawing lands, 0 to 1 across the screen.
        scale: Multiplier on the size it would have if fitted to the screen, so
            1.0 is "as large as it goes with a margin".
        rotation: Degrees clockwise.
    """

    centre: tuple[float, float] = (0.5, 0.5)
    scale: float = 1.0
    rotation: float = 0.0

    def moved(self, dx: float, dy: float) -> "Placement":
        return replace(self, centre=(self.centre[0] + dx, self.centre[1] + dy))

    def zoomed(self, factor: float, *, low: float = 0.05, high: float = 6.0) -> "Placement":
        return replace(self, scale=max(low, min(high, self.scale * factor)))

    def turned(self, degrees: float) -> "Placement":
        return replace(self, rotation=(self.rotation + degrees) % 360.0)


def place_on_screen(paths, width: int, height: int, placement: Placement,
                    *, margin: float = 0.06):
    """Put *paths* on a screen of *width* x *height* as *placement* says.

    The base size is the one :func:`fit_to_screen` would choose, so a scale of
    one means the same thing whatever the drawing and whatever the phone, and
    the slider a person turns is a multiplier on something recognisable.
    """
    points = [point for path in paths for point in path]
    if not points:
        return []

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    source_width = max(max_x - min_x, 1)
    source_height = max(max_y - min_y, 1)
    source_centre = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

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
            ox, oy = x - source_centre[0], y - source_centre[1]
            rx = ox * cos - oy * sin
            ry = ox * sin + oy * cos
            line.append((round(target_x + rx * scale), round(target_y + ry * scale)))
        placed.append(line)
    return placed


def fit_to_screen(paths, width: int, height: int, *, margin: float = 0.06):
    """Scale paths to fill the device screen, keeping shape and a clear margin.

    What the desktop app does by dragging, for callers that have no canvas to
    drag on - the JSON engine, the command line, a test.
    """
    points = [point for path in paths for point in path]
    if not points:
        return []

    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    source_width = max(max_x - min_x, 1)
    source_height = max(max_y - min_y, 1)

    pad_x, pad_y = width * margin, height * margin
    scale = min((width - 2 * pad_x) / source_width, (height - 2 * pad_y) / source_height)
    offset_x = pad_x + (width - 2 * pad_x - source_width * scale) / 2 - min_x * scale
    offset_y = pad_y + (height - 2 * pad_y - source_height * scale) / 2 - min_y * scale

    return [[(round(x * scale + offset_x), round(y * scale + offset_y)) for x, y in path]
            for path in paths]
