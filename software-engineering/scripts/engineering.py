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

import yaml

# Installed skills may be read-only, and local Vercel installs copy unmanaged files verbatim.
sys.dont_write_bytecode = True


def _skill_version() -> str:
    """Read the release identity from the artifact's single version source."""
    skill_file = Path(__file__).resolve().parent.parent / "SKILL.md"
    parts = skill_file.read_text(encoding="utf-8").split("---", 2)
    if len(parts) != 3:
        raise RuntimeError("SKILL.md frontmatter is unavailable")
    frontmatter = yaml.safe_load(parts[1])
    try:
        version = frontmatter["metadata"]["version"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("SKILL.md metadata.version is unavailable") from exc
    if not isinstance(version, str) or not version:
        raise RuntimeError("SKILL.md metadata.version must be a non-empty string")
    return version


def _load_main():
    skill_root = Path(__file__).resolve().parent.parent
    skill_root_text = str(skill_root)
    if skill_root_text not in sys.path:
        sys.path.insert(0, skill_root_text)

    from scripts.cli import main

    return main


if __name__ == "__main__":
    raise SystemExit(_load_main()())
