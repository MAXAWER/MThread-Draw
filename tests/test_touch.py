import unittest

from mthread.touch import (
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    ABS_MT_TRACKING_ID,
    EV_ABS,
    build_stroke_events,
    parse_getevent_pl,
    pick_touchscreen,
    TouchDevice,
)

GETEVENT_PL = """add device 1: /dev/input/event0
  name:     "gpio-keys"
  events:
    KEY (0001): 0072  0073
add device 2: /dev/input/event3
  name:     "sec_touchscreen"
  events:
    KEY (0001): 014a
    ABS (0003): ABS_MT_SLOT          : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_TOUCH_MAJOR   : value 0, min 0, max 255, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X    : value 0, min 0, max 4095, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y    : value 0, min 0, max 4095, fuzz 0, flat 0, resolution 0
                ABS_MT_TRACKING_ID   : value 0, min 0, max 65535, fuzz 0, flat 0, resolution 0
                ABS_MT_PRESSURE      : value 0, min 0, max 255, fuzz 0, flat 0, resolution 0
"""


class ParseGeteventPlTests(unittest.TestCase):
    def setUp(self):
        self.devices = parse_getevent_pl(GETEVENT_PL)

    def test_finds_every_device(self):
        self.assertEqual([d.path for d in self.devices], ["/dev/input/event0", "/dev/input/event3"])

    def test_reads_names(self):
        self.assertEqual(self.devices[1].name, "sec_touchscreen")

    def test_only_touchscreen_has_coordinates(self):
        self.assertFalse(self.devices[0].is_touchscreen)
        self.assertTrue(self.devices[1].is_touchscreen)

    def test_reads_axis_ranges(self):
        touch = self.devices[1]
        self.assertEqual(touch.x_range, (0, 4095))
        self.assertEqual(touch.y_range, (0, 4095))
        self.assertEqual(touch.pressure_range, (0, 255))
        self.assertEqual(touch.touch_major_range, (0, 255))
        self.assertEqual(touch.tracking_id_range, (0, 65535))
        self.assertTrue(touch.has_slot)
        self.assertTrue(touch.has_btn_touch)

    def test_pick_touchscreen(self):
        self.assertEqual(pick_touchscreen(self.devices).path, "/dev/input/event3")

    def test_pick_returns_none_without_touchscreen(self):
        self.assertIsNone(pick_touchscreen([TouchDevice(path="/dev/input/event0")]))

    def test_empty_output_is_safe(self):
        self.assertEqual(parse_getevent_pl(""), [])


class CoordinateMappingTests(unittest.TestCase):
    """The bug this fixes: a 4096-step digitizer under a 1080 px display."""

    def setUp(self):
        self.touch = parse_getevent_pl(GETEVENT_PL)[1]

    def test_origin_maps_to_axis_minimum(self):
        self.assertEqual(self.touch.to_raw(0, 0, 1080, 2400), (0, 0))

    def test_far_corner_maps_to_axis_maximum(self):
        self.assertEqual(self.touch.to_raw(1079, 2399, 1080, 2400), (4095, 4095))

    def test_centre_maps_to_axis_centre(self):
        x, y = self.touch.to_raw(539.5, 1199.5, 1080, 2400)
        self.assertAlmostEqual(x, 2047, delta=1)
        self.assertAlmostEqual(y, 2047, delta=1)

    def test_out_of_range_is_clamped(self):
        self.assertEqual(self.touch.to_raw(-50, 99999, 1080, 2400), (0, 4095))

    def test_identity_when_ranges_match_screen(self):
        device = TouchDevice(path="/dev/input/event1", x_range=(0, 1079), y_range=(0, 2399))
        self.assertEqual(device.to_raw(300, 900, 1080, 2400), (300, 900))

    def test_swap_xy(self):
        device = TouchDevice(path="/dev/input/event1", x_range=(0, 99), y_range=(0, 99), swap_xy=True)
        self.assertEqual(device.to_raw(0, 2399, 1080, 2400), (99, 0))

    def test_rejects_degenerate_screen(self):
        with self.assertRaises(ValueError):
            self.touch.to_raw(0, 0, 1, 1)

    def test_device_without_ranges_passes_through(self):
        device = TouchDevice(path="/dev/input/event9")
        self.assertEqual(device.to_raw(12.4, 8.6, 1080, 2400), (12, 9))


class StrokeEventTests(unittest.TestCase):
    def setUp(self):
        self.touch = parse_getevent_pl(GETEVENT_PL)[1]
        self.events = build_stroke_events(self.touch, [(0, 0), (1079, 2399)], 1080, 2400, tracking_id=7)

    def test_empty_path_produces_nothing(self):
        self.assertEqual(build_stroke_events(self.touch, [], 1080, 2400), [])

    def test_tracking_id_is_claimed_then_released(self):
        tracking = [value for etype, code, value in self.events if code == ABS_MT_TRACKING_ID]
        self.assertEqual(tracking, [7, -1])

    def test_coordinates_are_translated_not_raw(self):
        xs = [value for etype, code, value in self.events if etype == EV_ABS and code == ABS_MT_POSITION_X]
        ys = [value for etype, code, value in self.events if etype == EV_ABS and code == ABS_MT_POSITION_Y]
        self.assertEqual(xs, [0, 4095])
        self.assertEqual(ys, [0, 4095])

    def test_one_sync_per_point_plus_final_release(self):
        syncs = [e for e in self.events if e[0] == 0]
        self.assertEqual(len(syncs), 3)

    def test_optional_axes_are_skipped_when_unsupported(self):
        bare = TouchDevice(path="/dev/input/event1", x_range=(0, 999), y_range=(0, 999))
        events = build_stroke_events(bare, [(1, 1)], 1080, 2400)
        codes = {code for _, code, _ in events}
        self.assertNotIn(0x3A, codes)   # no pressure
        self.assertNotIn(0x2F, codes)   # no slot
        self.assertNotIn(0x14A, codes)  # no BTN_TOUCH


if __name__ == "__main__":
    unittest.main()
