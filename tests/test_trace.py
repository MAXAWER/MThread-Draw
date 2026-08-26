import unittest

import numpy as np

from adbtouch.trace import rank_strokes, thin, trace_skeleton


def bar(height=40, width=60, thickness=5):
    """A horizontal bar, the simplest thing with a meaningful skeleton."""
    image = np.zeros((height, width), dtype=bool)
    mid = height // 2
    image[mid - thickness // 2:mid + thickness // 2 + 1, 5:width - 5] = True
    return image


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
