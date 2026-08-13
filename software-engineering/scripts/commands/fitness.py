"""Adapter for adopted architectural fitness functions."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.context import load_adopted_project
from ..verification.checks import run_check
from ..verification.fitness import from_manifest, run_fitness, validate_fitness
from .contracts import (
    DECLARED_EXECUTION,
    EXIT_CHECK_FAILED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", nargs="?", default="list", choices=("list", "explain", "run"))
    parser.add_argument("names", nargs="*")


def _exit_for(results) -> int:
    statuses = {result.status for result in results}
    if statuses & {"failed", "timed_out"}:
        return EXIT_CHECK_FAILED
    if "unavailable" in statuses:
        return EXIT_UNAVAILABLE
    return EXIT_OK


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    root, manifest = adopted.root, adopted.manifest
    names = set(args.names)
    selected = [item for item in from_manifest(manifest) if not names or item.name in names]
    if args.action == "list":
        return CommandResult("passed", root, {"fitness": [item.name for item in selected]})
    issues = validate_fitness(root, selected)
    if args.action == "explain":
        return CommandResult(
            "failed" if issues else "passed",
            root,
            {
                "fitness": [asdict(item) for item in selected],
                "findings": [asdict(item) for item in issues],
            },
            EXIT_CHECK_FAILED if issues else EXIT_OK,
        )
    results = run_fitness(
        selected,
        lambda name, argv: run_check(
            manifest.checks[next(item.check for item in manifest.fitness if item.name == name)],
            root,
        ),
    )
    code = _exit_for(results)
    return CommandResult(
        "passed" if code == EXIT_OK else ("unavailable" if code == EXIT_UNAVAILABLE else "failed"),
        root,
        {
            "findings": [asdict(item) for item in issues],
            "results": [item.to_dict() for item in results],
        },
        code,
    )


SPEC = CommandSpec(
    "fitness",
    "list, explain, or run fitness functions",
    configure,
    handle,
    explanation(
        "fitness",
        "Architectural fitness functions",
        "List, explain, or run checks tied to recorded architectural invariants.",
        ("an adopted architecture decision names an executable characteristic",),
        ("automating taste or an unrecorded preference",),
        effects=DECLARED_EXECUTION,
        evidence=("selection rationale, references, validation findings, and check result",),
        limitations=("a passing fitness function establishes only its declared property",),
        next_commands=("engineering fitness explain --json",),
    ),
)
