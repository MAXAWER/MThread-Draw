import os
import pathlib
import unittest
import unittest.mock

from mthread.device import Device, DeviceInfo, REMOTE_TMP
from mthread.injector import InjectorUnavailableError
from mthread.touch import ABS_MT_POSITION_X, ABS_MT_TRACKING_ID, TouchDevice


def make_device(screen=(1080, 2400), touch=None, raw=True):
    """A Device with the ADB layer stubbed out, so batching logic can be tested."""
    device = Device.__new__(Device)
    device.adb_path = "/nonexistent/adb"
    device.serial = "TEST"
    device._screen_size = screen
    device._touch_device = touch or TouchDevice(
        path="/dev/input/event3",
        x_range=(0, 4095),
        y_range=(0, 4095),
        pressure_range=(0, 255),
        tracking_id_range=(0, 65535),
        has_slot=True,
        has_btn_touch=True,
    )
    device._supports_raw = raw
    device.injector_error = False
    device.scripts = []
    device.run_script = lambda lines, **kwargs: device.scripts.append(list(lines))
    return device


class DeviceInfoTests(unittest.TestCase):
    def test_ready_state(self):
        self.assertTrue(DeviceInfo("X", "device").is_ready)
        self.assertFalse(DeviceInfo("X", "offline").is_ready)

    def test_states_are_explained_in_plain_words(self):
        self.assertIn("USB debugging", DeviceInfo("X", "unauthorized").human_state)
        self.assertIn("cable", DeviceInfo("X", "offline").human_state)

    def test_unknown_state_passes_through(self):
        self.assertEqual(DeviceInfo("X", "weird").human_state, "weird")


class DrawPathsTests(unittest.TestCase):
    def test_sends_one_script_for_a_small_drawing(self):
        device = make_device()
        sent = device.draw_paths([[(0, 0), (100, 100)], [(5, 5), (200, 200)]])
        self.assertEqual(sent, 2)
        self.assertEqual(len(device.scripts), 1)

    def test_every_line_targets_the_touch_device(self):
        device = make_device()
        device.draw_paths([[(0, 0), (10, 10)]])
        for line in device.scripts[0]:
            self.assertTrue(line.startswith("sendevent /dev/input/event3") or line.startswith("sleep"))

    def test_coordinates_are_rescaled_to_the_digitizer(self):
        device = make_device()
        device.draw_paths([[(0, 0), (1079, 2399)]])
        xs = [int(l.split()[-1]) for l in device.scripts[0] if l.startswith("sendevent") and int(l.split()[3]) == ABS_MT_POSITION_X]
        self.assertEqual(xs, [0, 4095])

    def test_each_stroke_gets_its_own_tracking_id(self):
        device = make_device()
        device.draw_paths([[(0, 0), (10, 10)], [(20, 20), (30, 30)], [(40, 40), (50, 50)]])
        ids = [
            int(l.split()[-1])
            for l in device.scripts[0]
            if l.startswith("sendevent") and int(l.split()[3]) == ABS_MT_TRACKING_ID
        ]
        self.assertEqual(ids, [1, -1, 2, -1, 3, -1])

    def test_degenerate_paths_are_skipped(self):
        device = make_device()
        self.assertEqual(device.draw_paths([[(1, 1)], []]), 0)

    def test_long_drawings_are_chunked(self):
        device = make_device()
        paths = [[(i, i), (i + 10, i + 10)] for i in range(200)]
        device.draw_paths(paths, chunk_size=500)
        self.assertGreater(len(device.scripts), 1)

    def test_cancellation_stops_early(self):
        device = make_device()
        seen = {"n": 0}

        def keep_going():
            seen["n"] += 1
            return seen["n"] <= 2

        sent = device.draw_paths([[(i, i), (i + 5, i + 5)] for i in range(10)], should_continue=keep_going)
        self.assertEqual(sent, 2)

    def test_progress_reaches_the_end(self):
        device = make_device()
        seen = []
        device.draw_paths([[(0, 0), (10, 10)]], progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (1, 1))

    def test_device_without_raw_touch_still_maps_one_to_one(self):
        plain = TouchDevice(path="/dev/input/event1")
        device = make_device(touch=plain)
        device.draw_paths([[(12, 34), (56, 78)]])
        xs = [int(l.split()[-1]) for l in device.scripts[0] if l.startswith("sendevent") and int(l.split()[3]) == ABS_MT_POSITION_X]
        self.assertEqual(xs, [12, 56])


