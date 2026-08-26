"""Turn a photograph into strokes a hand could have drawn.

Canny is the obvious choice and the wrong one. It answers "where does brightness
change", which on a photograph means every texture, every shadow edge and every
compression artefact - and it answers in outlines, so a pen stroke one pixel
wide comes back as two lines with a gap between them. Traced faithfully that is
porridge: thousands of tiny fragments that read as noise at any size.

What a person draws is different, and this module builds it in three steps.

**XDoG** decides where the lines are. A difference of Gaussians finds the scale
at which structure lives and suppresses the rest, and the extended form pushes
the result to black or white with a soft threshold, which is exactly the
decision an artist makes: this edge is worth a line, that shading is not. It is
the standard way to get line art out of a photograph and it is thirty lines of
arithmetic.

**Thinning** reduces whatever survives to a single pixel of width, so a line is
a line rather than a filled ribbon.

**Skeleton tracing** then walks those pixels into polylines, breaking at
junctions. The result is one stroke per line - not one loop around each side of
it - which is why the retrace hack Canny needs has no equivalent here.
"""

from __future__ import annotations

import numpy as np

__all__ = ["xdog", "ridges", "thin", "trace_skeleton", "rank_strokes"]


#: Eight-neighbour offsets, diagonals last so a walk prefers straight steps.
_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


