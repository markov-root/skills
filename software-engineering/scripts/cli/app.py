"""Process entry, registry dispatch, and top-level exception translation."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

from ..commands.contracts import (
    EXIT_BASELINE_INCOMPATIBLE,
    EXIT_INVALID_POLICY,
    EXIT_OK,
    EXIT_UNAVAILABLE,
    INCOMPATIBLE_ERRORS,
    INVALID_ERRORS,
    CommandResult,
)
from .parser import build_parser
from .rendering import emit
from .result import envelope


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_OK
    spec = args._command_spec
    try:
        result = spec.handle(args)
    except INCOMPATIBLE_ERRORS as exc:
        result = CommandResult(
            "incompatible",
            None,
            {
                "errors": [str(exc)],
                "next_commands": [f"engineering explain command.{spec.name}"],
            },
            EXIT_BASELINE_INCOMPATIBLE,
        )
    except INVALID_ERRORS as exc:
        result = CommandResult(
            "invalid",
            None,
            {
                "errors": [str(exc)],
                "next_commands": [f"engineering explain command.{spec.name}"],
            },
            EXIT_INVALID_POLICY,
        )
    except (RuntimeError, subprocess.SubprocessError) as exc:
        result = CommandResult(
            "unavailable",
            None,
            {
                "errors": [str(exc)],
                "next_commands": [f"engineering explain command.{spec.name}"],
            },
            EXIT_UNAVAILABLE,
        )
    payload = envelope(spec.name, result)
    emit(payload, json_output=args.json, human=result.human)
    return result.exit_code
