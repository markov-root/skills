"""Read-only project, manifest, and instruction discovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..execution import run_process


@dataclass(frozen=True)
class Project:
    root: Path
    manifest: Path
    git_root: Path | None


@dataclass(frozen=True)
class Instruction:
    path: Path
    kind: str
    precedence: int
    sha256: str
    drift: str | None = None


@dataclass(frozen=True)
class DeclaredDocument:
    path: Path
    exists: bool
    sha256: str | None


@dataclass(frozen=True)
class ObservedProject:
    root: Path
    git_root: Path | None
    manifest: Path | None
    requested: Path | None = None
    promoted: bool = False
    requested_manifest: bool = False


class DiscoveryError(ValueError):
    pass


def _git_root(start: Path) -> Path | None:
    result = run_process(
        ("git", "-C", str(start), "rev-parse", "--show-toplevel"),
        root=start,
        timeout_seconds=10,
        max_output_bytes=16_384,
    )
    if result.status != "passed":
        return None
    candidate = Path(result.stdout.decode(errors="replace").strip()).resolve()
    return candidate if candidate.is_dir() else None


def discover_project(start: str | Path = ".") -> Project:
    start_path = Path(start).resolve()
    if start_path.is_file():
        start_path = start_path.parent
    if not start_path.is_dir():
        raise DiscoveryError(f"start path is not a directory: {start_path}")
    git_root = _git_root(start_path)
    if git_root is not None:
        manifest = git_root / "engineering.yaml"
        if not manifest.is_file():
            raise DiscoveryError(f"engineering.yaml not found at Git root: {git_root}")
        return Project(git_root, manifest, git_root)
    for directory in (start_path, *start_path.parents):
        manifest = directory / "engineering.yaml"
        if manifest.is_file():
            return Project(directory, manifest, None)
    raise DiscoveryError(f"engineering.yaml not found from {start_path}")


def discover_observation_root(start: str | Path = ".") -> ObservedProject:
    """Find a safe inspection root without requiring adopted engineering policy."""
    start_path = Path(start).resolve()
    if start_path.is_file():
        raise DiscoveryError(
            f"project root is a file, not a directory: {start_path}; "
            f"pass a directory (its parent is {start_path.parent})"
        )
    if not start_path.is_dir():
        raise DiscoveryError(f"start path is not a directory: {start_path}")
    requested_manifest = (start_path / "engineering.yaml").is_file()
    git_root = _git_root(start_path)
    if git_root is not None:
        manifest = git_root / "engineering.yaml"
        return ObservedProject(
            git_root,
            git_root,
            manifest if manifest.is_file() else None,
            requested=start_path,
            promoted=git_root != start_path,
            requested_manifest=requested_manifest,
        )
    markers = (
        "engineering.yaml",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "AGENTS.md",
    )
    for directory in (start_path, *start_path.parents):
        if any((directory / marker).is_file() for marker in markers):
            manifest = directory / "engineering.yaml"
            return ObservedProject(
                directory,
                None,
                manifest if manifest.is_file() else None,
                requested=start_path,
                promoted=directory != start_path,
                requested_manifest=requested_manifest,
            )
    return ObservedProject(
        start_path,
        None,
        None,
        requested=start_path,
        promoted=False,
        requested_manifest=requested_manifest,
    )


def root_resolution(observed: ObservedProject) -> dict[str, object]:
    """Serializable summary of how an observation root was resolved.

    Surfaces upward promotion so a caller run against a nested workspace is not
    misled into treating an enclosing repository's manifest or tasks as its own.
    """
    requested = observed.requested if observed.requested is not None else observed.root
    return {
        "requested": str(requested),
        "resolved": str(observed.root),
        "promoted": observed.promoted,
        "requested_has_manifest": observed.requested_manifest,
    }


def discover_instructions(
    project: Project,
    start: str | Path = ".",
    *,
    global_agents: str | Path | None = None,
) -> tuple[Instruction, ...]:
    """Return applicable instructions from low to high precedence."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    try:
        current.relative_to(project.root)
    except ValueError as exc:
        raise DiscoveryError(f"start path escapes project root: {current}") from exc

    directories: list[Path] = []
    cursor = current
    while True:
        directories.append(cursor)
        if cursor == project.root:
            break
        cursor = cursor.parent
    directories.reverse()

    found: list[Instruction] = []
    if global_agents is not None:
        global_path = Path(global_agents).resolve()
        if global_path.is_file():
            found.append(_instruction(global_path, "global", len(found)))
    for directory in directories:
        agents = directory / "AGENTS.md"
        claude = directory / "CLAUDE.md"
        if agents.is_file():
            _require_contained(agents, project.root, "instruction")
            found.append(_instruction(agents, "agents", len(found)))
        if claude.is_file() or claude.is_symlink():
            _require_contained(claude, project.root, "instruction")
            drift = _claude_drift(agents, claude)
            found.append(_instruction(claude, "claude", len(found), drift))
    return tuple(found)


def discover_documents(
    project: Project, documents: tuple[str, ...]
) -> tuple[DeclaredDocument, ...]:
    """Report declared project documents without following paths outside the project."""
    found: list[DeclaredDocument] = []
    for relative in documents:
        path = project.root / relative
        _require_contained(path, project.root, "declared document")
        if path.is_file():
            found.append(
                DeclaredDocument(path, True, hashlib.sha256(path.read_bytes()).hexdigest())
            )
        else:
            found.append(DeclaredDocument(path, False, None))
    return tuple(found)


def _require_contained(path: Path, root: Path, kind: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise DiscoveryError(f"{kind} escapes project root: {path}") from exc


def _instruction(path: Path, kind: str, precedence: int, drift: str | None = None) -> Instruction:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise DiscoveryError(f"cannot read instruction file {path}: {exc}") from exc
    return Instruction(path, kind, precedence, hashlib.sha256(content).hexdigest(), drift)


def _claude_drift(agents: Path, claude: Path) -> str | None:
    if not agents.is_file():
        return "CLAUDE.md exists without AGENTS.md"
    try:
        if claude.is_symlink() and claude.resolve() == agents.resolve():
            return None
        if claude.read_bytes() == agents.read_bytes():
            return "CLAUDE.md duplicates AGENTS.md but is not its symlink"
    except OSError as exc:
        return f"cannot compare CLAUDE.md: {exc}"
    return "CLAUDE.md content conflicts with AGENTS.md"
