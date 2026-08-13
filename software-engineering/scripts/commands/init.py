"""Adapter for preview-first `engineering.yaml` initialization.

Thin adapter: it inspects the repository, derives non-authoritative suggestions, and renders the
starter-manifest plan produced by ``project.initialization``. Preview is the default; writing
requires explicit ``--apply`` and never overwrites an existing manifest.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..inspection import inspect_repository
from ..project.initialization import plan_init
from ..project.suggestions import suggest_manifest
from .contracts import CommandResult, CommandSpec, Effects, explanation

_EFFECTS = Effects(
    "reads the repository and, only with --apply, writes a new engineering.yaml",
    "none",
    "with --apply, creates engineering.yaml only when absent; never overwrites existing policy",
    "none",
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write engineering.yaml; without it the command only previews the proposed manifest",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    report = suggest_manifest(args.project_root, inspection=inspect_repository(args.project_root))
    plan = plan_init(args.project_root, report, apply=args.apply)
    return CommandResult("passed", Path(report["root"]), plan.to_dict(), human=_render(plan))


def _render(plan) -> str:
    mode = "APPLIED" if plan.apply else "dry-run (re-run with --apply to write)"
    lines = [
        f"Initialize starter manifest → {plan.target}  [{mode}]",
        "  Review before adopting: 'core_outcome' is a placeholder and checks are candidates.",
        "",
        plan.manifest_text.rstrip("\n"),
    ]
    return "\n".join(lines)


SPEC = CommandSpec(
    "init",
    "preview or write a starter engineering.yaml from review candidates",
    configure,
    handle,
    explanation(
        "init",
        "Starter manifest initialization",
        "Generate a minimal, valid engineering.yaml from review candidates, preview-first.",
        ("a repository has no engineering.yaml and wants a reviewed starting point",),
        (
            "overwriting existing policy",
            "treating the generated starter as adopted or approved policy",
        ),
        prerequisites=("a readable target directory without an existing engineering.yaml",),
        effects=_EFFECTS,
        evidence=("the proposed manifest text and whether it was written",),
        limitations=(
            "the output is a review starter, not adopted policy; core_outcome is a placeholder",
            "it never overwrites an existing manifest and validates before writing",
        ),
        next_commands=("engineering suggest-manifest --markdown", "engineering inspect"),
        references=("docs/CONTRACT.md",),
    ),
)
