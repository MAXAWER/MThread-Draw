"""Entry point for the PyInstaller build.

``mthread_draw/__main__.py`` uses a relative import, which PyInstaller cannot use as
a top-level script. This module is the same call with an absolute import, plus a
self-test the build pipeline runs before shipping anything.
"""

from __future__ import annotations

import sys
from pathlib import Path


def selftest(report: str | None = None) -> int:
    """Check that the frozen build is actually complete, and say why if not.

    A packaged build breaks in ways a source checkout never does. ``mthread``
    imports its vectoriser lazily, through ``__getattr__``, so PyInstaller's
    static analysis cannot see it and silently leaves it out; the bundled adb
    can arrive without its execute bit; a data file can go missing. Every one of
    those surfaces as a dialog box on the user's first launch.

    Run by tools/build_app.py straight after the build, and by CI, so the
    failure lands in a log instead.
    """
    lines: list[str] = []
    ok = True

    try:
        import cv2
        import numpy
        import PIL

        lines.append(f"opencv {cv2.__version__}, numpy {numpy.__version__}, pillow {PIL.__version__}")
    except Exception as exc:  # pragma: no cover - only reachable in a broken build
        ok = False
        lines.append(f"imaging stack missing: {exc!r}")

    try:
        import customtkinter

        from mthread import Device, Recorder, Session, replay  # noqa: F401
        from mthread.vectorize import VectorizeSettings, Vectorizer  # noqa: F401
        from mthread_draw.app import App, main  # noqa: F401

        lines.append(f"customtkinter {customtkinter.__version__}, mthread and mthread_draw import cleanly")
    except Exception as exc:
        ok = False
        lines.append(f"application imports failed: {exc!r}")

    try:
        from mthread.adb import bundled_candidates, find_adb, run_adb

        path = find_adb()
        bundled = any(Path(candidate) == Path(path) for candidate in bundled_candidates())
        version = run_adb(path, ["version"], timeout=20.0).stdout.splitlines()[0]
        lines.append(f"adb: {path}")
        lines.append(f"     {version} ({'bundled' if bundled else 'found on this machine'})")
        if not bundled:
            lines.append("     warning: this build is not carrying its own adb")
    except Exception as exc:
        ok = False
        lines.append(f"adb unusable: {exc}")

    text = "\n".join(lines)
    print(text)
    if report:
        Path(report).write_text(text + f"\n\nresult: {'ok' if ok else 'FAILED'}\n", encoding="utf-8")
    return 0 if ok else 1


def run() -> int:
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        report = sys.argv[index + 1] if len(sys.argv) > index + 1 else None
        return selftest(report)

    from mthread_draw.app import main

    return main() or 0


if __name__ == "__main__":
    raise SystemExit(run())