def _gaussian(image: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur, done by hand to keep the dependency list short."""
    radius = max(1, int(round(sigma * 3)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x ** 2) / (2 * sigma * sigma))
    kernel /= kernel.sum()

    padded = np.pad(image, ((0, 0), (radius, radius)), mode="edge")
    blurred = np.zeros_like(image, dtype=np.float32)
    for offset, weight in enumerate(kernel):
        blurred += weight * padded[:, offset:offset + image.shape[1]]

    padded = np.pad(blurred, ((radius, radius), (0, 0)), mode="edge")
    out = np.zeros_like(image, dtype=np.float32)
    for offset, weight in enumerate(kernel):
        out += weight * padded[offset:offset + image.shape[0], :]
    return out


def xdog(gray: np.ndarray, *, sigma: float = 1.0, k: float = 1.6, tau: float = 0.98,
         phi: float = 12.0, ink: float = 0.12, min_contrast: float = 0.006) -> np.ndarray:
    """Extended difference of Gaussians: a photograph in, line art out.

    Args:
        gray: Greyscale image, any numeric type; scaled internally to 0-1.
        sigma: The scale the lines are found at, in pixels. Larger ignores fine
            texture and keeps only big structure - the single most useful knob
            for the difference between a sketch and a scribble.
        k: Ratio between the two blurs. 1.6 approximates a Laplacian of
            Gaussian, which is the classical choice.
        tau: How much of the wider blur to subtract. Near 1 gives thin, sparse
            lines; lower fills in.
        phi: Sharpness of the soft threshold. High values give crisp black.
        ink: Roughly what fraction of the picture should end up as line, from 0
            to 1. The threshold is taken as that quantile of the response, so
            the same setting means the same density of drawing on a dark photo
            and a bright one - which a fixed threshold emphatically does not.
        min_contrast: The floor, in absolute response, under which nothing is a
            line whatever the quantile says. Without it a relative threshold
            always finds its quota: point it at a clear sky and it will
            confidently draw the sensor noise, which is most of what makes a
            traced photograph look like scribble.

    Returns:
        A boolean array, True where a line belongs.
    """
    image = gray.astype(np.float32)
    if image.max() > 1.0:
        image /= 255.0

    narrow = _gaussian(image, sigma)
    wide = _gaussian(image, sigma * k)
    difference = narrow - tau * wide

    ink = max(0.005, min(0.6, ink))

    # Hysteresis, and it is the whole difference between line art and dust. One
    # threshold cuts through the middle of every line that fades: the strong
    # parts survive, the weak parts vanish, and what is left is dashes. So take
    # a strict threshold for seeds, a lenient one for what may join them, and
    # keep only the lenient pixels that can be reached from a seed.
    strong = (difference <= np.quantile(difference, ink * 0.35)) & (difference <= -min_contrast)
    weak = (difference <= np.quantile(difference, ink)) & (difference <= -min_contrast * 0.5)
    return _hysteresis(strong, weak)


def _hysteresis(strong: np.ndarray, weak: np.ndarray, max_passes: int = 96) -> np.ndarray:
    """Grow *strong* through *weak* until it stops growing."""
    keep = strong & weak
    height, width = keep.shape
    for _ in range(max_passes):
        padded = np.pad(keep, 1)
        grown = keep.copy()
        for dy, dx in _OFFSETS:
            grown |= padded[1 + dy:height + 1 + dy, 1 + dx:width + 1 + dx]
        grown &= weak
        if np.array_equal(grown, keep):
            break
        keep = grown
    return keep


def thin(mask: np.ndarray, max_passes: int = 40) -> np.ndarray:
    """Zhang-Suen thinning: reduce a region to a one-pixel-wide skeleton.

    Two sub-iterations per pass, each deleting boundary pixels whose removal
    cannot break the shape apart. Vectorised over the whole image, so a pass
    costs a handful of array operations rather than a loop over pixels.
    """
    image = mask.astype(np.uint8).copy()

    def neighbours(padded):
        # P2..P9 clockwise from north, the naming the algorithm is written in.
        return (padded[:-2, 1:-1], padded[:-2, 2:], padded[1:-1, 2:], padded[2:, 2:],
                padded[2:, 1:-1], padded[2:, :-2], padded[1:-1, :-2], padded[:-2, :-2])

    for _ in range(max_passes):
        changed = False
        for step in (0, 1):
            padded = np.pad(image, 1)
            p2, p3, p4, p5, p6, p7, p8, p9 = neighbours(padded)

            total = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            sequence = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            transitions = sum(((sequence[i] == 0) & (sequence[i + 1] == 1)).astype(np.uint8)
                              for i in range(8))

            if step == 0:
                first = (p2 * p4 * p6) == 0
                second = (p4 * p6 * p8) == 0
            else:
                first = (p2 * p4 * p8) == 0
                second = (p2 * p6 * p8) == 0

            removable = (image == 1) & (total >= 2) & (total <= 6) & (transitions == 1) \
                & first & second
            if removable.any():
                image[removable] = 0
                changed = True
        if not changed:
            break

    return image.astype(bool)


def trace_skeleton(skeleton: np.ndarray, min_points: int = 4):
    """Walk a one-pixel skeleton into polylines, breaking at junctions.

    Starts from endpoints, which is what makes the strokes come out the length a
    person would draw them; whatever is left afterwards is closed loops, and
    those are walked from any remaining pixel.

    Returns:
        A list of paths, each a list of ``(x, y)`` in image coordinates.
    """
    height, width = skeleton.shape
    alive = skeleton.copy()

    padded = np.pad(alive, 1).astype(np.uint8)
    degree = np.zeros_like(alive, dtype=np.uint8)
    for dy, dx in _OFFSETS:
        degree += padded[1 + dy:height + 1 + dy, 1 + dx:width + 1 + dx]
    degree[~alive] = 0

    visited = np.zeros_like(alive)
    paths = []

    def walk(start):
        """Follow a line, carrying straight on through crossings.

        Stopping at every junction would be tidier to write and much worse to
        look at: a lattice tower is nothing but crossings, and breaking there
        turns one girder into thirty stubs. A hand draws the girder and lets the
        crossing look after itself, so the walk keeps whichever continuation
        best matches the direction it was already going.
        """
        y, x = start
        path = [(x, y)]
        visited[y, x] = True
        heading = None

        while True:
            options = []
            for dy, dx in _OFFSETS:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and alive[ny, nx] and not visited[ny, nx]:
                    options.append((dy, dx, ny, nx))
            if not options:
                break

            if heading is None or len(options) == 1:
                dy, dx, ny, nx = options[0]
            else:
                # Straightest continuation: the largest dot product with the
                # direction of travel.
                dy, dx, ny, nx = max(
                    options, key=lambda o: o[0] * heading[0] + o[1] * heading[1])

            heading = (dy, dx)
            y, x = ny, nx
            visited[y, x] = True
            path.append((x, y))
        return path

    endpoints = np.argwhere(alive & (degree == 1))
    for start in endpoints:
        if visited[start[0], start[1]]:
            continue
        path = walk(tuple(start))
        if len(path) >= min_points:
            paths.append(path)

    remaining = np.argwhere(alive & ~visited)
    for start in remaining:
        if visited[start[0], start[1]]:
            continue
        path = walk(tuple(start))
        if len(path) >= min_points:
            paths.append(path)

    return paths


def rank_strokes(paths, limit: int | None = None, min_points: int = 4):
    """Longest first, and optionally only the longest few.

    Readability is mostly about what gets left out. The long strokes carry the
    subject; the short ones are texture, and past a few hundred of them a
    drawing stops looking like anything. Drawing the important ones first also
    means an interrupted drawing still resembles the picture.
    """
    def length(path):
        return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(path, path[1:]))

    ordered = sorted((path for path in paths if len(path) >= min_points),
                     key=length, reverse=True)
    return ordered[:limit] if limit else ordered


def ridges(strength: np.ndarray, *, keep: float = 0.65, seed_keep: float = 0.30,
           floor: float = 0.05) -> np.ndarray:
    """Reduce a soft edge-strength map to the crest of each ridge.

    A network answers with wide, soft ridges rather than lines. Thresholding one
    directly gives a band, and thinning a band gives the outline of the band -
    little closed cells around every patch of texture, which is what a neural
    edge map looks like when it is used carelessly.

    So take the same step Canny takes: keep a pixel only where it is at least as
    strong as its two neighbours across the ridge, which leaves the crest one
    pixel wide, then hysteresis to join the confident parts to the plausible
    ones.

    Args:
        strength: Edge strength, roughly 0 to 1.
        keep: Fraction of the meaningful pixels to admit as line.
        seed_keep: The stricter fraction used to seed the hysteresis.
        floor: Values below this are background and take no part in the
            statistics; without it a mostly-empty map skews every quantile.
    """
    import cv2

    gx = cv2.Sobel(strength.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(strength.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    angle = (np.rad2deg(np.arctan2(gy, gx)) + 180) % 180

    height, width = strength.shape
    padded = np.pad(strength, 1, mode="edge")

    def neighbour(dy, dx):
        return padded[1 + dy:height + 1 + dy, 1 + dx:width + 1 + dx]

    crest = np.zeros_like(strength, dtype=bool)
    for low, high, (dy, dx) in ((0, 22.5, (0, 1)), (22.5, 67.5, (-1, 1)),
                                (67.5, 112.5, (-1, 0)), (112.5, 157.5, (-1, -1)),
                                (157.5, 180.0, (0, 1))):
        band = (angle >= low) & (angle < high)
        crest |= band & (strength >= neighbour(dy, dx)) & (strength >= neighbour(-dy, -dx))

    meaningful = strength[strength > floor]
    if meaningful.size == 0:
        return np.zeros_like(strength, dtype=bool)

    ridge = strength * crest
    weak = ridge >= np.quantile(meaningful, 1.0 - keep)
    strong = ridge >= np.quantile(meaningful, 1.0 - seed_keep)
    return _hysteresis(strong & crest, weak & crest)
