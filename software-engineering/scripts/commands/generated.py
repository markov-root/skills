"""Adapter for isolated generated-artifact verification."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from ..project.context import load_adopted_project
from ..verification.generated import from_manifest, run_generator, verify_generated
from .contracts import (
    EXIT_CHECK_FAILED,
    EXIT_OK,
    TEMPORARY_COPY,
    CommandResult,
    CommandSpec,
    explanation,
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("names", nargs="*")


def handle(args: argparse.Namespace) -> CommandResult:
    adopted = load_adopted_project(args.project_root)
    names = set(args.names)
    declarations = [
        item for item in from_manifest(adopted.manifest) if not names or item.name in names
    ]
    findings = [
        finding
        for declaration in declarations
        for finding in verify_generated(adopted.root, declaration, run_generator)
    ]
    return CommandResult(
        "failed" if findings else "passed",
        adopted.root,
        {"findings": [asdict(item) for item in findings]},
        EXIT_CHECK_FAILED if findings else EXIT_OK,
    )


SPEC = CommandSpec(
    "generated",
    "verify generated artifacts in a temporary copy",
    configure,
    handle,
    explanation(
        "generated",
        "Generated-artifact drift",
        "Regenerate declared artifacts in isolation and compare them with the checkout.",
        ("generated outputs must be reproducible and current",),
        ("mutating the source checkout",),
        effects=TEMPORARY_COPY,
        evidence=("declared inputs/outputs and normalized drift findings",),
        limitations=("comparison covers only adopted generators and declared outputs",),
    ),
)
