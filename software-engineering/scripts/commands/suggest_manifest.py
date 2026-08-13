"""Adapter for non-authoritative manifest suggestions."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..inspection import inspect_repository
from ..project.suggestions import render_markdown, suggest_manifest
from .contracts import CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--markdown", action="store_true", help="render reviewable Markdown")


def handle(args: argparse.Namespace) -> CommandResult:
    if args.json and args.markdown:
        raise ValueError("--json and --markdown are mutually exclusive")
    report = suggest_manifest(
        args.project_root,
        inspection=inspect_repository(args.project_root),
    )
    root = Path(report["root"])
    data = {
        key: value
        for key, value in report.items()
        if key not in {"schema_version", "status", "root"}
    }
    return CommandResult(report["status"], root, data, human=render_markdown(report))


SPEC = CommandSpec(
    "suggest-manifest",
    "emit provenance-labelled review candidates without writing or enforcing policy",
    configure,
    handle,
    explanation(
        "suggest-manifest",
        "Manifest suggestions",
        "Turn observed project signals into provenance-labelled review candidates without adoption.",
        ("a repository has no reviewed engineering manifest",),
        ("automatically enforcing discovered commands",),
        prerequisites=("a readable target directory; engineering.yaml is optional",),
        evidence=("non-authoritative candidates with source, confidence, and rationale",),
        limitations=("suggestions are not policy or a stable manifest migration",),
        next_commands=("engineering explain command.start",),
    ),
)
