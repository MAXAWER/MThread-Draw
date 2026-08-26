"""Recordings that can be replayed on a phone other than the one they came from.

The original recording format stores raw kernel events, which is faithful and
useless anywhere else. Two things are wrong with it:

- The numbers are digitizer coordinates, and a digitizer's range has little to
  do with the display's. A recording made on a 4096-step panel replayed on a
  1080-pixel one lands nowhere near where it was made, which is why replaying
  one elsewhere was refused rather than attempted.
- Replaying it means writing to ``/dev/input``, which every recent Pixel denies
  to the shell. So the raw format cannot even be replayed on the phone that
  produced it.

This module decodes those events into gestures - strokes of ``(time, x, y)``
with the coordinates as fractions of the screen - and plays them back through
whichever path the device allows, the injector included. A fraction means the
same thing on any screen, so a recording travels.

    session = GestureSession.from_events(recorder.stop().events, device.touch_device)
    session.save("login.json")
    ...
    device.play_gestures(GestureSession.load("login.json"))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["GESTURE_FORMAT_VERSION", "GestureSession", "Stroke"]

#: Version 1 was the raw-event format in :mod:`mthread.session`; this is the
#: portable one and reading it is what tells the two apart.
GESTURE_FORMAT_VERSION = 2

# Multi-touch protocol B, which is what every modern touchscreen speaks.
EV_SYN, EV_ABS, EV_KEY = 0x00, 0x03, 0x01
SYN_REPORT = 0x00
ABS_MT_SLOT = 0x2F
ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x35, 0x36
ABS_MT_TRACKING_ID = 0x39
ABS_X, ABS_Y = 0x00, 0x01
BTN_TOUCH = 0x14A


@dataclass
class Stroke:
    """One finger, from the moment it lands to the moment it lifts."""

    #: ``(seconds from the start of the recording, x, y)``, x and y in 0..1.
    points: list[tuple[float, float, float]] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.points[0][0] if self.points else 0.0

    @property
    def end(self) -> float:
        return self.points[-1][0] if self.points else 0.0

    def as_list(self) -> list:
        return [[round(t, 4), round(x, 5), round(y, 5)] for t, x, y in self.points]

    @classmethod
    def from_list(cls, rows) -> "Stroke":
        return cls(points=[(float(t), float(x), float(y)) for t, x, y in rows])


@dataclass
class GestureSession:
    """A recording in screen fractions, replayable anywhere."""

    strokes: list[Stroke] = field(default_factory=list)
    screen_size: tuple[int, int] | None = None
    device_model: str = ""
    device_serial: str = ""
    created_at: str = ""
    note: str = ""
    version: int = GESTURE_FORMAT_VERSION

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def duration(self) -> float:
        return max((stroke.end for stroke in self.strokes), default=0.0)

    @property
    def point_count(self) -> int:
        return sum(len(stroke.points) for stroke in self.strokes)

    # ------------------------------------------------------------- recording

    @classmethod
    def from_events(cls, events, touch, **fields) -> "GestureSession":
        """Decode raw input events into strokes.

        Args:
            events: :class:`~mthread.session.InputEvent` objects, in order.
            touch: The :class:`~mthread.touch.TouchDevice` they came from,
                whose axis ranges are what makes the numbers meaningful.
        """
        if touch is None or not touch.is_touchscreen:
            raise ValueError("the recording cannot be converted without the digitizer's ranges")

        x_min, x_max = touch.x_range
        y_min, y_max = touch.y_range
        x_span = max(x_max - x_min, 1)
        y_span = max(y_max - y_min, 1)

        # One in-flight stroke per slot. Protocol B addresses a slot, changes
        # some of its axes, and commits with SYN_REPORT; a value not mentioned
        # since the last report has not changed, which is why the last position
        # is carried forward rather than reset.
        slot = 0
        live: dict[int, Stroke] = {}
        position: dict[int, list[int | None]] = {}
        finished: list[Stroke] = []
        pending_lift: list[int] = []
        touching = True  # single-touch panels announce this with BTN_TOUCH

        def commit(t: float) -> None:
            for index, stroke in list(live.items()):
                raw = position.get(index)
                if not raw or raw[0] is None or raw[1] is None:
                    continue
                x = (raw[0] - x_min) / x_span
                y = (raw[1] - y_min) / y_span
                if touch.swap_xy:
                    x, y = y, x
                point = (t, min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))
                # A finger reporting the same place twice is not a new sample.
                if stroke.points and stroke.points[-1][1:] == point[1:]:
                    continue
                stroke.points.append(point)

        for event in events:
            if event.type == EV_ABS:
                if event.code == ABS_MT_SLOT:
                    slot = event.value
                elif event.code == ABS_MT_TRACKING_ID:
                    if event.value < 0:
                        pending_lift.append(slot)
                    else:
                        live[slot] = Stroke()
                        position.setdefault(slot, [None, None])
                elif event.code in (ABS_MT_POSITION_X, ABS_X):
                    position.setdefault(slot, [None, None])[0] = event.value
                    if event.code == ABS_X and slot not in live and touching:
                        live.setdefault(slot, Stroke())
                elif event.code in (ABS_MT_POSITION_Y, ABS_Y):
                    position.setdefault(slot, [None, None])[1] = event.value
            elif event.type == EV_KEY and event.code == BTN_TOUCH:
                touching = bool(event.value)
                if touching:
                    live.setdefault(slot, Stroke())
                    position.setdefault(slot, [None, None])
                else:
                    pending_lift.append(slot)
            elif event.type == EV_SYN and event.code == SYN_REPORT:
                commit(event.t)
                for index in pending_lift:
                    stroke = live.pop(index, None)
                    if stroke is not None and len(stroke.points) >= 1:
                        finished.append(stroke)
                pending_lift.clear()

        for stroke in live.values():
            if stroke.points:
                finished.append(stroke)

        finished.sort(key=lambda stroke: stroke.start)
        return cls(strokes=finished, **fields)

    # ------------------------------------------------------------- replaying

    def to_pixels(self, width: int, height: int) -> list[list[tuple[int, int]]]:
        """The strokes as pixel paths on a screen of this size."""
        return [[(round(x * (width - 1)), round(y * (height - 1)))
                 for _, x, y in stroke.points] for stroke in self.strokes]

    # ------------------------------------------------------------------ file

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "kind": "gestures",
            "created_at": self.created_at,
            "device_model": self.device_model,
            "device_serial": self.device_serial,
            "screen_size": list(self.screen_size) if self.screen_size else None,
            "note": self.note,
            "duration": round(self.duration, 4),
            "stroke_count": len(self.strokes),
            "point_count": self.point_count,
            "strokes": [stroke.as_list() for stroke in self.strokes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GestureSession":
        version = int(data.get("version", 0))
        if version < GESTURE_FORMAT_VERSION:
            raise ValueError(
                "This is a raw-event recording from an older version. Those hold digitizer "
                "coordinates and can only be replayed on the phone that made them; record "
                "it again to get a portable one."
            )
        if version > GESTURE_FORMAT_VERSION:
            raise ValueError(
                f"This recording uses format version {version}, but this build only "
                f"understands up to {GESTURE_FORMAT_VERSION}. Update mthread to open it."
            )
        screen = data.get("screen_size")
        return cls(
            strokes=[Stroke.from_list(rows) for rows in data.get("strokes", [])],
            screen_size=tuple(screen) if screen else None,
            device_model=data.get("device_model", ""),
            device_serial=data.get("device_serial", ""),
            created_at=data.get("created_at", ""),
            note=data.get("note", ""),
            version=version,
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "GestureSession":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
