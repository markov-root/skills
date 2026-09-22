#!/usr/bin/env python3
"""Run from any installed artifact with Python 3.11 or newer."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
if sys.version_info < (3, 11):
    sys.exit("skill-manager requires Python 3.11 or newer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manager.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
