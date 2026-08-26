"""Decoding raw touch events into recordings that travel."""

import json
import tempfile
import unittest
from pathlib import Path

from mthread.gestures import GESTURE_FORMAT_VERSION, GestureSession, Stroke
from mthread.session import InputEvent
from mthread.touch import TouchDevice


def panel(**fields) -> TouchDevice:
    """A digitizer whose range is deliberately not the display's."""
    return TouchDevice(path="/dev/input/event2", name="touch",
                       x_range=(0, 4095), y_range=(0, 4095), has_slot=True, **fields)


def events(rows) -> list[InputEvent]:
    return [InputEvent(t=t, device="/dev/input/event2", type=etype, code=code, value=value)
            for t, etype, code, value in rows]


class DecodingTests(unittest.TestCase):

    def test_one_finger_becomes_one_stroke_in_screen_fractions(self):
        session = GestureSession.from_events(events([
            (0.00, 0x03, 0x39, 5),       # tracking id: a finger arrives
            (0.00, 0x03, 0x35, 0),       # x at the very left
            (0.00, 0x03, 0x36, 0),       # y at the very top
            (0.00, 0x00, 0x00, 0),       # SYN_REPORT
            (0.05, 0x03, 0x35, 4095),    # to the far corner
            (0.05, 0x03, 0x36, 4095),
            (0.05, 0x00, 0x00, 0),
            (0.10, 0x03, 0x39, -1),      # lifted
            (0.10, 0x00, 0x00, 0),
        ]), panel())

        self.assertEqual(len(session.strokes), 1)
        self.assertEqual(session.strokes[0].points,
                         [(0.0, 0.0, 0.0), (0.05, 1.0, 1.0)])

    def test_the_same_recording_lands_on_any_screen(self):
        """The point of the format: a fraction means the same thing everywhere.

        One maps to the last addressable pixel rather than to the width, so a
        touch recorded at the very edge stays on the screen instead of landing
        one pixel past it.
        """
        session = GestureSession(strokes=[Stroke([(0.0, 0.0, 0.5), (0.1, 1.0, 0.5)])])
        self.assertEqual(session.to_pixels(1000, 2000), [[(0, 1000), (999, 1000)]])
        self.assertEqual(session.to_pixels(400, 800), [[(0, 400), (399, 400)]])

    def test_two_fingers_are_two_strokes(self):
        session = GestureSession.from_events(events([
            (0.0, 0x03, 0x2F, 0), (0.0, 0x03, 0x39, 1),
            (0.0, 0x03, 0x35, 1000), (0.0, 0x03, 0x36, 1000),
            (0.0, 0x03, 0x2F, 1), (0.0, 0x03, 0x39, 2),
            (0.0, 0x03, 0x35, 3000), (0.0, 0x03, 0x36, 3000),
            (0.0, 0x00, 0x00, 0),
            (0.1, 0x03, 0x2F, 0), (0.1, 0x03, 0x35, 1200),
            (0.1, 0x03, 0x2F, 1), (0.1, 0x03, 0x35, 2800),
            (0.1, 0x00, 0x00, 0),
            (0.2, 0x03, 0x2F, 0), (0.2, 0x03, 0x39, -1),
            (0.2, 0x03, 0x2F, 1), (0.2, 0x03, 0x39, -1),
            (0.2, 0x00, 0x00, 0),
        ]), panel())

        self.assertEqual(len(session.strokes), 2)
        self.assertEqual([len(stroke.points) for stroke in session.strokes], [2, 2])

    def test_a_finger_that_does_not_move_reports_once(self):
        """A held finger repeats its position every frame; that is not motion."""
        rows = [(0.0, 0x03, 0x39, 7), (0.0, 0x03, 0x35, 100), (0.0, 0x03, 0x36, 100),
                (0.0, 0x00, 0x00, 0)]
        for frame in range(1, 6):
            rows.append((frame / 60.0, 0x00, 0x00, 0))
        rows += [(0.2, 0x03, 0x39, -1), (0.2, 0x00, 0x00, 0)]

        session = GestureSession.from_events(events(rows), panel())
        self.assertEqual(len(session.strokes[0].points), 1)

    def test_a_swapped_panel_is_untangled_on_the_way_in(self):
        session = GestureSession.from_events(events([
            (0.0, 0x03, 0x39, 1), (0.0, 0x03, 0x35, 0), (0.0, 0x03, 0x36, 4095),
            (0.0, 0x00, 0x00, 0), (0.1, 0x03, 0x39, -1), (0.1, 0x00, 0x00, 0),
        ]), panel(swap_xy=True))
        self.assertEqual(session.strokes[0].points[0][1:], (1.0, 0.0))

    def test_a_recording_without_the_digitizer_ranges_is_refused(self):
        with self.assertRaises(ValueError):
            GestureSession.from_events(events([]), TouchDevice(path="/dev/input/event2"))


class FileTests(unittest.TestCase):

    def test_it_round_trips(self):
        session = GestureSession(strokes=[Stroke([(0.0, 0.1, 0.2), (0.5, 0.3, 0.4)])],
                                 screen_size=(1080, 1920), device_model="Pixel 8 Pro")
        with tempfile.TemporaryDirectory() as folder:
            path = session.save(Path(folder) / "one.json")
            back = GestureSession.load(path)
        self.assertEqual(back.device_model, "Pixel 8 Pro")
        self.assertEqual(back.screen_size, (1080, 1920))
        self.assertEqual(back.strokes[0].points, session.strokes[0].points)
        self.assertAlmostEqual(back.duration, 0.5)

    def test_an_old_raw_recording_says_what_to_do_about_it(self):
        """Version 1 files hold digitizer coordinates and cannot be made portable."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.json"
            path.write_text(json.dumps({"version": 1, "events": []}), encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                GestureSession.load(path)
        self.assertIn("record it again", str(caught.exception).lower())

    def test_a_newer_file_is_refused_rather_than_half_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "future.json"
            path.write_text(json.dumps({"version": GESTURE_FORMAT_VERSION + 1}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                GestureSession.load(path)


if __name__ == "__main__":
    unittest.main()
