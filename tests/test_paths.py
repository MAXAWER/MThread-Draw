import unittest

from mthread.paths import drop_specks, join_strokes, stroke_length, tidy


class LengthTests(unittest.TestCase):
    def test_measures_along_the_line(self):
        self.assertAlmostEqual(stroke_length([(0, 0), (3, 4), (3, 14)]), 15.0)

    def test_a_single_point_has_no_length(self):
        self.assertEqual(stroke_length([(5, 5)]), 0.0)


class JoinTests(unittest.TestCase):
    def test_fragments_that_meet_become_one_stroke(self):
        joined = join_strokes([[(0, 0), (10, 0)], [(10, 0), (20, 0)]])
        self.assertEqual(joined, [[(0, 0), (10, 0), (20, 0)]])

    def test_a_fragment_is_reversed_to_fit(self):
        joined = join_strokes([[(0, 0), (10, 0)], [(20, 0), (10, 0)]])
        self.assertEqual(joined, [[(0, 0), (10, 0), (20, 0)]])

    def test_a_gap_within_tolerance_still_joins(self):
        self.assertEqual(len(join_strokes([[(0, 0), (10, 0)], [(13, 0), (20, 0)]], tolerance=4)), 1)

    def test_a_gap_beyond_tolerance_does_not(self):
        self.assertEqual(len(join_strokes([[(0, 0), (10, 0)], [(30, 0), (40, 0)]], tolerance=4)), 2)

    def test_a_chain_of_fragments_collapses_to_one(self):
        pieces = [[(x, 0), (x + 10, 0)] for x in range(0, 100, 10)]
        joined = join_strokes(pieces)
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0][0], (0, 0))
        self.assertEqual(joined[0][-1], (100, 0))

    def test_no_point_is_invented_or_lost(self):
        pieces = [[(0, 0), (10, 0)], [(10, 0), (10, 10)], [(50, 50), (60, 60)]]
        joined = join_strokes(pieces)
        self.assertEqual(sum(len(path) for path in joined), 5)

    def test_degenerate_fragments_are_ignored(self):
        self.assertEqual(join_strokes([[(1, 1)], []]), [])


class SpeckTests(unittest.TestCase):
    def test_short_fragments_go(self):
        self.assertEqual(drop_specks([[(0, 0), (3, 0)]], min_length=8), [])

    def test_long_ones_stay(self):
        path = [(0, 0), (30, 0)]
        self.assertEqual(drop_specks([path], min_length=8), [path])


class TidyTests(unittest.TestCase):
    def test_a_speck_that_bridges_two_fragments_is_kept(self):
        """Order matters: join first, drop after. A four-pixel piece is worth
        keeping when it is the join between two real strokes."""
        pieces = [[(0, 0), (40, 0)], [(40, 0), (44, 0)], [(44, 0), (90, 0)]]
        self.assertEqual(len(tidy(pieces, join_tolerance=2, min_length=10)), 1)

    def test_a_speck_on_its_own_is_dropped(self):
        pieces = [[(0, 0), (40, 0)], [(500, 500), (503, 500)]]
        self.assertEqual(len(tidy(pieces, join_tolerance=2, min_length=10)), 1)

    def test_both_steps_can_be_turned_off(self):
        pieces = [[(0, 0), (2, 0)], [(2, 0), (4, 0)]]
        self.assertEqual(tidy(pieces, join_tolerance=0, min_length=0), pieces)


if __name__ == "__main__":
    unittest.main()
