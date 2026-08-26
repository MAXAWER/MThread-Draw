import unittest

from mthread_draw.geometry import CanvasView, place_paths


class CanvasViewTests(unittest.TestCase):
    def setUp(self):
        # A 1080x2400 phone shown as a 270x600 rectangle at canvas (50, 30).
        self.view = CanvasView(origin=(50, 30), size=(270, 600), screen=(1080, 2400))

    def test_ratio(self):
        self.assertEqual(self.view.ratio, (4.0, 4.0))

    def test_origin_maps_to_screen_origin(self):
        self.assertEqual(self.view.canvas_to_screen(50, 30), (0.0, 0.0))

    def test_far_corner_maps_to_screen_size(self):
        self.assertEqual(self.view.canvas_to_screen(320, 630), (1080.0, 2400.0))

    def test_round_trip(self):
        canvas = self.view.screen_to_canvas(540, 1200)
        self.assertEqual(self.view.canvas_to_screen(*canvas), (540.0, 1200.0))

    def test_degenerate_rectangle_is_rejected(self):
        with self.assertRaises(ValueError):
            CanvasView(origin=(0, 0), size=(0, 100), screen=(1080, 2400)).ratio


class PlacePathsTests(unittest.TestCase):
    def setUp(self):
        self.view = CanvasView(origin=(50, 30), size=(270, 600), screen=(1080, 2400))

    def test_image_at_screen_origin_unscaled(self):
        placed = place_paths([[(0, 0), (10, 20)]], self.view, image_origin=(50, 30), image_scale=1.0)
        self.assertEqual(placed, [[(0, 0), (40, 80)]])

    def test_image_offset_shifts_every_point(self):
        placed = place_paths([[(0, 0)] , [(0, 0), (5, 5)]], self.view, image_origin=(60, 40), image_scale=1.0)
        self.assertEqual(placed[0][0], (40, 40))

    def test_zoom_multiplies_with_the_view_ratio(self):
        placed = place_paths([[(0, 0), (10, 0)]], self.view, image_origin=(50, 30), image_scale=2.0)
        self.assertEqual(placed[0][1], (80, 0))

    def test_calibration_offset_is_added_in_device_pixels(self):
        placed = place_paths([[(0, 0), (10, 0)]], self.view, image_origin=(50, 30), image_scale=1.0, offset=(7, -3))
        self.assertEqual(placed[0][0], (7, -3))

    def test_single_point_paths_are_dropped(self):
        self.assertEqual(place_paths([[(1, 1)]], self.view, (50, 30), 1.0), [])

    def test_duplicate_points_are_collapsed(self):
        placed = place_paths([[(0, 0), (0, 0), (0, 0), (10, 10)]], self.view, (50, 30), 1.0)
        self.assertEqual(len(placed[0]), 2)

    def test_path_that_collapses_entirely_is_dropped(self):
        self.assertEqual(place_paths([[(0, 0), (0, 0)]], self.view, (50, 30), 1.0), [])


if __name__ == "__main__":
    unittest.main()
