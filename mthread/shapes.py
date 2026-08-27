"""Drawings that need no photograph: shapes from equations, text from a font.

    heart()          a heart
    star(points=5)   a star with as many points as you like
    text("hello")    words, in whatever font the machine has

The shapes are parametric curves evaluated straight into points, which is why
they come out smooth at any size and cost nothing to produce.

Text is different, and deliberately so: rather than carry a stroke font around,
it renders the words with Pillow and hands the result to the ordinary tracer.
The advantage is that every font on the machine is available and the result
looks like that font; the cost is that letters come out as outlines, because
that is what a filled glyph is - a shape with an inside and an outside, and this
program draws with one finger.

All of them return paths in a 0..1 square, so the caller places them on a screen
the same way it places a traced photograph.
"""

from __future__ import annotations

import math

__all__ = ["SHAPES", "circle", "heart", "polygon", "spiral", "square", "star", "text", "wave"]


def _closed(points):
    """Repeat the first point at the end, so a shape's outline joins up."""
    return list(points) + [points[0]]


def _fit(paths):
    """Scale paths into the unit square, keeping their proportions."""
    everything = [point for path in paths for point in path]
    min_x = min(x for x, _ in everything)
    max_x = max(x for x, _ in everything)
    min_y = min(y for _, y in everything)
    max_y = max(y for _, y in everything)
    span = max(max_x - min_x, max_y - min_y, 1e-9)
    dx = (1.0 - (max_x - min_x) / span) / 2.0
    dy = (1.0 - (max_y - min_y) / span) / 2.0
    return [[((x - min_x) / span + dx, (y - min_y) / span + dy) for x, y in path]
            for path in paths]


def heart(samples: int = 220):
    """The usual parametric heart, upright and centred."""
    points = []
    for index in range(samples):
        t = index / samples * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        # Negated because a screen's y runs downwards, and a heart that points
        # the wrong way is not a heart.
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t)
              - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((x, y))
    return _fit([_closed(points)])


def star(points: int = 5, inner: float = 0.42, samples_per_edge: int = 6):
    """A star of *points* points; *inner* is how deep the notches cut."""
    if points < 2:
        raise ValueError("a star needs at least two points")
    corners = []
    for index in range(points * 2):
        angle = index * math.pi / points - math.pi / 2
        radius = 1.0 if index % 2 == 0 else inner
        corners.append((radius * math.cos(angle), radius * math.sin(angle)))

    # Corners alone would be enough for a straight-edged shape, but a few points
    # along each edge keep the pacing even when the drawing is timed like a hand.
    line = []
    for first, second in zip(corners, corners[1:] + corners[:1]):
        for step in range(samples_per_edge):
            fraction = step / samples_per_edge
            line.append((first[0] + (second[0] - first[0]) * fraction,
                         first[1] + (second[1] - first[1]) * fraction))
    return _fit([_closed(line)])


def circle(samples: int = 160):
    return _fit([_closed([(math.cos(index / samples * 2 * math.pi),
                           math.sin(index / samples * 2 * math.pi))
                          for index in range(samples)])])


def square():
    return _fit([_closed([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])])


def polygon(sides: int = 6):
    if sides < 3:
        raise ValueError("a polygon needs at least three sides")
    return _fit([_closed([(math.cos(index / sides * 2 * math.pi - math.pi / 2),
                           math.sin(index / sides * 2 * math.pi - math.pi / 2))
                          for index in range(sides)])])


def spiral(turns: float = 3.0, samples: int = 400):
    points = []
    for index in range(samples + 1):
        fraction = index / samples
        angle = fraction * turns * 2 * math.pi
        radius = fraction
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return _fit([points])


def wave(cycles: float = 3.0, samples: int = 240):
    # The x span is the number of cycles rather than one, so three cycles come
    # out as a wave rather than as a narrow zigzag: _fit normalises by whichever
    # side is longer, and with x fixed at one that side was always the height.
    return _fit([[(index / samples * cycles, 0.35 * math.sin(index / samples * cycles * 2 * math.pi))
                  for index in range(samples + 1)]])


def text(words: str, *, font: str | None = None, size: int = 220,
         sensitivity: float = 6.0, detail: float = 8.0):
    """Trace *words* into paths, using a real font.

    Rendering and then tracing rather than carrying a stroke font: every font on
    the machine becomes available, and the letters look like that font. Letters
    arrive as outlines, an unavoidable consequence of a filled glyph being a
    shape with an inside and an outside while this program draws with one finger.

    Args:
        font: A font file, or a name Pillow can find. Falls back to whatever the
            platform offers, and finally to Pillow's own bitmap font.
        size: Pixel height to render at. Larger costs tracing time and buys
            smoother letters; it does not change the final size, which the
            caller chooses when placing the paths.
    """
    from PIL import Image, ImageDraw, ImageFont

    from .vectorize import VectorizeSettings, Vectorizer

    if not words:
        raise ValueError("there is nothing to draw")

    candidates = [font] if font else []
    candidates += ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Helvetica.ttc"]
    face = None
    for name in candidates:
        if not name:
            continue
        try:
            face = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if face is None:
        face = ImageFont.load_default()

    # Measured before drawing, because a glyph may reach above and to the left
    # of its own origin and would be clipped by a canvas sized after the fact.
    scratch = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = scratch.textbbox((0, 0), words, font=face)
    pad = max(8, size // 10)
    canvas = Image.new("L", (right - left + pad * 2, bottom - top + pad * 2), 255)
    ImageDraw.Draw(canvas).text((pad - left, pad - top), words, font=face, fill=0)

    settings = VectorizeSettings.from_sliders(sensitivity, detail,
                                              target_width=None, method="canny")
    vectorizer = Vectorizer()
    vectorizer.load_array(_as_bgr(canvas))
    _, paths = vectorizer.process(settings)
    if not paths:
        raise ValueError("the text traced to nothing; try a larger size")
    return _fit(paths)


def _as_bgr(grey):
    """A greyscale PIL image as the BGR array the vectoriser expects."""
    import numpy as np

    array = np.asarray(grey.convert("RGB"))
    return array[:, :, ::-1].copy()


#: The ones the command line offers by name, so `mthread shape --help` can list
#: them without the caller knowing the module.
SHAPES = {
    "heart": heart,
    "star": star,
    "circle": circle,
    "square": square,
    "polygon": polygon,
    "spiral": spiral,
    "wave": wave,
}
