"""Coherent line drawing: filter along the lines, not across the pixels.

Canny and XDoG both decide about each pixel on its own. A line, though, is not
a property of a pixel - it is a property of a direction being repeated by the
neighbours. That is why per-pixel methods break a long edge into dashes as soon
as its contrast dips, and why they answer a photograph with thousands of
fragments: they have no way to prefer a continuation.

This module builds the missing structure first, then filters with it, following
Kang, Lee and Chui's flow-based approach:

1. **Edge tangent flow.** Start from the gradient, take the perpendicular, and
   smooth that vector field while letting strong edges dominate weak ones. The
   result is a direction at every pixel that says "the line here runs this way",
   and it stays coherent across the gaps where contrast fails.

2. **Difference of Gaussians across the flow.** Sample perpendicular to the
   line, where an edge is a sharp step, rather than in the fixed x and y a
   convolution would use.

3. **Blur the response along the flow.** A pixel whose neighbours *in the
   direction of the line* also look like a line gets reinforced; a pixel whose
   response is an accident of noise has nothing agreeing with it and fades.

Step three is what turns an edge map into a drawing: it is the machinery that
lets a faint but genuine contour survive while confident noise does not.
"""

from __future__ import annotations

import numpy as np

__all__ = ["edge_tangent_flow", "coherent_lines"]


