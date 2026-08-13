"""Read-only project-health observations consumed by doctor."""

from __future__ import annotations

import glob
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from ..execution import resolve_executable
from ..policy.manifest import Manifest


@dataclass(frozen=True)
class HealthIssue:
    id: str
    severity: str
    evidence: str
    rationale: str
    repair: str
    ci_blocking: bool = False


CI_PATTERNS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".forgejo/workflows/*.yml",
    ".forgejo/workflows/*.yaml",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    ".circleci/config.yml",
    "Jenkinsfile",
)

TEMPLATE_MARKERS = (
    re.compile(r"\{\{\s*(?:project|package|service)[^}]*\}\}", re.IGNORECASE),
    re.compile(r"<PROJECT[_ -][A-Z0-9_ -]*>"),
    re.compile(r"\b(?:CHANGEME|YOUR_PROJECT_NAME)\b"),
    re.compile(r"\[PROJECT NAME\]", re.IGNORECASE),
)


def inspect_command_availability(root: Path, manifest: Manifest) -> tuple[HealthIssue, ...]:
    issues: list[HealthIssue] = []
    for check in manifest.checks.values():
        commands = [("command", check.command)]
        if check.version_command is not None:
            commands.append(("version_command", check.version_command))
        for field, command in commands:
            resolved = resolve_executable(command[0], root=root, cwd=check.cwd)
            if resolved is None:
                issues.append(
                    HealthIssue(
                        "commands.unavailable",
                        "error",
                        f"check {check.name!r} {field} executable {command[0]!r} is unavailable",
                        "adopted checks must be executable in the current environment",
                        "install the project tool or correct the declared argument vector",
                        True,
                    )
                )
    return tuple(issues)


def inspect_reviewer_health(root: Path, manifest: Manifest) -> tuple[HealthIssue, ...]:
    """Validate explicitly adopted semantic reviewers without executing them."""
    issues: list[HealthIssue] = []
    for item in manifest.reviewers.values():
        commands = [("command", item.command)]
        if item.version_command is not None:
            commands.append(("version_command", item.version_command))
        for field, command in commands:
            if resolve_executable(command[0], root=root, cwd=item.cwd) is None:
                issues.append(
                    HealthIssue(
                        "reviewers.command-unavailable",
                        "error" if item.blocking else "warning",
                        (
                            f"reviewer {item.name!r} {field} executable "
                            f"{command[0]!r} is unavailable"
                        ),
                        "an adopted reviewer must have a usable execution contract",
                        "install/configure the reviewer adapter or remove the project adoption",
                        item.blocking,
                    )
                )
        cwd = (root / item.cwd).resolve()
        try:
            cwd.relative_to(root.resolve())
        except ValueError:
            cwd_valid = False
        else:
            cwd_valid = cwd.is_dir()
        if not cwd_valid:
            issues.append(
                HealthIssue(
                    "reviewers.cwd-unavailable",
                    "error" if item.blocking else "warning",
                    f"reviewer {item.name!r} cwd {item.cwd!r} is unavailable",
                    "review execution must remain inside an existing project directory",
                    "correct the declared cwd",
                    item.blocking,
                )
            )
    return tuple(issues)


def inspect_ci_coverage(root: Path, manifest: Manifest) -> tuple[HealthIssue, ...]:
    files = _glob_contained_files(root, CI_PATTERNS)
    if not files:
        return (
            HealthIssue(
                "ci.no-config",
                "warning",
                "no recognized CI configuration file was found",
                "declared checks have no repository-local CI execution evidence",
                "add a supported CI configuration or review this finding as not applicable",
                True,
            ),
        )
    contents = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in files)
    covered: set[str] = set()
    if re.search(r"\bengineering\s+check\s+full\b", contents):
        covered.update(manifest.checks)
    for name, profile in manifest.profiles.items():
        if re.search(rf"\bengineering\s+check\s+{re.escape(name)}\b", contents):
            covered.update(profile.checks)
    for name, check in manifest.checks.items():
        direct = shlex.join(check.command)
        simple = " ".join(check.command)
        if (
            re.search(rf"\bengineering\s+check\s+{re.escape(name)}\b", contents)
            or direct in contents
            or simple in contents
        ):
            covered.add(name)
    evidence_paths = ", ".join(path.relative_to(root).as_posix() for path in files)
    return tuple(
        HealthIssue(
            "ci.check-not-evidenced",
            "warning",
            f"check {name!r} has no recognizable direct invocation in {evidence_paths}",
            "a declared check should have reviewable CI coverage or an explicit exception",
            "invoke the check/profile/full selector in CI or document why it remains local-only",
            True,
        )
        for name in sorted(set(manifest.checks) - covered)
    )


def inspect_path_policy(root: Path, manifest: Manifest) -> tuple[HealthIssue, ...]:
    issues: list[HealthIssue] = []
    if manifest.project.risk in {"high", "critical"} and not manifest.paths.sensitive:
        issues.append(
            HealthIssue(
                "sensitive.none-declared",
                "warning",
                f"project risk is {manifest.project.risk!r} but paths.sensitive is empty",
                "high-risk work needs explicit sensitive-boundary visibility",
                "declare the repository globs that require heightened review",
                True,
            )
        )
    for pattern in manifest.paths.sensitive:
        if not _glob_contained_files(root, (pattern,)):
            issues.append(
                HealthIssue(
                    "sensitive.pattern-unmatched",
                    "warning",
                    f"sensitive pattern {pattern!r} matched no files",
                    "stale path policy can hide the boundaries agents expect to protect",
                    "correct or remove the stale sensitive-path pattern",
                )
            )
    for pattern in manifest.paths.forbidden:
        for path in _glob_contained_files(root, (pattern,)):
            issues.append(
                HealthIssue(
                    "forbidden.path-present",
                    "error",
                    f"forbidden pattern {pattern!r} matched {path.relative_to(root).as_posix()!r}",
                    "forbidden repository content violates adopted project policy",
                    "remove the content through the project's approved process or revise policy",
                    True,
                )
            )
    return tuple(issues)


def inspect_project_templates(root: Path, manifest: Manifest) -> tuple[HealthIssue, ...]:
    issues: list[HealthIssue] = []
    for relative in manifest.project.documents:
        path = root / relative
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            issues.append(
                HealthIssue(
                    "templates.document-unsafe",
                    "error",
                    f"declared project document {relative!r} resolves outside the project",
                    "project authority must not silently cross the repository boundary",
                    "replace the symlink with a contained document or remove the declaration",
                    True,
                )
            )
            continue
        if not path.is_file():
            issues.append(
                HealthIssue(
                    "templates.document-missing",
                    "warning",
                    f"declared project document {relative!r} is missing",
                    "declared authority and project context must be available to agents",
                    "create the document or remove the stale declaration",
                    True,
                )
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            marker = next(
                (pattern.search(line) for pattern in TEMPLATE_MARKERS if pattern.search(line)), None
            )
            if marker is not None:
                issues.append(
                    HealthIssue(
                        "templates.placeholder",
                        "warning",
                        f"{relative}:{line_number}: unresolved marker {marker.group(0)!r}",
                        "unfilled project templates provide misleading authority and context",
                        "replace the placeholder with project-specific content",
                        True,
                    )
                )
    return tuple(issues)


def _glob_contained_files(root: Path, patterns: tuple[str, ...]) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    found: set[Path] = set()
    for pattern in patterns:
        for value in glob.glob(str(root / pattern), recursive=True):
            path = Path(value)
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(resolved_root)
            except ValueError:
                continue
            found.add(path)
    return tuple(sorted(found))
