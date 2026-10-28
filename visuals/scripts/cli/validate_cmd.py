#!/usr/bin/env python3
"""`visuals validate` — contract validation over an adopted project.

Read-only. Reports the four ADR 0004 blocking conditions (exit 1 when any
fires) and the project-selected advisory findings (never affecting the exit
code), names the advisory checks that did NOT run, and reconciles the consumer
manifest in both directions. `--json` emits one versioned object with findings
keyed by location.

Exit codes: 0 ok (including any number of advisory findings), 1 blocking
condition, 2 usage, 3 unavailable (not an adopted project, or an invalid or
unreadable project config).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config as config_module
import validate as validate_module


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, without the
    program name or the command name — the dispatcher declares no flags for us
    (that would be a second command catalog), so we parse our own here."""
    parser = argparse.ArgumentParser(prog="visuals validate", add_help=False)
    parser.add_argument(
        "slug", nargs="?", default=None,
        help="validate one visual (by directory name) instead of the whole project",
    )
    parser.add_argument("--json", action="store_true", help="emit a versioned JSON report")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2  # usage

    try:
        config_resolved = config_module.resolve_config(Path.cwd())
    except config_module.ConfigError as exc:
        print(f"visuals validate: cannot validate: {exc}", file=sys.stderr)
        return validate_module.EXIT_UNAVAILABLE
    if config_resolved is None:
        print(
            "visuals validate: not an adopted project — no visuals.toml found "
            f"walking up from {Path.cwd()}; run `visuals init` first "
            "(validate never guesses a project)",
            file=sys.stderr,
        )
        return validate_module.EXIT_UNAVAILABLE

    try:
        report = validate_module.run_validation(config_resolved, slug=args.slug)
    except validate_module.ValidateError as exc:
        print(f"visuals validate: {exc}", file=sys.stderr)
        return validate_module.EXIT_USAGE

    if args.json:
        print(json.dumps(report.to_json_dict(), indent=2))
    else:
        print(report.human())
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover - direct invocation aid
    raise SystemExit(main(sys.argv[1:]))