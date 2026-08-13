"""Deterministic parser composition from the static command registry."""

from __future__ import annotations

import argparse

from .registry import COMMAND_SPECS, select_explanations
from .rendering import render_explanations


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
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for spec in COMMAND_SPECS:
        command = subparsers.add_parser(spec.name, help=spec.help)
        spec.configure(command)
        _common(command)
        command.set_defaults(
            _command_spec=spec,
            _explanation_selector=select_explanations,
            _explanation_renderer=render_explanations,
        )
    return parser
