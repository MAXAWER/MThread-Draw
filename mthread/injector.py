"""Drive the on-device touch injector.

Why this exists is in ``injector/src/com/mthread/Injector.java``: on a phone
where the shell user cannot write to ``/dev/input``, the only other way in is
the framework, and the ``input`` command pays a whole process - about 110 ms -
for every single point. That is not a pacing problem that can be tuned away. A
sixty-point stroke takes seven seconds, and nothing that takes seven seconds
looks like a hand.

The injector is started once, and then points are streamed to it over stdin. It
injects them itself, in microseconds, and sleeps between them for exactly as
long as we ask. That turns timing from something the transport imposes into
something we choose, which is what makes both of the interesting cases possible:
drawing as fast as the screen can take it, and drawing at the speed of a hand.
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .adb import no_window_kwargs
from .errors import MThreadError

__all__ = ["InjectorUnavailableError", "Pacing", "TouchInjector", "pace_stroke"]

REMOTE_JAR = "/data/local/tmp/mthread-injector.jar"
JAR_NAME = "injector.jar"


class InjectorUnavailableError(MThreadError):
    """The device would not run the injector; the caller should fall back."""


def bundled_jar() -> Path | None:
    """The jar shipped with the library, wherever it ended up.

    It sits beside this module in a source checkout and in a wheel. In a
    PyInstaller build the data files are unpacked somewhere else entirely, so
    that is checked too.
    """
    here = Path(__file__).resolve().parent / JAR_NAME
    if here.is_file():
        return here

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for candidate in (Path(meipass) / "mthread" / JAR_NAME, Path(meipass) / JAR_NAME):
            if candidate.is_file():
                return candidate
    return None


@dataclass(frozen=True)
class Pacing:
    """How fast the pen moves, in the units a hand thinks in.

    Attributes:
        speed: Pen speed along a stroke, in pixels per second. A person drawing
            on a phone runs somewhere around 600 to 1500.
        ease: How much slower the pen is at the two ends of a stroke than in the
            middle, from 0 to 1.
        curvature_drag: How much a tight curve slows the pen.
        min_step_ms / max_step_ms: Bounds on the wait between two points. The
            floor keeps a fast stroke from becoming a flood of events the
            compositor drops; the ceiling stops a hairpin from stalling.
        lift_ms: Pen-up time between strokes, before travel is added.
        travel_speed: How fast the hand crosses the gap between two strokes,
            in pixels per second.
        jitter: Proportional randomness on every wait, so the rhythm is not
            metronomic.
        batch: How many points to deliver per event, as history, instead of one
            event each. 0 sends them one at a time, which every app understands.
            Higher is faster and stops being universal: the extra samples only
            arrive for apps that read them, and the input pipeline drops the
            tail of an over-long batch.
    """

    speed: float = 1100.0
    ease: float = 0.55
    curvature_drag: float = 0.6
    min_step_ms: float = 4.0
    max_step_ms: float = 45.0
    lift_ms: float = 90.0
    travel_speed: float = 2600.0
    jitter: float = 0.18
    batch: int = 0

    @classmethod
    def instant(cls) -> "Pacing":
        """Immediate: the whole stroke inside one event, waiting for nothing.

        Sending points one at a time cannot be instant, because the receiving
        app samples input per frame and everything delivered between two frames
        collapses into one position. A single event carrying the stroke as
        history sidesteps that entirely - which is exactly how a 240 Hz
        digitizer talks to an app drawing at 120.
        """
        return cls(speed=1e9, ease=0.0, curvature_drag=0.0, min_step_ms=1.0,
                   max_step_ms=1.0, lift_ms=2.0, travel_speed=1e9, jitter=0.0)


def pace_stroke(points, pacing: Pacing, rng: random.Random) -> list[float]:
    """Work out how long to wait after each point of a stroke.

    Distance over speed, with the pen slowing at both ends and through curves -
    the same velocity profile a hand has, expressed here as time rather than as
    point spacing, because with the injector the time is ours to set.
    """
    if len(points) < 2 or pacing.max_step_ms <= 0:
        return [0.0] * len(points)

    segments = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(segments) or 1.0

    delays: list[float] = []
    travelled = 0.0
    for index, length in enumerate(segments):
        travelled += length
        u = travelled / total

        # Clamp before the fractional power: rounding can push u a hair
        # past 1, and a negative base raised to 0.7 is a complex number.
        envelope = 1.0 - pacing.ease * (1.0 - max(0.0, math.sin(math.pi * u)) ** 0.7)

        turn = 0.0
        if 0 < index < len(segments) - 1:
            ax = points[index][0] - points[index - 1][0]
            ay = points[index][1] - points[index - 1][1]
            bx = points[index + 1][0] - points[index][0]
            by = points[index + 1][1] - points[index][1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            if la > 1e-6 and lb > 1e-6:
                cosine = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
                turn = math.acos(cosine) / math.pi

        speed = pacing.speed * max(0.12, envelope) / (1.0 + pacing.curvature_drag * turn * 5.0)
        step = length / max(speed, 1.0) * 1000.0
        if pacing.jitter:
            step *= 1.0 + rng.uniform(-pacing.jitter, pacing.jitter)
        delays.append(max(pacing.min_step_ms, min(pacing.max_step_ms, step)))

    delays.append(0.0)
    return delays


class TouchInjector:
    """A live injector process on the device.

    Use it as a context manager; it starts the process, waits for its READY,
    and shuts it down again on the way out::

        with TouchInjector(device) as pen:
            pen.stroke([(100, 200), (400, 200)], Pacing())
    """

    def __init__(self, device, jar: Path | None = None):
        self.device = device
        self.jar = Path(jar) if jar else bundled_jar()
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ start

    def start(self) -> None:
        if self.jar is None or not self.jar.is_file():
            raise InjectorUnavailableError(
                "The injector jar is missing. Build it with "
                "`python tools/build_injector.py`, or draw with method='input'."
            )

        self.device.adb("push", str(self.jar), REMOTE_JAR, timeout=60.0)

        command = [
            self.device.adb_path, "-s", self.device.serial, "shell",
            f"CLASSPATH={REMOTE_JAR} app_process / com.mthread.Injector",
        ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **no_window_kwargs(),
        )

        greeting = (self.process.stdout.readline() or "").strip()
        if greeting != "READY":
            detail = greeting or "the process produced no output"
            self.close()
            raise InjectorUnavailableError(f"The injector would not start: {detail}")

    # ------------------------------------------------------------------ using

    def _write(self, lines) -> None:
        if self.process is None or self.process.poll() is not None:
            raise InjectorUnavailableError("The injector is not running.")
        self.process.stdin.write("\n".join(lines) + "\n")
        self.process.stdin.flush()

    def stroke(self, points, pacing: Pacing | None = None,
               rng: random.Random | None = None) -> float:
        """Draw one stroke, waiting between points as *pacing* says to.

        Returns how many milliseconds of work were handed to the device, which
        the caller needs in order to know how far ahead of the drawing it has
        run. Writing is nearly free; the waiting all happens on the phone.
        """
        if len(points) < 2:
            return 0.0
        pacing = pacing or Pacing()
        rng = rng or random.Random()
        delays = pace_stroke(points, pacing, rng)

        if pacing.batch > 1:
            # Chunks, not the whole stroke: an event can carry its earlier
            # samples, but the pipeline drops the tail of a very long batch and
            # not every app reads history at all.
            lines = [f"D {points[0][0]:.1f} {points[0][1]:.1f}"]
            rest = points[1:]
            for start in range(0, len(rest), pacing.batch):
                chunk = rest[start:start + pacing.batch]
                lines += [f"H {x:.1f} {y:.1f}" for x, y in chunk[:-1]]
                lines.append(f"M {chunk[-1][0]:.1f} {chunk[-1][1]:.1f}")
            lines.append(f"U {points[-1][0]:.1f} {points[-1][1]:.1f}")
        else:
            lines = [f"D {points[0][0]:.1f} {points[0][1]:.1f}"]
            for (x, y), delay in zip(points[1:], delays):
                if delay > 0.05:
                    lines.append(f"S {delay:.2f}")
                lines.append(f"M {x:.1f} {y:.1f}")
            lines.append(f"U {points[-1][0]:.1f} {points[-1][1]:.1f}")

        with self._lock:
            self._write(lines)
        return float(sum(delays))

    def timed_stroke(self, points, delays) -> float:
        """Draw a stroke whose waits are given rather than computed.

        Replay needs the timing that was recorded, not the timing a pacing model
        would invent, so this takes the gaps as they were measured.
        """
        if len(points) < 2:
            return 0.0
        lines = [f"D {points[0][0]:.1f} {points[0][1]:.1f}"]
        total = 0.0
        for (x, y), delay in zip(points[1:], list(delays) + [0.0] * len(points)):
            if delay > 0.05:
                lines.append(f"S {delay:.2f}")
                total += delay
            lines.append(f"M {x:.1f} {y:.1f}")
        lines.append(f"U {points[-1][0]:.1f} {points[-1][1]:.1f}")
        with self._lock:
            self._write(lines)
        return total

    def pause(self, millis: float) -> float:
        if millis > 0.05:
            with self._lock:
                self._write([f"S {millis:.2f}"])
            return float(millis)
        return 0.0

    def sync(self, timeout: float = 600.0) -> None:
        """Block until everything sent so far has been injected.

        The injector reads its commands from a pipe, so a write returning says
        nothing about the drawing being finished; this asks it to answer once it
        has worked through the backlog.
        """
        with self._lock:
            self._write(["P"])
            if self.process is None:
                return
            reply = (self.process.stdout.readline() or "").strip()
        if reply.startswith("ERR"):
            raise MThreadError(f"The injector reported: {reply}")

    # ------------------------------------------------------------------- stop

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin:
                process.stdin.write("Q\n")
                process.stdin.flush()
                process.stdin.close()
            process.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            process.kill()

    def __enter__(self) -> "TouchInjector":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
