"""Pure coordinate maths shared by the canvas and the drawing thread.

Kept free of Tk so it can be unit tested without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Placement moved into the library, placing a drawing being part of drawing
# it rather than part of any one interface. Re-exported so callers that
# already import it from here keep working.
from mthread.placement import Placement, fit_to_screen, place_on_screen

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
