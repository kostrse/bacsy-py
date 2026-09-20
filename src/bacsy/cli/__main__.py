"""Entry point for `python -m bacsy.cli`."""

from __future__ import annotations

import sys

from bacsy.cli import main

if __name__ == "__main__":
    sys.exit(main())
