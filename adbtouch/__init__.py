"""adbtouch - fast synthetic touch input, recording and replay for Android over ADB.

The library exists because ``adb shell input tap`` is too slow to be useful for
anything continuous: every call spawns a process on the device and costs
100-300 ms. Writing raw events to ``/dev/input`` through a single pushed script
is orders of magnitude faster, and it is what makes both gesture replay and
image drawing practical.

Typical use::

    from adbtouch import Device, Recorder, Session, replay

    device = Device()
    recorder = Recorder(device)
    recorder.start()
    ...                       # do things on the phone
    session = recorder.stop()
    session.save("login.json")

    replay(device, Session.load("login.json"), speed=2.0)
"""

from .adb import find_adb
from .device import Device, DeviceInfo, list_devices
from .hand import HandSettings, reorder_strokes, simulate
from .injector import InjectorUnavailableError, Pacing, TouchInjector
from .errors import (
    AdbCommandError,
    AdbNotFoundError,
    AdbTouchError,
    DeviceNotConnectedError,
    TouchDeviceNotFoundError,
)
from .player import build_replay_script, replay
from .recorder import Recorder, parse_getevent_line
from .session import InputEvent, Session
from .touch import TouchDevice, build_stroke_events, parse_getevent_pl, pick_touchscreen

__version__ = "1.1.0"

#: AGPL-3.0, with a commercial licence available from the author for use in
#: products that will not publish their source. See TERMS.md.
__license__ = "AGPL-3.0-only"

#: Image vectorisation is the only part that needs OpenCV, so it is imported on
#: first use. That keeps ``pip install adbtouch`` dependency-free for the common
#: case of recording and replaying gestures.
_LAZY = {"Vectorizer": "vectorize", "VectorizeSettings": "vectorize"}


def __getattr__(name):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(f".{module}", __name__), name)


def __dir__():
    return sorted(list(globals()) + list(_LAZY))

__all__ = [
    "__version__",
    "Device", "DeviceInfo", "list_devices", "find_adb",
    "HandSettings", "simulate", "reorder_strokes",
    "TouchInjector", "Pacing", "InjectorUnavailableError",
    "Recorder", "Session", "InputEvent", "replay", "build_replay_script", "parse_getevent_line",
    "TouchDevice", "parse_getevent_pl", "pick_touchscreen", "build_stroke_events",
    "Vectorizer", "VectorizeSettings",
    "AdbTouchError", "AdbNotFoundError", "AdbCommandError",
    "DeviceNotConnectedError", "TouchDeviceNotFoundError",
]
