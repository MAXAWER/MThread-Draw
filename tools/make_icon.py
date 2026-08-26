"""Draw the application icon.

Two outputs: a large PNG, which PyInstaller converts to an .icns for the macOS
bundle, and a multi-resolution .ico for the Windows executable and its Start
Menu shortcut. Generated rather than committed as binary art nobody can edit.

    python tools/make_icon.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
Ico_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BACK_TOP = (58, 82, 152)
BACK_BOTTOM = (32, 44, 88)
PHONE = (250, 250, 252)
PHONE_EDGE = (206, 212, 226)
STROKE = (28, 32, 44)
PEN = (232, 72, 68)


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def build() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded-square backdrop with a vertical gradient, drawn into a mask so the
    # corners stay clean at every downscale.
    gradient = Image.new("RGB", (1, SIZE))
    for y in range(SIZE):
        gradient.putpixel((0, y), lerp(BACK_TOP, BACK_BOTTOM, y / SIZE))
    gradient = gradient.resize((SIZE, SIZE))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (SIZE - 1, SIZE - 1)], SIZE * 0.22, fill=255)
    image.paste(gradient, (0, 0), mask)

    # The phone, upright and centred.
    px, py, pw, ph = 300, 168, 424, 688
    draw.rounded_rectangle([(px, py), (px + pw, py + ph)], 64, fill=PHONE, outline=PHONE_EDGE, width=6)
    draw.rounded_rectangle([(px + pw / 2 - 52, py + 26), (px + pw / 2 + 52, py + 40)], 7, fill=PHONE_EDGE)

    # A single continuous stroke across the screen - the thing the app does.
    path = [(368, 706), (404, 604), (462, 668), (516, 468), (568, 588), (614, 386), (656, 496)]
    draw.line(path, fill=STROKE, width=26, joint="curve")

    # The pen, caught mid-stroke at the end of the line.
    tip = path[-1]
    draw.ellipse([(tip[0] - 62, tip[1] - 62), (tip[0] + 62, tip[1] + 62)], outline=PEN, width=16)
    draw.ellipse([(tip[0] - 22, tip[1] - 22), (tip[0] + 22, tip[1] + 22)], fill=PEN)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="packaging", help="directory for mthreaddraw.png and mthreaddraw.ico")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    icon = build()

    icon.save(out / "mthreaddraw.png")
    icon.save(out / "mthreaddraw.ico", sizes=Ico_SIZES)
    print(f"wrote {out / 'mthreaddraw.png'} and {out / 'mthreaddraw.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
