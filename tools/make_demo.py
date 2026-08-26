"""Render the README demo assets from real vectoriser runs.

Nothing here is mocked: the strokes animated in the GIF, and every line in the
gallery, are exactly the paths :class:`mthread.Vectorizer` hands to the device,
in the order the device draws them. The source panels are the unmodified colour
photographs that produced them, which is the whole point - you feed it an
ordinary picture, not prepared line art.

    python tools/make_demo.py                 # -> docs/demo.gif, pipeline.png, examples.png
    python tools/make_demo.py --hero guitar   # animate a different example
    python tools/make_demo.py --image my.jpg --method flow

What the GIF cannot show is the phone itself; see docs/DEMO.md for recording the
real thing with scrcpy.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from mthread.vectorize import VectorizeSettings, Vectorizer


@dataclass(frozen=True)
class Example:
    """One photograph, and the settings that suit it.

    The tracer is chosen the way the application asks the question - by what is
    in the picture, not by the name of an algorithm.
    """

    name: str
    path: str
    method: str
    subject: str
    sensitivity: float = 5.0
    detail: float = 7.0


EXAMPLES = (
    Example("guitar", "examples/guitar.jpg", "canny", "an object"),
    Example("motorcycle", "examples/motorcycle.jpg", "canny", "a machine"),
    Example("cat", "examples/cat.jpg", "flow", "an animal", detail=8.0),
    # The lighthouse sits against a night sky full of stars, and every star is
    # an edge. Turning the sensitivity down leaves the building and keeps a
    # scattering of them, which is what the photograph looks like.
    Example("lighthouse", "examples/lighthouse.jpg", "canny", "a landscape", sensitivity=4.0),
)

# Everything is drawn at this multiple and scaled back down. A one-pixel line
# drawn straight into the final image is a staircase, and a wall of staircases
# is most of why the old assets looked cheap.
SUPERSAMPLE = 3

MARGIN = 28
BEZEL = 14
CORNER = 34
SCREEN_MARGIN = 16

# The phone is held whichever way suits the picture, and everything else is
# sized around that: a portrait photograph on a landscape screen ends up as a
# postage stamp in the middle, which says nothing about the drawing.
LANDSCAPE = dict(canvas=(1240, 620), source=(MARGIN, 128, 540, 400),
                 phone=(650, 84, 560, 330))
PORTRAIT = dict(canvas=(1160, 800), source=(MARGIN, 132, 450, 590),
                phone=(590, 56, 400, 700))

FRAMES = 46
HOLD_FRAMES = 14
FRAME_MS = 80

# The page is dark and the marks on it are white, which is the identity the
# repository uses everywhere. The phone screen is the one exception: it stays
# white with black ink, because that is what the phone actually shows.
PAGE = (12, 13, 17)
BODY = (245, 246, 250)
SCREEN = (255, 255, 255)
INK = (20, 20, 22)
PEN = (226, 62, 62)
LABEL = (150, 154, 166)
RULE = (48, 51, 60)
#: Ink for a drawing shown on the page rather than on the phone.
PAGE_INK = (238, 240, 246)
#: The phone body. Once the page went dark this stopped being the text
#: colour: a light body around a light screen is one pale blob.
PHONE = (32, 34, 42)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else (
        "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def trace(example: Example, target_width: int = 900):
    """Run the real pipeline, and report what it cost."""
    settings = VectorizeSettings.from_sliders(
        example.sensitivity, example.detail, target_width=target_width, method=example.method)
    vectorizer = Vectorizer()
    vectorizer.load_image(example.path)
    preview, paths = vectorizer.process(settings)
    print(f"{example.name:<12} {example.method:<6} "
          f"{len(paths):>4} strokes, {sum(map(len, paths)):>6} points")
    return vectorizer, preview, paths


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


def ink_mask(paths, size, width: float = 1.5) -> Image.Image:
    """Draw *paths* into a coverage mask, antialiased by supersampling.

    Returned white-on-black, so it can be used directly as a paste mask for
    whatever colour the ink is meant to be.
    """
    big = Image.new("L", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE), 0)
    draw = ImageDraw.Draw(big)
    pen_width = max(1, round(width * SUPERSAMPLE))
    for path in paths:
        if len(path) >= 2:
            draw.line([(x * SUPERSAMPLE, y * SUPERSAMPLE) for x, y in path],
                      fill=255, width=pen_width, joint="curve")
    return big.resize(size, Image.LANCZOS)


def stamp(canvas: Image.Image, mask: Image.Image, colour, origin=(0, 0)) -> None:
    """Paste a solid colour through a coverage mask."""
    canvas.paste(Image.new("RGB", mask.size, colour), origin, mask)


def drawing(paths, size, width: float = 1.5) -> Image.Image:
    """A finished line drawing on the page, at *size*."""
    canvas = Image.new("RGB", size, PAGE)
    stamp(canvas, ink_mask(paths, size, width), PAGE_INK)
    return canvas


# ------------------------------------------------------------------- the GIF


def phone_backdrop(source: Image.Image, example: Example, stroke_count: int, layout):
    """Everything that does not change between frames: source panel and phone."""
    canvas = Image.new("RGB", layout["canvas"], PAGE)
    draw = ImageDraw.Draw(canvas)
    bx, by, bw, bh = layout["source"]
    phone_x, phone_y, phone_w, phone_h = layout["phone"]

    thumb = source.copy()
    thumb.thumbnail((bw, bh), Image.LANCZOS)
    tx = bx + (bw - thumb.width) // 2
    ty = by + (bh - thumb.height) // 2
    canvas.paste(thumb, (tx, ty))
    draw.rectangle([(tx - 1, ty - 1), (tx + thumb.width, ty + thumb.height)], outline=RULE)

    draw.text((bx, by - 62), "an ordinary colour photograph", font=_font(26, bold=True), fill=BODY)
    draw.text((bx, by - 30), f"{source.width}x{source.height}, nothing prepared by hand",
              font=_font(17), fill=LABEL)
    draw.text((bx, ty + thumb.height + 16),
              f"{stroke_count} strokes traced from it", font=_font(17), fill=LABEL)

    # A long arrow across the gap, so the two panels read as one sentence.
    y = phone_y + phone_h // 2
    draw.line([(bx + bw + 18, y), (phone_x - 30, y)], fill=RULE, width=3)
    draw.polygon([(phone_x - 30, y), (phone_x - 48, y - 10), (phone_x - 48, y + 10)], fill=RULE)

    draw.rounded_rectangle(
        [(phone_x, phone_y), (phone_x + phone_w - 1, phone_y + phone_h - 1)], CORNER, fill=PHONE)
    draw.rounded_rectangle(
        [(phone_x + BEZEL, phone_y + BEZEL),
         (phone_x + phone_w - BEZEL - 1, phone_y + phone_h - BEZEL - 1)],
        CORNER - 9, fill=SCREEN)
    if phone_w > phone_h:
        speaker = [(phone_x + phone_w - 12, phone_y + phone_h // 2 - 28),
                   (phone_x + phone_w - 6, phone_y + phone_h // 2 + 28)]
    else:
        speaker = [(phone_x + phone_w // 2 - 28, phone_y + 6),
                   (phone_x + phone_w // 2 + 28, phone_y + 13)]
    draw.rounded_rectangle(speaker, 4, fill=(78, 81, 92))
    return canvas, ty + thumb.height + 40


def render_gif(paths, source: Image.Image, example: Example, out: Path) -> None:
    layout = PORTRAIT if source.height > source.width else LANDSCAPE
    shell, source_bottom = phone_backdrop(source, example, len(paths), layout)
    phone_x, phone_y, phone_w, phone_h = layout["phone"]

    inset = BEZEL + SCREEN_MARGIN
    screen_origin = (phone_x + inset, phone_y + inset)
    screen_size = (phone_w - 2 * inset, phone_h - 2 * inset)
    placed = fit_paths(paths, (0, 0, *screen_size))
    total = sum(len(path) for path in placed)

    font = _font(17)
    caption_y = phone_y + phone_h + 30

    # The two panels are different heights and neither is predictable, so the
    # canvas is generous and then trimmed to whichever of them ends lower.
    shell = shell.crop((0, 0, shell.width, max(source_bottom, caption_y + 22) + MARGIN))

    # The photograph is dithered once, into a palette the drawing then reuses,
    # and every frame after that is quantised without dithering. Doing it the
    # other way round - dithering each finished frame - costs twice: the panel
    # quietly boils as the pattern is recomputed, and the error diffusion finds
    # the pen's pure red a useful approximation of the cat's nose, so the
    # photograph comes out speckled with it.
    #
    # Ink, pen and a grey ramp are appended by hand. Median cut allocates
    # colours by how much of the picture they cover; the pen covers a few
    # hundred pixels of one frame, and the grey along an antialiased line covers
    # almost nothing, so neither survives a vote.
    ramp = [tuple(round(255 + (INK[channel] - 255) * step / 8) for channel in range(3))
            for step in range(1, 9)]
    reserved = [*ramp, INK, PEN]
    quantised = shell.convert("RGB").quantize(colors=256 - len(reserved),
                                              method=Image.MEDIANCUT,
                                              dither=Image.FLOYDSTEINBERG)
    palette = Image.new("P", (1, 1))
    palette.putpalette(quantised.getpalette()[: (256 - len(reserved)) * 3]
                       + [channel for colour in reserved for channel in colour])
    # Everything is composed on top of the already-dithered photograph, so the
    # panel's pixels are exact palette entries and survive the pass untouched.
    shell = quantised.convert("RGB")

    frames = []
    for index in range(FRAMES + HOLD_FRAMES):
        target = total if index >= FRAMES else int(total * (index + 1) / FRAMES)
        frame = shell.copy()

        drawn, so_far, pen = 0, [], None
        for path in placed:
            if drawn >= target:
                break
            take = min(len(path), target - drawn)
            if take >= 2:
                so_far.append(path[:take])
                pen = path[take - 1]
            drawn += len(path)

        stamp(frame, ink_mask(so_far, screen_size), INK, screen_origin)
        if index < FRAMES and pen is not None:
            nib = Image.new("L", screen_size, 0)
            ring = ImageDraw.Draw(nib)
            ring.ellipse([(pen[0] - 8, pen[1] - 8), (pen[0] + 8, pen[1] + 8)], outline=255, width=2)
            ring.ellipse([(pen[0] - 3, pen[1] - 3), (pen[0] + 3, pen[1] + 3)], fill=255)
            stamp(frame, nib, PEN, screen_origin)

        caption = "done" if index >= FRAMES else f"{target:,} / {total:,} touch points"
        ImageDraw.Draw(frame).text((phone_x + phone_w // 2, caption_y), caption,
                                   font=font, fill=LABEL, anchor="mm")
        frames.append(frame.quantize(palette=palette, dither=Image.NONE))

    # disposal=1 leaves each frame in place, so the encoder only has to store
    # the rectangle that changed - and the only thing that changes is the phone
    # screen. Disposing to background instead re-encodes the dithered
    # photograph sixty times over, which was five sixths of the old file. The
    # screen area is repainted whole every frame, so the pen marker still has
    # somewhere to be erased to.
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=FRAME_MS,
                   loop=0, optimize=True, disposal=1)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(frames)} frames, {shell.size})")


# ------------------------------------------------------------------- stills


def render_pipeline(source, edges, paths, out: Path) -> None:
    """Three panels: what you feed in, what the tracer sees, what gets drawn."""
    panel, gap, top = 420, 26, 46
    canvas = Image.new("RGB", (panel * 3 + gap * 4, panel + top + gap), PAGE)
    draw = ImageDraw.Draw(canvas)
    font = _font(18)

    lines = drawing(fit_paths(paths, (8, 8, panel - 16, panel - 16)), (panel, panel))
    labels = ("1. your photograph, as it is",
              "2. the lines the tracer finds",
              "3. strokes sent to the phone")
    for index, (image, label) in enumerate(
            zip((source, Image.fromarray(255 - edges).convert("RGB"), lines), labels)):
        thumb = image.copy()
        thumb.thumbnail((panel, panel), Image.LANCZOS)
        x = gap + index * (panel + gap) + (panel - thumb.width) // 2
        y = top + (panel - thumb.height) // 2
        canvas.paste(thumb, (x, y))
        draw.rectangle([(x - 1, y - 1), (x + thumb.width, y + thumb.height)], outline=RULE)
        draw.text((gap + index * (panel + gap), 16), label, font=font, fill=LABEL)

    canvas.save(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def render_gallery(results, out: Path) -> None:
    """Photograph over drawing, one column per example.

    The point of this picture is that the tracer is not tuned per subject: the
    only thing that changes between columns is which of the two the application
    picks from what is in the photograph.
    """
    panel, gap, top, label = 320, 22, 40, 46
    columns = len(results)
    canvas = Image.new("RGB", (columns * panel + (columns + 1) * gap,
                               top + 2 * panel + label + gap * 2), PAGE)
    draw = ImageDraw.Draw(canvas)

    for index, (example, source, paths) in enumerate(results):
        x = gap + index * (panel + gap)

        thumb = source.copy()
        thumb.thumbnail((panel, panel), Image.LANCZOS)
        photo_y = top + (panel - thumb.height) // 2
        canvas.paste(thumb, (x + (panel - thumb.width) // 2, photo_y))
        draw.rectangle([(x + (panel - thumb.width) // 2 - 1, photo_y - 1),
                        (x + (panel - thumb.width) // 2 + thumb.width, photo_y + thumb.height)],
                       outline=RULE)

        box = (8, 8, panel - 16, panel - 16)
        canvas.paste(drawing(fit_paths(paths, box), (panel, panel)), (x, top + panel + gap))

        draw.text((x, 14), example.subject, font=_font(19, bold=True), fill=BODY)
        draw.text((x, top + 2 * panel + gap + 8),
                  f"{len(paths)} strokes, {sum(map(len, paths)):,} points",
                  font=_font(15), fill=LABEL)
        draw.text((x, top + 2 * panel + gap + 28),
                  f'tracer: {"buildings, machines, objects" if example.method == "canny" else "portraits, animals, nature"}',
                  font=_font(15), fill=LABEL)

    canvas.save(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="docs", help="directory for the generated assets")
    parser.add_argument("--hero", default="guitar", choices=[e.name for e in EXAMPLES],
                        help="which example is animated in demo.gif")
    parser.add_argument("--image", help="trace one image of your own instead")
    parser.add_argument("--method", default="canny", choices=["canny", "flow", "neural", "contour"])
    parser.add_argument("--detail", type=float, default=7.0, help="1-10, as in the app")
    parser.add_argument("--sensitivity", type=float, default=5.0, help="1-10, as in the app")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.image:
        one = Example("custom", args.image, args.method, "your image",
                      args.sensitivity, args.detail)
        vectorizer, _, paths = trace(one)
        source = Image.open(one.path).convert("RGB")
        render_gif(paths, source, one, out_dir / "demo.gif")
        render_pipeline(source, vectorizer.edges, paths, out_dir / "pipeline.png")
        return 0

    results = []
    for example in EXAMPLES:
        vectorizer, _, paths = trace(example)
        results.append((example, Image.open(example.path).convert("RGB"), paths, vectorizer))

    render_gallery([(e, s, p) for e, s, p, _ in results], out_dir / "examples.png")

    hero = next(row for row in results if row[0].name == args.hero)
    render_gif(hero[2], hero[1], hero[0], out_dir / "demo.gif")

    # The pipeline picture explains the steps, so it wants the least ambiguous
    # subject rather than the prettiest one.
    steps = next(row for row in results if row[0].name == "guitar")
    render_pipeline(steps[1], steps[3].edges, steps[2], out_dir / "pipeline.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
