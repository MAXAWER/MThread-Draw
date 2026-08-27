# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the MThread Draw engine.

The engine and nothing else. It used to build a Tk window as well, and that
window is gone: on Windows the native WinUI front end replaced it, on macOS a
native one does, and a Tk window that started slowly and looked like nothing
else on either platform was not worth keeping for the sake of symmetry.

What is left is what both front ends need - one console program that speaks the
JSON protocol in mthread_draw.server, with the injector jar and adb inside it:

    python tools/build_app.py

One directory rather than one file, deliberately. A one-file build unpacks
itself into a temporary directory on every launch, and with OpenCV and adb
inside that is several seconds of nothing happening; antivirus software also
treats the self-extraction as suspicious. The installer hides the directory.

adb comes from the platform-tools directory, put there by
tools/fetch_platform_tools.py. If it is absent the build still works and the
engine falls back to whatever adb the machine has, exactly like a source
checkout.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
IS_WINDOWS = sys.platform.startswith("win")

VERSION = "1.2.0"

datas = [(str(ROOT / "mthread" / "injector.jar"), "mthread")]

platform_tools = ROOT / "platform-tools"
if platform_tools.is_dir():
    datas += [(str(item), "platform-tools") for item in platform_tools.iterdir() if item.is_file()]
else:
    print("MThreadDraw.spec: platform-tools not found - the engine will need adb on PATH")

analysis = Analysis(
    [str(ROOT / "tools" / "engine_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    # mthread imports its vectoriser through __getattr__ so that the core
    # library stays dependency-free. PyInstaller cannot see through that, and
    # leaves the module out unless it is named here.
    hiddenimports=["mthread.vectorize"],
    hookspath=[],
    runtime_hooks=[],
    # rembg and its onnxruntime are optional and enormous; someone who wants
    # background removal can install the library from source. Tkinter goes with
    # the window that used it.
    excludes=["rembg", "onnxruntime", "matplotlib", "pytest", "tkinter", "customtkinter"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="mthread-draw-engine",
    debug=False,
    strip=False,
    upx=False,
    # A console program on purpose: it speaks JSON on stdin and stdout, and the
    # front end starts it with the window hidden.
    console=True,
    icon=str(ROOT / "packaging" / ("mthreaddraw.ico" if IS_WINDOWS else "mthreaddraw.png")),
)

engine = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="mthread-draw-engine",
)