class RunScriptTests(unittest.TestCase):
    """The script must not be written into the user's working directory."""

    def _capture(self, lines):
        device = Device.__new__(Device)
        device.adb_path = "/nonexistent/adb"
        device.serial = "TEST"
        device._screen_size = (1080, 2400)
        device._touch_device = None
        calls = []

        def fake_run_adb(adb_path, args, **kwargs):
            calls.append(list(args))
            if args[2] == "push":
                calls.append(["<<body>>", pathlib.Path(args[3]).read_text()])
            return unittest.mock.Mock(returncode=0, stdout="", stderr="")

        with unittest.mock.patch("mthread.device.run_adb", side_effect=fake_run_adb):
            device.run_script(lines)
        return calls

    def test_scripts_go_to_a_writable_device_directory(self):
        self.assertEqual(REMOTE_TMP, "/data/local/tmp")

    def test_local_file_is_not_left_in_the_working_directory(self):
        before = set(os.listdir("."))
        self._capture(["sendevent /dev/input/event3 0 0 0"])
        self.assertEqual(set(os.listdir(".")) - before, set())

    def test_remote_path_is_unique_per_call(self):
        first = self._capture(["echo 1"])
        second = self._capture(["echo 1"])
        push_one = [c for c in first if len(c) > 2 and c[2] == "push"][0][4]
        push_two = [c for c in second if len(c) > 2 and c[2] == "push"][0][4]
        self.assertTrue(push_one.startswith(REMOTE_TMP))
        self.assertNotEqual(push_one, push_two)

    def test_script_has_a_shebang_and_the_commands(self):
        calls = self._capture(["sendevent /dev/input/event3 3 57 1", "sleep 0.100"])
        body = [c[1] for c in calls if c[0] == "<<body>>"][0]
        self.assertTrue(body.startswith("#!/system/bin/sh"))
        self.assertIn("sendevent /dev/input/event3 3 57 1", body)
        self.assertIn("sleep 0.100", body)

    def test_remote_file_is_cleaned_up(self):
        calls = self._capture(["echo 1"])
        self.assertTrue(any("rm" in call for call in calls))

    def test_temp_file_is_deleted_afterwards(self):
        calls = self._capture(["echo 1"])
        local = [c for c in calls if len(c) > 2 and c[2] == "push"][0][3]
        self.assertFalse(os.path.exists(local))



