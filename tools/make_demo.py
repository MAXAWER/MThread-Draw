"""Render the README demo assets from a real vectoriser run.

Nothing here is mocked: the strokes animated in the GIF are exactly the paths
:class:`adbtouch.Vectorizer` hands to the device, in the order the device draws
them. The source panel is the unmodified colour image that produced them, which
is the whole point - you feed it an ordinary picture, not prepared line art.

What the GIF cannot show is the phone itself; see docs/DEMO.md for recording the
real thing with scrcpy.

    python tools/make_demo.py [image] [--out docs]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from adbtouch.vectorize import VectorizeSettings, Vectorizer

MARGIN = 24
BEZEL = 12
CORNER = 26
SCREEN_MARGIN = 14

# The phone is held whichever way suits the picture, and everything else is
# sized around that: a portrait photograph on a landscape screen ends up as a
# postage stamp in the middle, which says nothing about the drawing.
LANDSCAPE = dict(canvas=(990, 450), source=(MARGIN, 92, 420, 300),
                 phone=(500, 66, 466, 262))
PORTRAIT = dict(canvas=(900, 620), source=(MARGIN, 96, 360, 470),
                phone=(470, 40, 300, 540))

CANVAS_W, CANVAS_H = LANDSCAPE["canvas"]
SOURCE_BOX = LANDSCAPE["source"]
PHONE_X, PHONE_Y, PHONE_W, PHONE_H = LANDSCAPE["phone"]


def use_layout(source) -> None:
    """Pick the layout that suits the source image, before anything is drawn."""
    global CANVAS_W, CANVAS_H, SOURCE_BOX, PHONE_X, PHONE_Y, PHONE_W, PHONE_H
    layout = PORTRAIT if source.height > source.width else LANDSCAPE
    CANVAS_W, CANVAS_H = layout["canvas"]
    SOURCE_BOX = layout["source"]
    PHONE_X, PHONE_Y, PHONE_W, PHONE_H = layout["phone"]

FRAMES = 46
HOLD_FRAMES = 12
FRAME_MS = 80

PAGE = (255, 255, 255)
BODY = (28, 30, 34)
SCREEN = (255, 255, 255)
INK = (17, 17, 17)
PEN = (226, 62, 62)
LABEL = (110, 114, 122)
RULE = (216, 219, 224)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_paths(paths, box):
    """Scale and centre *paths* into *box* = (x, y, w, h).

    Fitted to the ink rather than to the source canvas, so whatever margin the
    original image happened to carry does not shrink the drawing.
    """
    points = [point for path in paths for point in path]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    src_w = max(max_x - min_x, 1)
    src_h = max(max_y - min_y, 1)

    bx, by, bw, bh = box
    scale = min(bw / src_w, bh / src_h)
    dx = bx + (bw - src_w * scale) / 2 - min_x * scale
    dy = by + (bh - src_h * scale) / 2 - min_y * scale
    return [[(x * scale + dx, y * scale + dy) for x, y in path] for path in paths]


def backdrop(source: Image.Image, stroke_count: int) -> Image.Image:
    """Everything that does not change between frames: source panel and phone."""
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), PAGE)
    draw = ImageDraw.Draw(canvas)

    bx, by, bw, bh = SOURCE_BOX
    thumb = source.copy()
    thumb.thumbnail((bw, bh), Image.LANCZOS)
    tx = bx + (bw - thumb.width) // 2
    ty = by + (bh - thumb.height) // 2
    canvas.paste(thumb, (tx, ty))
    draw.rectangle([(tx - 1, ty - 1), (tx + thumb.width, ty + thumb.height)], outline=RULE)

    draw.text((bx, by - 48), "an ordinary colour image", font=_font(21, bold=True), fill=BODY)
    draw.text((bx, by - 22), f"{source.width}x{source.height} PNG, nothing prepared by hand",
              font=_font(15), fill=LABEL)
    draw.text((bx, ty + thumb.height + 14),
              f"{stroke_count} strokes traced from it", font=_font(15), fill=LABEL)

    # A long arrow across the gap, so the two panels read as one sentence.
    y = PHONE_Y + PHONE_H // 2
    draw.line([(bx + bw + 14, y), (PHONE_X - 24, y)], fill=RULE, width=3)
    draw.polygon([(PHONE_X - 24, y), (PHONE_X - 40, y - 9), (PHONE_X - 40, y + 9)], fill=RULE)

    draw.rounded_rectangle(
        [(PHONE_X, PHONE_Y), (PHONE_X + PHONE_W - 1, PHONE_Y + PHONE_H - 1)], CORNER, fill=BODY
    )
    draw.rounded_rectangle(
        [(PHONE_X + BEZEL, PHONE_Y + BEZEL),
         (PHONE_X + PHONE_W - BEZEL - 1, PHONE_Y + PHONE_H - BEZEL - 1)],
        CORNER - 8, fill=SCREEN,
    )
    if PHONE_W > PHONE_H:
        speaker = [(PHONE_X + PHONE_W - 11, PHONE_Y + PHONE_H // 2 - 24),
                   (PHONE_X + PHONE_W - 5, PHONE_Y + PHONE_H // 2 + 24)]
    else:
        speaker = [(PHONE_X + PHONE_W // 2 - 24, PHONE_Y + 5),
                   (PHONE_X + PHONE_W // 2 + 24, PHONE_Y + 11)]
    draw.rounded_rectangle(speaker, 3, fill=(60, 62, 68))
    return canvas


def render_gif(paths, source: Image.Image, out: Path) -> None:
    shell = backdrop(source, len(paths))
    screen_box = (
        PHONE_X + BEZEL + SCREEN_MARGIN,
        PHONE_Y + BEZEL + SCREEN_MARGIN,
        PHONE_W - 2 * (BEZEL + SCREEN_MARGIN),
        PHONE_H - 2 * (BEZEL + SCREEN_MARGIN),
    )
    placed = fit_paths(paths, screen_box)
    total = sum(len(p) for p in placed)
    font = _font(14)
    caption_y = PHONE_Y + PHONE_H + 26

    frames = []
    for index in range(FRAMES + HOLD_FRAMES):
        target = total if index >= FRAMES else int(total * (index + 1) / FRAMES)
        frame = shell.copy()
        draw = ImageDraw.Draw(frame)

        drawn = 0
        pen = None
        for path in placed:
            if drawn >= target:
                break
            take = min(len(path), target - drawn)
            if take >= 2:
                draw.line(path[:take], fill=INK, width=1, joint="curve")
                pen = path[take - 1]
            drawn += len(path)

        if index < FRAMES and pen is not None:
            draw.ellipse([(pen[0] - 6, pen[1] - 6), (pen[0] + 6, pen[1] + 6)], outline=PEN, width=2)
            draw.ellipse([(pen[0] - 2, pen[1] - 2), (pen[0] + 2, pen[1] + 2)], fill=PEN)

        caption = "done" if index >= FRAMES else f"{target:,} / {total:,} touch points"
        draw.text((PHONE_X + PHONE_W // 2, caption_y), caption, font=font, fill=LABEL, anchor="mm")
        frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=64))

    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(frames)} frames)")


def render_pipeline(source, edges, preview, out: Path) -> None:
    """Three panels: what you feed in, what Canny sees, what gets drawn."""
    panel = 400
    gap, top = 24, 36
    canvas = Image.new("RGB", (panel * 3 + gap * 4, panel + top + gap), PAGE)
    draw = ImageDraw.Draw(canvas)
    font = _font(16)

    edges_img = Image.fromarray(255 - edges).convert("RGB")
    labels = ("1. your image, as it is", "2. edges the vectoriser finds", "3. strokes sent to the phone")
    for index, (image, label) in enumerate(zip((source, edges_img, preview), labels)):
        thumb = image.copy()
        thumb.thumbnail((panel, panel), Image.LANCZOS)
        x = gap + index * (panel + gap) + (panel - thumb.width) // 2
        y = top + (panel - thumb.height) // 2
        canvas.paste(thumb, (x, y))
        draw.rectangle([(x - 1, y - 1), (x + thumb.width, y + thumb.height)], outline=RULE)
        draw.text((gap + index * (panel + gap), 12), label, font=font, fill=LABEL)

    canvas.save(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", default="examples/castle.png")
    parser.add_argument("--out", default="docs", help="directory for demo.gif and pipeline.png")
    parser.add_argument("--detail", type=float, default=7.0, help="1-10, as in the app")
    parser.add_argument("--sensitivity", type=float, default=5.0, help="1-10, as in the app")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = VectorizeSettings.from_sliders(args.sensitivity, args.detail, target_width=900)
    vectorizer = Vectorizer()
    vectorizer.load_image(args.image)
    preview, paths = vectorizer.process(settings)
    print(f"{len(paths)} strokes, {sum(len(p) for p in paths)} points")

    source = Image.open(args.image).convert("RGB")
    use_layout(source)
    render_gif(paths, source, out_dir / "demo.gif")
    render_pipeline(source, vectorizer.edges, preview, out_dir / "pipeline.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
