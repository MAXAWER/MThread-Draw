"""Build the packaged AutoDraw application, and its installer.

One command, the same one CI runs, so a release can be reproduced locally:

    python tools/build_app.py            # app only
    python tools/build_app.py --msi      # + Windows installer  (needs WiX 5)
    python tools/build_app.py --dmg      # + macOS disk image   (macOS only)
    python tools/build_app.py --archive  # + a .tar.gz / .zip of the app folder

The result is self-contained: Python, OpenCV, Tk and adb all travel inside it,
so the person installing AutoDraw installs nothing else.

Requires PyInstaller, and for --msi the `wix` dotnet tool:

    dotnet tool install --global wix
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "packaging" / "AutoDraw.spec"

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def version() -> str:
    """Read the version from the package, so nothing carries a second copy."""
    scope: dict = {}
    for line in (ROOT / "autodraw" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            exec(line, scope)  # noqa: S102 - a single literal assignment
            return scope["__version__"]
    raise SystemExit("could not find __version__ in autodraw/__init__.py")


def arch_tag() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)


def run(*command: str, cwd: Path | None = None) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], cwd=str(cwd or ROOT), check=True)


def ensure_icon() -> None:
    icon = ROOT / "packaging" / ("autodraw.ico" if IS_WINDOWS else "autodraw.png")
    if not icon.is_file():
        run(sys.executable, ROOT / "tools" / "make_icon.py")


def ensure_platform_tools(skip: bool) -> None:
    if skip:
        print("skipping adb: the app will fall back to whatever the machine has")
        return
    run(sys.executable, ROOT / "tools" / "fetch_platform_tools.py", "--out", ROOT / "platform-tools")


def build_app() -> Path:
    app = DIST / ("AutoDraw.app" if IS_MAC else "AutoDraw")
    # Clear the previous app, not the whole dist directory: dist also holds the
    # installers, and on Windows something as ordinary as an open Explorer
    # window keeps a handle on the folder itself.
    if app.exists():
        shutil.rmtree(app, ignore_errors=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", SPEC)

    if not app.exists():
        raise SystemExit(f"PyInstaller did not produce {app}")

    fix_adb_permissions(app)
    selftest(app)
    return app


def selftest(app: Path) -> None:
    """Run the packaged app's own completeness check before anything ships.

    Without this a broken build looks exactly like a working one until someone
    double-clicks it and gets a traceback in a dialog box.
    """
    executable = app / "Contents" / "MacOS" / "AutoDraw" if IS_MAC else app / (
        "AutoDraw.exe" if IS_WINDOWS else "AutoDraw")
    report = BUILD / "selftest.txt"
    report.unlink(missing_ok=True)

    print("running the packaged app's self-test")
    result = subprocess.run([str(executable), "--selftest", str(report)], cwd=str(ROOT))
    text = report.read_text(encoding="utf-8") if report.is_file() else "(no report written)"
    print(text)
    if result.returncode != 0:
        raise SystemExit("the packaged build is incomplete - see the self-test output above")


def fix_adb_permissions(app: Path) -> None:
    """Restore the execute bit on the bundled adb.

    PyInstaller copies data files without their mode, so on macOS and Linux the
    adb it ships arrives unrunnable - and the failure surfaces much later, as a
    permission error from inside the app.
    """
    if IS_WINDOWS:
        return
    for adb in app.rglob("platform-tools/adb"):
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  chmod +x {adb.relative_to(app.parent)}")


def build_msi(app: Path) -> Path:
    if not IS_WINDOWS:
        raise SystemExit("--msi only works on Windows")
    if shutil.which("wix") is None:
        raise SystemExit("wix not found. Install it with: dotnet tool install --global wix")

    out = DIST / f"AutoDraw-{version()}-{arch_tag()}.msi"
    run(
        "wix", "build", ROOT / "packaging" / "AutoDraw.wxs",
        "-arch", "x64",
        "-d", f"Version={version()}",
        "-d", f"SourceDir={app}",
        "-d", f"IconFile={ROOT / 'packaging' / 'autodraw.ico'}",
        "-o", out,
    )
    size_mb = out.stat().st_size // 1024 // 1024
    # WiX only warns when it harvests nothing - a relative SourceDir resolves
    # against the .wxs file, not the working directory - and happily writes a
    # perfectly valid installer that installs no application at all.
    if size_mb < 20:
        raise SystemExit(f"{out.name} is only {size_mb} MB; the file harvest found nothing")
    print(f"built {out} ({size_mb} MB)")
    return out


def build_dmg(app: Path) -> Path:
    if not IS_MAC:
        raise SystemExit("--dmg only works on macOS")

    out = DIST / f"AutoDraw-{version()}-{arch_tag()}.dmg"
    staging = BUILD / "dmg"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    # The customary drag-to-install layout.
    os.symlink("/Applications", staging / "Applications")

    if out.exists():
        out.unlink()
    run("hdiutil", "create", "-volname", "AutoDraw", "-srcfolder", staging,
        "-ov", "-format", "UDZO", out)
    print(f"built {out} ({out.stat().st_size // 1024 // 1024} MB)")
    return out


def build_winui() -> Path:
    """Publish the Windows front end with the engine folded into it.

    The front end is a window and nothing more; it launches the engine as a
    child process. Publishing self-contained means the result is a folder that
    runs, rather than a folder plus a runtime somebody has to install first.
    """
    if not IS_WINDOWS:
        raise SystemExit("--winui only works on Windows")

    project = ROOT / "winui" / "AutoDraw.WinUI.csproj"
    out = DIST / "AutoDraw-WinUI"
    run("dotnet", "publish", project, "-c", "Release", "-r", "win-x64",
        "--self-contained", "true", "-o", out)

    engine = DIST / "autodraw-engine"
    if not engine.is_dir():
        raise SystemExit("the engine was not built; run without --no-adb first")
    target = out / "engine"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(engine, target)

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"built {out} ({size // 1024 // 1024} MB)")
    return out


def build_archive(app: Path) -> Path:
    """A plain archive of the app folder, for people who do not want an installer."""
    stem = f"AutoDraw-{version()}-{platform.system().lower()}-{arch_tag()}"
    if IS_WINDOWS:
        out = Path(shutil.make_archive(str(DIST / stem), "zip", root_dir=app.parent, base_dir=app.name))
    else:
        out = DIST / f"{stem}.tar.gz"
        with tarfile.open(out, "w:gz") as archive:
            archive.add(app, arcname=app.name)
    print(f"built {out} ({out.stat().st_size // 1024 // 1024} MB)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--msi", action="store_true", help="also build the Windows installer")
    parser.add_argument("--dmg", action="store_true", help="also build the macOS disk image")
    parser.add_argument("--archive", action="store_true", help="also build a zip / tar.gz")
    parser.add_argument("--winui", action="store_true",
                        help="also publish the WinUI 3 front end with the engine inside it")
    parser.add_argument("--no-adb", action="store_true", help="do not bundle platform-tools")
    args = parser.parse_args()

    ensure_icon()
    ensure_platform_tools(args.no_adb)
    app = build_app()
    print(f"built {app}")

    if args.msi:
        build_msi(app)
    if args.dmg:
        build_dmg(app)
    if args.winui:
        build_winui()
    if args.archive:
        build_archive(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
