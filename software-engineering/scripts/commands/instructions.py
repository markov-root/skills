"""Adapter for instruction authority discovery and drift reporting."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.context import load_adopted_project
from ..project.discovery import discover_documents, discover_instructions
from .contracts import EXIT_CHECK_FAILED, EXIT_OK, CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--global-agents",
        metavar="PATH",
        help="explicit global AGENTS.md to report below project instructions",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    root, manifest, project = adopted.root, adopted.manifest, adopted.discovery
    rows = [
        {
            **asdict(item),
            "path": (
                item.path.relative_to(root).as_posix()
                if item.path.is_relative_to(root)
                else str(item.path)
            ),
        }
        for item in discover_instructions(
            project,
            args.project_root,
            global_agents=args.global_agents,
        )
    ]
    documents = [
        {**asdict(item), "path": item.path.relative_to(root).as_posix()}
        for item in discover_documents(project, manifest.project.documents)
    ]
    drift = any(row["drift"] for row in rows)
    return CommandResult(
        "failed" if drift else "passed",
        root,
        {"instructions": rows, "declared_documents": documents},
        EXIT_CHECK_FAILED if drift else EXIT_OK,
    )


SPEC = CommandSpec(
    "instructions",
    "resolve applicable instruction files",
    configure,
    handle,
    explanation(
        "instructions",
        "Instruction authority",
        "Resolve project/global instruction precedence, declared documents, digests, and drift.",
        ("authority must be inspected or sealed",),
        ("searching arbitrary machine-global files",),
        prerequisites=("an adopted engineering.yaml",),
        evidence=("ordered sources, hashes, paths, and drift state",),
        limitations=("only an explicitly supplied global source may be outside the project",),
    ),
)
