"""Render the README demo assets from a real vectoriser run.

Nothing here is mocked: the strokes animated in the GIF are exactly the paths
:class:`adbtouch.Vectorizer` hands to the device, in the order the device draws
them. What the GIF cannot show is the phone itself - see docs/DEMO.md for
recording the real thing with scrcpy.

    python tools/make_demo.py [image] [--out docs]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from adbtouch.vectorize import VectorizeSettings, Vectorizer

# Phone mock-up, in pixels of the finished GIF.
PHONE_W, PHONE_H = 340, 640
BEZEL = 14
CORNER = 34
SCREEN_MARGIN = 18

FRAMES = 52
HOLD_FRAMES = 14
FRAME_MS = 70

BODY = (28, 30, 34)
SCREEN = (255, 255, 255)
INK = (17, 17, 17)
PEN = (226, 62, 62)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
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


def phone_shell() -> Image.Image:
    shell = Image.new("RGB", (PHONE_W, PHONE_H), (255, 255, 255))
    draw = ImageDraw.Draw(shell)
    draw.rounded_rectangle([(0, 0), (PHONE_W - 1, PHONE_H - 1)], CORNER, fill=BODY)
    draw.rounded_rectangle(
        [(BEZEL, BEZEL), (PHONE_W - BEZEL - 1, PHONE_H - BEZEL - 1)], CORNER - 8, fill=SCREEN
    )
    draw.rounded_rectangle(
        [(PHONE_W // 2 - 26, 5), (PHONE_W // 2 + 26, 11)], 3, fill=(60, 62, 68)
    )
    return shell


def render_gif(paths, out: Path) -> None:
    shell = phone_shell()
    screen_box = (
        BEZEL + SCREEN_MARGIN,
        BEZEL + SCREEN_MARGIN + 24,
        PHONE_W - 2 * (BEZEL + SCREEN_MARGIN),
        PHONE_H - 2 * (BEZEL + SCREEN_MARGIN) - 48,
    )
    placed = fit_paths(paths, screen_box)
    total = sum(len(p) for p in placed)
    font = _font(15)

    frames = []
    for index in range(FRAMES + HOLD_FRAMES):
        drawn_target = total if index >= FRAMES else int(total * (index + 1) / FRAMES)
        frame = shell.copy()
        draw = ImageDraw.Draw(frame)

        drawn = 0
        pen = None
        for path in placed:
            if drawn >= drawn_target:
                break
            take = min(len(path), drawn_target - drawn)
            if take >= 2:
                draw.line(path[:take], fill=INK, width=2, joint="curve")
                pen = path[take - 1]
            drawn += len(path)

        if index < FRAMES and pen is not None:
            draw.ellipse(
                [(pen[0] - 7, pen[1] - 7), (pen[0] + 7, pen[1] + 7)], outline=PEN, width=2
            )
            draw.ellipse([(pen[0] - 2, pen[1] - 2), (pen[0] + 2, pen[1] + 2)], fill=PEN)

        caption = "done" if index >= FRAMES else f"{drawn_target}/{total} points"
        draw.text((PHONE_W // 2, PHONE_H - BEZEL - 26), caption, font=font,
                  fill=(120, 124, 130), anchor="mm")
        frames.append(frame.convert("P", palette=Image.ADAPTIVE, colors=32))

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
    panel = 320
    gap, top = 22, 34
    canvas = Image.new("RGB", (panel * 3 + gap * 4, panel + top + gap), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    font = _font(15)

    edges_img = Image.fromarray(255 - edges).convert("RGB")
    for index, (image, label) in enumerate(
        ((source, "1. your image"), (edges_img, "2. detected edges"), (preview, "3. strokes sent to the phone"))
    ):
        thumb = image.copy()
        thumb.thumbnail((panel, panel), Image.LANCZOS)
        x = gap + index * (panel + gap) + (panel - thumb.width) // 2
        y = top + (panel - thumb.height) // 2
        canvas.paste(thumb, (x, y))
        draw.rectangle([(x - 1, y - 1), (x + thumb.width, y + thumb.height)], outline=(220, 222, 226))
        draw.text((gap + index * (panel + gap), 12), label, font=font, fill=(90, 94, 100))

    canvas.save(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", default="examples/sample.png")
    parser.add_argument("--out", default="docs", help="directory for demo.gif and pipeline.png")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    vectorizer = Vectorizer()
    vectorizer.load_image(args.image)
    preview, paths = vectorizer.process(VectorizeSettings(target_width=800))
    print(f"{len(paths)} strokes, {sum(len(p) for p in paths)} points")

    render_gif(paths, out_dir / "demo.gif")
    render_pipeline(Image.open(args.image), vectorizer.edges, preview, out_dir / "pipeline.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
