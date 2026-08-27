"""Build the macOS front end, wrap it in a bundle, and make a disk image.

    python tools/build_macos.py            # -> dist/MThreadDraw.app
    python tools/build_macos.py --dmg      # + dist/MThreadDraw-<version>-<arch>.dmg

macOS only. The front end is a Swift package rather than an Xcode project, so
this assembles the .app around the built binary: a bundle is a directory with a
plist in it, and hand-assembling one keeps the build to `swift build` with no
project file to drift out of sync.

The engine goes inside the bundle's Resources, which is where Engine.swift looks
for it, so the application a person drags to Applications carries Python, OpenCV
and adb with it and needs nothing installed.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PROJECT = ROOT / "macos"

BUNDLE_ID = "io.github.maxawer.mthread-draw"


def version() -> str:
    for line in (ROOT / "mthread_draw" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            scope: dict = {}
            exec(line, scope)  # noqa: S102 - a single literal assignment
            return scope["__version__"]
    raise SystemExit("could not find __version__ in mthread_draw/__init__.py")


def arch_tag() -> str:
    import platform
    return {"arm64": "arm64", "x86_64": "x64"}.get(platform.machine(), platform.machine())


def run(*command, cwd: Path | None = None) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], cwd=str(cwd or ROOT), check=True)


def build_binary() -> Path:
    run("swift", "build", "-c", "release", cwd=PROJECT)
    binary = PROJECT / ".build" / "release" / "MThreadDraw"
    if not binary.is_file():
        raise SystemExit(f"swift build did not produce {binary}")
    return binary


def make_icon() -> Path | None:
    """Convert the PNG icon into the .icns a bundle wants.

    iconutil is part of the developer tools and is present on any machine that
    can run swift build, so this is not an extra dependency in practice.
    """
    source = ROOT / "packaging" / "mthreaddraw.png"
    if not source.is_file() or shutil.which("iconutil") is None:
        return None

    iconset = DIST / "MThreadDraw.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    # The sizes a bundle icon is expected to carry; sips is the built-in
    # resizer, so nothing outside the system is needed.
    for size in (16, 32, 64, 128, 256, 512):
        for scale, suffix in ((1, ""), (2, "@2x")):
            pixels = size * scale
            run("sips", "-z", pixels, pixels, source,
                "--out", iconset / f"icon_{size}x{size}{suffix}.png")

    icns = DIST / "MThreadDraw.icns"
    run("iconutil", "-c", "icns", iconset, "-o", icns)
    shutil.rmtree(iconset)
    return icns


def assemble(binary: Path) -> Path:
    app = DIST / "MThreadDraw.app"
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir(parents=True)

    shutil.copy2(binary, contents / "MacOS" / "MThreadDraw")
    os.chmod(contents / "MacOS" / "MThreadDraw", 0o755)

    icns = make_icon()
    if icns is not None:
        shutil.copy2(icns, contents / "Resources" / "MThreadDraw.icns")

    plist = {
        "CFBundleName": "MThread Draw",
        "CFBundleDisplayName": "MThread Draw",
        "CFBundleExecutable": "MThreadDraw",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version(),
        "CFBundleVersion": version(),
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        # The window is frosted glass; a light-only or dark-only app would look
        # wrong against half the desktops it is put on.
        "NSRequiresAquaSystemAppearance": False,
        # It drives adb to reach the phone. Without this macOS refuses the
        # connection instead of prompting for it.
        "NSAppleEventsUsageDescription":
            "MThread Draw runs adb to reach your Android device.",
    }
    if icns is not None:
        plist["CFBundleIconFile"] = "MThreadDraw"
    (contents / "Info.plist").write_bytes(plistlib.dumps(plist))

    engine = DIST / "mthread-draw-engine"
    if engine.is_dir():
        shutil.copytree(engine, contents / "Resources" / "engine")
        print(f"  engine folded in from {engine}")
    else:
        print("  no engine in dist/: build it first with tools/build_app.py, or the "
              "app will look for a source checkout")

    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    print(f"built {app} ({size // 1024 // 1024} MB)")
    return app


def build_dmg(app: Path) -> Path:
    out = DIST / f"MThreadDraw-{version()}-{arch_tag()}.dmg"
    staging = DIST / "dmg"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    # The customary drag-to-install layout.
    os.symlink("/Applications", staging / "Applications")

    if out.exists():
        out.unlink()
    run("hdiutil", "create", "-volname", "MThread Draw", "-srcfolder", staging,
        "-ov", "-format", "UDZO", out)
    shutil.rmtree(staging)
    print(f"built {out} ({out.stat().st_size // 1024 // 1024} MB)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dmg", action="store_true", help="also build the disk image")
    args = parser.parse_args()

    if sys.platform != "darwin":
        raise SystemExit("the macOS front end only builds on macOS")

    DIST.mkdir(exist_ok=True)
    app = assemble(build_binary())
    if args.dmg:
        build_dmg(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
