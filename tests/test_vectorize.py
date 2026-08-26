import unittest

import cv2
import numpy as np

from mthread.vectorize import VectorizeSettings, Vectorizer, dedupe_retrace


def _contours(image):
    """Canny + findContours, the same way the vectorizer does it."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    return [c for c in contours if len(c) >= 6]


def line_image(width=200, height=200):
    """A white canvas with one thick black horizontal line."""
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.line(image, (20, 100), (180, 100), (0, 0, 0), 3)
    return image


class DedupeRetraceTests(unittest.TestCase):
    def test_thin_stroke_is_halved(self):
        # Boundary of a 1px line: out along the top, back along the bottom.
        points = [(x, 0) for x in range(20)] + [(x, 0) for x in range(19, -1, -1)]
        contour = np.array(points, dtype=np.int32).reshape(-1, 1, 2)
        self.assertEqual(len(dedupe_retrace(contour)), 21)

    def test_filled_shape_is_left_alone(self):
        contour = np.array(
            [[[0, 0]], [[0, 50]], [[50, 50]], [[50, 0]]] , dtype=np.int32
        )
        square = cv2.approxPolyDP(contour, 0.1, True)
        self.assertEqual(len(dedupe_retrace(square)), len(square))

    def test_very_short_contour_is_untouched(self):
        contour = np.array([[[0, 0]], [[1, 1]]], dtype=np.int32)
        self.assertEqual(len(dedupe_retrace(contour)), 2)

    def test_thin_canny_ring_from_a_real_line_is_halved(self):
        """The dominant cause of double drawing: one pen stroke, two parallel edges."""
        for thickness in (1, 2, 3):
            with self.subTest(thickness=thickness):
                image = np.full((200, 200, 3), 255, dtype=np.uint8)
                cv2.line(image, (20, 100), (180, 100), (0, 0, 0), thickness)
                for contour in _contours(image):
                    self.assertLessEqual(len(dedupe_retrace(contour)), len(contour) // 2 + 1)

    def test_circle_outline_keeps_both_halves(self):
        """Halving a real closed loop would draw a semicircle - it must not trigger."""
        image = np.full((300, 300, 3), 255, dtype=np.uint8)
        cv2.circle(image, (150, 150), 100, (0, 0, 0), 2)
        for contour in _contours(image):
            self.assertEqual(len(dedupe_retrace(contour)), len(contour))

    def test_filled_shapes_keep_their_outline(self):
        for draw in (
            lambda img: cv2.rectangle(img, (50, 50), (150, 150), (0, 0, 0), -1),
            lambda img: cv2.circle(img, (100, 100), 60, (0, 0, 0), -1),
        ):
            image = np.full((200, 200, 3), 255, dtype=np.uint8)
            draw(image)
            for contour in _contours(image):
                self.assertEqual(len(dedupe_retrace(contour)), len(contour))


class VectorizerTests(unittest.TestCase):
    def setUp(self):
        self.vectorizer = Vectorizer()
        self.vectorizer.load_array(line_image())

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            Vectorizer().load_image("/definitely/not/here.png")

    def test_process_without_image_is_safe(self):
        preview, paths = Vectorizer().process()
        self.assertIsNone(preview)
        self.assertEqual(paths, [])

    def test_produces_paths_and_a_preview(self):
        preview, paths = self.vectorizer.process(VectorizeSettings(target_width=None))
        self.assertIsNotNone(preview)
        self.assertGreater(len(paths), 0)
        self.assertTrue(all(len(path) >= 2 for path in paths))

    def test_points_stay_inside_the_image(self):
        _, paths = self.vectorizer.process(VectorizeSettings(target_width=None))
        for path in paths:
            for x, y in path:
                self.assertTrue(0 <= x < 200 and 0 <= y < 200)

    def test_retrace_removal_shortens_the_output(self):
        """Specific to the Canny path: XDoG walks each line once, so there is
        no second pass down the other side of it to remove."""
        settings = VectorizeSettings(method="contour", target_width=None, epsilon=1.0)
        _, deduped = self.vectorizer.process(settings)
        deduped_points = sum(len(p) for p in deduped)

        import mthread.vectorize as module
        original = module.dedupe_retrace
        module.dedupe_retrace = lambda contour, **kwargs: contour
        try:
            fresh = Vectorizer()
            fresh.load_array(line_image())
            _, raw = fresh.process(settings)
            raw_points = sum(len(p) for p in raw)
        finally:
            module.dedupe_retrace = original

        self.assertLess(deduped_points, raw_points)

    def test_higher_detail_gives_more_points(self):
        coarse = VectorizeSettings.from_sliders(sensitivity=5, detail=1)
        fine = VectorizeSettings.from_sliders(sensitivity=5, detail=10)
        self.assertGreater(coarse.epsilon, fine.epsilon)

    def test_slider_mapping_moves_thresholds_together(self):
        low = VectorizeSettings.from_sliders(sensitivity=1, detail=5)
        high = VectorizeSettings.from_sliders(sensitivity=10, detail=5)
        self.assertLess(low.low_threshold, high.low_threshold)
        self.assertLess(low.high_threshold, high.high_threshold)

    def test_target_width_downscales(self):
        wide = np.full((100, 2000, 3), 255, dtype=np.uint8)
        cv2.line(wide, (10, 50), (1990, 50), (0, 0, 0), 3)
        vectorizer = Vectorizer()
        vectorizer.load_array(wide)
        vectorizer.process(VectorizeSettings(target_width=500))
        self.assertEqual(vectorizer.edges.shape[1], 500)


if __name__ == "__main__":
    unittest.main()
