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

import os
import sys
from pathlib import Path


# Task 0134: compiled bytecode belongs in one user cache directory, never inside the
# (possibly read-only, possibly installed) skill folder, so warm starts skip the
# recompilation of the ~92-module runtime. Mirrors the skill's own cache layout.
def _bytecode_cache_prefix() -> str:
    cache_home = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    version = f"py{sys.version_info.major}{sys.version_info.minor}"
    return str(Path(cache_home) / "software-engineering" / "pycache" / version)


sys.pycache_prefix = _bytecode_cache_prefix()

# Tell the bundled launcher that Python started, so it never mistakes an application error
# for a uv cache failure and re-runs the command (task 0102).
if _started := os.environ.pop("ENGINEERING_LAUNCHER_STARTED", None):
    try:
        Path(_started).touch()
    except OSError:
        pass


def _skill_version() -> str:
    """Read the release identity from the artifact's single version source."""
    import yaml  # deferred: only needed when the version is actually rendered

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
