"""Fitness declarations and explainable affected-check selection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ..policy.manifest import Manifest
from ..policy.path_matching import matching_pattern


@dataclass(frozen=True)
class FitnessFunction:
    name: str
    command: tuple[str, ...]
    invariant: str
    adr: str
    paths: tuple[str, ...] = ()
    exception_until: date | None = None


@dataclass(frozen=True)
class FitnessIssue:
    fitness: str
    code: str
    message: str


@dataclass(frozen=True)
class Selection:
    check: str
    selected: bool
    reason: str


def from_manifest(manifest: Manifest) -> tuple[FitnessFunction, ...]:
    """Project adopted fitness declarations into the executable domain model."""

    functions: list[FitnessFunction] = []
    for item in manifest.fitness:
        expiries = [date.fromisoformat(exception.expires) for exception in item.exceptions]
        check = manifest.checks[item.check]
        functions.append(
            FitnessFunction(
                item.name,
                check.command,
                item.rationale,
                item.references[0] if item.references else "",
                item.applies_to,
                min(expiries) if expiries else None,
            )
        )
    return tuple(functions)


def validate_fitness(
    root: Path, functions: Sequence[FitnessFunction], today: date | None = None
) -> tuple[FitnessIssue, ...]:
    current = today or datetime.now(UTC).date()
    issues: list[FitnessIssue] = []
    for function in functions:
        if not function.invariant.strip():
            issues.append(FitnessIssue(function.name, "missing-invariant", "invariant is required"))
        adr = (root / function.adr).resolve()
        try:
            adr.relative_to(root.resolve())
        except ValueError:
            issues.append(FitnessIssue(function.name, "unsafe-adr", "ADR escapes project root"))
        else:
            if not adr.is_file():
                issues.append(FitnessIssue(function.name, "missing-adr", function.adr))
        if function.exception_until and function.exception_until < current:
            issues.append(
                FitnessIssue(
                    function.name, "expired-exception", function.exception_until.isoformat()
                )
            )
    return tuple(issues)


def select_affected(
    changed_paths: Sequence[str],
    check_paths: Mapping[str, Sequence[str]],
    *,
    full: bool = False,
) -> tuple[Selection, ...]:
    selections: list[Selection] = []
    for name in sorted(check_paths):
        patterns = check_paths[name]
        matched = next(
            (
                (path, pattern)
                for path in changed_paths
                if (pattern := matching_pattern(path, patterns)) is not None
            ),
            None,
        )
        if full:
            selections.append(Selection(name, True, "full mode"))
        elif not patterns:
            selections.append(Selection(name, True, "no applies_to restriction"))
        elif matched:
            selections.append(Selection(name, True, f"{matched[0]!r} matched {matched[1]!r}"))
        else:
            selections.append(Selection(name, False, "no changed path matched declared paths"))
    return tuple(selections)


def run_fitness(
    functions: Sequence[FitnessFunction],
    runner: Callable[[str, Sequence[str]], object],
    names: Sequence[str] | None = None,
) -> tuple[object, ...]:
    selected = set(names) if names is not None else None
    return tuple(
        runner(function.name, function.command)
        for function in functions
        if selected is None or function.name in selected
    )
