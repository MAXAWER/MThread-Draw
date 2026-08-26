"""Turning a raster image into stroke paths a device can draw."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .paths import tidy

__all__ = ["VectorizeSettings", "Vectorizer", "dedupe_retrace"]


def dedupe_retrace(contour: np.ndarray, *, max_width: float = 6.0, samples: int = 9) -> np.ndarray:
    """Collapse a contour that traces both sides of the same thin stroke.

    ``cv2.findContours`` walks the *boundary* of a region. A pen stroke has no
    meaningful interior, so Canny turns it into a pair of parallel edges and the
    boundary runs up one side and back down the other. Sending that to the device
    draws every line twice: once forwards, once a pixel or two away in reverse.

    The test is geometric rather than area-based. For each of a few sample points
    in the first half of the contour we measure the distance to the nearest point
    in the second half. If every sample has a close partner the two halves are
    the same stroke, and the first half alone reproduces it. A genuine closed
    outline - a circle, a filled shape - has its halves on opposite sides and is
    returned untouched.

    Args:
        max_width: Strokes thinner than this many pixels are treated as retraced.
            Six covers the one to three pixel lines that line art produces; a
            genuinely thick bar is a filled region and keeps its full outline.
        samples: How many probe points to take; more is slower but stricter.
    """
    count = len(contour)
    if count < 6:
        return contour

    points = contour.reshape(-1, 2).astype(np.float32)
    split = count // 2
    first, second = points[:split], points[split:]
    if len(first) < 2 or len(second) < 2:
        return contour

    probes = first[np.linspace(0, len(first) - 1, min(samples, len(first))).astype(int)]
    # Distance from each probe to its nearest neighbour on the return path.
    gaps = np.sqrt(((probes[:, None, :] - second[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    if gaps.max() <= max_width:
        return contour[: split + 1]
    return contour


@dataclass
class VectorizeSettings:
    """Knobs for :meth:`Vectorizer.process`.

    Attributes:
        target_width: Downscale wide images to this width before edge detection.
        low_threshold / high_threshold: Canny hysteresis bounds.
        epsilon: Douglas-Peucker tolerance; larger means fewer, coarser points.
        min_points: Contours shorter than this are discarded as speckle.
        join_tolerance: Fragments whose ends are this close are joined into one
            stroke. findContours returns pieces, not strokes, and every extra
            piece costs a pen lift.
        min_length: Strokes shorter than this many pixels are dropped, being
            invisible in the result and not free to draw.
        remove_background: Use ``rembg`` if it is installed.
    """

    target_width: int | None = 1000
    low_threshold: int = 50
    high_threshold: int = 150
    epsilon: float = 1.0
    min_points: int = 5
    join_tolerance: float = 6.0
    min_length: float = 10.0
    remove_background: bool = False

    @classmethod
    def from_sliders(cls, sensitivity: float, detail: float, **kwargs) -> "VectorizeSettings":
        """Build settings from the two 1-10 sliders the GUI exposes."""
        return cls(
            low_threshold=int(20 + (sensitivity - 1) * 10),
            high_threshold=int(60 + (sensitivity - 1) * 15),
            epsilon=0.5 + (10 - detail) * 0.5,
            **kwargs,
        )


class Vectorizer:
    """Loads an image and converts it into a list of polyline paths."""

    def __init__(self):
        self.original_image: np.ndarray | None = None
        self.edges: np.ndarray | None = None
        self.paths: list[list[tuple[int, int]]] = []

    def load_image(self, path: str) -> np.ndarray:
        """Read an image from disk into BGR form."""
        image = cv2.imread(path)
        if image is None:
            raise ValueError(f"Could not read an image from {path!r}")
        self.original_image = image
        return image

    def load_array(self, image: np.ndarray) -> np.ndarray:
        self.original_image = image
        return image

    # ---------------------------------------------------------------- pipeline

    def _remove_background(self, image: np.ndarray) -> np.ndarray:
        try:
            from rembg import remove
        except ImportError:
            return image
        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        cut = remove(pil)
        if cut.mode != "RGBA":
            return image
        canvas = Image.new("RGB", cut.size, (255, 255, 255))
        canvas.paste(cut, mask=cut.split()[3])
        return cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _detect_edges(image: np.ndarray, low: int, high: int) -> np.ndarray:
        """Canny edges, using OpenCL when the platform offers it."""
        try:
            gpu = cv2.UMat(image)
            gray = cv2.cvtColor(gpu, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            return cv2.Canny(blurred, low, high).get()
        except cv2.error:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            return cv2.Canny(blurred, low, high)

    def process(self, settings: VectorizeSettings | None = None):
        """Run the pipeline and return ``(preview_image, paths)``.

        The preview is a white-on-black-free PIL image suitable for display; the
        paths are lists of ``(x, y)`` points in the coordinate space of that
        preview, which the caller then positions on the device screen.
        """
        settings = settings or VectorizeSettings()
        if self.original_image is None:
            return None, []

        image = self.original_image.copy()
        if settings.remove_background:
            image = self._remove_background(image)

        height, width = image.shape[:2]
        if settings.target_width and settings.target_width < width:
            scale = settings.target_width / width
            image = cv2.resize(
                image, (settings.target_width, int(height * scale)), interpolation=cv2.INTER_AREA
            )

        self.edges = self._detect_edges(image, settings.low_threshold, settings.high_threshold)
        contours, _ = cv2.findContours(self.edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        self.paths = []
        for contour in contours:
            if len(contour) < settings.min_points:
                continue
            trimmed = dedupe_retrace(contour)
            approx = cv2.approxPolyDP(trimmed, settings.epsilon, False)
            points = [(int(point[0][0]), int(point[0][1])) for point in approx]
            if len(points) >= 2:
                self.paths.append(points)

        self.paths = tidy(self.paths, join_tolerance=settings.join_tolerance,
                          min_length=settings.min_length)

        preview = np.full((*self.edges.shape, 3), 255, dtype=np.uint8)
        for path in self.paths:
            cv2.polylines(preview, [np.array(path, dtype=np.int32)], False, (0, 0, 0), 1)
        return Image.fromarray(preview), self.paths

    @property
    def point_count(self) -> int:
        return sum(len(path) for path in self.paths)
