"""High level control of a single Android device over ADB."""

from __future__ import annotations

import os
import math
import random
import re
import tempfile
import uuid
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from .adb import find_adb, popen_adb, run_adb
from .errors import DeviceNotConnectedError, TouchDeviceNotFoundError
from .hand import HandSettings, simulate
from .injector import InjectorUnavailableError, Pacing, TouchInjector
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


def restart_server(adb_path: str | None = None) -> None:
    """Stop and start the adb daemon.

    The daemon can end up running but enumerating nothing - it was started
    before the USB driver settled, or another copy of adb on the machine claimed
    port 5037 first. ``adb devices`` then reports an empty list for a phone that
    is plugged in and working, and no amount of asking again helps.

    Only worth doing when the list came back empty: killing the daemon
    disconnects anything else using it, Android Studio included.
    """
    adb = adb_path or find_adb()
    run_adb(adb, ["kill-server"], check=False)
    run_adb(adb, ["start-server"], check=False)


def find_devices(adb_path: str | None = None) -> list[DeviceInfo]:
    """List devices, reviving a wedged daemon once before giving up."""
    adb = adb_path or find_adb()
    devices = list_devices(adb)
    if devices:
        return devices
    restart_server(adb)
    return list_devices(adb)


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
        self._supports_raw: bool | None = None
        #: Set when the injector refused to start and the slow path was used.
        self.injector_error = False

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
        remote = f"{REMOTE_TMP}/mthread_{uuid.uuid4().hex}.sh"

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

    @property
    def supports_raw_touch(self) -> bool:
        """Whether this device lets the shell user write to ``/dev/input``.

        On a Pixel running a recent Android it does not, and not because of file
        permissions: the node is ``crw-rw---- root input`` and the shell user is
        in the ``input`` group, but SELinux denies the ``shell`` domain the write
        anyway. ``sendevent`` then fails per line with "Permission denied" while
        the script as a whole exits cleanly - which looks exactly like a program
        that draws nothing for no reason.

        So it is probed once, with a bare ``SYN_REPORT`` that changes nothing
        even where it does land.
        """
        if self._supports_raw is None:
            try:
                path = self.touch_device.path
            except TouchDeviceNotFoundError:
                self._supports_raw = False
                return self._supports_raw
            proc = self.shell("sendevent", path, "0", "0", "0", check=False)
            output = (proc.stdout or "") + (proc.stderr or "")
            self._supports_raw = proc.returncode == 0 and "denied" not in output.lower()
        return self._supports_raw

    def input_devices(self) -> list[TouchDevice]:
        """Every ``/dev/input`` device the phone exposes, with its axis ranges."""
        out = self.shell("getevent", "-pl", timeout=20.0).stdout
        return parse_getevent_pl(out)

    def draw_paths(
        self,
        paths: Sequence[Sequence[tuple[float, float]]],
        *,
        method: str = "auto",
        speed: float = 1.0,
        human: float = 0.0,
        seed: int | None = None,
        hand_settings: HandSettings | None = None,
        pacing: Pacing | None = None,
        point_delay_ms: int = 0,
        stroke_delay_ms: int = 20,
        chunk_size: int = 4000,
        progress=None,
        should_continue=None,
    ) -> int:
        """Draw *paths* (display pixel coordinates) and return the strokes sent.

        Args:
            method: ``"raw"`` writes kernel events directly. ``"injector"``
                streams points to a small process running on the device, which
                is the only path where the time between points is ours to
                choose - and therefore the only one that can look like a hand.
                ``"input"`` shells out to the ``input`` command once per point,
                which needs nothing installed but costs about 110 ms each.
                ``"auto"`` takes raw where it is allowed, the injector where it
                is not, and ``input`` if even that fails.
            speed: Multiplier on the pacing. Above 1 draws faster, below 1
                slower. It cannot make ``"input"`` quick - that path costs about
                a tenth of a second per point whatever happens - but it does let
                either path be slowed to something a person could have done.
            human: 0 draws the geometry exactly. Above 0 hands the paths to
                :func:`mthread.hand.simulate`, which rounds the corners, varies
                the pen speed, adds tremor, overshoots the ends and reorders the
                strokes into the sequence a person would use. 1.0 is a steady
                hand, 3.0 a careless one. Note that it changes the point count,
                and so the time the drawing takes.
            hand_settings: Full control over the simulation; see
                :class:`mthread.hand.HandSettings`.
            pacing: Timing for the injector path; see
                :class:`mthread.injector.Pacing`. Defaults to hand speed when
                *human* is set and to as-fast-as-possible when it is not.
            seed: Fixes the randomness, so a "human" drawing can be repeated.
            progress: Called with ``(done, total)`` as strokes are sent.
            should_continue: Polled once per stroke; return False to stop.
        """
        if method not in ("auto", "raw", "input", "injector"):
            raise ValueError(f"unknown drawing method {method!r}")
        if method == "auto":
            method = "raw" if self.supports_raw_touch else "injector"

        shaped = simulate(paths, human, seed, hand_settings) if human else paths

        if method == "raw":
            return self._draw_paths_raw(
                shaped, speed=speed, point_delay_ms=point_delay_ms,
                stroke_delay_ms=stroke_delay_ms, chunk_size=chunk_size,
                progress=progress, should_continue=should_continue,
            )

        if method == "injector":
            try:
                return self._draw_paths_injector(
                    shaped, speed=speed, human=human, seed=seed, pacing=pacing,
                    progress=progress, should_continue=should_continue,
                )
            except InjectorUnavailableError:
                # Nothing about a device guarantees app_process will run a jar
                # for us. The slow path always works, so say so and take it.
                self.injector_error = True

        return self._draw_paths_input(
            shaped, speed=speed, human=human, seed=seed, stroke_delay_ms=stroke_delay_ms,
            progress=progress, should_continue=should_continue,
        )

    def _draw_paths_injector(
        self,
        paths,
        *,
        speed: float = 1.0,
        human: float = 0.0,
        seed: int | None = None,
        pacing: Pacing | None = None,
        progress=None,
        should_continue=None,
    ) -> int:
        """Draw through the on-device injector, one process for the whole job.

        This is the path where timing is real. Points are streamed to a process
        that is already running, so the wait between them is whatever we ask for
        rather than however long it takes to start another one.
        """
        width, height = self.screen_size
        rng = random.Random(seed)

        if pacing is None:
            pacing = Pacing() if human else Pacing.instant()
        if speed and speed != 1.0 and pacing.speed < 1e8:
            pacing = replace(pacing, speed=pacing.speed * speed,
                             travel_speed=pacing.travel_speed * speed)

        def clamp(point):
            return (max(0.0, min(width - 1.0, float(point[0]))),
                    max(0.0, min(height - 1.0, float(point[1]))))

        sent = 0
        pen = None
        with TouchInjector(self) as injector:
            for index, path in enumerate(paths, start=1):
                if should_continue is not None and not should_continue():
                    break
                if len(path) < 2:
                    continue

                points = [clamp(point) for point in path]
                if pen is not None and pacing.lift_ms:
                    # The hand has to get there. Longer gaps take longer.
                    travel = math.dist(pen, points[0]) / max(pacing.travel_speed, 1.0) * 1000.0
                    injector.pause(pacing.lift_ms + travel)

                injector.stroke(points, pacing, rng)
                pen = points[-1]
                sent += 1

                if progress is not None and index % 8 == 0:
                    progress(index, len(paths))

            injector.sync()

        if progress is not None:
            progress(len(paths), len(paths))
        return sent

    def _draw_paths_raw(
        self,
        paths,
        *,
        speed: float = 1.0,
        point_delay_ms: int = 0,
        stroke_delay_ms: int = 20,
        chunk_size: int = 4000,
        progress=None,
        should_continue=None,
    ) -> int:
        """Draw by writing kernel input events, batched into pushed scripts."""
        width, height = self.screen_size
        device = self.touch_device
        scale = 1.0 / max(speed, 0.01)
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
                    lines.append(f"sleep {point_delay_ms * scale / 1000:.3f}")
            if stroke_delay_ms:
                lines.append(f"sleep {stroke_delay_ms * scale / 1000:.3f}")
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

    def _draw_paths_input(
        self,
        paths,
        *,
        speed: float = 1.0,
        human: float = 0.0,
        seed: int | None = None,
        stroke_delay_ms: int = 20,
        strokes_per_script: int = 12,
        progress=None,
        should_continue=None,
    ) -> int:
        """Draw through ``input motionevent``, for devices that refuse raw events.

        Each ``input`` invocation starts a process on the device and costs
        roughly a tenth of a second, so the commands are batched into pushed
        scripts exactly as the raw path batches its events. Separate invocations
        still join into one gesture - the DOWN, the MOVEs and the UP arrive as
        one continuous stroke - which is what makes a polyline possible here at
        all, rather than a row of disconnected segments.
        """
        width, height = self.screen_size
        rng = random.Random(seed)
        scale = 1.0 / max(speed, 0.01)
        lines: list[str] = []
        sent = 0
        pending = 0

        def clamp(value: float, limit: int) -> int:
            return max(0, min(limit - 1, int(round(value))))

        for index, path in enumerate(paths, start=1):
            if should_continue is not None and not should_continue():
                break
            if len(path) < 2:
                continue

            points = [(clamp(x, width), clamp(y, height)) for x, y in path]
            lines.append(f"input motionevent DOWN {points[0][0]} {points[0][1]}")
            for x, y in points[1:]:
                lines.append(f"input motionevent MOVE {x} {y}")
            lines.append(f"input motionevent UP {points[-1][0]} {points[-1][1]}")

            pause = stroke_delay_ms * scale / 1000
            if human:
                pause += rng.uniform(0, 0.12 * human)
            if pause > 0.001:
                lines.append(f"sleep {pause:.3f}")

            sent += 1
            pending += 1
            if pending >= strokes_per_script:
                self.run_script(lines)
                lines = []
                pending = 0
                if progress is not None:
                    progress(index, len(paths))

        if lines:
            self.run_script(lines)
        if progress is not None:
            progress(len(paths), len(paths))
        return sent

    def estimate_duration(self, paths, *, method: str = "auto", speed: float = 1.0,
                          human: float = 0.0) -> float:
        """Roughly how many seconds :meth:`draw_paths` will take.

        Worth showing before starting: on the ``input`` path a detailed picture
        is minutes of work, and a progress bar that appears to have frozen is
        indistinguishable from one that has.
        """
        if method == "auto":
            method = "raw" if self.supports_raw_touch else "injector"
        points = sum(len(path) for path in paths if len(path) >= 2)
        strokes = sum(1 for path in paths if len(path) >= 2)
        if method == "input":
            # Measured on a Pixel 8 Pro: one `input` process costs about 110 ms.
            return (points + strokes * 2) * 0.11 / max(speed, 0.01)
        if method == "injector":
            # Two seconds to start the process, then whatever pacing asks for.
            per_point = 0.012 if human else 0.0015
            return 2.0 + (points * per_point + strokes * 0.12 * bool(human)) / max(speed, 0.01)
        return (strokes * 0.02 + points * 0.0004) / max(speed, 0.01)

    # ----------------------------------------------------------------- streams

    def stream_getevent(self):
        """Start ``getevent -t`` and return the live process for the recorder."""
        return popen_adb(self.adb_path, self._args(["shell", "getevent", "-t"]))
