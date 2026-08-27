"""Build the engine, the front end for this platform, and the installer.

One command, the same one CI runs, so a release can be reproduced locally:

    python tools/build_app.py            # the engine on its own
    python tools/build_app.py --winui    # + the Windows front end (Windows)
    python tools/build_app.py --msi      # + the Windows installer (needs WiX 5)

Everything is built in a scratch directory outside the checkout; dist/ receives
only the finished installer and zip.

The engine is self-contained: Python, OpenCV and adb all travel inside it, so
the person installing MThread Draw installs nothing else.

There is no Tk window any more. Windows gets the WinUI front end and macOS a
native one; both drive this same engine over a pipe.

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
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
#: Everything is built here and only the finished artifacts are copied into
#: dist/. This checkout lives in OneDrive on at least one machine, and a sync
#: client holds handles on files while it uploads them: writing several thousand
#: of them into a synced folder failed at a different step every time - deleting
#: last build's output, zipping a DLL, harvesting for the installer - always with
#: an access denied that named a file rather than the cause. Copying four
#: finished files in at the end does not collide.
STAGE = Path(tempfile.gettempdir()) / "mthread-draw-stage"
WORKPATH = STAGE / "work"
SPEC = ROOT / "packaging" / "MThreadDraw.spec"
#: Pinned because WiX 6 and later want a separate maintenance-fee
#: licence accepted before they will build unattended.
WIX_VERSION = "5.0.2"

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def version() -> str:
    """Read the version from the package, so nothing carries a second copy."""
    scope: dict = {}
    for line in (ROOT / "mthread_draw" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            exec(line, scope)  # noqa: S102 - a single literal assignment
            return scope["__version__"]
    raise SystemExit("could not find __version__ in mthread_draw/__init__.py")


def arch_tag() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)


def run(*command: str, cwd: Path | None = None) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], cwd=str(cwd or ROOT), check=True)


def remove_tree(path: Path, attempts: int = 6) -> None:
    """Delete a directory, waiting out whatever is holding a file in it.

    This checkout lives in OneDrive on at least one machine, and a sync client
    keeps handles on files while it uploads them. Deleting a few hundred
    megabytes of build output therefore fails with an access denied on a
    different file each time, and PyInstaller's own cleanup dies the same way
    with a message that names a font rather than the cause. Retrying gets past
    it; read-only attributes, which sync clients also set, are cleared on the
    way.
    """
    if not path.exists():
        return
    for attempt in range(attempts):
        def unlock(func, target, _exc):
            os.chmod(target, stat.S_IWRITE)
            func(target)

        shutil.rmtree(path, onexc=unlock)
        if not path.exists():
            return
        time.sleep(0.5 * (attempt + 1))
    raise SystemExit(
        f"could not delete {path}. Something is holding a file in it - a file "
        f"manager, an antivirus scan, or a sync client. Close it and try again."
    )


def ensure_icon() -> None:
    icon = ROOT / "packaging" / ("mthreaddraw.ico" if IS_WINDOWS else "mthreaddraw.png")
    if not icon.is_file():
        run(sys.executable, ROOT / "tools" / "make_icon.py")


def ensure_platform_tools(skip: bool) -> None:
    if skip:
        print("skipping adb: the app will fall back to whatever the machine has")
        return
    run(sys.executable, ROOT / "tools" / "fetch_platform_tools.py", "--out", ROOT / "platform-tools")


def deliver(source: Path) -> Path:
    """Copy a finished artifact into dist/, replacing what was there."""
    DIST.mkdir(exist_ok=True)
    target = DIST / source.name
    if target.exists():
        target.unlink()
    shutil.copy2(source, target)
    return target


def build_engine() -> Path:
    """The engine both front ends launch, with Python, OpenCV and adb inside."""
    engine = STAGE / "mthread-draw-engine"
    # Clear the previous build, not the whole dist directory: dist also holds
    # the installer, and on Windows an open Explorer window is enough to keep a
    # handle on the folder itself.
    remove_tree(engine)
    # PyInstaller's scratch directory goes outside the checkout. This one lives
    # in OneDrive, which holds handles on files while it syncs them, and --clean
    # then fails to delete last build's localpycs with an access denied that
    # says nothing about why. Anywhere the sync client is not watching works.
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--workpath", WORKPATH, "--distpath", STAGE, SPEC)

    if not engine.exists():
        raise SystemExit(f"PyInstaller did not produce {engine}")

    fix_adb_permissions(engine)
    selftest(engine)
    return engine


def selftest(engine: Path) -> None:
    """Run the packaged app's own completeness check before anything ships.

    Without this a broken build looks exactly like a working one until someone
    double-clicks it and gets a traceback in a dialog box.
    """
    executable = engine / ("mthread-draw-engine.exe" if IS_WINDOWS
                           else "mthread-draw-engine")
    report = BUILD / "selftest.txt"
    report.unlink(missing_ok=True)

    print("running the packaged app's self-test")
    result = subprocess.run([str(executable), "--selftest", str(report)], cwd=str(ROOT))
    text = report.read_text(encoding="utf-8") if report.is_file() else "(no report written)"
    print(text)
    if result.returncode != 0:
        raise SystemExit("the packaged build is incomplete - see the self-test output above")


def fix_adb_permissions(engine: Path) -> None:
    """Restore the execute bit on the bundled adb.

    PyInstaller copies data files without their mode, so on macOS and Linux the
    adb it ships arrives unrunnable - and the failure surfaces much later, as a
    permission error from inside the app.
    """
    if IS_WINDOWS:
        return
    for adb in engine.rglob("platform-tools/adb"):
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  chmod +x {adb.relative_to(engine.parent)}")


#: The WiX extensions the installer needs: one for the dialogs, one for the
#: action that offers to start the program at the end.
WIX_EXTENSIONS = ("WixToolset.UI.wixext",)


def ensure_wix_extensions() -> None:
    """Add the extensions if this machine has not got them.

    `wix extension add -g` is idempotent, so this is cheap to repeat and means a
    fresh checkout or a fresh CI runner needs no separate step.
    """
    for name in WIX_EXTENSIONS:
        run("wix", "extension", "add", "-g", f"{name}/{WIX_VERSION}")


def build_msi(app: Path) -> Path:
    """The Windows installer, which installs the WinUI front end.

    Not the Tk one: on Windows the native window is the one people should get,
    and the Tk window is what macOS and Linux run. The archives still carry it
    for anyone who wants it.
    """
    if not IS_WINDOWS:
        raise SystemExit("--msi only works on Windows")
    if shutil.which("wix") is None:
        raise SystemExit("wix not found. Install it with: dotnet tool install --global wix")

    source = STAGE / "MThreadDraw-WinUI"
    if not (source / "MThreadDraw.exe").is_file():
        raise SystemExit("the WinUI front end is not built; --msi implies --winui")

    ensure_wix_extensions()
    out = STAGE / f"MThreadDraw-{version()}-{arch_tag()}.msi"
    run(
        "wix", "build", ROOT / "packaging" / "MThreadDraw.wxs",
        "-arch", "x64",
        *[arg for name in WIX_EXTENSIONS for arg in ("-ext", name)],
        "-d", f"Version={version()}",
        "-d", f"SourceDir={source}",
        "-d", f"IconFile={ROOT / 'packaging' / 'mthreaddraw.ico'}",
        "-o", out,
    )
    size_mb = out.stat().st_size // 1024 // 1024
    # WiX only warns when it harvests nothing - a relative SourceDir resolves
    # against the .wxs file, not the working directory - and happily writes a
    # perfectly valid installer that installs no application at all.
    if size_mb < 100:
        raise SystemExit(f"{out.name} is only {size_mb} MB; the file harvest found nothing")
    print(f"built {out} ({size_mb} MB)")
    return deliver(out)


def build_winui() -> Path:
    """Publish the Windows front end with the engine folded into it.

    The front end is a window and nothing more; it launches the engine as a
    child process. Publishing self-contained means the result is a folder that
    runs, rather than a folder plus a runtime somebody has to install first.
    """
    if not IS_WINDOWS:
        raise SystemExit("--winui only works on Windows")

    project = ROOT / "winui" / "MThreadDraw.WinUI.csproj"
    out = STAGE / "MThreadDraw-WinUI"
    run("dotnet", "publish", project, "-c", "Release", "-r", "win-x64",
        "--self-contained", "true", "-o", out)

    engine = STAGE / "mthread-draw-engine"
    if not engine.is_dir():
        raise SystemExit("the engine was not built; run without --no-adb first")
    target = out / "engine"
    remove_tree(target)
    shutil.copytree(engine, target)

    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"built {out} ({size // 1024 // 1024} MB)")

    # A release asset has to be one file, and a folder of four thousand is a
    # poor thing to ask anyone to download by hand.
    archive = Path(shutil.make_archive(
        str(STAGE / f"MThreadDraw-WinUI-{version()}-{arch_tag()}"), "zip",
        root_dir=out.parent, base_dir=out.name))
    print(f"built {archive} ({archive.stat().st_size // 1024 // 1024} MB)")
    deliver(archive)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--msi", action="store_true",
                        help="also build the Windows installer, which installs the "
                             "WinUI front end and therefore builds it too")
    parser.add_argument("--winui", action="store_true",
                        help="also publish the WinUI 3 front end with the engine inside it")
    parser.add_argument("--no-adb", action="store_true", help="do not bundle platform-tools")
    args = parser.parse_args()

    ensure_icon()
    ensure_platform_tools(args.no_adb)
    engine = build_engine()
    print(f"built {engine}")

    if args.winui or args.msi:
        build_winui()
    if args.msi:
        build_msi(engine)
    print(f"artifacts in {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