class FallbackDrawingTests(unittest.TestCase):
    """Devices that refuse raw events - every recent Pixel - still have to draw.

    SELinux denies the shell domain write access to /dev/input there, so
    sendevent fails per line while the script exits cleanly. The framework's own
    `input motionevent` injection works, and separate invocations join into one
    gesture, which is what lets a polyline through.
    """

    def test_input_path_speaks_motionevent(self):
        device = make_device(raw=False)
        device.draw_paths([[(10, 10), (20, 20), (30, 10)]], method="input")
        body = "\n".join(device.scripts[0])
        self.assertIn("input motionevent DOWN 10 10", body)
        self.assertIn("input motionevent MOVE 20 20", body)
        self.assertIn("input motionevent UP 30 10", body)
        self.assertNotIn("sendevent", body)

    def test_auto_uses_raw_when_it_is_allowed(self):
        device = make_device(raw=True)
        device.draw_paths([[(10, 10), (20, 20)]])
        self.assertIn("sendevent", "\n".join(device.scripts[0]))

    def test_one_down_and_one_up_per_stroke(self):
        device = make_device(raw=False)
        device.draw_paths([[(1, 1), (2, 2)], [(3, 3), (4, 4)]], method="input")
        body = "\n".join(line for script in device.scripts for line in script)
        self.assertEqual(body.count("motionevent DOWN"), 2)
        self.assertEqual(body.count("motionevent UP"), 2)

    def test_coordinates_stay_on_the_screen(self):
        device = make_device(screen=(1080, 2400), raw=False)
        device.draw_paths([[(-50, -50), (5000, 9000)]], method="input")
        body = "\n".join(device.scripts[0])
        self.assertIn("DOWN 0 0", body)
        self.assertIn("UP 1079 2399", body)

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(ValueError):
            make_device().draw_paths([[(1, 1), (2, 2)]], method="telepathy")

    def test_estimate_warns_that_the_input_path_is_slow(self):
        device = make_device(raw=False)
        paths = [[(i, i) for i in range(50)] for _ in range(10)]
        slow = device.estimate_duration(paths, method="input")
        fast = device.estimate_duration(paths, method="raw")
        self.assertGreater(slow, fast * 10)
        self.assertAlmostEqual(device.estimate_duration(paths, method="input", speed=2),
                               slow / 2, places=3)

    def test_auto_prefers_the_injector_when_raw_is_refused(self):
        device = make_device(raw=False)
        started = []

        class Stub:
            def __init__(self, owner, jar=None):
                started.append(owner)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def stroke(self, points, pacing=None, rng=None):
                started.append(("stroke", len(points)))
                # The real one answers with the milliseconds it queued, which is
                # how the caller knows when to wait for the device.
                return 0.0

            def pause(self, millis):
                return 0.0

            def sync(self, timeout=600.0):
                pass

        with unittest.mock.patch("mthread.device.TouchInjector", Stub):
            device.draw_paths([[(1, 1), (2, 2)]])
        self.assertEqual(started[0], device)
        self.assertEqual(device.scripts, [])

    def test_the_injector_waits_rather_than_queueing_the_whole_drawing(self):
        """Stop can only work if the host has not already sent everything.

        Every wait in a stroke happens on the phone, so writing one costs
        nothing and an unbounded loop hands over the entire drawing in a
        fraction of a second. The host then finishes while the device is still
        drawing out of a buffer nothing can reach, and Stop does nothing at all.
        """
        device = make_device(raw=False)
        events = []

        class Stub:
            def __init__(self, owner, jar=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def stroke(self, points, pacing=None, rng=None):
                events.append("stroke")
                return 300.0  # more than the look-ahead budget, on its own

            def pause(self, millis):
                return 0.0

            def sync(self, timeout=600.0):
                events.append("sync")

        paths = [[(1, 1), (2, 2)], [(3, 3), (4, 4)], [(5, 5), (6, 6)]]
        with unittest.mock.patch("mthread.device.TouchInjector", Stub):
            device.draw_paths(paths)

        # A wait after each stroke, because each one exceeds the budget alone.
        self.assertEqual(events, ["stroke", "sync", "stroke", "sync",
                                  "stroke", "sync", "sync"])

    def test_stopping_leaves_the_rest_of_the_drawing_unsent(self):
        device = make_device(raw=False)
        drawn = []

        class Stub:
            def __init__(self, owner, jar=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def stroke(self, points, pacing=None, rng=None):
                drawn.append(points[0])
                return 300.0

            def pause(self, millis):
                return 0.0

            def sync(self, timeout=600.0):
                pass

        paths = [[(index, index), (index + 1, index + 1)] for index in range(10)]
        with unittest.mock.patch("mthread.device.TouchInjector", Stub):
            sent = device.draw_paths(paths, should_continue=lambda: len(drawn) < 3)

        self.assertEqual(sent, 3)
        self.assertEqual(len(drawn), 3)

    def test_a_refusing_injector_drops_through_to_input(self):
        """Nothing guarantees app_process will run a jar for us. The slow path
        always works, so an unavailable injector must not be fatal."""
        device = make_device(raw=False)

        def refuse(*args, **kwargs):
            raise InjectorUnavailableError("no app_process here")

        with unittest.mock.patch("mthread.device.TouchInjector", refuse):
            device.draw_paths([[(1, 1), (2, 2)]])
        self.assertIn("input motionevent", chr(10).join(device.scripts[0]))
        self.assertTrue(device.injector_error)

