"""Live view of the device screen.

The work is done on the phone by ``com.mthread.Mirror`` in the same jar the
touch injector uses; see that class for why. The short version: capturing costs
about 300 ms and everything else - PNG encoding on the device, or sixteen
megabytes of framebuffer over the cable - costs seconds, so the phone scales
and JPEG-compresses before anything is sent.

    with ScreenMirror(device) as mirror:
        jpeg = mirror.frame()

Pull-based on purpose. One request, one frame: a slow reader gets fewer frames
rather than a growing backlog of stale ones.
"""

from __future__ import annotations

import base64
import subprocess
import threading
from pathlib import Path

from .adb import no_window_kwargs
from .errors import MThreadError
from .injector import REMOTE_JAR, bundled_jar

__all__ = ["MirrorUnavailableError", "ScreenMirror"]


class MirrorUnavailableError(MThreadError):
    """The mirror could not be started on the device."""


class ScreenMirror:
    """A capture process living on the device, asked for one frame at a time."""

    def __init__(self, device, jar: Path | None = None,
                 max_width: int = 480, quality: int = 60):
        self.device = device
        self.jar = Path(jar) if jar else bundled_jar()
        self.max_width = max_width
        self.quality = quality
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def __enter__(self) -> "ScreenMirror":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------ start

    def start(self) -> None:
        if self.jar is None or not self.jar.is_file():
            raise MirrorUnavailableError(
                "The injector jar is missing. Build it with "
                "`python tools/build_injector.py`.")

        self.device.adb("push", str(self.jar), REMOTE_JAR, timeout=60.0)
        self.process = subprocess.Popen(
            # "shell -T", and neither of the two obvious alternatives.
            #
            # Plain "shell" allocates a pty, a pty turns every line feed into a
            # carriage return and a line feed, and a JPEG is full of 0x0A bytes:
            # the image arrives longer than it left and is no longer an image.
            # The first frame looks like it worked and every frame after it is
            # out of step by however many newlines the first one contained.
            #
            # "exec-out" has no pty and is the usual answer for binary output,
            # but it is output only - stdin never reaches the process, so the
            # first request is never heard and it hangs after READY.
            #
            # -T asks for no pty on a channel that still carries both.
            [self.device.adb_path, "-s", self.device.serial, "shell", "-T",
             f"CLASSPATH={REMOTE_JAR} app_process / com.mthread.Mirror"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **no_window_kwargs(),
        )

        greeting = self._readline()
        if greeting != b"READY":
            self.close()
            raise MirrorUnavailableError(
                f"The mirror would not start: {greeting.decode('utf-8', 'replace') or 'no output'}")

    # ------------------------------------------------------------------ using

    def frame(self) -> bytes:
        """Capture one frame and return it as JPEG bytes."""
        with self._lock:
            if self.process is None or self.process.poll() is not None:
                raise MirrorUnavailableError("The mirror is not running.")

            self.process.stdin.write(f"{self.max_width} {self.quality}\n".encode())
            self.process.stdin.flush()

            reply = self._readline()
            if not reply.startswith(b"F "):
                raise MirrorUnavailableError(
                    reply.decode("utf-8", "replace") or "the mirror stopped answering")
            return base64.b64decode(reply[2:])

    def close(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.stdin.write(b"Q\n")
                self.process.stdin.flush()
                self.process.wait(timeout=3)
        except Exception:
            pass
        finally:
            if self.process.poll() is None:
                self.process.kill()
            self.process = None

    # ----------------------------------------------------------------- pipes

    def _readline(self) -> bytes:
        """Read one line, tolerating whatever adb did to the line ending."""
        out = bytearray()
        while True:
            char = self.process.stdout.read(1)
            if not char:
                return bytes(out).strip()
            if char == b"\n":
                return bytes(out).strip()
            out += char

