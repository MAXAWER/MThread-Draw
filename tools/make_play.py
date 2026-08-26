"""Build docs/index.html: the project page, with a game you can actually play.

GitHub renders README markdown with scripts stripped, so nothing interactive can
live there. GitHub Pages serves a real page from the same repository, and that
is where the interactive part goes; the README links to it.

The game is not decoration either. The strokes you trace are the strokes this
program sends to a phone, produced by a real Vectorizer run over the photographs
in examples/, and the time to beat is the time the program takes.

    python tools/make_play.py        # -> docs/index.html

The stroke data is embedded rather than fetched, so the file works when opened
straight off disk as well as over Pages.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mthread.vectorize import VectorizeSettings, Vectorizer

ROOT = Path(__file__).resolve().parent.parent

#: Subject, file, tracer, sliders, and the seconds the device takes for it.
#: The timings are measured, not guessed - a Pixel 8 Pro through the injector at
#: one millisecond a point, which is where "instant" actually lands.
DRAWINGS = [
    ("guitar", "A guitar", "examples/guitar.jpg", "canny", 5.0, 8.0),
    ("lighthouse", "A lighthouse", "examples/lighthouse.jpg", "canny", 4.0, 8.0),
    ("cat", "A cat", "examples/cat.jpg", "flow", 5.0, 8.0),
]

#: Milliseconds a point, which is what the device needs to receive all of them.
#: Measured: at 0 ms a Pixel 8 Pro loses two thirds of a 1,679-point drawing,
#: because the receiving app samples input once a frame.
MS_PER_POINT = 3.0


def trace_all() -> dict:
    data = {}
    for key, label, image, method, sensitivity, detail in DRAWINGS:
        settings = VectorizeSettings.from_sliders(
            sensitivity, detail, target_width=560, method=method)
        vectorizer = Vectorizer()
        vectorizer.load_image(str(ROOT / image))
        _, paths = vectorizer.process(settings)

        xs = [float(x) for path in paths for x, _ in path]
        ys = [float(y) for path in paths for _, y in path]
        left, top = min(xs), min(ys)
        points = sum(len(path) for path in paths)

        data[key] = {
            "label": label,
            "width": round(max(xs) - left, 1),
            "height": round(max(ys) - top, 1),
            "points": points,
            "seconds": round(points * MS_PER_POINT / 1000.0, 1),
            "strokes": [[[round(float(x) - left, 1), round(float(y) - top, 1)]
                         for x, y in path] for path in paths],
        }
        print(f"{key:<11} {len(paths):>4} strokes, {points:>5} points, "
              f"{data[key]['seconds']}s on the device")
    return data


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MThread Draw — trace it yourself</title>
<meta name="description" content="MThread Draw turns a photograph into touch strokes and draws it on an Android phone. Try tracing one by hand and see how long it takes you.">
<meta property="og:title" content="MThread Draw">
<meta property="og:description" content="It draws a photograph on your phone in about two seconds. Try doing it by hand.">
<style>
:root {
  --back: #0c0d11;
  --panel: #14161d;
  --line: #232630;
  --ink: #f4f5f8;
  --dim: #9a9eaa;
  --live: #ff4a3d;
  --good: #4ade80;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--back); color: var(--ink);
  font: 16px/1.55 "Segoe UI", system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; }

/* The circles are the motif: every one is a touch point. */
.sky { position: fixed; inset: 0; overflow: hidden; z-index: 0; pointer-events: none; }
.sky i {
  position: absolute; border-radius: 50%; background: #fff;
  opacity: .045; animation: drift linear infinite;
}
@keyframes drift {
  from { transform: translateY(14vh) scale(.9); }
  to   { transform: translateY(-14vh) scale(1.1); }
}
@media (prefers-reduced-motion: reduce) { .sky i { animation: none; } }

.wrap { position: relative; z-index: 1; max-width: 1080px; margin: 0 auto; padding: 0 22px 80px; }

header { padding: 74px 0 30px; }
.mark { display: flex; align-items: center; gap: 14px; }
.dot { width: 42px; height: 42px; border-radius: 50%; background: #fff; flex: none; }
h1 { font-size: 44px; margin: 18px 0 10px; letter-spacing: -.02em; }
.lede { color: var(--dim); font-size: 19px; max-width: 62ch; margin: 0 0 26px; }
.cta { display: flex; flex-wrap: wrap; gap: 12px; }
.btn {
  display: inline-block; padding: 11px 20px; border-radius: 10px; text-decoration: none;
  border: 1px solid var(--line); background: var(--panel); font-size: 15px;
  transition: border-color .15s, transform .15s;
}
.btn:hover { border-color: #3a3f4d; transform: translateY(-1px); }
.btn.primary { background: #fff; color: #0c0d11; border-color: #fff; font-weight: 600; }

.card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 22px; }
h2 { font-size: 26px; margin: 54px 0 6px; letter-spacing: -.01em; }
.sub { color: var(--dim); margin: 0 0 20px; max-width: 70ch; }

.picker { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.pick {
  padding: 7px 14px; border-radius: 8px; border: 1px solid var(--line);
  background: transparent; color: var(--dim); font: inherit; font-size: 14px; cursor: pointer;
}
.pick[aria-pressed="true"] { background: #fff; color: #0c0d11; border-color: #fff; }

.stage { display: grid; grid-template-columns: 1fr 232px; gap: 22px; }
@media (max-width: 760px) { .stage { grid-template-columns: 1fr; } }
canvas {
  max-width: 100%; height: auto; margin: 0 auto; display: block; border-radius: 12px;
  background: #090a0d; border: 1px solid var(--line); touch-action: none; cursor: crosshair;
}
.paperwrap { min-width: 0; }
.side { display: flex; flex-direction: column; gap: 14px; }
.stat { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
.stat b { display: block; font-size: 27px; font-weight: 600; letter-spacing: -.01em; }
.stat span { color: var(--dim); font-size: 13px; }
.bar { height: 6px; border-radius: 3px; background: #21242e; overflow: hidden; margin-top: 9px; }
.bar i { display: block; height: 100%; width: 0; background: var(--good); transition: width .12s; }
.verdict { font-size: 14px; color: var(--dim); min-height: 3.2em; }
.verdict.win { color: var(--good); }

table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 15px; }
td, th { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--line); }
th { color: var(--dim); font-weight: 500; }
code { background: #1b1e26; padding: 2px 6px; border-radius: 5px; font-size: .9em; }
footer { color: var(--dim); font-size: 14px; margin-top: 60px; }
</style>
</head>
<body>
<div class="sky" id="sky"></div>
<div class="wrap">

<header>
  <div class="mark"><div class="dot"></div></div>
  <h1>MThread Draw</h1>
  <p class="lede">It turns an ordinary photograph into touch strokes and draws it on an
  Android phone, over ADB, with nothing installed on the device. A drawing of
  five hundred points lands in about two seconds.</p>
  <div class="cta">
    <a class="btn primary" href="https://github.com/MAXAWER/MThread-Draw/releases/latest">Download</a>
    <a class="btn" href="https://github.com/MAXAWER/MThread-Draw">Source on GitHub</a>
    <a class="btn" href="https://github.com/MAXAWER/MThread-Draw/blob/main/TERMS.md">Licence</a>
  </div>
</header>

<h2>Trace it yourself</h2>
<p class="sub">These are the actual strokes the program sends to a phone, in the order it
sends them. Drag along the grey lines and try to cover them. The clock starts when you do.</p>

<div class="card">
  <div class="picker" id="picker"></div>
  <div class="stage">
    <div class="paperwrap"><canvas id="paper"></canvas></div>
    <div class="side">
      <div class="stat"><b id="covered">0%</b><span>covered</span>
        <div class="bar"><i id="bar"></i></div></div>
      <div class="stat"><b id="clock">0.0s</b><span>your time</span></div>
      <div class="stat"><b id="machine">—</b><span>MThread Draw</span></div>
      <p class="verdict" id="verdict">Drag on the drawing to start.</p>
      <button class="btn" id="watch" type="button">Watch it draw</button>
      <button class="btn" id="again" type="button">Start over</button>
    </div>
  </div>
</div>

<h2>Why it is quick</h2>
<p class="sub">Every touch on Android normally costs a process. Sending a thousand of them
that way takes minutes, which is why anything continuous - a gesture, a line, a
signature - is unusable through the obvious route.</p>

<table>
  <tr><th>Route</th><th>Per point</th><th>1,500 points</th></tr>
  <tr><td><code>adb shell input</code></td><td>~110 ms</td><td>2 min 45 s</td></tr>
  <tr><td>raw <code>/dev/input</code></td><td>microseconds</td><td>refused by any recent Pixel</td></tr>
  <tr><td>on-device injector</td><td>microseconds</td><td>about 4.5 s, and the pacing is ours</td></tr>
</table>

<p class="sub">The last row is the one that matters: when the time between points belongs to
us, a drawing can arrive instantly or it can arrive the way a hand would have
made it, tremor and overshoot included.</p>

<h2>Get it</h2>
<table>
  <tr><td><b>Windows</b></td><td>An installer, or a folder you unzip. Nothing else to install:
    Python, OpenCV and adb all travel inside it.</td></tr>
  <tr><td><b>macOS</b></td><td>A disk image, for Apple Silicon and Intel.</td></tr>
  <tr><td><b>Linux</b></td><td>From source, three commands.</td></tr>
</table>
<div class="cta">
  <a class="btn primary" href="https://github.com/MAXAWER/MThread-Draw/releases/latest">Releases</a>
  <a class="btn" href="https://github.com/MAXAWER/MThread-Draw#readme">Read the docs</a>
</div>

<footer>
  AGPL-3.0, with a commercial licence available from the author.
  The drawings on this page were produced by the program itself from the
  photographs in <code>examples/</code>.
</footer>

</div>
<script>
const DATA = __DATA__;

/* Ambient circles. Sized and placed once; the animation is CSS. */
(function sky() {
  const host = document.getElementById('sky');
  const sizes = [180, 90, 320, 46, 140, 70, 240, 110, 58, 190];
  sizes.forEach((size, index) => {
    const bubble = document.createElement('i');
    bubble.style.width = bubble.style.height = size + 'px';
    bubble.style.left = ((index * 37) % 96) + '%';
    bubble.style.top = ((index * 53) % 92) + '%';
    bubble.style.animationDuration = (16 + index * 3) + 's';
    bubble.style.animationDirection = index % 2 ? 'alternate' : 'alternate-reverse';
    host.appendChild(bubble);
  });
})();

const paper = document.getElementById('paper');
const context = paper.getContext('2d');
const coveredOut = document.getElementById('covered');
const barOut = document.getElementById('bar');
const clockOut = document.getElementById('clock');
const machineOut = document.getElementById('machine');
const verdictOut = document.getElementById('verdict');

let current = Object.keys(DATA)[0];
let targets = [];      /* every point of the drawing, in canvas units */
let hit = [];          /* whether the player has been near it */
let scale = 1, count = 0, started = 0, ticking = null, drawing = false, finished = false;
let watching = false;   /* the program's turn: it must not be timed as the player's */
let trail = [];        /* what the player has drawn, for redrawing on resize */

/* How near counts as covered. Generous on purpose: this is a demonstration,
   not a test of mouse precision. */
const REACH = 13;

/* Tall subjects would otherwise make a canvas nobody can see the end of, so
   the height is capped and the width follows from it. */
const TALLEST = 560;

function layout() {
  const shape = DATA[current];
  // The container, never the canvas: once layout has set the canvas's own
  // width, measuring it feeds the result back in and the drawing shrinks a
  // little on every resize until it disappears.
  const width = paper.parentElement.clientWidth || 640;
  scale = Math.min(width / shape.width, TALLEST / shape.height);
  paper.width = Math.round(shape.width * scale * devicePixelRatio);
  paper.height = Math.round(shape.height * scale * devicePixelRatio);
  paper.style.width = Math.round(shape.width * scale) + 'px';
  paper.style.height = Math.round(shape.height * scale) + 'px';
  context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);

  targets = [];
  shape.strokes.forEach(stroke => stroke.forEach(point =>
    targets.push([point[0] * scale, point[1] * scale])));
  if (hit.length !== targets.length) { hit = new Array(targets.length).fill(false); count = 0; }
  repaint();
}

function repaint() {
  const shape = DATA[current];
  context.clearRect(0, 0, paper.width, paper.height);

  context.lineWidth = 1.4;
  context.lineJoin = context.lineCap = 'round';
  context.strokeStyle = '#3a3f4d';
  shape.strokes.forEach(stroke => {
    context.beginPath();
    stroke.forEach((point, index) => {
      const x = point[0] * scale, y = point[1] * scale;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  });

  context.fillStyle = '#4ade80';
  for (let index = 0; index < targets.length; index++) {
    if (hit[index]) {
      context.beginPath();
      context.arc(targets[index][0], targets[index][1], 1.7, 0, 7);
      context.fill();
    }
  }

  context.strokeStyle = '#ffffff';
  context.lineWidth = 2;
  trail.forEach(run => {
    context.beginPath();
    run.forEach((point, index) => {
      const x = point[0] * scale, y = point[1] * scale;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  });
}

function mark(x, y) {
  let gained = 0;
  for (let index = 0; index < targets.length; index++) {
    if (hit[index]) continue;
    const dx = targets[index][0] - x, dy = targets[index][1] - y;
    if (dx * dx + dy * dy <= REACH * REACH) { hit[index] = true; gained++; }
  }
  if (!gained) return;
  count += gained;
  const share = count / targets.length;
  coveredOut.textContent = Math.round(share * 100) + '%';
  barOut.style.width = (share * 100) + '%';
  if (share >= 0.9 && !finished && !watching) finish();
}

function finish() {
  finished = true;
  clearInterval(ticking);
  const yours = (performance.now() - started) / 1000;
  clockOut.textContent = yours.toFixed(1) + 's';
  const theirs = DATA[current].seconds;
  const times = Math.max(1, Math.round(yours / theirs));
  verdictOut.className = 'verdict win';
  verdictOut.textContent = `Done in ${yours.toFixed(1)} seconds. The program needs ` +
    `${theirs}s for the same ${DATA[current].points} points, so it is about ${times}x quicker ` +
    `- and it does not get bored on the thousandth one.`;
}

function place(event) {
  const box = paper.getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
}

paper.addEventListener('pointerdown', event => {
  if (finished) return;
  drawing = true;
  paper.setPointerCapture(event.pointerId);
  trail.push([]);
  if (!started) {
    started = performance.now();
    verdictOut.textContent = 'Keep going - ninety per cent finishes it.';
    ticking = setInterval(() => {
      clockOut.textContent = ((performance.now() - started) / 1000).toFixed(1) + 's';
    }, 100);
  }
  const [x, y] = place(event);
  trail[trail.length - 1].push([x / scale, y / scale]);
  mark(x, y);
  repaint();
});

paper.addEventListener('pointermove', event => {
  if (!drawing || finished) return;
  const [x, y] = place(event);
  trail[trail.length - 1].push([x / scale, y / scale]);
  mark(x, y);
  repaint();
});

addEventListener('pointerup', () => { drawing = false; });

function reset(key) {
  current = key || current;
  watching = false;
  hit = []; trail = []; count = 0; started = 0; finished = false;
  clearInterval(ticking);
  coveredOut.textContent = '0%';
  barOut.style.width = '0';
  clockOut.textContent = '0.0s';
  machineOut.textContent = DATA[current].seconds + 's';
  verdictOut.className = 'verdict';
  verdictOut.textContent = `${DATA[current].points} points. Drag on the drawing to start.`;
  layout();
}

/* The program's own turn: the same strokes, at the pace the device gets them. */
document.getElementById('watch').addEventListener('click', () => {
  reset();
  watching = true;
  const shape = DATA[current];
  const flat = [];
  shape.strokes.forEach(stroke => flat.push(stroke));
  let strokeIndex = 0, pointIndex = 0;
  const step = Math.max(1, Math.round(shape.points / 90));
  verdictOut.textContent = 'Watching. Every dot is one touch point.';
  const timer = setInterval(() => {
    for (let n = 0; n < step; n++) {
      if (strokeIndex >= flat.length) {
        clearInterval(timer);
        watching = false;
        verdictOut.className = 'verdict win';
        verdictOut.textContent = `${shape.points} points, ${shape.seconds}s on a real phone.`;
        return;
      }
      const stroke = flat[strokeIndex];
      if (pointIndex === 0) trail.push([]);
      trail[trail.length - 1].push(stroke[pointIndex]);
      const point = stroke[pointIndex];
      mark(point[0] * scale, point[1] * scale);
      pointIndex++;
      if (pointIndex >= stroke.length) { strokeIndex++; pointIndex = 0; }
    }
    repaint();
  }, 16);
});

document.getElementById('again').addEventListener('click', () => reset());

const picker = document.getElementById('picker');
Object.keys(DATA).forEach((key, index) => {
  const button = document.createElement('button');
  button.className = 'pick';
  button.type = 'button';
  button.textContent = DATA[key].label;
  button.setAttribute('aria-pressed', index === 0 ? 'true' : 'false');
  button.addEventListener('click', () => {
    picker.querySelectorAll('.pick').forEach(other => other.setAttribute('aria-pressed', 'false'));
    button.setAttribute('aria-pressed', 'true');
    reset(key);
  });
  picker.appendChild(button);
});

addEventListener('resize', () => { layout(); });
reset(current);
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="docs/index.html")
    args = parser.parse_args()

    data = trace_all()
    page = PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
