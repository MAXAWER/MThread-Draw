"""Draw the sample image used by the README demo.

Deliberately an ordinary colour illustration rather than clean black line art:
the point of the demo is that you feed MThread Draw a normal picture and it works
out the strokes itself. It is also busy on purpose - towers, crenellations,
bridge arches, a treeline - because a demo that only ever draws a smiley says
nothing about what the vectoriser does with real detail.

Generated rather than checked in as a photograph so the repository owns its
demo art outright, with no attribution or licence to track.

    python tools/make_sample.py examples/castle.png
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1400, 1000
HORIZON = 660

SKY_TOP = (46, 66, 118)
SKY_MID = (150, 126, 158)
SKY_LOW = (248, 186, 122)

SUN = (255, 232, 176)
CLOUD = (238, 206, 200)

FAR_HILL = (96, 104, 148)
MID_HILL = (70, 80, 120)
SNOW = (226, 228, 240)

CLIFF = (114, 102, 106)
CLIFF_DARK = (56, 48, 56)
GRASS = (104, 136, 104)
GRASS_DARK = (46, 72, 60)

STONE = (226, 220, 206)
STONE_SHADE = (188, 180, 168)
STONE_DARK = (146, 140, 132)
ROOF = (158, 76, 70)
ROOF_DARK = (120, 56, 54)
WINDOW = (58, 52, 62)
FLAG = (206, 88, 78)

WATER = (112, 144, 184)
WATER_LIGHT = (176, 200, 224)
TREE = (34, 60, 50)


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def sky(draw: ImageDraw.ImageDraw) -> None:
    """Vertical gradient. Canny finds nothing here, which is the intent -
    a drawn version of this scene should be lines, not a shaded sky."""
    for y in range(HORIZON + 40):
        t = y / (HORIZON + 40)
        colour = lerp(SKY_TOP, SKY_MID, t / 0.72) if t < 0.72 else lerp(SKY_MID, SKY_LOW, (t - 0.72) / 0.28)
        draw.line([(0, y), (W, y)], fill=colour)


def sun(draw: ImageDraw.ImageDraw) -> None:
    cx, cy, r = 1055, 300, 74
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=SUN)
    for index in range(2):
        pad = r + 26 + index * 30
        draw.ellipse([(cx - pad, cy - pad), (cx + pad, cy + pad)],
                     outline=lerp(SUN, SKY_MID, 0.55 + index * 0.15), width=2)


def clouds(draw: ImageDraw.ImageDraw) -> None:
    bands = [
        (150, 210, 320, 30), (250, 232, 210, 22), (860, 168, 300, 26),
        (980, 236, 200, 18), (420, 150, 240, 20), (620, 250, 180, 16),
    ]
    for x, y, width, height in bands:
        draw.ellipse([(x, y), (x + width, y + height)], fill=CLOUD)
        draw.ellipse([(x + width * 0.25, y - height * 0.6), (x + width * 0.8, y + height * 0.7)], fill=CLOUD)


def mountains(draw: ImageDraw.ImageDraw) -> None:
    far = [(-40, 640), (140, 470), (250, 545), (390, 400), (520, 540),
           (660, 452), (780, 556), (930, 430), (1080, 552), (1240, 470),
           (1440, 620), (1440, 700), (-40, 700)]
    draw.polygon(far, fill=FAR_HILL)
    for peak_x, peak_y, spread in ((390, 400, 46), (930, 430, 40), (140, 470, 34)):
        draw.polygon(
            [(peak_x, peak_y), (peak_x + spread, peak_y + spread * 0.9),
             (peak_x + spread * 0.4, peak_y + spread * 0.55),
             (peak_x, peak_y + spread * 0.8),
             (peak_x - spread * 0.45, peak_y + spread * 0.6),
             (peak_x - spread, peak_y + spread * 0.95)],
            fill=SNOW,
        )

    mid = [(-40, 700), (180, 590), (340, 660), (520, 585), (700, 668),
           (900, 596), (1100, 664), (1300, 604), (1440, 676), (1440, 740), (-40, 740)]
    draw.polygon(mid, fill=MID_HILL)


def cliff(draw: ImageDraw.ImageDraw) -> None:
    """The rock the castle stands on, and the bank it grows out of."""
    rock = [(470, 596), (455, 660), (430, 700), (446, 760), (500, 806),
            (600, 838), (740, 846), (880, 826), (960, 786), (986, 726),
            (966, 664), (940, 606), (900, 580), (520, 580)]
    draw.polygon(rock, fill=CLIFF, outline=CLIFF_DARK, width=4)

    for points in (
        [(520, 610), (496, 690), (528, 764), (566, 812)],
        [(640, 600), (628, 690), (652, 780), (640, 836)],
        [(770, 596), (790, 684), (762, 772), (784, 842)],
        [(880, 604), (900, 678), (876, 750), (904, 812)],
    ):
        draw.line(points, fill=CLIFF_DARK, width=5, joint="curve")

    draw.polygon([(430, 700), (446, 760), (500, 806), (470, 700)], fill=CLIFF_DARK)
    draw.polygon([(966, 664), (986, 726), (960, 786), (944, 690)], fill=CLIFF_DARK)


def tower(draw: ImageDraw.ImageDraw, x: int, top: int, width: int, bottom: int,
          *, spire: bool = True, windows: int = 2) -> None:
    draw.rectangle([(x, top), (x + width, bottom)], fill=STONE, outline=STONE_DARK, width=3)
    draw.rectangle([(x + width * 0.62, top), (x + width, bottom)], fill=STONE_SHADE)
    draw.rectangle([(x, top), (x + width, bottom)], outline=STONE_DARK, width=3)

    # Crenellated crown: a band plus the merlons standing on it.
    band = 16
    draw.rectangle([(x - 7, top - band), (x + width + 7, top)], fill=STONE, outline=STONE_DARK, width=3)
    merlon_w = (width + 14) / 7
    for index in range(0, 7, 2):
        mx = x - 7 + index * merlon_w
        draw.rectangle([(mx, top - band - 15), (mx + merlon_w, top - band)],
                       fill=STONE, outline=STONE_DARK, width=3)

    if spire:
        apex = top - band - 15 - int(width * 1.15)
        draw.polygon([(x - 14, top - band - 15), (x + width + 14, top - band - 15),
                      (x + width / 2, apex)], fill=ROOF, outline=ROOF_DARK)
        draw.line([(x + width / 2, apex), (x + width / 2, apex - 40)], fill=STONE_DARK, width=3)
        draw.polygon([(x + width / 2, apex - 40), (x + width / 2 + 44, apex - 28),
                      (x + width / 2, apex - 16)], fill=FLAG, outline=ROOF_DARK)

    for index in range(windows):
        wy = top + 34 + index * 62
        wx = x + width / 2 - 11
        draw.rounded_rectangle([(wx, wy), (wx + 22, wy + 38)], 11, fill=WINDOW)


def castle(draw: ImageDraw.ImageDraw) -> None:
    base = 600

    # Curtain wall between the towers, with its own crenellations.
    draw.rectangle([(500, 486), (900, base)], fill=STONE, outline=STONE_DARK, width=3)
    for index in range(0, 17, 2):
        mx = 500 + index * 25
        draw.rectangle([(mx, 466), (mx + 25, 486)], fill=STONE, outline=STONE_DARK, width=3)

    # Gatehouse: a half-round arch over a square opening, portcullis behind it.
    draw.pieslice([(654, 500), (746, 592)], 180, 360, fill=STONE_SHADE)
    draw.rectangle([(654, 546), (746, base)], fill=STONE_SHADE)
    draw.arc([(654, 500), (746, 592)], 180, 360, fill=STONE_DARK, width=3)
    draw.line([(654, 546), (654, base)], fill=STONE_DARK, width=3)
    draw.line([(746, 546), (746, base)], fill=STONE_DARK, width=3)

    draw.pieslice([(668, 514), (732, 578)], 180, 360, fill=WINDOW)
    draw.rectangle([(668, 546), (732, base)], fill=WINDOW)
    for index in range(1, 4):
        draw.line([(668 + index * 16, 528), (668 + index * 16, base)], fill=STONE_DARK, width=2)
    for index in range(1, 4):
        draw.line([(668, 534 + index * 22), (732, 534 + index * 22)], fill=STONE_DARK, width=2)

    tower(draw, 470, 404, 86, base, windows=2)
    tower(draw, 828, 424, 78, base, windows=2)
    tower(draw, 626, 300, 66, 486, windows=3)      # keep, standing on the wall
    tower(draw, 736, 350, 58, 486, windows=2)

    # A hall roof tucked between the keep and the right tower.
    draw.polygon([(560, 486), (626, 486), (626, 430), (593, 404), (560, 430)],
                 fill=ROOF, outline=ROOF_DARK)
    draw.line([(593, 404), (593, 486)], fill=ROOF_DARK, width=2)


def bridge(draw: ImageDraw.ImageDraw) -> None:
    """A causeway from the near bank to the foot of the rock, on two arches."""
    left_x, left_y = 300, 838
    right_x, right_y = 474, 800

    def deck(x: float) -> float:
        return left_y + (right_y - left_y) * (x - left_x) / (right_x - left_x)

    for x in (344, 430):
        top = deck(x)
        draw.rectangle([(x - 20, top + 8), (x + 20, top + 104)], fill=STONE_SHADE,
                       outline=STONE_DARK, width=3)

    for x in (387,):
        top = deck(x) + 26
        draw.pieslice([(x - 44, top - 44), (x + 44, top + 44)], 180, 360,
                      fill=WATER, outline=STONE_DARK, width=3)

    draw.polygon([(left_x, left_y), (right_x, right_y), (right_x, right_y + 22), (left_x, left_y + 22)],
                 fill=STONE, outline=STONE_DARK)
    for index in range(8):
        x = left_x + index * (right_x - left_x) / 7
        top = deck(x)
        draw.line([(x, top), (x, top - 24)], fill=STONE_DARK, width=3)
    draw.line([(left_x, left_y - 24), (right_x, right_y - 24)], fill=STONE_DARK, width=3)


def water(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle([(0, 806), (W, H)], fill=WATER)
    for index in range(16):
        y = 826 + index * 11
        length = 120 + (index * 97) % 420
        x = 40 + (index * 233) % 900
        draw.line([(x, y), (x + length, y)], fill=WATER_LIGHT, width=3)
        draw.line([(x + length + 60, y), (x + length + 60 + length * 0.4, y)],
                  fill=WATER_LIGHT, width=2)


def banks(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon([(-40, 848), (110, 812), (240, 832), (322, 818), (322, 1040), (-40, 1040)], fill=GRASS)
    draw.polygon([(1104, 820), (1220, 792), (1440, 826), (1440, 1040), (1104, 1040)], fill=GRASS)
    draw.line([(-40, 848), (110, 812), (240, 832), (322, 818)], fill=GRASS_DARK, width=4, joint="curve")
    draw.line([(1104, 820), (1220, 792), (1440, 826)], fill=GRASS_DARK, width=4, joint="curve")


def pines(draw: ImageDraw.ImageDraw) -> None:
    def pine(x: int, base_y: int, height: int) -> None:
        width = height * 0.46
        draw.line([(x, base_y), (x, base_y - height * 0.22)], fill=CLIFF_DARK,
                  width=max(3, int(height * 0.05)))
        for tier in range(3):
            top = base_y - height + tier * height * 0.26
            spread = width * (0.55 + tier * 0.22)
            draw.polygon([(x, top), (x + spread, top + height * 0.34), (x - spread, top + height * 0.34)],
                         fill=TREE, outline=GRASS_DARK)

    for x, base_y, height in ((60, 916, 200), (150, 884, 168), (246, 926, 210)):
        pine(x, base_y, height)
    for x, base_y, height in ((1168, 898, 176), (1262, 936, 216), (1356, 890, 158), (1432, 920, 190)):
        pine(x, base_y, height)


def birds(draw: ImageDraw.ImageDraw) -> None:
    for x, y, size in ((300, 300, 18), (348, 268, 14), (392, 312, 11), (1150, 420, 15), (1200, 396, 12)):
        draw.arc([(x - size, y - size), (x, y + size)], 300, 360, fill=SKY_TOP, width=3)
        draw.arc([(x, y - size), (x + size, y + size)], 180, 240, fill=SKY_TOP, width=3)


def build() -> Image.Image:
    image = Image.new("RGB", (W, H), SKY_TOP)
    draw = ImageDraw.Draw(image)

    sky(draw)
    sun(draw)
    clouds(draw)
    mountains(draw)
    water(draw)
    cliff(draw)
    castle(draw)
    banks(draw)
    bridge(draw)
    pines(draw)
    birds(draw)

    # A whisper of blur: flat vector edges are unrealistically sharp, and the
    # demo is more honest if the vectoriser is fed something photograph-like.
    return image.filter(ImageFilter.GaussianBlur(0.4))


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("examples/castle.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    build().save(out)
    print(f"wrote {out} ({W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
