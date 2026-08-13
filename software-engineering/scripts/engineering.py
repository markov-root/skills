# /// script
# requires-python = "==3.12.*"
# dependencies = [
#   "jsonschema>=4.23,<5",
#   "markdown-it-py>=3.0,<5",
#   "pathspec>=0.12,<1",
#   "PyYAML>=6.0,<7",
# ]
# ///
"""Portable entry point for the bundled software-engineering runtime."""

from __future__ import annotations

import sys
from pathlib import Path

# Installed skills may be read-only, and local Vercel installs copy unmanaged files verbatim.
sys.dont_write_bytecode = True


def _load_main():
    skill_root = Path(__file__).resolve().parent.parent
    skill_root_text = str(skill_root)
    if skill_root_text not in sys.path:
        sys.path.insert(0, skill_root_text)

    from scripts.cli import main

    return main


if __name__ == "__main__":
    raise SystemExit(_load_main()())
