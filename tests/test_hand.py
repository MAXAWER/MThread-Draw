import math
import unittest

from adbtouch.hand import HandSettings, reorder_strokes, simulate


def bounds(paths):
    points = [point for path in paths for point in path]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


SQUARE = [[(100.0, 100.0), (400.0, 100.0), (400.0, 400.0), (100.0, 400.0), (100.0, 100.0)]]


class SimulateTests(unittest.TestCase):
    def test_zero_is_a_no_op(self):
        self.assertIs(simulate(SQUARE, 0), SQUARE)

    def test_the_drawing_stays_where_it_was(self):
        """Character, not position. A hand wobbles; it does not move the paper."""
        shaped = simulate(SQUARE, 1.0, seed=1)
        before = bounds(SQUARE)
        after = bounds(shaped)
        for original, drawn in zip(before, after):
            self.assertLess(abs(original - drawn), 12)

    def test_nothing_lands_exactly_on_the_geometry(self):
        shaped = simulate([[(0.0, 0.0), (200.0, 0.0)]], 1.0, seed=2)[0]
        off_axis = [y for _, y in shaped if abs(y) > 0.05]
        self.assertGreater(len(off_axis), len(shaped) // 2)

    def test_the_seed_makes_it_repeatable(self):
        self.assertEqual(simulate(SQUARE, 1.0, seed=9), simulate(SQUARE, 1.0, seed=9))
        self.assertNotEqual(simulate(SQUARE, 1.0, seed=9), simulate(SQUARE, 1.0, seed=10))

    def test_points_are_denser_where_the_pen_is_slower(self):
        """The velocity profile: every point costs the same to send, so spacing
        is speed. The ends of a stroke should be sampled more finely than the
        middle of a long straight."""
        shaped = simulate([[(0.0, 0.0), (600.0, 0.0)]], 1.0, seed=3,
                          settings=HandSettings(tremor=0, micro=0, smoothing=0, overshoot=0,
                                                entry_gap=0))[0]
        gaps = [math.dist(a, b) for a, b in zip(shaped, shaped[1:])]
        third = max(len(gaps) // 3, 1)
        self.assertLess(sum(gaps[:third]) / third, sum(gaps[third:-third or None]) / max(len(gaps) - 2 * third, 1))

    def test_a_hard_ceiling_on_points_per_stroke(self):
        huge = [[(float(i), float(i % 7)) for i in range(0, 40000, 3)]]
        shaped = simulate(huge, 1.0, seed=4, settings=HandSettings(max_points=50))
        self.assertLessEqual(len(shaped[0]), 52)

    def test_more_amount_wobbles_more(self):
        def spread(amount):
            shaped = simulate([[(0.0, 0.0), (300.0, 0.0)]], amount, seed=6)[0]
            return max(abs(y) for _, y in shaped)

        self.assertGreater(spread(3.0), spread(0.5))

    def test_degenerate_paths_are_dropped_not_crashed_on(self):
        self.assertEqual(simulate([[(1.0, 1.0)], []], 1.0, seed=1), [])

    def test_a_zero_length_stroke_survives(self):
        shaped = simulate([[(5.0, 5.0), (5.0, 5.0)]], 1.0, seed=1)
        self.assertLessEqual(len(shaped), 1)


class ReorderTests(unittest.TestCase):
    def test_nearest_stroke_comes_first(self):
        far = [(900.0, 900.0), (950.0, 900.0)]
        near = [(10.0, 10.0), (60.0, 10.0)]
        self.assertEqual(reorder_strokes([far, near])[0], near)

    def test_a_stroke_is_reversed_when_its_far_end_is_nearer(self):
        ordered = reorder_strokes([[(500.0, 0.0), (10.0, 0.0)]], start=(0.0, 0.0))
        self.assertEqual(ordered[0][0], (10.0, 0.0))

    def test_short_paths_are_dropped(self):
        self.assertEqual(reorder_strokes([[(1.0, 1.0)]]), [])

    def test_every_stroke_is_kept(self):
        paths = [[(float(i), 0.0), (float(i) + 5, 0.0)] for i in range(0, 100, 10)]
        self.assertEqual(len(reorder_strokes(paths)), len(paths))


class SettingsTests(unittest.TestCase):
    def test_amount_scales_the_wobble_but_barely_the_spacing(self):
        """Spacing is what a drawing costs, so it must not blow up with amount."""
        base = HandSettings()
        gentle = base.scaled(0.5)
        wild = base.scaled(3.0)
        self.assertGreater(wild.tremor, gentle.tremor * 4)
        self.assertGreater(wild.spacing, base.spacing * 0.4)

    def test_smoothing_and_ease_saturate(self):
        extreme = HandSettings().scaled(50)
        self.assertLessEqual(extreme.smoothing, 1.0)
        self.assertLessEqual(extreme.ease, 0.9)


if __name__ == "__main__":
    unittest.main()
