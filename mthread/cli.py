"""Command line front end: ``python -m mthread``."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .device import Device, list_devices
from .errors import MThreadError
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


def _placement_from(args):
    """The placement options every drawing command shares."""
    from .placement import Placement
    return Placement(
        centre=(args.x, args.y),
        scale=args.scale,
        rotation=args.rotate,
        flip_x=args.flip_x,
        flip_y=args.flip_y,
    )


def _add_placement_options(command) -> None:
    command.add_argument("--scale", type=float, default=1.0,
                         help="size, where 1.0 fills the screen with a margin")
    command.add_argument("--rotate", type=float, default=0.0, metavar="DEGREES")
    command.add_argument("--flip-x", action="store_true", help="mirror left to right")
    command.add_argument("--flip-y", action="store_true", help="mirror top to bottom")
    command.add_argument("--x", type=float, default=0.5, metavar="0..1",
                         help="where the middle lands across the screen")
    command.add_argument("--y", type=float, default=0.5, metavar="0..1")
    command.add_argument("--margin", type=float, default=0.06)
    command.add_argument("--speed", type=float, default=1.0)
    command.add_argument("--human", type=float, default=0.0,
                         help="0 draws mechanically; 1 to 3 like a hand")


def _draw_unit_paths(args, paths, what: str) -> int:
    """Place paths given in a 0..1 square onto the screen, and draw them."""
    from .placement import place_on_screen

    device = Device(args.serial)
    width, height = device.screen_size
    placed = place_on_screen(paths, width, height, _placement_from(args),
                             margin=args.margin)
    points = sum(len(path) for path in placed)
    print(f"{what}: {len(placed)} strokes, {points} points on {width}x{height}")

    drawn = device.draw_paths(placed, speed=args.speed, human=args.human)
    print(f"drawn {drawn} strokes")
    return 0


def _cmd_shape(args) -> int:
    from .shapes import SHAPES

    maker = SHAPES[args.shape]
    if args.shape == "star":
        paths = maker(points=args.points)
    elif args.shape == "polygon":
        paths = maker(sides=args.points)
    else:
        paths = maker()
    return _draw_unit_paths(args, paths, args.shape)


def _cmd_text(args) -> int:
    from .shapes import text

    paths = text(args.words, font=args.font, size=args.size)
    return _draw_unit_paths(args, paths, f"text {args.words!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mthread", description=__doc__)
    parser.add_argument("--version", action="version", version=f"mthread {__version__}")
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

    # Drawing something without preparing a picture first. A heart is a
    # parametric curve; there is no reason to make anyone find a JPEG of one.
    from .shapes import SHAPES
    shape = sub.add_parser("shape", help="draw a shape: " + ", ".join(SHAPES))
    shape.add_argument("shape", choices=sorted(SHAPES))
    shape.add_argument("--points", type=int, default=5,
                       help="points on a star, or sides on a polygon")
    _add_placement_options(shape)
    shape.set_defaults(func=_cmd_shape)

    words = sub.add_parser("text", help="draw text in any font on the machine")
    words.add_argument("words")
    words.add_argument("--font", help="a font file, or a name the system knows")
    words.add_argument("--size", type=int, default=220,
                       help="pixels to render at before tracing; larger is smoother")
    _add_placement_options(words)
    words.set_defaults(func=_cmd_text)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MThreadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
