"""Where the app keeps config.json, data/ and logs/.

Both the settings loader and the logger need this, and the logger cannot
ask settings for it (settings imports the logger), so it lives on its own
rather than being computed twice.

When frozen, __file__ points inside the PyInstaller bundle. For a onefile
build that bundle is a temp folder wiped the moment the app exits, which
would silently throw away the database, the settings and every log line.
Anchor to the executable instead.
"""

import os
import sys


def resolve_project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


PROJECT_ROOT = resolve_project_root()
