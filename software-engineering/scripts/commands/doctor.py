"""Adapter for aggregate adopted-contract diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.context import load_adopted_project
from ..verification.doctor import diagnose
from .contracts import EXIT_INVALID_POLICY, EXIT_OK, CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ci", action="store_true")


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    report = diagnose(adopted.root, adopted.manifest, args.project_root, ci=args.ci)
    return CommandResult(
        report.status,
        adopted.root,
        {
            "ci": args.ci,
            "ci_blocking_findings": report.ci_blocking_findings,
            "findings": [asdict(item) for item in report.findings],
        },
        EXIT_INVALID_POLICY if report.status == "failed" else EXIT_OK,
    )


SPEC = CommandSpec(
    "doctor",
    "aggregate read-only project diagnostics",
    configure,
    handle,
    explanation(
        "doctor",
        "Adopted-contract diagnostics",
        "Aggregate policy, tool, CI, path, documentation, generated, and template health.",
        ("checking whether an adopted project contract is coherent", "preparing CI diagnostics"),
        ("running checks or repairing findings",),
        prerequisites=("an adopted engineering.yaml",),
        evidence=("findings with severity, rationale, repair, and CI semantics",),
        limitations=("doctor is read-only and direct invocation evidence is not remote-run proof",),
        next_commands=("engineering doctor --ci --json",),
    ),
)
