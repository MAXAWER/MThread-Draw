import unittest

from mthread.recorder import parse_getevent_line


class ParseGeteventLineTests(unittest.TestCase):
    def test_parses_a_normal_line(self):
        result = parse_getevent_line("[   12345.678901] /dev/input/event2: 0003 0035 000004a1")
        self.assertEqual(result, (12345.678901, "/dev/input/event2", 3, 0x35, 0x4A1))

    def test_handles_tight_spacing(self):
        result = parse_getevent_line("[1.5] /dev/input/event0: 0000 0000 00000000")
        self.assertEqual(result, (1.5, "/dev/input/event0", 0, 0, 0))

    def test_tracking_id_release_is_negative_one(self):
        result = parse_getevent_line("[  10.0] /dev/input/event2: 0003 0039 ffffffff")
        self.assertEqual(result[4], -1)

    def test_large_positive_value_survives(self):
        result = parse_getevent_line("[  10.0] /dev/input/event2: 0003 0039 0000ffff")
        self.assertEqual(result[4], 65535)

    def test_ignores_banner_and_noise(self):
        for line in ("add device 1: /dev/input/event0", "", "   ", "could not get driver version"):
            self.assertIsNone(parse_getevent_line(line))

    def test_ignores_non_timestamped_output(self):
        self.assertIsNone(parse_getevent_line("/dev/input/event2: 0003 0035 000004a1"))


if __name__ == "__main__":
    unittest.main()
