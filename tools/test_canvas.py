"""Put a drawing canvas on the device, for checking that touches land correctly.

The canvas is an ordinary web page served from this machine; the device reaches
it through ``adb reverse``, so it works the same on a phone over USB, a phone
over wireless ADB, and an emulator, and needs no app installed.

    python tools/test_canvas.py                 # serve and open it on the device
    python tools/test_canvas.py --pattern       # then draw a calibration pattern

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


def calibration_paths(width: int, height: int) -> list[list[tuple[int, int]]]:
    """A rectangle, its diagonals and a centre cross, in display pixels."""
    left, right = width // 10, width - width // 10
    top, bottom = height // 10, height - height // 10
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
    args = parser.parse_args()

    if not list_devices():
        print("No device is attached. Plug a phone in with USB debugging on, "
              "start an emulator, or `adb connect <ip>:5555`.", file=sys.stderr)
        return 1

    device = Device(args.serial)
    width, height = device.screen_size
    url = f"http://localhost:{args.port}/canvas.html"

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

    if args.pattern:
        input("Let the page finish loading, then press Enter to draw the pattern...")
        paths = calibration_paths(width, height)
        drawn = device.draw_paths(paths)
        print(f"drew {drawn} strokes; the canvas counter should agree")
        print("The rectangle should sit a tenth of the screen in from every edge,")
        print("and the cross should be dead centre. If it is not, run `adbtouch info`.")

    try:
        input("Serving. Press Enter to stop.\n")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        server.shutdown()
        device.adb("reverse", "--remove", f"tcp:{args.port}", check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
