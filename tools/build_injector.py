"""Compile the on-device touch injector into a jar.

Needs a JDK and an Android SDK with build-tools and one platform installed; it
finds them itself if ANDROID_HOME or the usual per-platform location is set.

    python tools/build_injector.py

The result is adbtouch/injector.jar - a zip containing classes.dex, which is all
app_process needs. It lives inside the package so that a wheel and a frozen
build both carry it, and it is small enough (a few kilobytes) to be committed,
so nobody needs an Android SDK just to use the library.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "injector" / "src" / "com" / "adbtouch" / "Injector.java"
OUT_JAR = ROOT / "adbtouch" / "injector.jar"
WORK = ROOT / "build" / "injector"

IS_WINDOWS = sys.platform.startswith("win")


def find_sdk() -> Path:
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(name)
        if value and Path(value).is_dir():
            return Path(value)

    candidates = [
        Path.home() / "AppData" / "Local" / "Android" / "Sdk",
        Path.home() / "Library" / "Android" / "sdk",
        Path.home() / "Android" / "Sdk",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit("Could not find an Android SDK. Set ANDROID_HOME.")


def newest(directory: Path) -> Path:
    """The highest-numbered entry, so a machine with several keeps up."""
    entries = sorted((item for item in directory.iterdir() if item.is_dir()),
                     key=lambda item: item.name)
    if not entries:
        raise SystemExit(f"{directory} is empty")
    return entries[-1]


def find_javac() -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / ("javac.exe" if IS_WINDOWS else "javac")
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("javac")
    if not found:
        raise SystemExit("Could not find javac. Install a JDK or set JAVA_HOME.")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="Android SDK root; found automatically otherwise")
    args = parser.parse_args()

    sdk = Path(args.sdk) if args.sdk else find_sdk()
    android_jar = newest(sdk / "platforms") / "android.jar"
    build_tools = newest(sdk / "build-tools")
    d8 = build_tools / ("d8.bat" if IS_WINDOWS else "d8")
    if not android_jar.is_file():
        raise SystemExit(f"{android_jar} is missing")
    if not d8.is_file():
        raise SystemExit(f"{d8} is missing")

    print(f"sdk         : {sdk}")
    print(f"android.jar : {android_jar}")
    print(f"d8          : {d8}")

    if WORK.exists():
        shutil.rmtree(WORK)
    classes = WORK / "classes"
    classes.mkdir(parents=True)

    # Source and target 8: the injector runs on whatever ART the phone has, and
    # nothing here needs a newer language level.
    subprocess.run(
        [find_javac(), "-source", "8", "-target", "8", "-nowarn",
         "-bootclasspath", str(android_jar), "-classpath", str(android_jar),
         "-d", str(classes), str(SOURCE)],
        check=True,
    )

    class_files = sorted(str(path) for path in classes.rglob("*.class"))
    subprocess.run(
        [str(d8), "--release", "--min-api", "24", "--lib", str(android_jar),
         "--output", str(WORK), *class_files],
        check=True,
    )

    dex = WORK / "classes.dex"
    if not dex.is_file():
        raise SystemExit("d8 produced no classes.dex")

    OUT_JAR.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT_JAR, "w", zipfile.ZIP_DEFLATED) as jar:
        jar.write(dex, "classes.dex")

    print(f"built {OUT_JAR} ({OUT_JAR.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
