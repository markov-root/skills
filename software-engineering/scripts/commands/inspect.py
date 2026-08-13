"""Adapter for passive and explicitly selected active repository inspection."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..inspection import (
    inspect_repository,
    render_active_inspection,
    render_inspection,
    run_active_inspection,
)
from .contracts import (
    EXIT_CHECK_FAILED,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    CommandResult,
    CommandSpec,
    explanation,
)

ACTIVE_PROFILES = ("security", "privacy", "publication")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "profiles",
        nargs="*",
        choices=ACTIVE_PROFILES,
        help="explicit active inspection profiles; omit for passive repository mapping",
    )
    parser.add_argument(
        "--target",
        choices=("generic", "github", "forgejo"),
        default="generic",
        help="publication target used to evaluate privacy-safe Git identity",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="disable scanner network access and require locally cached vulnerability data",
    )
    parser.add_argument(
        "--dependency-evidence",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "import a bounded local dependency-evidence-v1 JSON artifact; repeat for independent "
            "production, full, or provider populations"
        ),
    )
    parser.add_argument(
        "--global-agents",
        metavar="PATH",
        help="explicit global AGENTS.md to report below project instructions",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    if args.profiles:
        if "publication" in args.profiles and args.target == "generic":
            raise ValueError("inspect publication requires an explicit --target")
        if args.offline and not {"security", "publication"}.intersection(args.profiles):
            raise ValueError("--offline requires the security or publication profile")
        if args.dependency_evidence and not {
            "security",
            "publication",
        }.intersection(args.profiles):
            raise ValueError("--dependency-evidence requires the security or publication profile")
        report = run_active_inspection(
            args.project_root,
            args.profiles,
            target=args.target,
            offline=args.offline,
            dependency_evidence_paths=args.dependency_evidence,
        )
        root = Path(report["root"])
        data = {
            key: value
            for key, value in report.items()
            if key not in {"schema_version", "status", "root"}
        }
        code = {
            "failed": EXIT_CHECK_FAILED,
            "unavailable": EXIT_UNAVAILABLE,
        }.get(report["status"], EXIT_OK)
        return CommandResult(report["status"], root, data, code, render_active_inspection(report))
    if args.target != "generic" or args.offline or args.dependency_evidence:
        raise ValueError(
            "--target, --offline, and --dependency-evidence require an active inspect profile"
        )
    report = inspect_repository(args.project_root, global_agents=args.global_agents)
    root = Path(report["root"])
    data = {key: value for key, value in report.items() if key not in {"schema_version", "root"}}
    return CommandResult("passed", root, data, EXIT_OK, render_inspection(report))


SPEC = CommandSpec(
    "inspect",
    "map a repository without requiring adopted policy",
    configure,
    handle,
    explanation(
        "inspect",
        "Repository inspection",
        "Map authority, languages, tooling, risks, and adoption state before acting.",
        ("entering an unfamiliar checkout", "preflighting security/privacy before publication"),
        ("running inferred project commands",),
        prerequisites=("a readable target directory",),
        evidence=("bounded passive facts or explicit active-layer records",),
        limitations=("passive findings are observations, not adopted policy",),
        next_commands=(
            "engineering suggest-manifest --json",
            'engineering start --intent "..." --paths ...',
        ),
        references=("SKILL.md", "docs/CONTRACT.md"),
    ),
)
