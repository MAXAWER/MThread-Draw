# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for the AutoDraw desktop app.

Used unchanged on all three platforms and both locally and in CI, so a release
build is the same build a maintainer can reproduce:

    python tools/build_app.py

One directory rather than one file, deliberately. A one-file build unpacks
itself into a temporary directory on every launch - with OpenCV and adb inside
that is several seconds of nothing happening, and antivirus software treats the
self-extraction as suspicious. The installers hide the directory anyway.

adb comes from the platform-tools directory, put there by
tools/fetch_platform_tools.py.
If it is absent the build still works; the app then falls back to whatever adb
the machine has, exactly like a source checkout.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

VERSION = "1.1.0"

datas = collect_data_files("customtkinter")
datas += [(str(ROOT / "adbtouch" / "injector.jar"), "adbtouch")]

platform_tools = ROOT / "platform-tools"
if platform_tools.is_dir():
    datas += [(str(item), "platform-tools") for item in platform_tools.iterdir() if item.is_file()]
else:
    print("AutoDraw.spec: platform-tools not found - the app will need adb on PATH")

icon = str(ROOT / "packaging" / ("autodraw.ico" if IS_WINDOWS else "autodraw.png"))

analysis = Analysis(
    [str(ROOT / "tools" / "pyinstaller_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    # adbtouch imports its vectoriser through __getattr__ so that the core
    # library stays dependency-free. PyInstaller cannot see through that, and
    # leaves the module out unless it is named here.
    hiddenimports=["customtkinter", "adbtouch.vectorize"],
    hookspath=[],
    runtime_hooks=[],
    # rembg and its onnxruntime are optional and enormous; someone who wants
    # background removal can install the library from source.
    excludes=["rembg", "onnxruntime", "matplotlib", "pytest", "tkinter.test"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AutoDraw",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

collected = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AutoDraw",
)

# The same engine again, as a console program the WinUI front end can launch.
# It shares the analysis, so it costs a second link rather than a second scan.
engine_analysis = Analysis(
    [str(ROOT / "tools" / "engine_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["customtkinter", "adbtouch.vectorize"],
    excludes=["rembg", "onnxruntime", "matplotlib", "pytest", "tkinter.test"],
    noarchive=False,
)
engine_pyz = PYZ(engine_analysis.pure)
engine_exe = EXE(
    engine_pyz,
    engine_analysis.scripts,
    [],
    exclude_binaries=True,
    name="autodraw-engine",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
engine = COLLECT(
    engine_exe,
    engine_analysis.binaries,
    engine_analysis.datas,
    strip=False,
    upx=False,
    name="autodraw-engine",
)

if IS_MAC:
    app = BUNDLE(
        collected,
        name="AutoDraw.app",
        icon=icon,
        bundle_identifier="io.github.maxawer.autodraw",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            # The app talks to a phone over USB; without this, macOS refuses
            # the connection instead of prompting.
            "NSAppleEventsUsageDescription": "AutoDraw drives adb to reach your device.",
        },
    )
