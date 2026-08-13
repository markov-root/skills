"""Adapter for the adopted engineering-run finish transaction."""

from __future__ import annotations

import argparse

from ..runs.workflow import finish_run
from .contracts import (
    DECLARED_EXECUTION,
    EXIT_APPROVAL_REQUIRED,
    EXIT_BASELINE_INCOMPATIBLE,
    EXIT_CHECK_FAILED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("run_id")
    parser.add_argument("--full", action="store_true", help="run every declared check")
    parser.add_argument(
        "--global-agents",
        metavar="PATH",
        help="explicit global AGENTS.md used when the run started",
    )
    parser.add_argument(
        "--manual-recovery",
        action="append",
        default=[],
        metavar="CODE",
        help="record a non-sensitive recovery code used during this run",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    result = finish_run(
        args.project_root,
        args.run_id,
        full=args.full,
        global_agents=args.global_agents,
        manual_recovery=args.manual_recovery,
    )
    code = {
        "approval_required": EXIT_APPROVAL_REQUIRED,
        "failed": EXIT_CHECK_FAILED,
        "unavailable": EXIT_UNAVAILABLE,
        "incompatible": EXIT_BASELINE_INCOMPATIBLE,
    }.get(result.status, EXIT_OK)
    return CommandResult(result.status, result.root, result.data, code, result.human)


SPEC = CommandSpec(
    "finish",
    "verify and seal a started engineering run",
    configure,
    handle,
    explanation(
        "finish",
        "Finish an engineering run",
        "Recalculate the real surface, execute applicable policy, and seal cautious completion evidence.",
        ("implementation for a started run is ready for verification",),
        ("no compatible start record exists",),
        effects=DECLARED_EXECUTION,
        evidence=("sealed final.json", "scope expansion, checks, findings, and residual risks"),
        limitations=("deterministic checks do not replace semantic or causal review",),
        next_commands=("engineering doctor --json",),
        references=("SKILL.md", "docs/CONTRACT.md"),
    ),
)
