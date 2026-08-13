"""Adapter exposing bounded guidance-quality fitness over the bundled knowledge corpus."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

from ..knowledge import evaluate_guidance_fitness
from ..resources import skill_root
from .contracts import (
    EXIT_CHECK_FAILED,
    EXIT_OK,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", nargs="?", default="fitness", choices=("fitness",))
    parser.add_argument(
        "--as-of",
        default=None,
        help="ISO date (YYYY-MM-DD) for source-freshness signals; defaults to today",
    )
    parser.add_argument(
        "--changed",
        action="append",
        default=[],
        metavar="RECORD_ID",
        help="restrict freshness triggers to these changed knowledge records; repeatable",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    root = skill_root()
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(UTC).date()
    report = evaluate_guidance_fitness(root, as_of=as_of, changed_ids=tuple(args.changed))
    blocking = report.blocking
    return CommandResult(
        "failed" if blocking else "passed",
        root,
        report.to_dict(),
        EXIT_CHECK_FAILED if blocking else EXIT_OK,
    )


SPEC = CommandSpec(
    "knowledge",
    "evaluate guidance-quality fitness over the bundled knowledge corpus",
    configure,
    handle,
    explanation(
        "knowledge",
        "Guidance-quality fitness",
        "Report deterministic structure/ownership/source contracts as blocking, and freshness and "
        "normative/duplication/conflict signals as advisory or review candidates, over the skill's "
        "own knowledge corpus.",
        ("maintaining or reviewing the authored knowledge corpus",),
        ("grading prose truth, elegance, or producing a universal quality score",),
        evidence=(
            "classified findings with path, line, evidence, and per-finding proof limit",
            "counts split into blocking, advisory, and candidate",
        ),
        limitations=(
            "only blocking findings assert a deterministic artifact contract",
            "advisories and candidates are review prompts, not proof a claim is stale or wrong",
        ),
        next_commands=("engineering knowledge fitness --json",),
    ),
)
