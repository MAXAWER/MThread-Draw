"""Draw the application icon: a white circle.

Two outputs: a large PNG, which PyInstaller converts to an .icns for the macOS
bundle, and a multi-resolution .ico for the Windows executable and its Start
Menu shortcut. Generated rather than committed as binary art nobody can edit.

    python tools/make_icon.py

The circle sits on a near-black square rather than on nothing. A white disc on
transparency is invisible against a light taskbar, a light Start Menu and half
of GitHub, which is not a mark - it is a hole. The square is what makes the
white read as white.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Everything is drawn at this multiple and scaled down: PIL's ellipse has no
# antialiasing of its own, and a jagged circle is worse than no circle.
SUPERSAMPLE = 4

BACK = (17, 18, 22)
CIRCLE = (255, 255, 255)
#: Fraction of the icon's width the circle spans. Small enough to breathe,
#: large enough to survive being drawn at sixteen pixels.
DIAMETER = 0.56
CORNER = 0.22


def build() -> Image.Image:
    big = SIZE * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle([(0, 0), (big - 1, big - 1)], big * CORNER, fill=BACK)

    radius = big * DIAMETER / 2
    centre = big / 2
    draw.ellipse([(centre - radius, centre - radius), (centre + radius, centre + radius)],
                 fill=CIRCLE)

    return image.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="packaging",
                        help="directory for mthreaddraw.png and mthreaddraw.ico")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    icon = build()

    icon.save(out / "mthreaddraw.png")
    icon.save(out / "mthreaddraw.ico", sizes=ICO_SIZES)
    print(f"wrote {out / 'mthreaddraw.png'} and {out / 'mthreaddraw.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
