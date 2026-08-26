"""Render the repository banner: a drawing assembling itself out of touch points.

The white circles are not decoration. Every one of them is a point this program
sends to the device, in the order it sends them, taken from a real
:class:`mthread.Vectorizer` run over `examples/guitar.jpg`. The line follows
behind because that is what the finger leaves.

    python tools/make_banner.py            # -> docs/banner.gif
    python tools/make_banner.py --still     # -> docs/banner.png as well

Everything is drawn at three times the size and scaled down; a one-pixel circle
drawn straight into the final image is a lump, not a circle.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mthread.vectorize import VectorizeSettings, Vectorizer

WIDTH, HEIGHT = 1280, 460
SUPERSAMPLE = 3

BACK = (12, 13, 17)
WHITE = (255, 255, 255)
DIM = (150, 154, 166)
FAINT = (34, 36, 44)

FRAMES = 56
HOLD = 16
FRAME_MS = 70

#: How many of the most recently placed points still show as a bright head.
COMET = 46

TEXT_BOX = (78, 0, 430, HEIGHT)
ART_BOX = (600, 44, 600, 340)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else (
        "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def trace(path: str, method: str = "flow"):
    settings = VectorizeSettings.from_sliders(5.0, 8.0, target_width=900, method=method)
    vectorizer = Vectorizer()
    vectorizer.load_image(path)
    _, paths = vectorizer.process(settings)
    return paths


def fit(paths, box):
    """Scale and centre the ink into *box* = (x, y, w, h)."""
    points = [point for path in paths for point in path]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    scale = min(box[2] / max(max_x - min_x, 1), box[3] / max(max_y - min_y, 1))
    dx = box[0] + (box[2] - (max_x - min_x) * scale) / 2 - min_x * scale
    dy = box[1] + (box[3] - (max_y - min_y) * scale) / 2 - min_y * scale
    return [[(x * scale + dx, y * scale + dy) for x, y in path] for path in paths]


def backdrop() -> Image.Image:
    """The part that never moves: the ground, the ambient rings, the wordmark."""
    big = Image.new("RGB", (WIDTH * SUPERSAMPLE, HEIGHT * SUPERSAMPLE), BACK)
    draw = ImageDraw.Draw(big)
    scale = SUPERSAMPLE

    # Ambient circles: soft filled discs, not hairline rings. A ring at this
    # weight reads as a scratch on the picture; a disc reads as a circle, which
    # is the whole motif.
    discs = [(150, 372, 128, 9), (1146, 92, 168, 8), (392, 74, 58, 12),
             (1042, 406, 96, 7), (268, 172, 30, 16), (556, 402, 44, 10),
             (1226, 262, 74, 9), (56, 96, 22, 14)]
    for cx, cy, radius, level in discs:
        draw.ellipse([((cx - radius) * scale, (cy - radius) * scale),
                      ((cx + radius) * scale, (cy + radius) * scale)],
                     fill=(BACK[0] + level, BACK[1] + level, BACK[2] + level))

    # Two outlined rings, for the bit of structure the discs alone do not give.
    for cx, cy, radius in ((196, 318, 212), (1096, 140, 250)):
        draw.ellipse([((cx - radius) * scale, (cy - radius) * scale),
                      ((cx + radius) * scale, (cy + radius) * scale)],
                     outline=FAINT, width=2 * scale)

    image = big.resize((WIDTH, HEIGHT), Image.LANCZOS)
    draw = ImageDraw.Draw(image)

    x = TEXT_BOX[0]
    draw.ellipse([(x, 130), (x + 36, 166)], fill=WHITE)
    draw.text((x, 192), "MThread Draw", font=_font(54, bold=True), fill=WHITE)
    draw.text((x, 266), "Draw any picture on an Android screen over ADB.",
              font=_font(19), fill=DIM)
    draw.text((x, 294), "Record and replay touch gestures. Nothing installed on the phone.",
              font=_font(19), fill=DIM)
    return image


def render(paths, out: Path, still: bool) -> None:
    placed = fit(paths, ART_BOX)
    points = [point for path in placed for point in path]
    # Segments carry the index of their later endpoint, so a segment appears at
    # the moment its second point is placed rather than a whole stroke at a time.
    segments, index = [], 0
    for path in placed:
        for first, second in zip(path, path[1:]):
            segments.append((index + 1, first, second))
        index += len(path)
    total = len(points)

    shell = backdrop()
    caption_font = _font(15)

    def frame_at(shown: int, head: bool) -> Image.Image:
        scale = SUPERSAMPLE
        layer = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), BACK)
        draw = ImageDraw.Draw(layer)

        for end, first, second in segments:
            if end > shown:
                break
            draw.line([(first[0] * scale, first[1] * scale),
                       (second[0] * scale, second[1] * scale)],
                      fill=(214, 216, 224), width=scale)

        for order, (px, py) in enumerate(points[:shown]):
            age = shown - order
            if head and age <= COMET:
                # The head fades from a bright wide dot to the resting size, so
                # the eye follows where the finger is rather than the whole shape.
                warmth = 1.0 - age / COMET
                radius = (1.3 + 2.6 * warmth) * scale
                level = int(150 + 105 * warmth)
                draw.ellipse([(px * scale - radius, py * scale - radius),
                              (px * scale + radius, py * scale + radius)],
                             fill=(level, level, min(255, level + 6)))
            elif order % 2 == 0:
                # Every point at rest turns the line into a caterpillar; every
                # other one keeps it legible as a row of circles.
                radius = 1.5 * scale
                draw.ellipse([(px * scale - radius, py * scale - radius),
                              (px * scale + radius, py * scale + radius)],
                             fill=(196, 199, 208))

        small = layer.resize((WIDTH, HEIGHT), Image.LANCZOS)
        # The art is composed onto the shell rather than drawn into it, so the
        # wordmark and rings are rendered once instead of fifty-six times.
        composed = shell.copy()
        art = small.crop((ART_BOX[0] - 40, ART_BOX[1] - 20,
                          ART_BOX[0] + ART_BOX[2] + 40, ART_BOX[1] + ART_BOX[3] + 20))
        composed.paste(art, (ART_BOX[0] - 40, ART_BOX[1] - 20), _mask(art))
        return composed

    def _mask(art: Image.Image) -> Image.Image:
        """Alpha from the art's own brightness, so the rings show through it.

        A hard threshold would be simpler and would throw away the antialiasing
        that the whole supersampled render exists to produce - the dots would go
        back to being lumps.
        """
        return art.convert("L").point(lambda value: min(255, int(value * 1.4)))

    frames = []
    for step in range(FRAMES + HOLD):
        shown = total if step >= FRAMES else max(2, int(total * (step + 1) / FRAMES))
        image = frame_at(shown, head=step < FRAMES)
        caption = (f"{total:,} touch points" if step >= FRAMES
                   else f"{shown:,} / {total:,} touch points")
        ImageDraw.Draw(image).text((ART_BOX[0] + ART_BOX[2] // 2, HEIGHT - 46), caption,
                                   font=caption_font, fill=DIM, anchor="mm")
        frames.append(image)

    if still:
        frames[-1].save(out.with_suffix(".png"))
        print(f"wrote {out.with_suffix('.png')}")

    palette = frames[-1].quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)
    quantised = [f.quantize(palette=palette, dither=Image.NONE) for f in frames]
    quantised[0].save(out, save_all=True, append_images=quantised[1:], duration=FRAME_MS,
                      loop=0, optimize=True, disposal=1)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(frames)} frames)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", default="examples/cat.jpg")
    parser.add_argument("--method", default="flow", choices=["canny", "flow"])
    parser.add_argument("--out", default="docs/banner.gif")
    parser.add_argument("--still", action="store_true", help="also write a PNG of the last frame")
    args = parser.parse_args()

    paths = trace(args.image, args.method)
    print(f"{len(paths)} strokes, {sum(map(len, paths))} points")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(paths, out, args.still)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
