#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<4"
# dependencies = [
#   "jsonschema>=4.20,<5",
#   "openai>=1.40,<3",
#   "pydantic>=2.6,<3",
#   "python-dotenv>=1.0,<2",
#   "pyyaml>=6.0,<7",
# ]
# ///
"""Portable entry point for the bundled Debate package."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))


if __name__ == "__main__":
    main = importlib.import_module("debate.cli").main
    main()
