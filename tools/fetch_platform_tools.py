"""Download Google's platform-tools so the installers can ship their own adb.

The whole point of the packaged builds is that a person who just wants to draw
on their phone should not have to find, download and PATH the Android SDK first.
That means the application carries adb inside it.

Note on redistribution: platform-tools is published by Google under the Android
Software Development Kit licence, and bundling it inside a release is a choice
the project makes deliberately - see docs/RELEASING.md. NOTICE.txt is kept
alongside the binary for that reason; do not drop it.

    python tools/fetch_platform_tools.py --out build/platform-tools
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

URLS = {
    "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
}

#: adb and what it needs to run, plus the licence notice. Everything else in the
#: archive - fastboot, etc1tool, the systrace scripts - is dead weight in a
#: drawing app, and platform-tools is 10 MB of which adb is about 5.
KEEP = {
    "adb", "adb.exe",
    "AdbWinApi.dll", "AdbWinUsbApi.dll",
    "NOTICE.txt", "source.properties",
}


def platform_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def fetch(key: str, out: Path, *, slim: bool = True) -> Path:
    url = URLS[key]
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "platform-tools.zip"
        print(f"downloading {url}")
        with urllib.request.urlopen(url) as response, archive.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        print(f"  {archive.stat().st_size // 1024 // 1024} MB")

        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.namelist():
                name = Path(member).name
                if not name or member.endswith("/"):
                    continue
                if slim and name not in KEEP:
                    continue
                target = out / name
                with zipped.open(member) as source, target.open("wb") as handle:
                    shutil.copyfileobj(source, handle)

    adb = out / ("adb.exe" if key == "windows" else "adb")
    if not adb.is_file():
        raise SystemExit(f"platform-tools archive did not contain {adb.name}")
    if key != "windows":
        # Zip archives carry a mode, but zipfile does not apply it on extract.
        adb.chmod(adb.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"extracted {len(list(out.iterdir()))} files to {out}")
    return adb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="build/platform-tools")
    parser.add_argument("--platform", choices=sorted(URLS), help="defaults to the running platform")
    parser.add_argument("--full", action="store_true", help="keep the whole archive, not just adb")
    parser.add_argument("--force", action="store_true", help="re-download even if it is already there")
    args = parser.parse_args()

    out = Path(args.out)
    key = platform_key(args.platform)
    adb = out / ("adb.exe" if key == "windows" else "adb")
    if adb.is_file() and not args.force:
        print(f"{adb} is already there; pass --force to replace it")
        return 0

    fetch(key, out, slim=not args.full)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
