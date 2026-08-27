"""Shapes from equations, text from a font, and where they land."""

import math
import unittest

from mthread.placement import Placement, fit_to_screen, place_on_screen
from mthread.shapes import SHAPES, heart, star, text


def bounds(paths):
    points = [point for path in paths for point in path]
    return (min(x for x, _ in points), min(y for _, y in points),
            max(x for x, _ in points), max(y for _, y in points))


class ShapeTests(unittest.TestCase):

    def test_every_shape_fits_the_unit_square(self):
        """Callers place them; they do not each invent their own coordinates."""
        for name, maker in SHAPES.items():
            with self.subTest(shape=name):
                left, top, right, bottom = bounds(maker())
                self.assertGreaterEqual(left, -1e-9, name)
                self.assertGreaterEqual(top, -1e-9, name)
                self.assertLessEqual(right, 1 + 1e-9, name)
                self.assertLessEqual(bottom, 1 + 1e-9, name)

    def test_every_shape_keeps_its_proportions(self):
        """One side touches both edges; the other is centred, not stretched."""
        for name, maker in SHAPES.items():
            with self.subTest(shape=name):
                left, top, right, bottom = bounds(maker())
                longer = max(right - left, bottom - top)
                self.assertAlmostEqual(longer, 1.0, places=6, msg=name)

    def test_a_shape_closes(self):
        outline = heart()[0]
        self.assertEqual(outline[0], outline[-1])

    def test_a_star_has_the_points_asked_for(self):
        """Counted by how many times the radius reaches its maximum."""
        outline = star(points=7)[0][:-1]   # the closing repeat is not a corner
        centre = (0.5, 0.5)
        radii = [math.dist(point, centre) for point in outline]
        # Counted around the loop, because the first tip is at index zero and a
        # plain sliding window never gets to consider it.
        count = len(radii)
        peaks = sum(1 for index in range(count)
                    if radii[index] > 0.45
                    and radii[index] >= radii[index - 1]
                    and radii[index] >= radii[(index + 1) % count])
        self.assertEqual(peaks, 7)

    def test_a_star_needs_at_least_two_points(self):
        with self.assertRaises(ValueError):
            star(points=1)


class TextTests(unittest.TestCase):

    def test_it_traces_to_something(self):
        paths = text("Hi", size=140)
        self.assertGreater(len(paths), 0)
        self.assertGreater(sum(len(path) for path in paths), 20)
        left, top, right, bottom = bounds(paths)
        self.assertAlmostEqual(max(right - left, bottom - top), 1.0, places=6)

    def test_wider_words_come_out_wider(self):
        narrow = bounds(text("l", size=140))
        wide = bounds(text("mmmmmm", size=140))
        self.assertGreater(wide[2] - wide[0], narrow[2] - narrow[0])

    def test_nothing_to_draw_says_so(self):
        with self.assertRaises(ValueError):
            text("")


class PlacementTests(unittest.TestCase):

    def setUp(self):
        self.square = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]

    def test_the_default_is_what_fitting_does(self):
        self.assertEqual(place_on_screen(self.square, 1000, 2000),
                         fit_to_screen(self.square, 1000, 2000))

    def test_half_scale_halves_it(self):
        full = bounds(place_on_screen(self.square, 1000, 2000))
        half = bounds(place_on_screen(self.square, 1000, 2000, Placement(scale=0.5)))
        self.assertAlmostEqual((half[2] - half[0]) / (full[2] - full[0]), 0.5, places=2)

    def test_a_turned_drawing_still_fits(self):
        """The rotated box is what has to fit, not the upright one."""
        for degrees in (0, 30, 45, 60, 90, 135):
            with self.subTest(degrees=degrees):
                left, top, right, bottom = bounds(
                    place_on_screen(self.square, 1000, 2000, Placement(rotation=degrees)))
                self.assertGreaterEqual(left, 55)      # a 6% margin of 1000
                self.assertLessEqual(right, 945)
                self.assertGreaterEqual(top, 115)
                self.assertLessEqual(bottom, 1885)

    def test_flipping_mirrors_rather_than_moves(self):
        plain = place_on_screen(self.square, 1000, 2000)
        flipped = place_on_screen(self.square, 1000, 2000, Placement(flip_x=True))
        self.assertEqual(bounds(plain), bounds(flipped))
        self.assertEqual(flipped[0][0], plain[0][1])

    def test_flipping_twice_is_not_flipping(self):
        once = Placement().mirrored(horizontal=True)
        twice = once.mirrored(horizontal=True)
        self.assertTrue(once.flip_x)
        self.assertFalse(twice.flip_x)

    def test_the_centre_is_where_the_middle_goes(self):
        left, top, right, bottom = bounds(
            place_on_screen(self.square, 1000, 2000, Placement(centre=(0.25, 0.75), scale=0.2)))
        self.assertAlmostEqual((left + right) / 2, 250, delta=2)
        self.assertAlmostEqual((top + bottom) / 2, 1500, delta=2)

    def test_zoom_and_turn_stay_within_their_limits(self):
        self.assertEqual(Placement().zoomed(1000.0).scale, 6.0)
        self.assertEqual(Placement().zoomed(0.0001).scale, 0.05)
        self.assertEqual(Placement(rotation=350).turned(20).rotation, 10.0)

    def test_nothing_in_nothing_out(self):
        self.assertEqual(place_on_screen([], 1000, 2000), [])


if __name__ == "__main__":
    unittest.main()
