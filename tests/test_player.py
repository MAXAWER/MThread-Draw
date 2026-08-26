import unittest

from mthread.player import build_replay_script, iter_replay_chunks, replay
from mthread.session import InputEvent, Session


def events(*times):
    return [InputEvent(t, "/dev/input/event3", 3, 0x35, index) for index, t in enumerate(times)]


class ReplayScriptTests(unittest.TestCase):
    def test_first_event_needs_no_sleep(self):
        script = build_replay_script(events(0.0))
        self.assertEqual(script, ["sendevent /dev/input/event3 3 53 0"])

    def test_gap_becomes_a_sleep(self):
        script = build_replay_script(events(0.0, 0.5))
        self.assertIn("sleep 0.500", script)

    def test_tiny_gaps_are_not_worth_a_sleep(self):
        script = build_replay_script(events(0.0, 0.001, 0.002))
        self.assertEqual([line for line in script if line.startswith("sleep")], [])

    def test_speed_scales_the_wait(self):
        fast = build_replay_script(events(0.0, 1.0), speed=2.0)
        self.assertIn("sleep 0.500", fast)

    def test_sleep_totals_track_absolute_time_without_drift(self):
        # 400 events a third of a second apart: naive per-event rounding would
        # accumulate visible error over a recording this long.
        times = [i / 3 for i in range(400)]
        script = build_replay_script(events(*times))
        slept = sum(float(line.split()[1]) for line in script if line.startswith("sleep"))
        self.assertAlmostEqual(slept, times[-1], delta=0.01)

    def test_rejects_non_positive_speed(self):
        with self.assertRaises(ValueError):
            build_replay_script(events(0.0), speed=0)

    def test_negative_values_are_emitted_verbatim(self):
        script = build_replay_script([InputEvent(0.0, "/dev/input/event3", 3, 0x39, -1)])
        self.assertEqual(script[0], "sendevent /dev/input/event3 3 57 -1")

    def test_chunks_cover_every_event(self):
        chunks = list(iter_replay_chunks(events(*[i / 10 for i in range(25)]), chunk_events=10))
        sends = sum(len([l for l in chunk if l.startswith("sendevent")]) for chunk in chunks)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(sends, 25)

    def test_each_chunk_starts_without_a_leading_sleep(self):
        for chunk in iter_replay_chunks(events(*[i * 1.0 for i in range(9)]), chunk_events=3):
            self.assertTrue(chunk[0].startswith("sendevent"))


class FakeDevice:
    def __init__(self, screen=(1080, 2400)):
        self.screen_size = screen
        self.scripts = []

    def run_script(self, lines, **kwargs):
        self.scripts.append(list(lines))


class ReplayTests(unittest.TestCase):
    def test_replay_sends_the_script(self):
        device = FakeDevice()
        session = Session(events=events(0.0, 0.1), screen_size=(1080, 2400))
        replay(device, session)
        self.assertEqual(len(device.scripts), 1)

    def test_repeat_runs_it_again(self):
        device = FakeDevice()
        session = Session(events=events(0.0, 0.1), screen_size=(1080, 2400))
        replay(device, session, repeat=3)
        self.assertEqual(len(device.scripts), 3)

    def test_mismatched_screen_is_refused(self):
        device = FakeDevice(screen=(720, 1600))
        session = Session(events=events(0.0), screen_size=(1080, 2400))
        with self.assertRaises(ValueError) as ctx:
            replay(device, session)
        self.assertIn("1080x2400", str(ctx.exception))

    def test_recording_without_screen_metadata_is_allowed(self):
        device = FakeDevice()
        replay(device, Session(events=events(0.0)))
        self.assertEqual(len(device.scripts), 1)

    def test_empty_session_does_nothing(self):
        device = FakeDevice()
        replay(device, Session())
        self.assertEqual(device.scripts, [])

    def test_cancellation_stops_before_sending(self):
        device = FakeDevice()
        session = Session(events=events(*[i / 10 for i in range(20)]), screen_size=(1080, 2400))
        replay(device, session, should_continue=lambda: False)
        self.assertEqual(device.scripts, [])

    def test_progress_reports_completion(self):
        device = FakeDevice()
        seen = []
        session = Session(events=events(*[i / 10 for i in range(20)]), screen_size=(1080, 2400))
        replay(device, session, progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen[-1], (20, 20))


if __name__ == "__main__":
    unittest.main()
