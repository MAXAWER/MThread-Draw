"""Draw the line-art sample used by the README demo.

Kept as a script rather than a checked-in binary blob nobody can edit: the
sample is deliberately thin black lines on white, which is the input shape the
vectoriser is happiest with, and regenerating it is one command.

    python tools/make_sample.py examples/sample.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 900
INK = (0, 0, 0)
WIDTH = 4


def draw_cat(draw: ImageDraw.ImageDraw) -> None:
    # Ears first, so the head outline drawn over them hides the join.
    draw.line([(252, 300), (296, 138), (404, 246)], fill=INK, width=WIDTH, joint="curve")
    draw.line([(648, 300), (604, 138), (496, 246)], fill=INK, width=WIDTH, joint="curve")
    draw.line([(300, 268), (322, 190), (372, 250)], fill=INK, width=WIDTH, joint="curve")
    draw.line([(600, 268), (578, 190), (528, 250)], fill=INK, width=WIDTH, joint="curve")

    draw.ellipse([(210, 220), (690, 640)], outline=INK, width=WIDTH)

    # Eyes: outline plus a filled pupil, which Canny turns into a clean ring.
    draw.ellipse([(320, 380), (410, 452)], outline=INK, width=WIDTH)
    draw.ellipse([(490, 380), (580, 452)], outline=INK, width=WIDTH)
    draw.ellipse([(352, 400), (378, 434)], fill=INK)
    draw.ellipse([(522, 400), (548, 434)], fill=INK)

    draw.polygon([(428, 486), (472, 486), (450, 514)], outline=INK, width=WIDTH)
    draw.arc([(390, 500), (450, 560)], start=0, end=90, fill=INK, width=WIDTH)
    draw.arc([(450, 500), (510, 560)], start=90, end=180, fill=INK, width=WIDTH)

    for y0, y1 in ((470, 442), (500, 500), (530, 558)):
        draw.line([(300, y0), (140, y1)], fill=INK, width=WIDTH)
        draw.line([(600, y0), (760, y1)], fill=INK, width=WIDTH)

    # Body: two flanks running from under the head down to the floor line.
    draw.line([(268, 560), (214, 700), (206, 812)], fill=INK, width=WIDTH, joint="curve")
    draw.line([(632, 560), (686, 700), (694, 812)], fill=INK, width=WIDTH, joint="curve")
    draw.line([(206, 812), (694, 812)], fill=INK, width=WIDTH)

    draw.ellipse([(236, 760), (356, 820)], outline=INK, width=WIDTH)
    draw.ellipse([(544, 760), (664, 820)], outline=INK, width=WIDTH)

    # Tail, curling out to the right.
    draw.arc([(660, 640), (860, 840)], start=90, end=300, fill=INK, width=WIDTH)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("examples/sample.png")
    image = Image.new("RGB", (SIZE, SIZE), "white")
    draw_cat(ImageDraw.Draw(image))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"wrote {out} ({SIZE}x{SIZE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
