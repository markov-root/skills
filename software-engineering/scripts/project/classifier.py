"""Explainable path-based change classification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..execution import run_process
from ..policy.path_matching import matching_pattern


@dataclass(frozen=True)
class Change:
    path: str
    status: str
    old_path: str | None = None


@dataclass(frozen=True)
class Classification:
    category: str
    path: str
    rule: str
    evidence: str
    approval_required: bool = False


BUILTINS: dict[str, tuple[str, ...]] = {
    "dependency": (
        "**/package.json",
        "**/pyproject.toml",
        "**/requirements*.txt",
        "**/uv.lock",
        "**/poetry.lock",
        "**/Pipfile.lock",
        "**/package-lock.json",
        "**/pnpm-lock.yaml",
        "**/yarn.lock",
        "**/bun.lock",
        "**/bun.lockb",
        "**/Cargo.lock",
        "**/go.sum",
        "**/Gemfile.lock",
        "**/composer.lock",
    ),
    "migration": ("**/migrations/**", "**/migration/**"),
    "public-contract": ("**/schemas/**", "**/openapi*", "**/api/**"),
    "deployment": ("**/Dockerfile*", "**/.github/workflows/**", "**/deploy/**"),
    "security": (
        "**/security/**",
        "**/auth/**",
        "**/authentication/**",
        "**/authorization/**",
        "**/secrets/**",
        "**/.env",
        "**/.env.*",
        "**/security.*",
        "**/auth.*",
        "**/authentication.*",
        "**/authorization.*",
        "**/secret.*",
        "**/secrets.*",
    ),
    "generated": ("**/generated/**", "**/*.generated.*"),
    "test": ("**/test*/**", "**/*_test.*", "**/*.test.*"),
    "instruction": ("**/AGENTS.md", "**/CLAUDE.md", "**/CONTRIBUTING.md"),
}


def classify_changes(
    changes: Sequence[Change],
    rules: Mapping[str, Sequence[str]] | None = None,
    approvals: Sequence[str] = (),
) -> tuple[Classification, ...]:
    configured = rules or {}
    findings: list[Classification] = []
    for change in changes:
        paths = (change.path,) if change.old_path is None else (change.old_path, change.path)
        for category, patterns in [*configured.items(), *BUILTINS.items()]:
            match = next(
                (
                    (path, pattern)
                    for path in paths
                    if (pattern := matching_pattern(path, patterns)) is not None
                ),
                None,
            )
            if match is not None:
                matched, pattern = match
                findings.append(
                    Classification(
                        category,
                        change.path,
                        f"manifest:{category}" if category in configured else f"builtin:{category}",
                        f"{change.status} path {matched!r} matched {pattern!r}",
                        category in approvals,
                    )
                )
    return tuple(dict.fromkeys(findings))


def git_changes(root: Path, base_ref: str | None = None) -> tuple[Change, ...]:
    """Collect staged/unstaged/untracked changes, or changes from a base ref."""
    commands = [("git", "-C", str(root), "diff", "--name-status", "-z")]
    if base_ref:
        verify = run_process(
            ("git", "-C", str(root), "rev-parse", "--verify", base_ref),
            root=root,
            timeout_seconds=10,
            max_output_bytes=16_384,
        )
        if verify.status != "passed":
            raise RuntimeError(f"base ref unavailable: {base_ref}")
        commands[0] = (*commands[0], base_ref)
    else:
        commands.append(("git", "-C", str(root), "diff", "--cached", "--name-status", "-z"))
    result: list[Change] = []
    for args in commands:
        proc = run_process(
            args,
            root=root,
            timeout_seconds=30,
            max_output_bytes=10_000_000,
        )
        if proc.status != "passed":
            error = proc.stderr.decode(errors="replace").strip()
            raise RuntimeError(error or "git diff failed")
        fields = proc.stdout.decode(errors="surrogateescape").split("\0")
        index = 0
        while index < len(fields) and fields[index]:
            item_status = fields[index]
            index += 1
            if item_status.startswith(("R", "C")):
                old, new = fields[index], fields[index + 1]
                result.append(Change(new, item_status, old))
                index += 2
            else:
                result.append(Change(fields[index], item_status))
                index += 1
    if not base_ref:
        untracked = run_process(
            ("git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"),
            root=root,
            timeout_seconds=10,
            max_output_bytes=10_000_000,
        )
        if untracked.status == "passed":
            result.extend(
                Change(path, "??") for path in untracked.stdout.decode().split("\0") if path
            )
    return tuple(dict.fromkeys(result))


def git_commit(root: Path) -> str | None:
    """Return the current Git commit when the project has one."""

    result = run_process(
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        root=root,
        timeout_seconds=10,
        max_output_bytes=16_384,
    )
    return result.stdout.decode(errors="replace").strip() if result.status == "passed" else None
