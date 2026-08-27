"""The engine, driven over a pipe, so a native interface can be a thin one.

    python -m mthread_draw.server

Reads one JSON request per line on stdin and writes one JSON message per line
on stdout. That is the whole protocol, and it is deliberately the dullest thing
that could work: a Windows front end written in C# should not need to
understand tracing, ADB or touch injection, and this project should not need a
second implementation of any of them in another language.

Requests look like::

    {"id": 1, "op": "connect"}
    {"id": 2, "op": "preview", "sensitivity": 5, "detail": 7, "method": "canny"}

Replies carry the same id::

    {"id": 1, "ok": true, "result": {"serial": "...", "width": 1344, ...}}
    {"id": 2, "ok": false, "error": "No device is ready."}

Anything without an id is an event, sent while a long operation runs::

    {"event": "progress", "done": 120, "total": 540}
    {"event": "status", "text": "Drawing 540 strokes"}

Operations that take time - preview, draw - run on a worker thread, so that
"stop" arrives while there is still something to stop.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from PIL import Image, ImageDraw

from mthread import Device, VectorizeSettings, Vectorizer, find_devices, simulate
from mthread.gestures import GestureSession
from mthread.mirror import ScreenMirror
from mthread.recorder import Recorder
from mthread.errors import MThreadError

from .geometry import Placement, place_on_screen

#: Width of the placement overlay. It is stretched over the mirror by the
#: front end, so it only has to be fine enough to read, not full resolution.
OVERLAY_WIDTH = 540


class Engine:
    """One device, one image, one drawing at a time."""

    def __init__(self, write):
        self._write = write
        self.device: Device | None = None
        self.vectorizer = Vectorizer()
        self.paths: list = []
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.drawing = threading.Event()
        self.mirror: ScreenMirror | None = None
        self.mirror_thread: threading.Thread | None = None
        self.mirror_stop: threading.Event | None = None
        #: The size of the last frame captured, which is the only thing that
        #: knows which way up the phone is being held.
        self.frame_size: tuple[int, int] | None = None
        #: Where the drawing sits. Starts fitted to the screen; the front end
        #: moves, scales and turns it from there.
        self.placement = Placement()
        self.recorder: Recorder | None = None
        self.session: GestureSession | None = None

    # ---------------------------------------------------------------- talking

    def event(self, name: str, **fields) -> None:
        self._write({"event": name, **fields})

    def status(self, text: str) -> None:
        self.event("status", text=text)

    # ------------------------------------------------------------ operations

    def op_devices(self) -> dict:
        return {"devices": [
            {"serial": d.serial, "state": d.state, "description": d.human_state}
            for d in find_devices()
        ]}

    def op_connect(self, serial: str | None = None) -> dict:
        self.device = Device(serial)
        width, height = self.device.screen_size
        return {
            "serial": self.device.serial,
            "width": width,
            "height": height,
            "raw_touch": self.device.supports_raw_touch,
        }

    def op_screenshot(self) -> dict:
        self._require_device()
        path = Path(tempfile.gettempdir()) / "mthread_draw_screen.png"
        self.device.screenshot(str(path))
        return {"path": str(path)}

    # -------------------------------------------------------------- mirroring

    def op_mirror(self, on: bool = True, max_width: int = 520,
                  quality: int = 60) -> dict:
        """Start or stop the live view of the device screen.

        Frames are written to two files in turn and announced as events. Two,
        because a front end that has just been handed a path may still have the
        file open when the next frame is ready, and one file would mean either a
        torn image or a failed write.
        """
        self._stop_mirror()
        if not on:
            return {"mirroring": False}

        self._require_device()
        self.mirror = ScreenMirror(self.device, max_width=max_width, quality=quality)
        self.mirror.start()
        self.mirror_stop = threading.Event()
        self.mirror_thread = threading.Thread(target=self._mirror_loop, daemon=True)
        self.mirror_thread.start()

        width, height = self.device.screen_size
        return {"mirroring": True, "width": width, "height": height}

    def _mirror_loop(self) -> None:
        slot = 0
        while not self.mirror_stop.is_set():
            if self.drawing.is_set():
                # Capturing costs the device real work, and it is competing with
                # the drawing for it. The view resumes when the stroke is done.
                self.mirror_stop.wait(0.2)
                continue
            try:
                jpeg = self.mirror.frame()
            except Exception as error:
                self.event("mirror_lost", error=str(error))
                return
            slot = 1 - slot
            path = Path(tempfile.gettempdir()) / f"mthread_draw_frame_{slot}.jpg"
            path.write_bytes(jpeg)
            with Image.open(path) as frame:
                self.frame_size = frame.size
            self.event("frame", path=str(path),
                       width=self.frame_size[0], height=self.frame_size[1])

    def _stop_mirror(self) -> None:
        if self.mirror_stop is not None:
            self.mirror_stop.set()
        if self.mirror_thread is not None:
            self.mirror_thread.join(timeout=5)
        if self.mirror is not None:
            self.mirror.close()
        self.mirror = self.mirror_thread = self.mirror_stop = None

    def op_load_image(self, path: str) -> dict:
        image = self.vectorizer.load_image(path)
        return {"width": int(image.shape[1]), "height": int(image.shape[0])}

    def op_place(self, dx: float = 0.0, dy: float = 0.0, zoom: float = 1.0,
                 turn: float = 0.0, reset: bool = False) -> dict:
        """Nudge the drawing about, and redraw the overlay that shows where.

        Relative rather than absolute, because the front end is describing a
        gesture - a drag of so far, a wheel notch - and relative keeps the two
        ends from disagreeing about what the current position is.
        """
        if reset:
            self.placement = Placement()
        else:
            if dx or dy:
                self.placement = self.placement.moved(dx, dy)
            if zoom and zoom != 1.0:
                self.placement = self.placement.zoomed(zoom)
            if turn:
                self.placement = self.placement.turned(turn)
        return {
            "overlay": self._overlay(),
            "centre": list(self.placement.centre),
            "scale": round(self.placement.scale, 3),
            "rotation": round(self.placement.rotation, 1),
        }

    def op_preview(self, sensitivity: float = 5, detail: float = 7,
                   method: str = "canny", margin: float = 0.06) -> dict:
        started = time.perf_counter()
        settings = VectorizeSettings.from_sliders(sensitivity, detail, method=method)
        preview, paths = self.vectorizer.process(settings)
        self.paths = paths

        path = Path(tempfile.gettempdir()) / "mthread_draw_preview.png"
        preview.save(path)
        return {
            "path": str(path),
            "overlay": self._overlay(),
            "strokes": len(paths),
            "points": sum(len(p) for p in paths),
            "seconds": round(time.perf_counter() - started, 2),
        }

    def _overlay(self) -> str | None:
        """The strokes where they will actually land, on a transparent ground.

        A preview beside the phone tells you what will be drawn; a preview lying
        on top of the phone tells you where. The second is the one people
        actually want, and it costs nothing extra - the placement is the same
        call the drawing itself makes.
        """
        if self.device is None or not self.paths:
            return None

        width, height = self.screen_now()
        placed = place_on_screen(self.paths, width, height, self.placement)

        scale = OVERLAY_WIDTH / width
        image = Image.new("RGBA", (OVERLAY_WIDTH, round(height * scale)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for stroke in placed:
            if len(stroke) >= 2:
                draw.line([(x * scale, y * scale) for x, y in stroke],
                          fill=(255, 64, 58, 235), width=2, joint="curve")

        path = Path(tempfile.gettempdir()) / "mthread_draw_overlay.png"
        image.save(path)
        return str(path)

    def op_estimate(self, speed: float = 1.0, human: float = 0.0) -> dict:
        self._require_device()
        if not self.paths:
            return {"seconds": 0.0}
        paths = simulate(self.paths, human, seed=0) if human > 0 else self.paths
        return {"seconds": round(self.device.estimate_duration(paths, speed=speed), 1)}

    def op_draw(self, speed: float = 1.0, human: float = 0.0,
                margin: float = 0.06) -> dict:
        self._require_device()
        if not self.paths:
            raise MThreadError("Load an image and take a preview first.")

        width, height = self.screen_now()
        placed = place_on_screen(self.paths, width, height, self.placement)
        self.cancel.clear()
        self.drawing.set()
        self.status(f"Drawing {len(placed)} strokes")

        try:
            drawn = self.device.draw_paths(
                placed,
                speed=speed,
                human=human,
                progress=lambda done, total: self.event("progress", done=done, total=total),
                should_continue=lambda: not self.cancel.is_set(),
            )
        finally:
            self.drawing.clear()
        return {"strokes": drawn, "stopped": self.cancel.is_set()}

    # ---------------------------------------------------- recording gestures

    def op_record_start(self) -> dict:
        self._require_device()
        if self.recorder is not None and self.recorder.is_recording:
            raise MThreadError("Already recording.")
        self.recorder = Recorder(self.device)
        self.recorder.start()
        self.status("Recording. Do something on the phone.")
        return {"recording": True}

    def op_record_stop(self) -> dict:
        if self.recorder is None:
            raise MThreadError("Nothing is being recorded.")
        raw = self.recorder.stop()
        self.recorder = None

        # The digitizer's ranges are what turn its numbers into fractions of a
        # screen, and they are only knowable here, on the phone that recorded.
        self.session = GestureSession.from_events(
            raw.events, self.device.touch_device,
            screen_size=self.device.screen_size,
            device_serial=self.device.serial,
            device_model=self.device.model,
        )
        return self._session_summary()

    def op_session_save(self, path: str) -> dict:
        if self.session is None:
            raise MThreadError("There is no recording to save.")
        self.session.save(path)
        return {"path": path, **self._session_summary()}

    def op_session_open(self, path: str) -> dict:
        self.session = GestureSession.load(path)
        return {"path": path, **self._session_summary()}

    def op_play(self, speed: float = 1.0, repeat: int = 1) -> dict:
        self._require_device()
        if self.session is None or not self.session.strokes:
            raise MThreadError("Open or record something first.")

        self.cancel.clear()
        self.drawing.set()
        self.status(f"Replaying {len(self.session.strokes)} strokes")
        try:
            played = self.device.play_gestures(
                self.session, speed=speed, repeat=repeat,
                progress=lambda done, total: self.event("progress", done=done, total=total),
                should_continue=lambda: not self.cancel.is_set(),
            )
        finally:
            self.drawing.clear()
        return {"strokes": played, "stopped": self.cancel.is_set()}

    def _session_summary(self) -> dict:
        session = self.session
        if session is None:
            return {"strokes": 0, "points": 0, "seconds": 0.0}
        return {
            "strokes": len(session.strokes),
            "points": session.point_count,
            "seconds": round(session.duration, 2),
            "recorded_on": session.device_model or session.device_serial,
            "recorded_size": list(session.screen_size) if session.screen_size else None,
        }

    def op_stop(self) -> dict:
        self.cancel.set()
        return {"stopping": True}

    def screen_now(self) -> tuple[int, int]:
        """The screen as it is being held, not as it was manufactured.

        ``wm size`` reports the natural orientation and does not change when the
        phone is turned, so a drawing placed from it lands rotated on a phone in
        landscape, and the preview is squashed into a portrait frame. The
        captured frame is the one thing that knows: if it is the other way round
        from the natural size, so is the phone.
        """
        width, height = self.device.screen_size
        if self.frame_size:
            frame_width, frame_height = self.frame_size
            if (frame_width > frame_height) != (width > height):
                return height, width
        return width, height

    def _require_device(self) -> None:
        if self.device is None:
            raise MThreadError("No device is connected.")


#: Operations that may take a while, and so must not block the reader.
SLOW = {"preview", "draw", "screenshot", "connect", "mirror", "place",
        "play", "record_stop", "session_open", "session_save"}


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    lock = threading.Lock()

    def write(message: dict) -> None:
        with lock:
            stdout.write(json.dumps(message) + "\n")
            stdout.flush()

    engine = Engine(write)
    write({"event": "ready", "version": __import__("mthread_draw").__version__})

    def run(request: dict) -> None:
        identifier = request.get("id")
        operation = request.get("op", "")
        handler = getattr(engine, f"op_{operation}", None)
        if handler is None:
            write({"id": identifier, "ok": False, "error": f"unknown operation {operation!r}"})
            return

        arguments = {k: v for k, v in request.items() if k not in ("id", "op")}
        try:
            write({"id": identifier, "ok": True, "result": handler(**arguments)})
        except MThreadError as exc:
            write({"id": identifier, "ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - the front end still needs telling
            write({"id": identifier, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                   "traceback": traceback.format_exc()})

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            write({"ok": False, "error": "not JSON"})
            continue

        if request.get("op") == "quit":
            break
        if request.get("op") in SLOW:
            # A worker per slow request, so that stop is heard while drawing.
            worker = threading.Thread(target=run, args=(request,), daemon=True)
            engine.worker = worker
            worker.start()
        else:
            run(request)

    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
