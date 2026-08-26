import json
import tempfile
import unittest
from pathlib import Path

from mthread.session import SESSION_FORMAT_VERSION, InputEvent, Session


def sample_session():
    return Session(
        events=[
            InputEvent(0.0, "/dev/input/event3", 3, 0x39, 1),
            InputEvent(0.25, "/dev/input/event3", 3, 0x35, 500),
            InputEvent(1.5, "/dev/input/event3", 3, 0x39, -1),
        ],
        screen_size=(1080, 2400),
        device_serial="ABC123",
        note="login flow",
    )


class SessionTests(unittest.TestCase):
    def test_duration_is_last_timestamp(self):
        self.assertAlmostEqual(sample_session().duration, 1.5)

    def test_empty_session_has_zero_duration(self):
        self.assertEqual(Session().duration, 0.0)

    def test_devices_are_unique_and_ordered(self):
        session = sample_session()
        session.events.append(InputEvent(2.0, "/dev/input/event0", 1, 114, 1))
        self.assertEqual(session.devices, ["/dev/input/event3", "/dev/input/event0"])

    def test_created_at_is_filled_in(self):
        self.assertTrue(Session().created_at)

    def test_round_trip_through_dict(self):
        original = sample_session()
        restored = Session.from_dict(original.to_dict())
        self.assertEqual(len(restored.events), 3)
        self.assertEqual(restored.screen_size, (1080, 2400))
        self.assertEqual(restored.device_serial, "ABC123")
        self.assertEqual(restored.note, "login flow")
        self.assertEqual(restored.events[2].value, -1)

    def test_round_trip_through_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            sample_session().save(path)
            restored = Session.load(path)
        self.assertAlmostEqual(restored.duration, 1.5)

    def test_events_are_stored_compactly(self):
        payload = json.loads(json.dumps(sample_session().to_dict()))
        self.assertIsInstance(payload["events"][0], list)
        self.assertEqual(payload["event_count"], 3)

    def test_future_format_version_is_rejected(self):
        payload = sample_session().to_dict()
        payload["version"] = SESSION_FORMAT_VERSION + 1
        with self.assertRaises(ValueError):
            Session.from_dict(payload)

    def test_missing_optional_fields_are_tolerated(self):
        restored = Session.from_dict({"version": 1, "events": [[0.0, "/dev/input/event3", 3, 53, 10]]})
        self.assertIsNone(restored.screen_size)
        self.assertEqual(len(restored.events), 1)


if __name__ == "__main__":
    unittest.main()
