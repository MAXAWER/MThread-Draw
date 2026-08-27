"""Render the README's hero: a drawing that draws itself, in real strokes.

    python tools/make_hero.py                # -> docs/hero.svg

Nothing here is illustration. The lines are what :class:`mthread.Vectorizer`
produces from `examples/motorcycle.jpg`, in the order the program would send
them to a phone, and the animation is the same order played out over eleven
seconds. A reader watching the top of the README is watching the product work.

SVG rather than the GIF the banner uses, for three reasons. It is a tenth of the
bytes at four times the resolution; it stays sharp on a display of any density;
and the timing is declarative, so a stroke can begin the moment the one before
it ends without a frame budget to spend.

Two things had to be measured rather than assumed.

GitHub serves images through a proxy that passes SVG through unchanged, so SMIL
animation inside one plays - but only inside an `<img>`. Inline SVG in Markdown
is stripped, so the file must be referenced, never pasted.

The whole thing has to hold together at about 900 px wide, which is what a
README column actually gets. Everything here is laid out for that and scales
from it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mthread.vectorize import VectorizeSettings, Vectorizer

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "examples" / "motorcycle.jpg"
OUT = ROOT / "docs" / "hero.svg"

WIDTH, HEIGHT = 1280, 520

#: The picture sits on the right; the words have the left.
ART = (700, 60, 520, 400)

#: Total time for every stroke to be drawn, and the pause before it repeats.
DRAW_SECONDS = 11.0
HOLD_SECONDS = 2.6

#: A stroke shorter than this is a speck. Dropping them keeps the file small
#: and, more to the point, keeps the animation from spending its time on dust.
MINIMUM_POINTS = 6

#: Points closer together than this add bytes and nothing else at this size.
MINIMUM_STEP = 1.6


#: Sensitivity low and detail high: the low threshold keeps the long contours of
#: the tank and the rider whole rather than breaking them into dashes, and the
#: detail fills in the engine. Rendered at every combination that seemed
#: plausible, this is the one where the motorcycle is a motorcycle.
SENSITIVITY, DETAIL = 4.0, 9.5


def trace() -> list[list[tuple[float, float]]]:
    settings = VectorizeSettings.from_sliders(SENSITIVITY, DETAIL,
                                              target_width=900, method="canny")
    vectorizer = Vectorizer()
    vectorizer.load_image(str(SOURCE))
    _, paths = vectorizer.process(settings)
    return [path for path in paths if len(path) >= MINIMUM_POINTS]


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


def thin(path):
    """Drop points that land on top of the ones before them."""
    kept = [path[0]]
    for point in path[1:]:
        last = kept[-1]
        if abs(point[0] - last[0]) + abs(point[1] - last[1]) >= MINIMUM_STEP:
            kept.append(point)
    if len(kept) < 2:
        kept.append(path[-1])
    return kept


def length_of(path) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return total


def polyline(path) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in path)


def strokes_svg(paths) -> str:
    """Every stroke, each waiting its turn.

    The reveal is a dash the length of the stroke, offset out of sight and
    animated back to zero: the standard trick, and the only one that works
    without scripting. Each stroke's start is its share of the total ink, so
    a long stroke takes longer than a short one - the way drawing works.
    """
    total = sum(length_of(path) for path in paths) or 1.0
    cycle = DRAW_SECONDS + HOLD_SECONDS
    lines = []
    elapsed = 0.0
    for path in paths:
        length = length_of(path)
        start = DRAW_SECONDS * (elapsed / total)
        # Clamped: a two-point stroke drawing for eight milliseconds reads as a
        # pop rather than a stroke, and below about forty the eye cannot see a
        # direction anyway.
        span = max(DRAW_SECONDS * (length / total), 0.04)
        elapsed += length

        begin = max(start / cycle, 0.001)
        end = min((start + span) / cycle, 0.999)
        if end <= begin:
            end = min(begin + 0.001, 0.999)

        lines.append(
            f'<polyline points="{polyline(path)}" '
            f'stroke-dasharray="{length:.1f}" stroke-dashoffset="{length:.1f}">'
            f'<animate attributeName="stroke-dashoffset" '
            f'dur="{cycle:.2f}s" repeatCount="indefinite" '
            f'values="{length:.1f};{length:.1f};0;0" '
            f'keyTimes="0;{begin:.4f};{end:.4f};1"/>'
            f"</polyline>")
    return "\n    ".join(lines)


def build(paths) -> str:
    ink = strokes_svg([thin(path) for path in fit(paths, ART)])
    cycle = DRAW_SECONDS + HOLD_SECONDS

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}"
     width="{WIDTH}" height="{HEIGHT}" role="img"
     aria-label="MThread Draw: a traced drawing assembling itself stroke by stroke">
  <title>MThread Draw</title>
  <defs>
    <linearGradient id="ground" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0d0f14"/>
      <stop offset="0.55" stop-color="#12151d"/>
      <stop offset="1" stop-color="#0a0c11"/>
    </linearGradient>
    <linearGradient id="glass" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.08"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0.015"/>
    </linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.30"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0.04"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#7aa2ff" stop-opacity="0.20"/>
      <stop offset="1" stop-color="#7aa2ff" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="{WIDTH}" height="{HEIGHT}" fill="url(#ground)"/>
  <circle cx="985" cy="250" r="330" fill="url(#halo)"/>

  <!-- The wordmark, and the one sentence that says what this is. -->
  <g fill="#ffffff" font-family="Segoe UI, Inter, Helvetica Neue, Arial, sans-serif">
    <circle cx="98" cy="132" r="17" fill="#ffffff"/>
    <text x="128" y="142" font-size="21" letter-spacing="6" opacity="0.62">ANDROID · ADB</text>
    <text x="82" y="238" font-size="76" font-weight="700">MThread Draw</text>
    <text x="86" y="296" font-size="25" opacity="0.72">Draw any picture on a phone's screen,</text>
    <text x="86" y="332" font-size="25" opacity="0.72">by touching it. Nothing installed on the phone.</text>

    <g font-size="19" opacity="0.55">
      <text x="86" y="404">1,679 points in 5.0 seconds</text>
      <text x="86" y="434">Records gestures · replays them on another phone</text>
      <text x="86" y="464">Windows · macOS · Linux · AGPL-3.0</text>
    </g>
  </g>

  <!-- The phone, and the drawing arriving in it. -->
  <g>
    <rect x="{ART[0] - 34}" y="{ART[1] - 30}" width="{ART[2] + 68}" height="{ART[3] + 60}"
          rx="42" fill="url(#glass)" stroke="url(#edge)" stroke-width="1.2"/>
    <rect x="{ART[0] - 18}" y="{ART[1] - 14}" width="{ART[2] + 36}" height="{ART[3] + 28}"
          rx="30" fill="#0b0d12" fill-opacity="0.55"/>
    <g fill="none" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round"
       stroke-linejoin="round" opacity="0.92">
    {ink}
    </g>
  </g>

  <!-- The cycle marker: a hairline that crosses as the drawing is drawn, so a
       still frame still says the thing is timed. -->
  <rect x="82" y="{HEIGHT - 26}" width="1116" height="2" rx="1" fill="#ffffff" opacity="0.07"/>
  <rect x="82" y="{HEIGHT - 26}" width="0" height="2" rx="1" fill="#ffffff" opacity="0.45">
    <animate attributeName="width" dur="{cycle:.2f}s" repeatCount="indefinite"
             values="0;1116;1116" keyTimes="0;{DRAW_SECONDS / cycle:.4f};1"/>
  </rect>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    paths = trace()
    svg = build(paths)
    args.out.write_text(svg, encoding="utf-8", newline="\n")
    kilobytes = args.out.stat().st_size / 1024
    strokes = len(paths)
    points = sum(len(path) for path in paths)
    print(f"wrote {args.out} - {strokes} strokes, {points} points, {kilobytes:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
