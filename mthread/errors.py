"""Exception types raised by :mod:`mthread`."""

__all__ = ["MThreadError", "AdbNotFoundError", "AdbCommandError", "DeviceNotConnectedError", "TouchDeviceNotFoundError"]


class MThreadError(Exception):
    """Base class for every error raised by this library."""


class AdbNotFoundError(MThreadError):
    """The ``adb`` executable could not be located on this machine."""


class AdbCommandError(MThreadError):
    """An ``adb`` invocation exited with a non-zero status."""

    def __init__(self, args, returncode, stderr=""):
        self.args_list = list(args)
        self.returncode = returncode
        self.stderr = (stderr or "").strip()
        detail = f": {self.stderr}" if self.stderr else ""
        super().__init__(f"adb {' '.join(self.args_list)} failed with code {returncode}{detail}")


class DeviceNotConnectedError(MThreadError):
    """An operation needed a device but none was attached."""


class TouchDeviceNotFoundError(MThreadError):
    """No touchscreen input device could be detected on the device."""
