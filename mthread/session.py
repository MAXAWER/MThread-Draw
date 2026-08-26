"""The on-disk format for recorded input sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["InputEvent", "Session", "SESSION_FORMAT_VERSION"]

#: Bumped whenever the file layout changes in a way older readers cannot handle.
SESSION_FORMAT_VERSION = 1


@dataclass
class InputEvent:
    """A single kernel input event, timed relative to the start of the recording."""

    t: float
    device: str
    type: int
    code: int
    value: int

    def as_list(self) -> list:
        return [round(self.t, 6), self.device, self.type, self.code, self.value]

    @classmethod
    def from_list(cls, row) -> "InputEvent":
        t, device, etype, code, value = row
        return cls(t=float(t), device=str(device), type=int(etype), code=int(code), value=int(value))


@dataclass
class Session:
    """A recording of everything the user did on the device.

    Events are stored as compact lists rather than objects: a minute of touch
    input is easily 50k events, and the array-of-objects form triples the file
    size for no benefit.
    """

    events: list[InputEvent] = field(default_factory=list)
    screen_size: tuple[int, int] | None = None
    device_serial: str = ""
    device_model: str = ""
    created_at: str = ""
    note: str = ""
    version: int = SESSION_FORMAT_VERSION

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def duration(self) -> float:
        return self.events[-1].t if self.events else 0.0

    @property
    def devices(self) -> list[str]:
        seen: dict[str, None] = {}
        for event in self.events:
            seen.setdefault(event.device, None)
        return list(seen)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "device_serial": self.device_serial,
            "device_model": self.device_model,
            "screen_size": list(self.screen_size) if self.screen_size else None,
            "note": self.note,
            "duration": round(self.duration, 6),
            "event_count": len(self.events),
            "events": [event.as_list() for event in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        version = int(data.get("version", 1))
        if version > SESSION_FORMAT_VERSION:
            raise ValueError(
                f"This recording uses format version {version}, but this build only understands "
                f"up to {SESSION_FORMAT_VERSION}. Update mthread to open it."
            )
        screen = data.get("screen_size")
        return cls(
            events=[InputEvent.from_list(row) for row in data.get("events", [])],
            screen_size=tuple(screen) if screen else None,
            device_serial=data.get("device_serial", ""),
            device_model=data.get("device_model", ""),
            created_at=data.get("created_at", ""),
            note=data.get("note", ""),
            version=version,
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
