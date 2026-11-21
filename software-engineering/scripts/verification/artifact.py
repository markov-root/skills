"""Report which skill artifact is running and whether other installs drifted from it."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from ..resources import skill_root

SKILL_NAME = "software-engineering"
SOURCE_ENV = "ENGINEERING_SOURCE_ROOT"
# Global skill directories of the harnesses this skill supports.
HARNESS_SKILL_DIRS = (
    ".agents/skills",
    ".claude/skills",
    ".codex/skills",
    ".config/opencode/skills",
    ".pi/agent/skills",
)


def _version(root: Path) -> str | None:
    try:
        parts = (root / "SKILL.md").read_text(encoding="utf-8").split("---", 2)
        version = yaml.safe_load(parts[1])["metadata"]["version"]
    except (OSError, ValueError, IndexError, KeyError, TypeError, yaml.YAMLError):
        return None
    return version if isinstance(version, str) and version else None


def _install(entry: Path) -> dict[str, Any]:
    kind = "symlink" if entry.is_symlink() else "copy"
    resolved = entry.resolve()
    return {
        "path": str(entry),
        "kind": kind,
        "resolved": str(resolved),
        "version": _version(resolved),
    }


def artifact_identity(
    home: Path | None = None,
    env: dict[str, str] | None = None,
    skill_dirs: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return the running artifact, discovered installs, and drift warnings."""

    environ = os.environ if env is None else env
    home = Path.home() if home is None else home
    running = skill_root()
    version = _version(running)
    installs = [
        _install(entry)
        for relative in (HARNESS_SKILL_DIRS if skill_dirs is None else skill_dirs)
        if (entry := home / relative / SKILL_NAME).exists() or entry.is_symlink()
    ]
    warnings: list[str] = []
    for install in installs:
        if install["version"] != version:
            warnings.append(
                f"{install['path']} is {install['version'] or 'unreadable'}, "
                f"running artifact is {version}"
            )
    source = environ.get(SOURCE_ENV)
    if source:
        source_version = _version(Path(source).expanduser())
        if source_version is None:
            warnings.append(f"{SOURCE_ENV}={source} has no readable SKILL.md version")
        elif source_version != version:
            warnings.append(f"source {source} is {source_version}, running artifact is {version}")
    return {
        "version": version,
        "path": str(running),
        "installs": installs,
        "source": source or None,
        "drift": warnings,
    }


def render_artifact(identity: dict[str, Any]) -> list[str]:
    lines = [f"- Skill artifact: {identity['version']} at `{identity['path']}`"]
    lines.extend(f"- Warning: install drift: {message}" for message in identity["drift"])
    return lines
