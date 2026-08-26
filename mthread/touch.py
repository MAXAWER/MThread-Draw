"""Touchscreen description and coordinate translation for raw ``/dev/input`` events."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "EV_SYN", "EV_KEY", "EV_ABS",
    "ABS_MT_SLOT", "ABS_MT_TOUCH_MAJOR", "ABS_MT_POSITION_X", "ABS_MT_POSITION_Y",
    "ABS_MT_TRACKING_ID", "ABS_MT_PRESSURE", "BTN_TOUCH", "SYN_REPORT",
    "TouchDevice", "parse_getevent_pl", "build_stroke_events",
]

# Linux input-event codes (see include/uapi/linux/input-event-codes.h).
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

ABS_MT_SLOT = 0x2F
ABS_MT_TOUCH_MAJOR = 0x30
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
ABS_MT_PRESSURE = 0x3A

BTN_TOUCH = 0x14A
SYN_REPORT = 0x00

_ADD_DEVICE_RE = re.compile(r"^\s*add device\s+\d+:\s*(\S+)")
_NAME_RE = re.compile(r'^\s*name:\s*"(.*)"')
_AXIS_RE = re.compile(
    r"(ABS_MT_[A-Z_]+|ABS_[A-Z_]+)\s*:\s*value\s+-?\d+,\s*min\s+(-?\d+),\s*max\s+(-?\d+)"
)
_SECTION_RE = re.compile(r"^\s*([A-Z]+)\s*\(([0-9a-fA-F]{4})\):")
#: ``getevent -pl`` labels key codes on most builds but falls back to raw hex on
#: others, so both spellings of BTN_TOUCH have to be recognised.
_BTN_TOUCH_RE = re.compile(r"\bBTN_TOUCH\b|(?<![0-9a-fA-F])014[aA](?![0-9a-fA-F])")


@dataclass
class TouchDevice:
    """A touchscreen as reported by ``getevent -pl``.

    The digitizer usually has its own coordinate range, and on many phones that
    range does *not* match the display resolution reported by ``wm size``.
    Sending display pixels straight to ``sendevent`` therefore lands in the wrong
    place; :meth:`to_raw` performs the conversion that fixes it.
    """

    path: str
    name: str = ""
    x_range: tuple[int, int] | None = None
    y_range: tuple[int, int] | None = None
    pressure_range: tuple[int, int] | None = None
    touch_major_range: tuple[int, int] | None = None
    tracking_id_range: tuple[int, int] | None = None
    has_btn_touch: bool = False
    has_slot: bool = False
    axes: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: Set when the digitizer's X axis runs along the display's Y axis.
    swap_xy: bool = False

    @property
    def is_touchscreen(self) -> bool:
        return self.x_range is not None and self.y_range is not None

    def to_raw(self, x: float, y: float, screen_w: int, screen_h: int) -> tuple[int, int]:
        """Map a display pixel to this digitizer's coordinate space.

        Coordinates outside the screen are clamped rather than rejected, so a
        path that strays a few pixels off-screen still draws its visible part.
        """
        if not self.is_touchscreen:
            return int(round(x)), int(round(y))
        if screen_w <= 1 or screen_h <= 1:
            raise ValueError("screen dimensions must be greater than 1 pixel")

        u = min(max(x / (screen_w - 1), 0.0), 1.0)
        v = min(max(y / (screen_h - 1), 0.0), 1.0)
        if self.swap_xy:
            u, v = v, u

        x_min, x_max = self.x_range
        y_min, y_max = self.y_range
        raw_x = x_min + u * (x_max - x_min)
        raw_y = y_min + v * (y_max - y_min)
        return int(round(raw_x)), int(round(raw_y))

    def pressure_value(self, fraction: float = 0.5) -> int | None:
        """A mid-scale pressure value, or ``None`` if the device reports none."""
        if not self.pressure_range:
            return None
        lo, hi = self.pressure_range
        return int(round(lo + (hi - lo) * min(max(fraction, 0.0), 1.0)))

    def touch_major_value(self, fraction: float = 0.1) -> int | None:
        if not self.touch_major_range:
            return None
        lo, hi = self.touch_major_range
        return max(1, int(round(lo + (hi - lo) * min(max(fraction, 0.0), 1.0))))


def parse_getevent_pl(output: str) -> list[TouchDevice]:
    """Parse ``adb shell getevent -pl`` into :class:`TouchDevice` records.

    Every input device is returned, not just touchscreens, so callers can decide
    what to do with keyboards and buttons; use :attr:`TouchDevice.is_touchscreen`
    to filter.
    """
    devices: list[TouchDevice] = []
    current: TouchDevice | None = None
    section: str | None = None

    for line in output.splitlines():
        add = _ADD_DEVICE_RE.match(line)
        if add:
            current = TouchDevice(path=add.group(1))
            devices.append(current)
            section = None
            continue
        if current is None:
            continue

        name = _NAME_RE.match(line)
        if name:
            current.name = name.group(1)
            continue

        header = _SECTION_RE.match(line)
        if header:
            section = header.group(1)

        # Continuation lines are indented under their section header, so the
        # last seen header still applies.
        if section == "KEY" and _BTN_TOUCH_RE.search(line):
            current.has_btn_touch = True

        for axis, lo, hi in _AXIS_RE.findall(line):
            bounds = (int(lo), int(hi))
            current.axes[axis] = bounds
            if axis == "ABS_MT_POSITION_X":
                current.x_range = bounds
            elif axis == "ABS_MT_POSITION_Y":
                current.y_range = bounds
            elif axis == "ABS_MT_PRESSURE":
                current.pressure_range = bounds
            elif axis == "ABS_MT_TOUCH_MAJOR":
                current.touch_major_range = bounds
            elif axis == "ABS_MT_TRACKING_ID":
                current.tracking_id_range = bounds
            elif axis == "ABS_MT_SLOT":
                current.has_slot = True

    return devices


def pick_touchscreen(devices: Iterable[TouchDevice]) -> TouchDevice | None:
    """Choose the most plausible touchscreen from a list of input devices.

    Prefers a multitouch device that also reports a tracking ID, falling back to
    the one with the largest coordinate space.
    """
    candidates = [d for d in devices if d.is_touchscreen]
    if not candidates:
        return None
    with_tracking = [d for d in candidates if d.tracking_id_range is not None]
    pool = with_tracking or candidates
    return max(pool, key=lambda d: (d.x_range[1] - d.x_range[0]) * (d.y_range[1] - d.y_range[0]))


def build_stroke_events(
    device: TouchDevice,
    points: Sequence[tuple[float, float]],
    screen_w: int,
    screen_h: int,
    *,
    tracking_id: int = 1,
    pressure_fraction: float = 0.5,
) -> list[tuple[int, int, int]]:
    """Build the ``(type, code, value)`` events that draw one continuous stroke.

    Emits the modern (type B) multitouch protocol: a slot, a tracking ID held for
    the whole stroke, then one report per point, then a release. Optional axes are
    only emitted when the device actually advertises them.
    """
    if not points:
        return []

    events: list[tuple[int, int, int]] = []
    if device.has_slot:
        events.append((EV_ABS, ABS_MT_SLOT, 0))
    events.append((EV_ABS, ABS_MT_TRACKING_ID, tracking_id))
    if device.has_btn_touch:
        events.append((EV_KEY, BTN_TOUCH, 1))

    pressure = device.pressure_value(pressure_fraction)
    major = device.touch_major_value()

    for x, y in points:
        raw_x, raw_y = device.to_raw(x, y, screen_w, screen_h)
        events.append((EV_ABS, ABS_MT_POSITION_X, raw_x))
        events.append((EV_ABS, ABS_MT_POSITION_Y, raw_y))
        if pressure is not None:
            events.append((EV_ABS, ABS_MT_PRESSURE, pressure))
        if major is not None:
            events.append((EV_ABS, ABS_MT_TOUCH_MAJOR, major))
        events.append((EV_SYN, SYN_REPORT, 0))

    events.append((EV_ABS, ABS_MT_TRACKING_ID, -1))
    if device.has_btn_touch:
        events.append((EV_KEY, BTN_TOUCH, 0))
    events.append((EV_SYN, SYN_REPORT, 0))
    return events
