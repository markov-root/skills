"""Adapter for the adopted engineering-run start transaction."""

from __future__ import annotations

import argparse

from ..runs.workflow import start_run
from .contracts import (
    DECLARED_EXECUTION,
    EXIT_APPROVAL_REQUIRED,
    EXIT_CHECK_FAILED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--intent", required=True, help="bounded human/agent intent for this run")
    parser.add_argument("--paths", nargs="*", default=(), metavar="PATH")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--global-agents",
        metavar="PATH",
        help="explicit global AGENTS.md to include below project instructions",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    result = start_run(
        args.project_root,
        intent=args.intent,
        paths=args.paths,
        run_id=args.run_id,
        global_agents=args.global_agents,
    )
    code = {
        "approval_required": EXIT_APPROVAL_REQUIRED,
        "failed": EXIT_CHECK_FAILED,
        "unavailable": EXIT_UNAVAILABLE,
    }.get(result.status, EXIT_OK)
    return CommandResult(result.status, result.root, result.data, code, result.human)


SPEC = CommandSpec(
    "start",
    "capture a baseline and working contract",
    configure,
    handle,
    explanation(
        "start",
        "Start an engineering run",
        "Bind intent, authority, scope, classifications, checks, tools, and pre-existing truth before edits.",
        ("beginning adopted non-trivial work",),
        (
            "the repository has not adopted engineering.yaml",
            "the change is one bounded mechanical edit",
        ),
        effects=DECLARED_EXECUTION,
        evidence=(
            "sealed baseline.json and start.json",
            "selected and omitted checks with reasons",
        ),
        limitations=("a baseline is evidence, not implementation correctness",),
        next_commands=("engineering finish RUN_ID",),
        references=("SKILL.md", "docs/CONTRACT.md"),
    ),
)
