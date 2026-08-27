"""The engine's layers, eraser and placement, driven the way a front end does.

No device is attached in any of this. Placement and erasing are decided against
a screen size, and the engine knows one whether or not a phone is plugged in -
which is also what makes a drawing arrangeable in advance, and what makes a
screenshot supplied by hand a workable substitute when capture fails.
"""

import tempfile
import unittest
from pathlib import Path

from mthread_draw.server import Engine

#: Tiny drawings rather than the photographs in examples/. The pipeline being
#: exercised is the same one; tracing a real photograph a dozen times over cost
#: the suite most of a minute and told it nothing extra.
_FIXTURES = tempfile.TemporaryDirectory()


def _shape(name: str, kind: str) -> Path:
    from PIL import Image, ImageDraw

    path = Path(_FIXTURES.name) / name
    if not path.exists():
        image = Image.new("RGB", (200, 300), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        if kind == "bars":
            for index in range(6):
                draw.rectangle([(20 + index * 28, 40), (36 + index * 28, 260)], fill=(20, 20, 20))
        else:
            for index in range(4):
                draw.ellipse([(30 + index * 8, 40 + index * 8),
                              (170 - index * 8, 260 - index * 8)], outline=(20, 20, 20), width=6)
        image.save(path)
    return path


GUITAR = _shape("bars.png", "bars")
CAT = _shape("rings.png", "rings")


class LayerTests(unittest.TestCase):

    def setUp(self):
        self.sent = []
        self.engine = Engine(self.sent.append)

    def load(self, image=GUITAR, **fields):
        return self.engine.op_load_image(str(image), **fields)

    def test_loading_adds_a_layer_rather_than_replacing_one(self):
        self.load(GUITAR)
        result = self.load(CAT)
        self.assertEqual(len(result["layers"]), 2)
        self.assertEqual(result["current"], 1)
        self.assertEqual(result["layers"][0]["name"], "bars.png")
        self.assertEqual(result["layers"][1]["name"], "rings.png")

    def test_replacing_is_available_and_keeps_the_placement(self):
        self.load(GUITAR)
        self.engine.op_place(dx=0.2, zoom=0.5)
        result = self.load(CAT, replace=True)
        self.assertEqual(len(result["layers"]), 1)
        self.assertAlmostEqual(result["layers"][0]["scale"], 0.5, places=3)

    def test_each_layer_keeps_its_own_placement(self):
        self.load(GUITAR)
        self.engine.op_place(zoom=0.25)
        self.load(CAT)
        self.engine.op_place(turn=90)

        layers = self.engine.op_layers()["layers"]
        self.assertAlmostEqual(layers[0]["scale"], 0.25, places=3)
        self.assertEqual(layers[0]["rotation"], 0.0)
        self.assertAlmostEqual(layers[1]["scale"], 1.0, places=3)
        self.assertEqual(layers[1]["rotation"], 90.0)

    def test_a_hidden_layer_is_not_drawn(self):
        self.load(GUITAR)
        self.load(CAT)
        both = self.engine.op_layers()["strokes"]
        self.engine.op_layer_visible(visible=False, index=0)
        one = self.engine.op_layers()["strokes"]
        self.assertLess(one, both)
        self.assertEqual(len(self.engine._all_placed()), one)

    def test_removing_a_layer_keeps_the_selection_in_range(self):
        self.load(GUITAR)
        self.load(CAT)
        result = self.engine.op_layer_remove()
        self.assertEqual(len(result["layers"]), 1)
        self.assertEqual(result["current"], 0)

    def test_raising_a_layer_changes_the_order_things_are_drawn_in(self):
        self.load(GUITAR)
        self.load(CAT)
        self.engine.op_layer_select(index=0)
        result = self.engine.op_layer_raise()
        self.assertEqual([layer["name"] for layer in result["layers"]],
                         ["rings.png", "bars.png"])
        self.assertEqual(result["current"], 1)

    def test_selecting_a_layer_that_is_not_there_says_so(self):
        self.load(GUITAR)
        with self.assertRaises(Exception):
            self.engine.op_layer_select(index=7)

    def test_placing_before_anything_is_loaded_says_what_to_do(self):
        with self.assertRaises(Exception) as caught:
            self.engine.op_place(dx=0.1)
        self.assertIn("load an image", str(caught.exception).lower())


class EraserTests(unittest.TestCase):

    def setUp(self):
        self.engine = Engine(lambda message: None)
        self.engine.op_load_image(str(GUITAR))

    def centre_of_a_stroke(self):
        """A point that is certainly on the drawing, in screen fractions."""
        from mthread.placement import place_on_screen

        width, height = self.engine.screen_now()
        placed = place_on_screen(self.engine.layer.paths, width, height,
                                 self.engine.layer.placement)
        longest = max(placed, key=len)
        x, y = longest[len(longest) // 2]
        return x / width, y / height

    def test_erasing_removes_strokes_under_the_point(self):
        before = self.engine.op_layers()["strokes"]
        x, y = self.centre_of_a_stroke()
        after = self.engine.op_erase(x=x, y=y, radius=0.03)["strokes"]
        self.assertLess(after, before)

    def test_erasing_nowhere_near_anything_removes_nothing(self):
        before = self.engine.op_layers()["strokes"]
        after = self.engine.op_erase(x=0.0, y=0.0, radius=0.001)["strokes"]
        self.assertEqual(after, before)

    def test_undo_brings_everything_back(self):
        before = self.engine.op_layers()["strokes"]
        x, y = self.centre_of_a_stroke()
        self.engine.op_erase(x=x, y=y, radius=0.05)
        self.assertLess(self.engine.op_layers()["strokes"], before)
        self.assertEqual(self.engine.op_erase(undo=True)["strokes"], before)

    def test_erased_strokes_are_not_drawn(self):
        x, y = self.centre_of_a_stroke()
        kept = self.engine.op_erase(x=x, y=y, radius=0.05)["strokes"]
        self.assertEqual(len(self.engine._all_placed()), kept)

    def test_re_tracing_forgets_erasures_rather_than_misapplying_them(self):
        """Stroke five of one tracing is not stroke five of the next."""
        x, y = self.centre_of_a_stroke()
        self.engine.op_erase(x=x, y=y, radius=0.05)
        self.assertGreater(self.engine.layer.erased, set())
        self.engine.op_preview(sensitivity=5, detail=4, method="canny")
        self.assertEqual(self.engine.layer.erased, set())


class ReprocessTests(unittest.TestCase):

    def test_settings_change_without_the_file_being_loaded_again(self):
        engine = Engine(lambda message: None)
        engine.op_load_image(str(CAT))
        # Counted in points rather than strokes: detail sets how finely a line is
        # followed, and on a simple shape the number of lines does not move.
        coarse = engine.op_preview(sensitivity=5, detail=1, method="canny")["points"]
        fine = engine.op_preview(sensitivity=5, detail=10, method="canny")["points"]
        self.assertGreater(fine, coarse)
        self.assertEqual(len(engine.layers), 1)


if __name__ == "__main__":
    unittest.main()
