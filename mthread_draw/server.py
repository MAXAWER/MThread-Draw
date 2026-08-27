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
from dataclasses import dataclass, field
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


@dataclass
class Layer:
    """One picture on the way to the screen, with its own settings and place.

    Several of these compose a drawing. Each keeps the paths it traced to, so
    changing one does not re-trace the others, and its own placement, so they
    can be arranged against each other before anything is drawn.
    """

    source: str
    name: str
    paths: list = field(default_factory=list)
    #: Indices of strokes the eraser has taken out. Kept rather than deleted so
    #: that re-tracing with different settings does not inherit erasures that
    #: were aimed at strokes which no longer exist.
    erased: set = field(default_factory=set)
    placement: Placement = field(default_factory=Placement)
    method: str = "canny"
    sensitivity: float = 5.0
    detail: float = 7.0
    visible: bool = True

    @property
    def kept(self) -> list:
        return [path for index, path in enumerate(self.paths) if index not in self.erased]

    def summary(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "strokes": len(self.kept),
            "erased": len(self.erased),
            "points": sum(len(path) for path in self.kept),
            "method": self.method,
            "detail": self.detail,
            "visible": self.visible,
            "scale": round(self.placement.scale, 3),
            "rotation": round(self.placement.rotation, 1),
            "flip_x": self.placement.flip_x,
            "flip_y": self.placement.flip_y,
        }


