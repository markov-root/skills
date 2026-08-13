"""Adapter for explainable Git path classification."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.classifier import classify_changes, git_changes
from ..project.context import load_adopted_project
from .contracts import (
    EXIT_APPROVAL_REQUIRED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-ref")


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    if adopted.discovery.git_root is None:
        return CommandResult(
            "unavailable",
            adopted.root,
            {"reason": "Git repository required"},
            EXIT_UNAVAILABLE,
        )
    rows = classify_changes(
        git_changes(adopted.root, args.base_ref),
        adopted.manifest.classifiers,
        adopted.manifest.approval_required,
    )
    approval = any(item.approval_required for item in rows)
    return CommandResult(
        "approval_required" if approval else "passed",
        adopted.root,
        {"classifications": [asdict(item) for item in rows]},
        EXIT_APPROVAL_REQUIRED if approval else EXIT_OK,
    )


SPEC = CommandSpec(
    "classify",
    "classify Git changes",
    configure,
    handle,
    explanation(
        "classify",
        "Change classification",
        "Explain configured and conservative built-in path classifications and approval requirements.",
        ("a Git change needs risk/category routing",),
        ("granting approval", "classifying non-Git changes"),
        prerequisites=("an adopted engineering.yaml in a Git repository",),
        evidence=("classification, matching rule/pattern, and approval flag per path",),
        limitations=("path signals are conservative routing evidence, not semantic truth",),
    ),
)
