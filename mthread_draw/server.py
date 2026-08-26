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

from mthread import Device, VectorizeSettings, Vectorizer, list_devices, simulate
from mthread.errors import MThreadError

from .geometry import fit_to_screen


class Engine:
    """One device, one image, one drawing at a time."""

    def __init__(self, write):
        self._write = write
        self.device: Device | None = None
        self.vectorizer = Vectorizer()
        self.paths: list = []
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None

    # ---------------------------------------------------------------- talking

    def event(self, name: str, **fields) -> None:
        self._write({"event": name, **fields})

    def status(self, text: str) -> None:
        self.event("status", text=text)

    # ------------------------------------------------------------ operations

    def op_devices(self) -> dict:
        return {"devices": [
            {"serial": d.serial, "state": d.state, "description": d.human_state}
            for d in list_devices()
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

    def op_load_image(self, path: str) -> dict:
        image = self.vectorizer.load_image(path)
        return {"width": int(image.shape[1]), "height": int(image.shape[0])}

    def op_preview(self, sensitivity: float = 5, detail: float = 7,
                   method: str = "canny") -> dict:
        started = time.perf_counter()
        settings = VectorizeSettings.from_sliders(sensitivity, detail, method=method)
        preview, paths = self.vectorizer.process(settings)
        self.paths = paths

        path = Path(tempfile.gettempdir()) / "mthread_draw_preview.png"
        preview.save(path)
        return {
            "path": str(path),
            "strokes": len(paths),
            "points": sum(len(p) for p in paths),
            "seconds": round(time.perf_counter() - started, 2),
        }

    def op_estimate(self, speed: float = 1.0, human: float = 0.0) -> dict:
        self._require_device()
        if not self.paths:
            return {"seconds": 0.0}
        paths = simulate(self.paths, human, seed=0) if human > 0 else self.paths
        return {"seconds": round(self.device.estimate_duration(paths, speed=speed), 1)}

    def op_draw(self, margin: float = 0.06, speed: float = 1.0,
                human: float = 0.0) -> dict:
        self._require_device()
        if not self.paths:
            raise MThreadError("Load an image and take a preview first.")

        width, height = self.device.screen_size
        placed = fit_to_screen(self.paths, width, height, margin=margin)
        self.cancel.clear()
        self.status(f"Drawing {len(placed)} strokes")

        drawn = self.device.draw_paths(
            placed,
            speed=speed,
            human=human,
            progress=lambda done, total: self.event("progress", done=done, total=total),
            should_continue=lambda: not self.cancel.is_set(),
        )
        return {"strokes": drawn, "stopped": self.cancel.is_set()}

    def op_stop(self) -> dict:
        self.cancel.set()
        return {"stopping": True}

    def _require_device(self) -> None:
        if self.device is None:
            raise MThreadError("No device is connected.")


#: Operations that may take a while, and so must not block the reader.
SLOW = {"preview", "draw", "screenshot", "connect"}


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
