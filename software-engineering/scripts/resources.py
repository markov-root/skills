"""Location-independent access to files shipped in the skill artifact."""

from __future__ import annotations

from pathlib import Path


class ResourceError(ValueError):
    """Raised when a requested skill resource is invalid or unavailable."""


def skill_root() -> Path:
    """Return the resolved root of the installed skill."""

    return Path(__file__).resolve().parent.parent


def _contained(relative: Path) -> Path:
    root = skill_root()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ResourceError(f"resource escapes the installed skill: {relative.as_posix()}")
    return candidate


def resource_path(*parts: str, required: bool = True) -> Path:
    """Resolve a contained resource and optionally require that it exists."""

    if not parts or any(not part or Path(part).is_absolute() for part in parts):
        raise ResourceError("resource path must contain non-empty relative parts")
    relative = Path(*parts)
    if ".." in relative.parts:
        raise ResourceError("resource path must not contain '..'")
    candidate = _contained(relative)
    if required and not candidate.exists():
        raise ResourceError(f"bundled resource is unavailable: {relative.as_posix()}")
    return candidate


def schema_path(name: str) -> Path:
    return resource_path("assets", "schemas", name)


def template_path(name: str) -> Path:
    return resource_path("assets", "templates", name)


def knowledge_path(name: str) -> Path:
    return resource_path("knowledge", name)


def source_index_path() -> Path:
    return resource_path("references", "SOURCES.md")


def changelog_path() -> Path:
    return resource_path("docs", "CHANGELOG.md")
