"""Entry point for the PyInstaller build.

``autodraw/__main__.py`` uses a relative import, which PyInstaller cannot use as
a top-level script. This module is the same two lines with an absolute import.
"""

from autodraw.app import main

raise SystemExit(main() or 0)
