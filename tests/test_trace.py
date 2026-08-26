import unittest

import numpy as np

from adbtouch.trace import rank_strokes, thin, trace_skeleton, xdog


def bar(height=40, width=60, thickness=5):
    """A horizontal bar, the simplest thing with a meaningful skeleton."""
    image = np.zeros((height, width), dtype=bool)
    mid = height // 2
    image[mid - thickness // 2:mid + thickness // 2 + 1, 5:width - 5] = True
    return image


class XdogTests(unittest.TestCase):
    def test_a_step_edge_becomes_a_line(self):
        gray = np.zeros((40, 40), dtype=np.uint8)
        gray[:, 20:] = 255
        mask = xdog(gray, sigma=1.0, ink=0.1)
        self.assertTrue(mask.any())
        # The line belongs at the step, not spread across the flat halves.
        columns = np.where(mask.any(axis=0))[0]
        self.assertLess(abs(int(columns.mean()) - 20), 4)

    def test_flat_images_produce_almost_nothing(self):
        gray = np.full((40, 40), 128, dtype=np.uint8)
        self.assertLess(xdog(gray, ink=0.1).mean(), 0.2)

    def test_ink_controls_how_much_line_there_is(self):
        rng = np.random.default_rng(0)
        gray = (rng.random((80, 80)) * 255).astype(np.uint8)
        self.assertLess(xdog(gray, ink=0.05).sum(), xdog(gray, ink=0.3).sum())

    def test_the_same_setting_means_the_same_density_at_any_brightness(self):
        """A fixed threshold would give a dark photo far more ink than a bright
        one; the quantile is what stops the sliders meaning different things
        from picture to picture."""
        rng = np.random.default_rng(1)
        base = rng.random((80, 80))
        dark = (base * 90).astype(np.uint8)
        bright = (base * 90 + 160).astype(np.uint8)
        self.assertAlmostEqual(xdog(dark, ink=0.15).mean(), xdog(bright, ink=0.15).mean(),
                               delta=0.05)


class ThinTests(unittest.TestCase):
    def test_a_thick_bar_becomes_one_pixel_tall(self):
        skeleton = thin(bar())
        for column in range(10, 45):
            self.assertLessEqual(skeleton[:, column].sum(), 2)

    def test_the_bar_is_still_there(self):
        self.assertTrue(thin(bar()).any())

    def test_nothing_in_nothing_out(self):
        self.assertFalse(thin(np.zeros((20, 20), dtype=bool)).any())


class TraceTests(unittest.TestCase):
    def test_a_bar_traces_to_one_stroke(self):
        paths = trace_skeleton(thin(bar()))
        self.assertEqual(len(paths), 1)
        self.assertGreater(len(paths[0]), 30)

    def test_the_stroke_runs_along_the_bar(self):
        path = trace_skeleton(thin(bar()))[0]
        xs = [x for x, _ in path]
        ys = [y for _, y in path]
        self.assertGreater(max(xs) - min(xs), 40)
        self.assertLessEqual(max(ys) - min(ys), 2)

    def test_a_cross_is_not_shattered_into_stubs(self):
        """Carrying straight on through a junction is the difference between
        drawing a girder and drawing thirty fragments of one."""
        image = np.zeros((60, 60), dtype=bool)
        image[29:32, 5:55] = True
        image[5:55, 29:32] = True
        paths = trace_skeleton(thin(image))
        self.assertLessEqual(len(paths), 3)
        self.assertGreater(max(len(path) for path in paths), 35)

    def test_specks_below_the_minimum_are_dropped(self):
        image = np.zeros((30, 30), dtype=bool)
        image[10, 10:12] = True
        self.assertEqual(trace_skeleton(thin(image), min_points=5), [])


class RankTests(unittest.TestCase):
    def test_longest_first(self):
        short = [(0, 0), (2, 0), (4, 0), (6, 0)]
        long = [(0, 10), (40, 10), (80, 10), (120, 10)]
        self.assertEqual(rank_strokes([short, long])[0], long)

    def test_the_limit_keeps_the_important_ones(self):
        paths = [[(0, i), (i * 3, i)] * 3 for i in range(1, 10)]
        kept = rank_strokes(paths, limit=3)
        self.assertEqual(len(kept), 3)

    def test_short_paths_are_dropped(self):
        self.assertEqual(rank_strokes([[(0, 0)]], min_points=4), [])


if __name__ == "__main__":
    unittest.main()
