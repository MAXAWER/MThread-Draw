"""Create an emulator without the SDK's package manager.

    python tools/make_avd.py --name mthread-test

An AVD is two text files: an ini naming the folder, and a config.ini describing
the device and pointing at a system image. `avdmanager` writes them for you, and
on this machine it cannot: the current Android CLI crashes with a stack buffer
overrun, and the deprecated `sdkmanager` now forwards to it. Writing them
directly needs nothing but a system image on disk.

It also means the emulator can be set up on a machine that has the image but not
the package metadata, which is the state Android Studio leaves behind when a
download is interrupted.

    python tools/make_avd.py --list        # what images are on this machine
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

#: Where an AVD lives, which is not inside the SDK.
AVD_HOME = Path(os.environ.get("ANDROID_AVD_HOME")
                or Path.home() / ".android" / "avd")


def find_sdk() -> Path:
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(name)
        if value and Path(value).is_dir():
            return Path(value)
    for candidate in (Path.home() / "AppData" / "Local" / "Android" / "Sdk",
                      Path.home() / "Library" / "Android" / "sdk",
                      Path.home() / "Android" / "Sdk"):
        if candidate.is_dir():
            return candidate
    raise SystemExit("Could not find an Android SDK. Set ANDROID_HOME.")


def images(sdk: Path):
    """Every system image with the files an emulator actually needs."""
    root = sdk / "system-images"
    if not root.is_dir():
        return []
    found = []
    for path in sorted(root.glob("*/*/*")):
        if (path / "system.img").is_file() or (path / "kernel-ranchu").is_file():
            api, tag, abi = path.parts[-3:]
            found.append((api, tag, abi, path))
    return found


def config(image, abi: str, tag: str, width: int, height: int, density: int,
           ram: int, storage: int, sdk: Path) -> str:
    relative = image.relative_to(sdk).as_posix().replace("/", "\\") + "\\"
    return "\n".join([
        "avd.ini.encoding=UTF-8",
        f"abi.type={abi}",
        f"hw.cpu.arch={'x86_64' if abi.endswith('x86_64') else 'arm64'}",
        f"image.sysdir.1={relative}",
        f"tag.id={tag}",
        f"tag.display={tag}",
        f"hw.lcd.width={width}",
        f"hw.lcd.height={height}",
        f"hw.lcd.density={density}",
        f"hw.ramSize={ram}",
        f"disk.dataPartition.size={storage}M",
        "hw.keyboard=yes",
        "hw.gpu.enabled=yes",
        "hw.gpu.mode=auto",
        "hw.audioInput=no",
        "hw.audioOutput=no",
        # No frame around the screen: the point of this emulator is that
        # something else is looking at its pixels.
        "showDeviceFrame=no",
        "skin.dynamic=yes",
        "hw.device.manufacturer=Google",
        "hw.initialOrientation=Portrait",
        "fastboot.forceColdBoot=no",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="mthread-test")
    parser.add_argument("--list", action="store_true", help="show the images available")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=2280)
    parser.add_argument("--density", type=int, default=440)
    parser.add_argument("--ram", type=int, default=2048, help="megabytes")
    parser.add_argument("--storage", type=int, default=4096, help="megabytes of user data")
    args = parser.parse_args()

    sdk = find_sdk()
    available = images(sdk)
    if args.list or not available:
        print(f"sdk: {sdk}")
        for api, tag, abi, path in available:
            print(f"  {api}  {tag}  {abi}")
        if not available:
            print("  no usable system image found - the folders exist but hold no system.img")
            return 1
        return 0

    api, tag, abi, image = available[-1]
    folder = AVD_HOME / f"{args.name}.avd"
    folder.mkdir(parents=True, exist_ok=True)

    (AVD_HOME / f"{args.name}.ini").write_text("\n".join([
        "avd.ini.encoding=UTF-8",
        f"path={folder}",
        f"path.rel=avd/{args.name}.avd",
        f"target={api}",
        "",
    ]), encoding="utf-8")

    (folder / "config.ini").write_text(
        config(image, abi, tag, args.width, args.height, args.density,
               args.ram, args.storage, sdk), encoding="utf-8")

    print(f"created {args.name} from {api}/{tag}/{abi}")
    print(f"  {folder}")
    print(f"start it with: {sdk / 'emulator' / 'emulator'} -avd {args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
