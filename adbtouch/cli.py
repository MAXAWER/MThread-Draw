"""Command line front end: ``python -m adbtouch``."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .device import Device, list_devices
from .errors import AdbTouchError
from .player import replay
from .recorder import Recorder
from .session import Session


def _cmd_devices(args) -> int:
    devices = list_devices()
    if not devices:
        print("No devices attached.")
        return 1
    for device in devices:
        print(f"{device.serial}\t{device.human_state}")
    return 0


def _cmd_info(args) -> int:
    device = Device(args.serial)
    width, height = device.screen_size
    print(f"serial      : {device.serial}")
    print(f"screen      : {width}x{height}")
    touch = device.touch_device
    print(f"touch input : {touch.path}  {touch.name!r}")
    print(f"x range     : {touch.x_range}")
    print(f"y range     : {touch.y_range}")
    print(f"pressure    : {touch.pressure_range}")
    if touch.x_range and (touch.x_range[1] - touch.x_range[0] + 1) != width:
        print("note        : digitizer resolution differs from the display; coordinates are rescaled.")

    if device.supports_raw_touch:
        print("raw input   : yes - drawing uses kernel events, which is the fast path")
    else:
        print("raw input   : NO - this device refuses sendevent on /dev/input")
        print("              Drawing falls back to Android's own input injection, which")
        print("              works but costs about a tenth of a second per point.")
        print("              Reading events is a separate permission: recording gestures")
        print("              may still work here even though drawing raw events does not.")
    return 0


def _cmd_record(args) -> int:
    device = Device(args.serial)
    recorder = Recorder(device)
    recorder.start()
    print(f"Recording from {recorder.only_devices or 'all input devices'}.")
    print("Interact with the phone, then press Enter to stop (Ctrl+C also works).")
    try:
        if args.duration:
            deadline = time.time() + args.duration
            while time.time() < deadline:
                time.sleep(0.2)
        else:
            input()
    except KeyboardInterrupt:
        print()
    session = recorder.stop()
    session.note = args.note or ""
    if recorder.error:
        print(f"Recorder reported: {recorder.error}", file=sys.stderr)
    if not session.events:
        print("Nothing was captured. Did the screen receive any touches?", file=sys.stderr)
        return 1
    session.save(args.output)
    print(f"Saved {len(session.events)} events ({session.duration:.1f}s) to {args.output}")
    return 0


def _cmd_play(args) -> int:
    device = Device(args.serial)
    session = Session.load(args.input)
    print(f"Replaying {len(session.events)} events ({session.duration:.1f}s) at {args.speed}x")

    def progress(done, total):
        print(f"\r  {done}/{total} events", end="", flush=True)

    replay(device, session, speed=args.speed, repeat=args.repeat, progress=progress)
    print("\nDone.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adbtouch", description=__doc__)
    parser.add_argument("--version", action="version", version=f"adbtouch {__version__}")
    parser.add_argument("-s", "--serial", help="target device serial")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="list attached devices").set_defaults(func=_cmd_devices)
    sub.add_parser("info", help="show screen and touchscreen details").set_defaults(func=_cmd_info)

    record = sub.add_parser("record", help="record touch input to a file")
    record.add_argument("-o", "--output", default="session.json")
    record.add_argument("-d", "--duration", type=float, help="stop automatically after N seconds")
    record.add_argument("--note", help="free-form description stored in the file")
    record.set_defaults(func=_cmd_record)

    play = sub.add_parser("play", help="replay a recorded file")
    play.add_argument("input")
    play.add_argument("--speed", type=float, default=1.0)
    play.add_argument("--repeat", type=int, default=1)
    play.set_defaults(func=_cmd_play)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except AdbTouchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