class Engine:
    """One device, one image, one drawing at a time."""

    def __init__(self, write):
        self._write = write
        self.device: Device | None = None
        self.vectorizer = Vectorizer()
        self.layers: list[Layer] = []
        self.current = 0
        #: Set when the automatic capture failed and a screenshot was supplied
        #: by hand instead, so the front end has something to place against.
        self.still: str | None = None
        self.still_size: tuple[int, int] | None = None
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.drawing = threading.Event()
        self.mirror: ScreenMirror | None = None
        self.mirror_thread: threading.Thread | None = None
        self.mirror_stop: threading.Event | None = None
        #: The size of the last frame captured, which is the only thing that
        #: knows which way up the phone is being held.
        self.frame_size: tuple[int, int] | None = None
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

    # ------------------------------------------------------------------ layers

    @property
    def layer(self) -> Layer:
        if not self.layers:
            raise MThreadError("Load an image first.")
        self.current = max(0, min(self.current, len(self.layers) - 1))
        return self.layers[self.current]

    def op_load_image(self, path: str, replace: bool = False) -> dict:
        """Add a picture, or replace the one selected.

        Adding rather than replacing by default: several pictures arranged
        against each other is the point of having layers at all, and a caller
        that wants the old single-image behaviour asks for it.
        """
        image = self.vectorizer.load_image(path)
        layer = Layer(source=path, name=Path(path).name)
        if replace and self.layers:
            layer.placement = self.layer.placement
            self.layers[self.current] = layer
        else:
            self.layers.append(layer)
            self.current = len(self.layers) - 1
        self._trace(layer)
        return {
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
            **self._layers_summary(),
        }

    def op_layers(self) -> dict:
        return self._layers_summary()

    def op_layer_select(self, index: int) -> dict:
        if not 0 <= index < len(self.layers):
            raise MThreadError(f"There is no layer {index}.")
        self.current = index
        return self._layers_summary()

    def op_layer_remove(self, index: int | None = None) -> dict:
        if not self.layers:
            raise MThreadError("There is nothing to remove.")
        index = self.current if index is None else index
        if not 0 <= index < len(self.layers):
            raise MThreadError(f"There is no layer {index}.")
        self.layers.pop(index)
        self.current = min(self.current, max(0, len(self.layers) - 1))
        return self._layers_summary()

    def op_layer_visible(self, visible: bool, index: int | None = None) -> dict:
        layer = self.layers[self.current if index is None else index]
        layer.visible = bool(visible)
        return self._layers_summary()

    def op_layer_raise(self, index: int | None = None) -> dict:
        """Move a layer later in the order, so it is drawn on top."""
        index = self.current if index is None else index
        if index + 1 < len(self.layers):
            self.layers[index], self.layers[index + 1] = (self.layers[index + 1],
                                                          self.layers[index])
            if self.current == index:
                self.current = index + 1
        return self._layers_summary()

    def _layers_summary(self) -> dict:
        return {
            "layers": [layer.summary() for layer in self.layers],
            "current": self.current,
            "overlay": self._overlay(),
            "strokes": sum(len(layer.kept) for layer in self.layers if layer.visible),
            "points": sum(len(path) for layer in self.layers if layer.visible
                          for path in layer.kept),
        }

    # ----------------------------------------------------------------- tracing

    def _trace(self, layer: Layer) -> float:
        """Re-run the tracer for one layer, from its own file and settings."""
        started = time.perf_counter()
        # The vectoriser holds one image, so a layer that is not the one it last
        # loaded has to be read again. Reading a JPEG costs a few milliseconds;
        # keeping a vectoriser per layer would cost a copy of every image.
        self.vectorizer.load_image(layer.source)
        settings = VectorizeSettings.from_sliders(
            layer.sensitivity, layer.detail, method=layer.method)
        preview, paths = self.vectorizer.process(settings)
        layer.paths = paths
        # Erasures were aimed at strokes that may no longer exist.
        layer.erased = set()

        path = Path(tempfile.gettempdir()) / "mthread_draw_preview.png"
        preview.save(path)
        self._preview_path = str(path)
        return time.perf_counter() - started

    def op_preview(self, sensitivity: float = 5, detail: float = 7,
                   method: str = "canny") -> dict:
        """Re-trace the selected layer with new settings, without reloading it."""
        layer = self.layer
        layer.sensitivity, layer.detail, layer.method = sensitivity, detail, method
        seconds = self._trace(layer)
        return {
            "path": self._preview_path,
            "seconds": round(seconds, 2),
            **self._layers_summary(),
        }

    # --------------------------------------------------------------- placement

    def op_place(self, dx: float = 0.0, dy: float = 0.0, zoom: float = 1.0,
                 turn: float = 0.0, flip_x: bool = False, flip_y: bool = False,
                 reset: bool = False) -> dict:
        """Nudge the selected layer about, and redraw the overlay.

        Relative rather than absolute, because the front end is describing a
        gesture - a drag of so far, a wheel notch - and relative keeps the two
        ends from disagreeing about what the current position is.
        """
        layer = self.layer
        if reset:
            layer.placement = Placement()
        else:
            if dx or dy:
                layer.placement = layer.placement.moved(dx, dy)
            if zoom and zoom != 1.0:
                layer.placement = layer.placement.zoomed(zoom)
            if turn:
                layer.placement = layer.placement.turned(turn)
            if flip_x or flip_y:
                layer.placement = layer.placement.mirrored(horizontal=flip_x,
                                                           vertical=flip_y)
        return self._layers_summary()

    # ------------------------------------------------------------------ eraser

    def op_erase(self, x: float = 0.0, y: float = 0.0, radius: float = 0.02,
                 undo: bool = False) -> dict:
        """Take out the strokes of the selected layer near a point.

        The point and the radius are fractions of the screen, because that is
        what the front end knows: it has a picture of the phone under the
        cursor, not the tracer's coordinate space. Which stroke is near enough
        is therefore decided after placement, not before it.
        """
        layer = self.layer
        if undo:
            layer.erased = set()
            return self._layers_summary()

        width, height = self.screen_now()
        placed = place_on_screen(layer.paths, width, height, layer.placement)
        reach = radius * max(width, height)
        target_x, target_y = x * width, y * height

        for index, stroke in enumerate(placed):
            if index in layer.erased:
                continue
            for px, py in stroke:
                if (px - target_x) ** 2 + (py - target_y) ** 2 <= reach * reach:
                    layer.erased.add(index)
                    break
        return self._layers_summary()

    # ---------------------------------------------------------------- overlays

    def _overlay(self) -> str | None:
        """Every visible layer where it will land, on a transparent ground.

        A preview beside the phone tells you what will be drawn; a preview lying
        on top of the phone tells you where. The selected layer is drawn bright
        and the rest dim, so it is clear which one the mouse is about to move.
        """
        if not self.layers:
            return None

        width, height = self.screen_now()
        scale = OVERLAY_WIDTH / width
        image = Image.new("RGBA", (OVERLAY_WIDTH, round(height * scale)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        for index, layer in enumerate(self.layers):
            if not layer.visible or not layer.kept:
                continue
            colour = (255, 64, 58, 235) if index == self.current else (110, 190, 255, 150)
            for stroke in place_on_screen(layer.kept, width, height, layer.placement):
                if len(stroke) >= 2:
                    draw.line([(x * scale, y * scale) for x, y in stroke],
                              fill=colour, width=2, joint="curve")

        path = Path(tempfile.gettempdir()) / "mthread_draw_overlay.png"
        image.save(path)
        return str(path)

    # ----------------------------------------------------------------- drawing

    def _all_placed(self) -> list:
        """Every visible layer's strokes, in device pixels, in drawing order."""
        width, height = self.screen_now()
        placed = []
        for layer in self.layers:
            if layer.visible and layer.kept:
                placed.extend(place_on_screen(layer.kept, width, height, layer.placement))
        return placed

    def op_estimate(self, speed: float = 1.0, human: float = 0.0) -> dict:
        self._require_device()
        placed = self._all_placed()
        if not placed:
            return {"seconds": 0.0}
        paths = simulate(placed, human, seed=0) if human > 0 else placed
        return {"seconds": round(self.device.estimate_duration(paths, speed=speed), 1)}

    def op_draw(self, speed: float = 1.0, human: float = 0.0) -> dict:
        self._require_device()
        placed = self._all_placed()
        if not placed:
            raise MThreadError("Load an image first.")

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

    def op_still(self, path: str) -> dict:
        """Use a screenshot taken by hand instead of one captured over ADB.

        Capture fails on some devices and in some emulators, and when it does
        there is nothing to place a drawing against. A screenshot taken on the
        phone and copied across is a picture of the same screen; it does not
        update, but it is enough to arrange a drawing on, and its proportions
        are the ones that matter for placement.
        """
        with Image.open(path) as image:
            self.still = path
            self.still_size = image.size
        return {"path": path, "width": self.still_size[0], "height": self.still_size[1],
                **self._layers_summary()}

    def screen_now(self) -> tuple[int, int]:
        """The screen as it is being held, not as it was manufactured.

        ``wm size`` reports the natural orientation and does not change when the
        phone is turned, so a drawing placed from it lands rotated on a phone in
        landscape, and the preview is squashed into a portrait frame. The
        captured frame is the one thing that knows: if it is the other way round
        from the natural size, so is the phone.
        """
        if self.device is None:
            # No phone attached: a screenshot supplied by hand is the only thing
            # that knows the shape of the screen, and failing that a common one
            # keeps placement working so a drawing can be arranged in advance.
            return self.still_size or (1080, 1920)
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
SLOW = {"preview", "draw", "screenshot", "connect", "mirror", "place", "erase",
        "load_image", "still", "layer_select", "layer_remove", "layer_visible",
        "layer_raise", "layers", "play", "record_stop", "session_open",
        "session_save"}


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
