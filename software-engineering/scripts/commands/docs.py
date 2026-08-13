"""Adapter for adopted Markdown validation."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..documents.markdown import findings_markdown
from ..documents.validation import expand_markdown_paths, validate_documents
from ..project.context import load_adopted_project
from .contracts import EXIT_CHECK_FAILED, EXIT_OK, CommandResult, CommandSpec, explanation


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--markdown", action="store_true", help="render findings as Markdown")


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    policy = adopted.manifest.docs
    paths = expand_markdown_paths(adopted.root, policy.include or ("**/*.md",))
    findings = validate_documents(adopted.root, policy, paths)
    return CommandResult(
        "failed" if findings else "passed",
        adopted.root,
        {"findings": [asdict(item) for item in findings]},
        EXIT_CHECK_FAILED if findings else EXIT_OK,
        findings_markdown(findings) if args.markdown else None,
    )


SPEC = CommandSpec(
    "docs",
    "validate declared Markdown documentation",
    configure,
    handle,
    explanation(
        "docs",
        "Documentation validation",
        "Validate adopted Markdown structure and optional role/currency policy read-only.",
        ("documentation links, structure, indexes, states, or task evidence are contractual",),
        ("grading prose truth or rewriting historical records",),
        prerequisites=("an adopted engineering.yaml with docs policy",),
        evidence=("path/line findings in JSON or Markdown",),
        limitations=("role authority exists only when the project explicitly adopts it",),
        next_commands=("engineering docs --json",),
    ),
)
