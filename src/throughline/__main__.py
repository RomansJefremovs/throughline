"""Entry point for `python -m throughline` and for the frozen sidecar.

The console script in pyproject.toml calls `cli:main` directly. PyInstaller
needs a file to point at, and a module that is run rather than imported
cannot use a relative import, so this one is absolute.
"""

import sys

from throughline.cli import main

if __name__ == "__main__":
    sys.exit(main())
