"""Entry point for the packaged engine.

The WinUI front end launches this rather than a Python interpreter, so a
release does not depend on Python being installed. Same server, same protocol.
"""

from autodraw.server import main

raise SystemExit(main())
