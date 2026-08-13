"""Bounded, zero-config, read-only passive repository observation."""

from __future__ import annotations

import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from ..execution import run_process
from ..project.discovery import (
    DiscoveryError,
    Project,
    discover_instructions,
    discover_observation_root,
    root_resolution,
)
from ..project.observation import (
    configuration_observation,
    manifest_observation,
    matched_paths,
    reviewer_observations,
    risk_observations,
)

MAX_FILES = 10_000
MAX_LIST = 200
MAX_COMMANDS = 100
MAX_VALUE = 300
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".engineering",
    "__pycache__",
}

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
}

PACKAGE_MARKERS = {
    "pyproject.toml": ("python", "python-project"),
    "uv.lock": ("python", "uv"),
    "requirements.txt": ("python", "pip"),
    "package.json": ("javascript", "node"),
    "pnpm-lock.yaml": ("javascript", "pnpm"),
    "yarn.lock": ("javascript", "yarn"),
    "package-lock.json": ("javascript", "npm"),
    "Cargo.toml": ("rust", "cargo"),
    "go.mod": ("go", "go"),
    "Gemfile": ("ruby", "bundler"),
    "composer.json": ("php", "composer"),
}

PROJECT_MARKERS = {
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "composer.json",
}

ARTIFACT_PATTERNS = {
    "tasks": ("docs/tasks/*.md", "tasks/*.md"),
    "decisions": ("docs/adr/*.md", "docs/adrs/*.md", "adr/*.md"),
    "architecture": (
        "docs/architecture*.md",
        "ARCHITECTURE.md",
        "docs/context/architecture.md",
    ),
}


def inspect_repository(
    start: str | Path = ".",
    *,
    global_agents: str | Path | None = None,
) -> dict[str, Any]:
    observed = discover_observation_root(start)
    root = observed.root.resolve()
    files, scan_truncated = _scan_files(root)
    relative_files = [path.relative_to(root).as_posix() for path in files]
    manifest = manifest_observation(observed.manifest, root)
    instructions = _instruction_facts(
        root,
        observed.git_root,
        start,
        global_agents=global_agents,
    )
    git = _git_facts(root, observed.git_root)
    languages, package_managers = _language_and_package_facts(relative_files)
    workspaces = _workspace_facts(root, files)
    commands = _command_candidates(root, files)
    artifacts = {
        name: matched_paths(relative_files, patterns)
        for name, patterns in ARTIFACT_PATTERNS.items()
    }
    signals = risk_observations(relative_files)
    configuration = configuration_observation(relative_files)
    reviewers = reviewer_observations(root, relative_files, observed.manifest)
    return {
        "schema_version": 1,
        "root": str(root),
        "root_resolution": root_resolution(observed),
        "repository": {
            "git": observed.git_root is not None,
            "scan_file_count": len(files),
            "scan_truncated": scan_truncated,
        },
        "git": git,
        "manifest": manifest,
        "instructions": instructions,
        "languages": languages,
        "package_managers": package_managers,
        "workspaces": workspaces,
        "configuration_sources": configuration,
        "command_candidates": commands,
        "artifacts": artifacts,
        "risk_signals": signals,
        "reviewers": reviewers,
        "next_commands": [
            "engineering explain command.inspect",
            "engineering suggest-manifest --json",
            'engineering start --intent "..." --paths ...',
        ],
    }


def _scan_files(root: Path) -> tuple[list[Path], bool]:
    files: list[Path] = []
    truncated = False
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in IGNORED_DIRECTORIES)
        current = Path(directory)
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink():
                try:
                    path.resolve().relative_to(root)
                except (OSError, ValueError):
                    continue
            files.append(path)
            if len(files) >= MAX_FILES:
                truncated = True
                return files, truncated
    return files, truncated


def _instruction_facts(
    root: Path,
    git_root: Path | None,
    start: str | Path,
    *,
    global_agents: str | Path | None,
) -> dict[str, Any]:
    project = Project(root, root / "engineering.yaml", git_root)
    try:
        instructions = discover_instructions(project, start, global_agents=global_agents)
    except DiscoveryError as exc:
        return {"sources": [], "findings": [str(exc)[:MAX_VALUE]]}
    sources = []
    findings = []
    for item in instructions:
        relative = (
            item.path.relative_to(root).as_posix()
            if item.path.is_relative_to(root)
            else str(item.path)
        )
        sources.append(
            {
                "path": relative,
                "kind": item.kind,
                "precedence": item.precedence,
                "sha256": item.sha256,
                "drift": item.drift,
            }
        )
        if item.drift:
            findings.append(f"{relative}: {item.drift}")
    return {"sources": sources, "findings": findings}


def _git_facts(root: Path, git_root: Path | None) -> dict[str, Any]:
    if git_root is None:
        return {
            "available": False,
            "commit": None,
            "branch": None,
            "dirty_count": 0,
            "dirty_paths": [],
            "truncated": False,
        }
    commit = _git_text(root, ["rev-parse", "HEAD"])
    branch = _git_text(root, ["branch", "--show-current"])
    status, output_truncated = _git_bytes(
        root, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]
    )
    paths: list[str] = []
    if status is not None:
        fields = status.decode(errors="surrogateescape").split("\0")
        for field in fields:
            if not field:
                continue
            value = field[3:] if len(field) > 3 else field
            if value and not value.startswith(".engineering/"):
                paths.append(value[:MAX_VALUE])
    return {
        "available": True,
        "commit": commit,
        "branch": branch,
        "dirty_count": len(paths),
        "dirty_paths": sorted(paths)[:MAX_LIST],
        "truncated": output_truncated or len(paths) > MAX_LIST,
    }


