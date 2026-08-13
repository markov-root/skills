"""Adapter for listing and explaining the registered public capability surface."""

from __future__ import annotations

import argparse

from .contracts import CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("identifiers", nargs="*", metavar="IDENTIFIER")
    parser.add_argument(
        "--kind",
        choices=("command", "profile", "adapter"),
        help="filter the catalog by capability kind",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    selected = args._explanation_selector(tuple(args.identifiers), kind=args.kind)
    detailed = bool(args.identifiers)
    return CommandResult(
        "passed",
        None,
        {
            "mode": "detail" if detailed else "list",
            "count": len(selected),
            "capabilities": [item.to_dict() for item in selected],
        },
        human=args._explanation_renderer(selected, detailed=detailed),
    )


SPEC = CommandSpec(
    "explain",
    "list or explain every public engineering capability",
    configure,
    handle,
    explanation(
        "explain",
        "Capability explanations",
        "List or explain the public engineering surface from one typed, bounded registry.",
        ("deciding why, when, or how to invoke the skill or CLI",),
        ("proving that another capability ran",),
        prerequisites=(
            "uv is available and the skill root is resolved from the discovered SKILL.md; no manifest required",
        ),
        evidence=("versioned JSON or human text rendered from the same records",),
        limitations=("static explanations do not classify arbitrary natural-language intent",),
        next_commands=("engineering explain command.inspect",),
        references=("SKILL.md", "docs/CONTRACT.md"),
    ),
)
