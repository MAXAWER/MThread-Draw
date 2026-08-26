"""Put a drawing canvas on the device, for checking that touches land correctly.

The canvas is an ordinary web page served from this machine; the device reaches
it through ``adb reverse``, so it works the same on a phone over USB, a phone
over wireless ADB, and an emulator, and needs no app installed.

    python tools/test_canvas.py                              # open the canvas
    python tools/test_canvas.py --pattern --shot out.png     # calibration pattern
    python tools/test_canvas.py --image examples/castle.png  # draw a picture on it

The pattern is a rectangle inset by a tenth of the screen, its diagonals, and a
cross in the middle. Held against the canvas grid it answers the question this
project keeps having to ask about unfamiliar hardware: are the coordinates
arriving where they were aimed, or is the digitizer scaled, swapped or mirrored?
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adbtouch import Device, list_devices  # noqa: E402
from adbtouch.errors import AdbTouchError  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PORT = 8731


def serve(port: int) -> socketserver.TCPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(HERE))
    handler.log_message = lambda *args, **kwargs: None  # type: ignore[assignment]

    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def fit_to_screen(paths, width, height, *, margin=0.06):
    """Scale paths to the screen, keeping their aspect ratio and a clear margin."""
    points = [point for path in paths for point in path]
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    src_w = max(max_x - min_x, 1)
    src_h = max(max_y - min_y, 1)

    pad_x, pad_y = width * margin, height * margin
    scale = min((width - 2 * pad_x) / src_w, (height - 2 * pad_y) / src_h)
    dx = pad_x + (width - 2 * pad_x - src_w * scale) / 2 - min_x * scale
    dy = pad_y + (height - 2 * pad_y - src_h * scale) / 2 - min_y * scale
    return [[(round(x * scale + dx), round(y * scale + dy)) for x, y in path] for path in paths]


def calibration_paths(width: int, height: int, margin: float = 0.12) -> list[list[tuple[int, int]]]:
    """A rectangle, its diagonals and a centre cross, in display pixels.

    The margin has to clear whatever chrome the canvas is sitting under - a
    browser toolbar at the top, the gesture bar at the bottom - or the pattern
    is drawn on the browser instead of on the page.
    """
    left, right = round(width * margin), round(width * (1 - margin))
    top, bottom = round(height * margin), round(height * (1 - margin))
    cx, cy = width // 2, height // 2
    arm = min(width, height) // 12

    def line(x1, y1, x2, y2, steps=40):
        return [(round(x1 + (x2 - x1) * i / steps), round(y1 + (y2 - y1) * i / steps))
                for i in range(steps + 1)]

    return [
        line(left, top, right, top),
        line(right, top, right, bottom),
        line(right, bottom, left, bottom),
        line(left, bottom, left, top),
        line(left, top, right, bottom),
        line(right, top, left, bottom),
        line(cx - arm, cy, cx + arm, cy),
        line(cx, cy - arm, cx, cy + arm),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--serial", help="target device serial")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pattern", action="store_true",
                        help="draw the calibration pattern once the canvas is open")
    parser.add_argument("--image", help="also draw this image on the canvas")
    parser.add_argument("--sensitivity", type=float, default=3.0, help="edge sensitivity, 1-10")
    parser.add_argument("--detail", type=float, default=8.0, help="detail, 1-10")
    parser.add_argument("--margin", type=float, default=0.12,
                        help="fraction of the screen to keep clear around the drawing")
    parser.add_argument("--hand", type=float, default=0.0,
                        help="draw like a hand: 0 is exact, 1 a steady hand, 3 careless")
    parser.add_argument("--speed", type=float, default=1.0, help="pacing multiplier")
    parser.add_argument("--shot", help="save a screenshot of the result here")
    parser.add_argument("--wait", type=float, default=4.0,
                        help="seconds to let the page load before drawing")
    parser.add_argument("--hold", action="store_true",
                        help="keep serving until Enter, when run from a terminal")
    args = parser.parse_args()

    if not list_devices():
        print("No device is attached. Plug a phone in with USB debugging on, "
              "start an emulator, or `adb connect <ip>:5555`.", file=sys.stderr)
        return 1

    device = Device(args.serial)
    width, height = device.screen_size
    url = f"http://localhost:{args.port}/canvas.html"

    # A screen that has gone to sleep takes the drawing to the lock screen and
    # the screenshot comes back black, which looks like a failure and is not.
    device.shell("input", "keyevent", "KEYCODE_WAKEUP", check=False)
    device.shell("input", "keyevent", "82", check=False)

    server = serve(args.port)
    print(f"serving {HERE / 'canvas.html'} on port {args.port}")

    device.adb("reverse", f"tcp:{args.port}", f"tcp:{args.port}")
    print(f"adb reverse: the device can now reach {url}")

    try:
        device.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
        print(f"opened {url} on {device.serial} ({width}x{height})")
    except AdbTouchError as exc:
        print(f"could not open a browser on the device: {exc}", file=sys.stderr)
        print(f"open {url} there by hand instead", file=sys.stderr)

    if args.wait:
        print(f"waiting {args.wait}s for the page to load")
        time.sleep(args.wait)

    if args.pattern:
        drawn = device.draw_paths(calibration_paths(width, height, args.margin),
                                  human=args.hand, speed=args.speed, seed=1)
        print(f"drew {drawn} strokes; the counter on the canvas should agree")
        print("The rectangle should sit a tenth of the screen in from every edge and")
        print("the cross dead centre. If it does not, start with `adbtouch info`.")

    if args.image:
        from adbtouch.vectorize import VectorizeSettings, Vectorizer

        vectorizer = Vectorizer()
        vectorizer.load_image(args.image)
        _, paths = vectorizer.process(
            VectorizeSettings.from_sliders(args.sensitivity, args.detail, target_width=900))
        placed = fit_to_screen(paths, width, height, margin=args.margin)
        seconds = device.estimate_duration(placed)
        print(f"{len(paths)} strokes from {args.image}, about {seconds:.0f}s")
        started = time.perf_counter()
        drawn = device.draw_paths(placed, human=args.hand, speed=args.speed, seed=1)
        print(f"drawing itself took {time.perf_counter() - started:.1f}s")
        print(f"drew {drawn} strokes")

    if args.shot:
        time.sleep(1.0)
        # screencap on a sleeping screen returns a black rectangle, which is a
        # confusing thing to hand someone as evidence.
        device.shell("input", "keyevent", "KEYCODE_WAKEUP", check=False)
        time.sleep(0.5)
        device.screenshot(args.shot)
        print(f"screenshot: {args.shot}")

    if args.hold and sys.stdin.isatty():
        try:
            input("Serving. Press Enter to stop. ")
        except (KeyboardInterrupt, EOFError):
            pass

    server.shutdown()
    device.adb("reverse", "--remove", f"tcp:{args.port}", check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
