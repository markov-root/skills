"""Deterministic parser composition from the static command registry."""

from __future__ import annotations

import argparse

from .registry import COMMAND_SPECS, select_explanations
from .rendering import render_explanations


def _release_version() -> str:
    # Lazy to keep importing the parser independent from the executable entry point.
    from ..engineering import _skill_version

    return _skill_version()


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit one versioned JSON object")
    parser.add_argument(
        "--project-root",
        default=".",
        metavar="PATH",
        help="path within the target project",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="engineering",
        description="Deterministic software-engineering policy enforcement.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_release_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for spec in COMMAND_SPECS:
        command = subparsers.add_parser(spec.name, help=spec.help)
        spec.configure(command)
        _common(command)
        if spec.name == "document":
            command.add_argument(
                "--project",
                metavar="ID",
                help="select one manifest-v2 document project",
            )
            # Task 0106: the document default is None (explicit) so the manifestless
            # --docs-root mode can prove an explicit --project-root; omitted roots are
            # normalized back to "." inside document.handle for every verb.
            command.set_defaults(project_root=None)
        command.set_defaults(
            _command_spec=spec,
            _explanation_selector=select_explanations,
            _explanation_renderer=render_explanations,
        )
    return parser
