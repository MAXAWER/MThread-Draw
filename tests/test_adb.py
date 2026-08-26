import os
import shlex
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adbtouch.adb import bundled_candidates, find_adb, run_adb
from adbtouch.errors import AdbCommandError, AdbNotFoundError

IS_WINDOWS = sys.platform.startswith("win")


def make_fake_adb(directory: Path, *, stdout: str = "", stderr: str = "", exit_code: int = 0) -> Path:
    """Write a stand-in for the adb binary that prints fixed output and exits.

    Windows cannot execute a ``#!/bin/sh`` script, so there the stand-in is a
    ``.cmd`` that shells out to the running interpreter - which also keeps the
    output byte-exact, with no shell adding line endings of its own.
    """
    if IS_WINDOWS:
        path = directory / "fake-adb.cmd"
        code = "import sys;"
        if stdout:
            code += f"sys.stdout.write({stdout!r});"
        if stderr:
            code += f"sys.stderr.write({stderr!r});"
        path.write_text(
            "@echo off\r\n"
            f'"{sys.executable}" -c "{code}"\r\n'
            f"exit /b {exit_code}\r\n"
        )
        return path

    body = ["#!/bin/sh"]
    if stdout:
        body.append(f"printf '%s' {shlex.quote(stdout)}")
    if stderr:
        body.append(f"printf '%s' {shlex.quote(stderr)} >&2")
    body.append(f"exit {exit_code}")

    path = directory / "fake-adb"
    path.write_text("\n".join(body) + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class FindAdbTests(unittest.TestCase):
    def assertSamePath(self, found: str, expected: Path) -> None:
        """Compare through ``resolve``.

        ``find_adb`` returns an absolute path but does not follow symlinks, and
        on macOS a temporary directory lives under ``/var``, which is itself a
        link to ``/private/var``. Comparing the raw strings fails there for no
        interesting reason.
        """
        self.assertEqual(Path(found).resolve(), expected.resolve())

    def test_explicit_path_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp))
            self.assertSamePath(find_adb(str(fake)), fake)

    def test_env_var_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp))
            with mock.patch.dict(os.environ, {"ADB_PATH": str(fake)}):
                self.assertSamePath(find_adb(), fake)

    def test_falls_back_to_path_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp))
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("adbtouch.adb.shutil.which", return_value=str(fake)):
                self.assertSamePath(find_adb(), fake)

    def test_missing_binary_raises_with_guidance(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("adbtouch.adb.shutil.which", return_value=None), \
             mock.patch("adbtouch.adb.os.path.isfile", return_value=False):
            with self.assertRaises(AdbNotFoundError) as ctx:
                find_adb()
        self.assertIn("ADB_PATH", str(ctx.exception))

    @unittest.skipIf(IS_WINDOWS, "every existing file passes os.access(X_OK) on Windows")
    def test_non_executable_candidate_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "adb"
            plain.write_text("not executable")
            plain.chmod(0o644)
            # The per-platform fallbacks have to go too: a machine with the
            # Android SDK installed in its default location - every macOS CI
            # runner, for one - would find a real adb there and never raise.
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("adbtouch.adb.shutil.which", return_value=None), \
                 mock.patch.dict("adbtouch.adb._FALLBACKS", {"win32": [], "darwin": [], "linux": []}):
                with self.assertRaises(AdbNotFoundError):
                    find_adb(str(plain))


class BundledAdbTests(unittest.TestCase):
    """The installers ship their own adb; a source checkout must not pretend to."""

    def test_source_checkout_offers_nothing(self):
        self.assertEqual(bundled_candidates(), [])

    def test_frozen_build_looks_beside_itself(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", r"C:\app" if IS_WINDOWS else "/app", create=True):
            found = bundled_candidates()
        name = "adb.exe" if IS_WINDOWS else "adb"
        self.assertTrue(any(c.endswith(os.path.join("platform-tools", name)) for c in found))

    def test_project_local_platform_tools_is_found(self):
        """What tools/fetch_platform_tools.py leaves behind in a source checkout.

        The file has to carry adb's real name here, since that is exactly what
        find_adb looks for; it never has to run.
        """
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "platform-tools"
            local.mkdir()
            fake = local / ("adb.exe" if IS_WINDOWS else "adb")
            fake.write_text("not a real adb")
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("adbtouch.adb.shutil.which", return_value=None), \
                 mock.patch("adbtouch.adb.Path.cwd", return_value=Path(tmp)), \
                 mock.patch.dict("adbtouch.adb._FALLBACKS", {"win32": [], "darwin": [], "linux": []}):
                self.assertEqual(Path(find_adb()).resolve(), fake.resolve())

    def test_bundled_copy_beats_whatever_is_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled = make_fake_adb(Path(tmp))
            elsewhere = make_fake_adb(Path(tempfile.mkdtemp()))
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("adbtouch.adb.bundled_candidates", return_value=[str(bundled)]), \
                 mock.patch("adbtouch.adb.shutil.which", return_value=str(elsewhere)):
                self.assertEqual(Path(find_adb()).resolve(), bundled.resolve())


class RunAdbTests(unittest.TestCase):
    def test_success_returns_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp), stdout="hello\n")
            self.assertEqual(run_adb(str(fake), ["devices"]).stdout.strip(), "hello")

    def test_failure_raises_instead_of_passing_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp), stderr="device offline\n", exit_code=1)
            with self.assertRaises(AdbCommandError) as ctx:
                run_adb(str(fake), ["shell", "input", "tap", "1", "2"])
        self.assertEqual(ctx.exception.returncode, 1)
        self.assertIn("device offline", str(ctx.exception))

    def test_check_false_swallows_the_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp), exit_code=3)
            self.assertEqual(run_adb(str(fake), ["x"], check=False).returncode, 3)

    def test_binary_mode_returns_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = make_fake_adb(Path(tmp), stdout="PNG")
            self.assertEqual(run_adb(str(fake), ["exec-out"], binary=True).stdout, b"PNG")


if __name__ == "__main__":
    unittest.main()
