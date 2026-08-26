"""Recording raw input events from a device with ``getevent -t``."""

from __future__ import annotations

import re
import threading
from typing import Callable

from .session import InputEvent, Session

__all__ = ["parse_getevent_line", "Recorder"]

# Example line:  [   12345.678901] /dev/input/event2: 0003 0039 00000001
_EVENT_RE = re.compile(
    r"^\[\s*(?P<time>\d+\.\d+)\s*\]\s*(?P<device>[^:\s]+):\s*"
    r"(?P<type>[0-9a-fA-F]+)\s+(?P<code>[0-9a-fA-F]+)\s+(?P<value>[0-9a-fA-F]+)\s*$"
)


def _to_signed32(raw: int) -> int:
    """Interpret a 32-bit hex field as signed, so a released touch reads as -1."""
    return raw - 0x1_0000_0000 if raw >= 0x8000_0000 else raw


def parse_getevent_line(line: str):
    """Parse one ``getevent -t`` line into ``(timestamp, device, type, code, value)``.

    Returns ``None`` for banners, blank lines and anything else non-numeric.
    """
    match = _EVENT_RE.match(line.strip())
    if not match:
        return None
    return (
        float(match.group("time")),
        match.group("device"),
        int(match.group("type"), 16),
        int(match.group("code"), 16),
        _to_signed32(int(match.group("value"), 16)),
    )


class Recorder:
    """Captures device input in the background until stopped.

    Timestamps are rebased so the first event sits at ``t = 0``, which makes a
    recording replayable regardless of how long the device had been up.

    Args:
        device: A connected :class:`~mthread.device.Device`.
        only_devices: Restrict capture to these ``/dev/input`` paths. Defaults to
            the detected touchscreen so stray button presses are not recorded.
        on_event: Optional callback invoked for every captured event, useful for
            driving a live counter in a UI.
    """

    def __init__(self, device, only_devices=None, on_event: Callable[[InputEvent], None] | None = None):
        self.device = device
        self.on_event = on_event
        if only_devices is None:
            try:
                only_devices = [device.touch_device.path]
            except Exception:
                only_devices = None
        self.only_devices = set(only_devices) if only_devices else None

        self._process = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._events: list[InputEvent] = []
        self._origin: float | None = None
        self.error: str | None = None

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def start(self) -> None:
        """Begin capturing. Does nothing if a capture is already running."""
        if self.is_recording:
            return
        with self._lock:
            self._events = []
        self._origin = None
        self.error = None
        self._stop.clear()
        self._process = self.device.stream_getevent()
        self._thread = threading.Thread(target=self._pump, name="mthread-recorder", daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            for line in self._process.stdout:
                if self._stop.is_set():
                    break
                parsed = parse_getevent_line(line)
                if parsed is None:
                    continue
                timestamp, path, etype, code, value = parsed
                if self.only_devices and path not in self.only_devices:
                    continue
                if self._origin is None:
                    self._origin = timestamp
                event = InputEvent(
                    t=max(0.0, timestamp - self._origin),
                    device=path,
                    type=etype,
                    code=code,
                    value=value,
                )
                with self._lock:
                    self._events.append(event)
                if self.on_event is not None:
                    self.on_event(event)
        except Exception as exc:  # pragma: no cover - depends on live hardware
            self.error = str(exc)

    def stop(self) -> Session:
        """Stop capturing and return the recorded :class:`Session`."""
        self._stop.set()
        if self._process is not None:
            for terminate in (self._process.terminate, self._process.kill):
                try:
                    terminate()
                    self._process.wait(timeout=3)
                    break
                except Exception:
                    continue
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._thread = None
        self._process = None

        with self._lock:
            events = list(self._events)

        session = Session(events=events, device_serial=getattr(self.device, "serial", ""))
        try:
            session.screen_size = self.device.screen_size
        except Exception:
            session.screen_size = None
        return session
