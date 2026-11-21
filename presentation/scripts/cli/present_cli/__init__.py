"""present — the presentation skill's CLI (see SKILL.md).

The version exists in exactly one place: SKILL.md `metadata.version`, read here at import.
"""
from __future__ import annotations

import re
from pathlib import Path

# The artifact root is the nearest ancestor holding SKILL.md (looked up, not counted).
SKILL_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "SKILL.md").is_file())
SCHEMA_DIR = SKILL_ROOT / "assets" / "schemas"
STANDARDS = (1,)  # standard majors this release can validate


def _read_version() -> str:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r'^\s+version:\s*"?(\d+\.\d+\.\d+)"?\s*$', text, re.M)
    return m.group(1) if m else "0.0.0"


__version__ = _read_version()
