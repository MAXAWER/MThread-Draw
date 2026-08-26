import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from adbtouch import neural
from adbtouch.trace import ridges


class ModelLocationTests(unittest.TestCase):
    def test_the_model_lives_outside_the_package(self):
        """A wheel must not grow by 46 MB, and a model should outlive an upgrade."""
        self.assertNotIn("adbtouch" + os.sep + "adbtouch", str(neural.model_path()))
        self.assertTrue(str(neural.model_path()).endswith(".onnx"))

    def test_the_cache_can_be_pointed_somewhere_else(self):
        with mock.patch.dict(os.environ, {"ADBTOUCH_CACHE": os.path.join("x", "y")}):
            self.assertEqual(neural.cache_dir(), Path("x") / "y")

    def test_a_missing_model_is_not_a_present_one(self):
        with mock.patch.dict(os.environ, {"ADBTOUCH_CACHE": os.path.join("nowhere", "at", "all")}):
            self.assertFalse(neural.have_model())

    def test_a_truncated_download_does_not_count_as_installed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ADBTOUCH_CACHE": tmp}):
                neural.model_path().write_bytes(b"not really a model")
                self.assertFalse(neural.have_model())

    def test_using_it_without_it_says_so_and_says_where(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"ADBTOUCH_CACHE": tmp}):
                with self.assertRaises(neural.ModelUnavailableError) as ctx:
                    neural.edge_probability(np.zeros((32, 32, 3), dtype=np.uint8))
        message = str(ctx.exception)
        self.assertIn("download_model", message)
        self.assertIn(tmp, message)

    def test_the_weights_come_from_the_opencv_zoo(self):
        """Provenance matters here: these are MIT, published by OpenCV, and that
        is the reason they can be shipped in a commercial licence at all."""
        self.assertIn("opencv/edge_detection_dexined", neural.MODEL_URL)


class RidgeTests(unittest.TestCase):
    def test_a_soft_ridge_becomes_a_thin_line(self):
        """A network answers in wide soft ridges. Thresholding one gives a band,
        and thinning a band gives the outline of the band - cells around every
        patch of texture, which is what a careless neural edge map looks like."""
        y = np.arange(41)[:, None].astype(np.float32)
        profile = np.exp(-((y - 20) ** 2) / 18.0)
        strength = np.tile(profile, (1, 60))

        crest = ridges(strength, keep=0.5, seed_keep=0.25)
        for column in range(5, 55):
            self.assertLessEqual(crest[:, column].sum(), 2)
        self.assertTrue(crest[18:23, 30].any())

    def test_an_empty_map_produces_nothing(self):
        self.assertFalse(ridges(np.zeros((30, 30), dtype=np.float32)).any())

    def test_keeping_more_admits_more(self):
        rng = np.random.default_rng(0)
        strength = rng.random((80, 80)).astype(np.float32)
        self.assertLessEqual(ridges(strength, keep=0.2, seed_keep=0.1).sum(),
                             ridges(strength, keep=0.8, seed_keep=0.4).sum())


if __name__ == "__main__":
    unittest.main()
