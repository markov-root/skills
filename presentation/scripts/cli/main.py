#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyyaml>=6.0",
#   "jsonschema>=4.22",
#   "python-pptx>=1.0",
#   "pillow>=10",
# ]
# ///
"""Entry point for `present`. Run through ../present (uv run --script) so dependencies resolve."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from present_cli.console import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
