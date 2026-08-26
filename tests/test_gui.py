import unittest

customtkinter = None
try:
    import customtkinter  # noqa: F401
except Exception:  # pragma: no cover - depends on the environment
    pass


@unittest.skipIf(customtkinter is None, "customtkinter is not installed")
class GuiImportTests(unittest.TestCase):
    """The GUI needs a display to run, but it should at least import cleanly."""

    def test_app_class_is_importable(self):
        from mthread_draw.app import App

        self.assertTrue(hasattr(App, "run"))

    def test_entry_point_exists(self):
        from mthread_draw.app import main

        self.assertTrue(callable(main))


if __name__ == "__main__":
    unittest.main()