def _git_text(root: Path, args: list[str]) -> str | None:
    value, _truncated = _git_bytes(root, args)
    if value is None:
        return None
    return value.decode(errors="replace").strip()[:MAX_VALUE] or None


def _git_bytes(root: Path, args: list[str]) -> tuple[bytes | None, bool]:
    result = run_process(
        ("git", "-C", str(root), *args),
        root=root,
        timeout_seconds=10,
        max_output_bytes=256_000,
    )
    if result.exit_code != 0:
        return None, result.stdout_truncated
    return result.stdout, result.stdout_truncated


def _language_and_package_facts(
    relative_files: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    managers: dict[str, set[str]] = {}
    for relative in relative_files:
        path = Path(relative)
        language = LANGUAGE_EXTENSIONS.get(path.suffix.lower())
        if language:
            counts[language] += 1
            samples.setdefault(language, [])
            if len(samples[language]) < 5:
                samples[language].append(relative)
        marker = PACKAGE_MARKERS.get(path.name)
        if marker:
            marker_language, manager = marker
            counts.setdefault(marker_language, 0)
            managers.setdefault(manager, set()).add(relative)
    languages = [
        {
            "name": name,
            "file_count": counts[name],
            "evidence": sorted(samples.get(name, [])),
        }
        for name in sorted(counts)
    ]
    package_managers = [
        {"name": name, "sources": sorted(paths)} for name, paths in sorted(managers.items())
    ]
    return languages, package_managers


def _workspace_facts(root: Path, files: list[Path]) -> dict[str, Any]:
    project_files = sorted(
        path.relative_to(root).as_posix() for path in files if path.name in PROJECT_MARKERS
    )
    declared_sources: list[str] = []
    package_json = root / "package.json"
    if package_json in files:
        try:
            loaded = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "workspaces" in loaded:
                declared_sources.append("package.json#workspaces")
        except (OSError, json.JSONDecodeError):
            pass
    pyproject = root / "pyproject.toml"
    if pyproject in files:
        try:
            loaded = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            if isinstance(loaded.get("tool", {}).get("uv", {}).get("workspace"), dict):
                declared_sources.append("pyproject.toml#tool.uv.workspace")
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return {
        "monorepo_candidate": len(project_files) > 1 or bool(declared_sources),
        "project_files": project_files[:MAX_LIST],
        "declared_sources": declared_sources,
        "truncated": len(project_files) > MAX_LIST,
    }


def _command_candidates(root: Path, files: list[Path]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    package_json = root / "package.json"
    if package_json in files:
        try:
            loaded = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = loaded.get("scripts", {}) if isinstance(loaded, dict) else {}
            if isinstance(scripts, dict):
                for name, command in sorted(scripts.items()):
                    if isinstance(name, str) and isinstance(command, str):
                        candidates.append(
                            _candidate(
                                name,
                                command,
                                f"package.json#scripts.{name}",
                                "package-script",
                            )
                        )
        except (OSError, json.JSONDecodeError):
            pass
    pyproject = root / "pyproject.toml"
    if pyproject in files:
        try:
            loaded = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            scripts = loaded.get("project", {}).get("scripts", {})
            if isinstance(scripts, dict):
                for name, target in sorted(scripts.items()):
                    if isinstance(name, str) and isinstance(target, str):
                        candidates.append(
                            _candidate(
                                name,
                                name,
                                f"pyproject.toml#project.scripts.{name}",
                                "entry-point",
                            )
                        )
        except (OSError, tomllib.TOMLDecodeError):
            pass
    for filename, tool in (
        ("Makefile", "make"),
        ("Justfile", "just"),
        ("justfile", "just"),
    ):
        path = root / filename
        if path in files:
            candidates.extend(_target_candidates(path, root, tool))
    for filename in ("AGENTS.md", "CONTRIBUTING.md"):
        path = root / filename
        if path in files:
            candidates.extend(_fenced_commands(path, root))
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in candidates:
        unique[(item["source"], item["name"], item["command"])] = item
    rows = sorted(
        unique.values(),
        key=lambda item: (item["source"], item["name"], item["command"]),
    )
    return {
        "items": rows[:MAX_COMMANDS],
        "truncated": len(rows) > MAX_COMMANDS,
        "inferred_commands_executed": False,
    }


def _candidate(name: str, command: str, source: str, kind: str) -> dict[str, Any]:
    return {
        "name": name[:MAX_VALUE],
        "command": command[:MAX_VALUE],
        "source": source[:MAX_VALUE],
        "kind": kind,
        "adopted": False,
    }


def _target_candidates(path: Path, root: Path, tool: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)")
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        match = pattern.match(line)
        if match and not match.group(1).startswith("."):
            name = match.group(1)
            rows.append(
                _candidate(
                    name,
                    f"{tool} {name}",
                    f"{path.relative_to(root).as_posix()}:{line_number}",
                    f"{tool}-target",
                )
            )
    return rows


def _fenced_commands(path: Path, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_shell = False
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        stripped = line.strip()
        if stripped.startswith("```"):
            language = stripped[3:].strip().lower()
            if in_shell:
                in_shell = False
            else:
                in_shell = language in {"bash", "sh", "shell", "console", "zsh"}
            continue
        if not in_shell or not stripped or stripped.startswith(("#", "$")):
            continue
        rows.append(
            _candidate(
                f"documented-line-{line_number}",
                stripped,
                f"{path.relative_to(root).as_posix()}:{line_number}",
                "documented-shell",
            )
        )
    return rows
