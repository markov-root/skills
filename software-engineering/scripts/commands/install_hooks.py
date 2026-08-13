"""Adapter for the opt-in harness hook installer.

Thin adapter: it only parses arguments and renders the plan produced by the ``harness`` domain. It
never enables a hook implicitly and defaults to a dry-run so writing requires explicit ``--apply``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..harness import HARNESSES, HOOKS, plan_installation
from .contracts import CommandResult, CommandSpec, Effects, explanation

_EFFECTS = Effects(
    "reads and, only with --apply, writes the one named harness config file or plugin directory",
    "none",
    "with --apply, merges or removes only this installer's own hook entries; dry-run by default",
    "none",
)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--harness",
        required=True,
        choices=HARNESSES,
        help="harness whose runtime config should be wired",
    )
    parser.add_argument(
        "--hook",
        choices=HOOKS,
        action="append",
        metavar="NAME",
        help="hook to wire (repeatable); default wires both shipped hooks",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the change; without it the command only prints the planned diff",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove only the entries this installer added",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="override the target config file (claude/codex) or plugin directory (opencode)",
    )


def handle(args: argparse.Namespace) -> CommandResult:
    hooks = tuple(dict.fromkeys(args.hook)) if args.hook else HOOKS
    target = Path(args.config).expanduser() if args.config else None
    plan = plan_installation(
        args.harness,
        hooks,
        apply=args.apply,
        uninstall=args.uninstall,
        target=target,
    )
    data = plan.to_dict()
    return CommandResult("passed", None, data, human=_render(plan))


def _render(plan) -> str:
    verb = "Uninstall" if plan.operation == "uninstall" else "Install"
    mode = "APPLIED" if plan.apply else "dry-run (re-run with --apply to write)"
    lines = [f"{verb} hooks for {plan.harness} → {plan.target}  [{mode}]"]
    for unit in plan.units:
        lines.append(f"  - {unit.hook}: {unit.action} — {unit.detail}")
    if not plan.changed:
        lines.append("  (no changes needed)")
    return "\n".join(lines)


SPEC = CommandSpec(
    "install-hooks",
    "wire the shipped hook scripts into a harness config",
    configure,
    handle,
    explanation(
        "install-hooks",
        "Harness hook installer",
        "Idempotently merge or remove the shipped consult-gate and lifecycle hooks in a harness.",
        ("a harness should run the shipped hooks without hand-editing its config",),
        (
            "enabling hooks automatically on skill install",
            "changing hook semantics or writing outside the named harness config",
        ),
        prerequisites=("uv is available and the shipped hook scripts are present",),
        effects=_EFFECTS,
        evidence=("the planned or applied per-hook merge actions and target path",),
        limitations=(
            "installation is an explicit opt-in and never enables a hook by default",
            "it merges only its own entries and refuses a malformed or foreign target",
        ),
        next_commands=("engineering explain command.install-hooks",),
        references=("references/enforcement-hooks.md", "references/lifecycle-hooks.md"),
    ),
)
