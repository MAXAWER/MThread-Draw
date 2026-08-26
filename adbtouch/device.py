"""High level control of a single Android device over ADB."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from typing import Iterable, Sequence

from .adb import find_adb, popen_adb, run_adb
from .errors import DeviceNotConnectedError, TouchDeviceNotFoundError
from .touch import TouchDevice, build_stroke_events, parse_getevent_pl, pick_touchscreen

__all__ = ["DeviceInfo", "Device", "list_devices"]

_SIZE_RE = re.compile(r"(\d+)x(\d+)")
#: Remote scratch directory that is writable by the shell user on every Android release.
REMOTE_TMP = "/data/local/tmp"


@dataclass(frozen=True)
class DeviceInfo:
    """A device as reported by ``adb devices``."""

    serial: str
    state: str

    @property
    def is_ready(self) -> bool:
        return self.state == "device"

    @property
    def human_state(self) -> str:
        return {
            "device": "ready",
            "offline": "offline - reconnect the cable",
            "unauthorized": "unauthorized - confirm the USB debugging prompt on the phone",
        }.get(self.state, self.state)


def list_devices(adb_path: str | None = None) -> list[DeviceInfo]:
    """Return every device ``adb`` currently knows about, ready or not."""
    adb = adb_path or find_adb()
    proc = run_adb(adb, ["devices"])
    devices: list[DeviceInfo] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append(DeviceInfo(serial=parts[0], state=parts[1]))
    return devices


class Device:
    """A connected Android device.

    Args:
        serial: Device serial. When omitted the first ready device is used.
        adb_path: Explicit path to ``adb``; discovered automatically otherwise.
    """

    def __init__(self, serial: str | None = None, adb_path: str | None = None):
        self.adb_path = adb_path or find_adb()
        if serial is None:
            ready = [d for d in list_devices(self.adb_path) if d.is_ready]
            if not ready:
                raise DeviceNotConnectedError(
                    "No device is ready. Check the cable, enable USB debugging, "
                    "and accept the authorisation prompt on the phone."
                )
            serial = ready[0].serial
        self.serial = serial
        self._touch_device: TouchDevice | None = None
        self._screen_size: tuple[int, int] | None = None

    # ------------------------------------------------------------------ basics

    def _args(self, extra: Sequence) -> list:
        return ["-s", self.serial, *extra]

    def adb(self, *command, timeout: float | None = 30.0, check: bool = True):
        """Run an ``adb`` command against this device.

        For the subcommands that are not shell commands - ``reverse``,
        ``forward``, ``install``, ``push`` - which callers would otherwise have
        to assemble the ``-s <serial>`` themselves for.
        """
        return run_adb(self.adb_path, self._args(command), timeout=timeout, check=check)

    def shell(self, *command, timeout: float | None = 30.0, check: bool = True):
        """Run a shell command on the device and return the completed process."""
        return run_adb(self.adb_path, self._args(["shell", *command]), timeout=timeout, check=check)

    @property
    def screen_size(self) -> tuple[int, int]:
        """Display size in pixels, honouring an active ``wm size`` override."""
        if self._screen_size is None:
            out = self.shell("wm", "size").stdout
            physical = override = None
            for line in out.splitlines():
                match = _SIZE_RE.search(line)
                if not match:
                    continue
                value = (int(match.group(1)), int(match.group(2)))
                if "Override size" in line:
                    override = value
                elif "Physical size" in line:
                    physical = value
            size = override or physical
            if size is None:
                raise DeviceNotConnectedError(f"Could not read the screen size from: {out!r}")
            self._screen_size = size
        return self._screen_size

    def screenshot(self, local_path: str) -> str:
        """Capture the screen straight into *local_path* and return that path."""
        proc = run_adb(
            self.adb_path,
            self._args(["exec-out", "screencap", "-p"]),
            timeout=60.0,
            binary=True,
        )
        with open(local_path, "wb") as handle:
            handle.write(proc.stdout)
        return local_path

    def set_pointer_location(self, enabled: bool) -> None:
        """Toggle the developer-option touch overlay, handy for calibration."""
        self.shell("settings", "put", "system", "pointer_location", "1" if enabled else "0", check=False)

    # ------------------------------------------------------------- script exec

    def run_script(self, lines: Iterable[str], *, timeout: float | None = 600.0) -> None:
        """Push a shell script to the device and execute it in one round trip.

        Batching matters: each ``adb shell`` invocation costs 100-300 ms, so
        issuing thousands of individual commands is orders of magnitude slower
        than shipping one script. The local file is created in the system temp
        directory and the remote name is unique, so concurrent runs never clash.
        """
        body = "#!/system/bin/sh\n" + "\n".join(lines) + "\n"
        remote = f"{REMOTE_TMP}/adbtouch_{uuid.uuid4().hex}.sh"

        handle = tempfile.NamedTemporaryFile("w", suffix=".sh", newline="\n", delete=False, encoding="utf-8")
        try:
            handle.write(body)
            handle.close()
            run_adb(self.adb_path, self._args(["push", handle.name, remote]), timeout=120.0)
            try:
                run_adb(self.adb_path, self._args(["shell", "sh", remote]), timeout=timeout)
            finally:
                run_adb(self.adb_path, self._args(["shell", "rm", "-f", remote]), check=False, timeout=30.0)
        finally:
            try:
                os.unlink(handle.name)
            except OSError:
                pass

    # ------------------------------------------------------------ simple input

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 100) -> None:
        self.shell("input", "swipe", *[str(int(v)) for v in (x1, y1, x2, y2, duration_ms)])

    # ------------------------------------------------------------- touch layer

    @property
    def touch_device(self) -> TouchDevice:
        """The detected touchscreen, including its own coordinate ranges."""
        if self._touch_device is None:
            devices = self.input_devices()
            picked = pick_touchscreen(devices)
            if picked is None:
                raise TouchDeviceNotFoundError(
                    "No touchscreen was found in `getevent -pl` output. "
                    "Raw touch input is unavailable; the slower `input swipe` path still works."
                )
            self._touch_device = picked
        return self._touch_device

    def input_devices(self) -> list[TouchDevice]:
        """Every ``/dev/input`` device the phone exposes, with its axis ranges."""
        out = self.shell("getevent", "-pl", timeout=20.0).stdout
        return parse_getevent_pl(out)

    def draw_paths(
        self,
        paths: Sequence[Sequence[tuple[float, float]]],
        *,
        point_delay_ms: int = 0,
        stroke_delay_ms: int = 20,
        chunk_size: int = 4000,
        progress=None,
        should_continue=None,
    ) -> int:
        """Draw *paths* (display pixel coordinates) using raw touch events.

        Returns the number of strokes actually sent. Pass *should_continue* to
        support cancellation; it is polled once per stroke.
        """
        width, height = self.screen_size
        device = self.touch_device
        lines: list[str] = []
        sent = 0

        for index, path in enumerate(paths, start=1):
            if should_continue is not None and not should_continue():
                break
            if len(path) < 2:
                continue
            events = build_stroke_events(device, path, width, height, tracking_id=index)
            for etype, code, value in events:
                lines.append(f"sendevent {device.path} {etype} {code} {value}")
                if point_delay_ms and etype == 0:
                    lines.append(f"sleep {point_delay_ms / 1000:.3f}")
            if stroke_delay_ms:
                lines.append(f"sleep {stroke_delay_ms / 1000:.3f}")
            sent += 1

            if len(lines) >= chunk_size:
                self.run_script(lines)
                lines = []
                if progress is not None:
                    progress(index, len(paths))

        if lines:
            self.run_script(lines)
        if progress is not None:
            progress(len(paths), len(paths))
        return sent

    # ----------------------------------------------------------------- streams

    def stream_getevent(self):
        """Start ``getevent -t`` and return the live process for the recorder."""
        return popen_adb(self.adb_path, self._args(["shell", "getevent", "-t"]))