def _sobel(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    padded = np.pad(image, 1, mode="edge")
    kernel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    kernel_y = kernel_x.T

    gx = np.zeros_like(image, dtype=np.float32)
    gy = np.zeros_like(image, dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            window = padded[dy:dy + image.shape[0], dx:dx + image.shape[1]]
            gx += kernel_x[dy, dx] * window
            gy += kernel_y[dy, dx] * window
    return gx, gy


def _sample(image: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Bilinear sample of *image* at floating point coordinates, clamped."""
    height, width = image.shape
    xs = np.clip(xs, 0, width - 1.001)
    ys = np.clip(ys, 0, height - 1.001)

    x0 = xs.astype(np.int32)
    y0 = ys.astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    fx = xs - x0
    fy = ys - y0

    return (image[y0, x0] * (1 - fx) * (1 - fy)
            + image[y0, x1] * fx * (1 - fy)
            + image[y1, x0] * (1 - fx) * fy
            + image[y1, x1] * fx * fy)


def edge_tangent_flow(gray: np.ndarray, radius: int = 4, iterations: int = 3,
                      eta: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """The direction each line runs in, at every pixel.

    Smoothing a vector field is not the same as smoothing an image: two
    tangents pointing opposite ways describe the same line, so one has to be
    flipped before they are added or they cancel. Strong edges are also allowed
    to impose their direction on weak neighbours, which is what carries a
    contour across the places it fades.

    Returns:
        ``(tx, ty)``, a unit vector per pixel, pointing along the line.
    """
    image = gray.astype(np.float32)
    if image.max() > 1.0:
        image /= 255.0

    gx, gy = _sobel(image)
    magnitude = np.hypot(gx, gy)
    if magnitude.max() > 0:
        magnitude /= magnitude.max()

    # Perpendicular to the gradient is along the edge.
    tx, ty = -gy, gx
    norm = np.hypot(tx, ty)
    norm[norm == 0] = 1.0
    tx, ty = tx / norm, ty / norm

    height, width = image.shape
    offsets = [(dy, dx)
               for dy in range(-radius, radius + 1)
               for dx in range(-radius, radius + 1)
               if dy * dy + dx * dx <= radius * radius]

    for _ in range(iterations):
        new_x = np.zeros_like(tx)
        new_y = np.zeros_like(ty)

        for dy, dx in offsets:
            shifted_tx = np.roll(np.roll(tx, dy, axis=0), dx, axis=1)
            shifted_ty = np.roll(np.roll(ty, dy, axis=0), dx, axis=1)
            shifted_mag = np.roll(np.roll(magnitude, dy, axis=0), dx, axis=1)

            # A stronger neighbour counts for more than a weaker one.
            weight_magnitude = (1.0 + np.tanh(eta * (shifted_mag - magnitude))) * 0.5
            dot = tx * shifted_tx + ty * shifted_ty
            weight_direction = np.abs(dot)
            sign = np.where(dot < 0, -1.0, 1.0)

            weight = weight_magnitude * weight_direction * sign
            new_x += weight * shifted_tx
            new_y += weight * shifted_ty

        norm = np.hypot(new_x, new_y)
        norm[norm == 0] = 1.0
        tx, ty = new_x / norm, new_y / norm

    return tx, ty


def coherent_lines(gray: np.ndarray, *, sigma_c: float = 1.0, sigma_m: float = 3.0,
                   rho: float = 0.99, ink: float = 0.10, passes: int = 1,
                   flow_radius: int = 3, flow_iterations: int = 2,
                   min_contrast: float = 0.0015, flow=None) -> np.ndarray:
    """A photograph in, coherent line art out.

    Args:
        sigma_c: Width of the difference of Gaussians measured across the line.
            Small keeps fine detail; large draws only the big shapes.
        sigma_m: How far along the line the response is reinforced. This is the
            coherence knob and the reason the output looks drawn rather than
            detected - raise it for longer, calmer lines.
        rho: How much of the wider Gaussian is subtracted, near 1 for thin lines.
        ink: Roughly what fraction of the picture becomes line. The threshold is
            that quantile of the filtered response, so one setting means one
            density of drawing whatever the photograph's exposure.
        passes: Re-running the filter on its own output sharpens the lines and
            closes small gaps. Two is usually enough; three is slower and
            occasionally better.
        flow_radius: Neighbourhood the tangent field is smoothed over.
        flow_iterations: How many times to smooth it.
        min_contrast: Absolute floor. Without one, a relative threshold always
            finds its quota and will happily draw the noise in a clear sky.
        flow: A tangent field from :func:`edge_tangent_flow`, when one has
            already been built. It depends only on the image, never on the
            settings, and it is most of the cost - so anything moving a slider
            should compute it once and pass it back in.

    Returns:
        A boolean array, True where a line belongs.
    """
    image = gray.astype(np.float32)
    if image.max() > 1.0:
        image /= 255.0

    tx, ty = flow if flow is not None else edge_tangent_flow(
        image, radius=flow_radius, iterations=flow_iterations)
    # Across the line is perpendicular to along it.
    nx, ny = ty, -tx

    height, width = image.shape
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                 np.arange(height, dtype=np.float32))

    span_c = max(1, int(np.ceil(sigma_c * 2 * 1.6)))
    steps_c = np.arange(-span_c, span_c + 1, dtype=np.float32)
    weights_narrow = np.exp(-(steps_c ** 2) / (2 * sigma_c ** 2))
    weights_narrow /= weights_narrow.sum()
    sigma_s = sigma_c * 1.6
    weights_wide = np.exp(-(steps_c ** 2) / (2 * sigma_s ** 2))
    weights_wide /= weights_wide.sum()

    # Walking the flow is the expensive part - every step is a bilinear sample
    # of the whole image - so take a fixed number of them and stride out to
    # cover sigma_m. Eight samples describe a Gaussian well enough, and the
    # cost then stops depending on how long the lines are asked to be.
    span_m = max(1.0, sigma_m * 2)
    samples = 8
    stride = span_m / samples
    steps_m = np.arange(samples + 1, dtype=np.float32) * stride
    weights_flow = np.exp(-(steps_m ** 2) / (2 * sigma_m ** 2))
    weights_flow /= weights_flow.sum() * 2

    source = image
    for _ in range(max(1, passes)):
        # 1. Difference of Gaussians, sampled across the line.
        narrow = np.zeros_like(source)
        wide = np.zeros_like(source)
        for step, w_narrow, w_wide in zip(steps_c, weights_narrow, weights_wide):
            values = _sample(source, grid_x + nx * step, grid_y + ny * step)
            narrow += w_narrow * values
            wide += w_wide * values
        response = narrow - rho * wide

        # 2. Reinforce along the line, by walking the flow field in both
        #    directions rather than in a straight line - the flow curves, and
        #    following the curve is the entire point.
        accumulated = np.zeros_like(response)
        for direction in (1.0, -1.0):
            x = grid_x.copy()
            y = grid_y.copy()
            for index, weight in enumerate(weights_flow):
                accumulated += weight * _sample(response, x, y)
                # Follow the curve rather than a straight line: the flow bends,
                # and bending with it is the whole reason this is not a blur.
                x = x + direction * stride * _sample(tx, x, y)
                y = y + direction * stride * _sample(ty, x, y)

        filtered = accumulated
        # 3. Threshold: a quantile, so one setting means one density of drawing
        #    whatever the exposure, floored in absolute contrast so that a flat
        #    sky stays blank instead of being filled to meet the quota.
        cut = float(np.quantile(filtered, max(0.005, min(0.6, ink))))
        edges = (filtered <= cut) & (filtered <= -min_contrast)

        # Feed the drawing back in for the next pass: black where a line was
        # found, so the next round sharpens what is already there.
        source = np.where(edges, 0.0, source)

    return edges
