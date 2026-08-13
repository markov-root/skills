"""Project-policy facts exposed to passive repository observation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..execution import resolve_executable
from ..policy.manifest import Manifest, ManifestError, load_manifest
from ..policy.path_matching import matches_any
from .classifier import BUILTINS
from .health import CI_PATTERNS

MAX_LIST = 200
MAX_VALUE = 300


def manifest_observation(path: Path | None, root: Path) -> dict[str, Any]:
    if path is None:
        return {
            "status": "absent",
            "path": None,
            "errors": [],
            "declared_checks": [],
            "declared_reviewers": [],
            "path_findings": [],
        }
    try:
        manifest = load_manifest(path)
    except ManifestError as exc:
        return {
            "status": "invalid",
            "path": path.relative_to(root).as_posix(),
            "errors": [value[:MAX_VALUE] for value in exc.issues[:MAX_LIST]],
            "declared_checks": [],
            "declared_reviewers": [],
            "path_findings": [],
        }
    return {
        "status": "valid",
        "path": path.relative_to(root).as_posix(),
        "errors": [],
        "declared_checks": sorted(manifest.checks),
        "declared_reviewers": sorted(manifest.reviewers),
        "path_findings": _missing_concrete_paths(manifest, root),
    }


def _missing_concrete_paths(manifest: Manifest, root: Path) -> list[dict[str, Any]]:
    """Concrete (non-glob) manifest-declared paths that do not exist under the root.

    ``load_manifest`` already rejects glob metacharacters in each of these fields, so
    every value here is a literal repository-relative path. A missing entry is drift,
    not manifest invalidity — e.g. a stale ``checks.*.cwd`` silently makes a check
    ``unavailable``. Reported as findings without changing manifest ``status``.
    """
    root_resolved = root.resolve()
    findings: list[dict[str, Any]] = []

    def record(field: str, name: str | None, relative: str, kind: str) -> None:
        candidate = root / relative
        try:
            candidate.resolve().relative_to(root_resolved)
        except (OSError, ValueError):
            findings.append(
                {
                    "field": field,
                    "name": name,
                    "path": relative,
                    "kind": kind,
                    "reason": "escapes_root",
                }
            )
            return
        present = candidate.is_dir() if kind == "dir" else candidate.is_file()
        if not present:
            findings.append(
                {
                    "field": field,
                    "name": name,
                    "path": relative,
                    "kind": kind,
                    "reason": "missing",
                }
            )

    for name, check in manifest.checks.items():
        if check.cwd not in (".", ""):
            record("checks.cwd", name, check.cwd, "dir")
    for declaration in manifest.fitness:
        for reference in declaration.references:
            record("fitness.references", declaration.name, reference, "file")
    if manifest.docs.currency is not None:
        for role in manifest.docs.currency.roles:
            record("docs.currency.roles.index", role.name, role.index, "file")
    for document in manifest.project.documents:
        record("project.documents", None, document, "file")
    return findings[:MAX_LIST]


def matched_paths(paths: list[str], patterns: tuple[str, ...]) -> dict[str, Any]:
    matched = sorted(path for path in paths if matches_any(path, patterns))
    return {"paths": matched[:MAX_LIST], "truncated": len(matched) > MAX_LIST}


def risk_observations(paths: list[str]) -> list[dict[str, Any]]:
    categories = ("generated", "migration", "public-contract", "security", "deployment")
    rows = []
    for category in categories:
        matched = sorted(path for path in paths if matches_any(path, BUILTINS[category]))
        rows.append(
            {
                "category": category,
                "count": len(matched),
                "samples": matched[:20],
                "truncated": len(matched) > 20,
                "source": f"builtin:{category}",
                "policy": False,
            }
        )
    return rows


def configuration_observation(paths: list[str]) -> dict[str, Any]:
    ci = sorted(path for path in paths if matches_any(path, CI_PATTERNS))
    configuration_patterns = (
        "Dockerfile*",
        "**/Dockerfile*",
        "docker-compose*.yml",
        "docker-compose*.yaml",
        "compose*.yml",
        "compose*.yaml",
        ".env.example",
        "**/.env.example",
        "Justfile",
        "justfile",
        "Makefile",
    )
    configuration = sorted(path for path in paths if matches_any(path, configuration_patterns))
    return {
        "ci": ci[:MAX_LIST],
        "configuration": configuration[:MAX_LIST],
        "truncated": len(ci) > MAX_LIST or len(configuration) > MAX_LIST,
    }


def reviewer_observations(
    root: Path, paths: list[str], manifest_path: Path | None
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if manifest_path is None:
        return []
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError:
        return []
    for name, item in manifest.reviewers.items():
        applicable = not item.applies_to or any(
            matches_any(path, item.applies_to) for path in paths
        )
        executable = _available_command(item.command[0], root, item.cwd)
        reason = ""
        if not applicable:
            state = "not_applicable"
        elif executable is None:
            state = "unavailable"
            reason = "declared reviewer executable is unavailable"
        else:
            state = "configured"
        rows[name] = {
            "id": name,
            "kind": "semantic-reviewer",
            "adapter": item.adapter,
            "state": state,
            "executable": executable,
            "probe_executable": None,
            "initialized": None,
            "source": "engineering.yaml",
            "adopted": True,
            "network": item.network,
            "reason": reason,
        }
    return [rows[name] for name in sorted(rows)]


def _available_command(executable: str, root: Path, cwd_name: str) -> str | None:
    return (
        executable if resolve_executable(executable, root=root, cwd=cwd_name) is not None else None
    )
