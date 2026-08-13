"""Adapter for explicitly adopted project checks."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.classifier import git_changes
from ..project.context import load_adopted_project
from ..verification.checks import run_check, run_checks
from ..verification.fitness import select_affected
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
    parser.add_argument("selector", nargs="?", default="fast")


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
    if args.selector == "affected":
        try:
            changed = [item.path for item in git_changes(root)]
        except RuntimeError as exc:
            return CommandResult("unavailable", root, {"reason": str(exc)}, EXIT_UNAVAILABLE)
        selections = select_affected(
            changed,
            {name: check.applies_to for name, check in manifest.checks.items()},
        )
        results = tuple(
            run_check(manifest.checks[item.check], root) for item in selections if item.selected
        )
    else:
        selections = ()
        results = run_checks(manifest, args.selector, root)
    code = _exit_for(results)
    status = (
        "passed" if code == EXIT_OK else ("unavailable" if code == EXIT_UNAVAILABLE else "failed")
    )
    return CommandResult(
        status,
        root,
        {
            "selector": args.selector,
            "selection": [asdict(item) for item in selections],
            "results": [result.to_dict() for result in results],
        },
        code,
    )


SPEC = CommandSpec(
    "check",
    "run a named check, profile, affected, or full set",
    configure,
    handle,
    explanation(
        "check",
        "Declared checks",
        "Run an adopted named, profile, affected, or full check selection.",
        ("a repository-declared verification command must run",),
        ("executing an inferred command candidate",),
        effects=DECLARED_EXECUTION,
        evidence=("bounded result status, exit code, duration, and redacted output",),
        limitations=(
            "affected selection is path-policy evidence, not a universal dependency graph",
        ),
        next_commands=("engineering check affected --json", "engineering check full --json"),
    ),
)
