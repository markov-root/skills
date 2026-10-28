#!/usr/bin/env python3
"""`visuals index` — derive the portfolio status view over an adopted project.

Read-only. One row per visual: current version, frame count, staleness
(content-based, mtime never consulted), blocking and advisory finding counts
(from validate's own severity implementation), and whether a consumer
manifest entry references it — with the consumer join reported in both
directions (audit F6) in the same output. Anomalies are rows with their cause
named, never omissions, and never exit codes: this is a status view, not a
gate; the four ADR 0004 blocking conditions belong to `validate`, and an
index exit code would be a fifth gate by the back door.

The index ranks, scores, and grades NOTHING (ADR 0004: no command ranks
designs). It derives, from the store on disk, the state that the corpus
maintains by hand in VISUALS-BRIEF.md's status column and HANDOFF.md's prose
(audit F5, F6) — replacing that hand-maintenance is the point.

`--json` emits one versioned object; the human table is rendered from the
same data.

Exit codes: 0 ok (a completed run, regardless of anomalies — they are data),
2 usage, 3 unavailable (not an adopted project, or an invalid or unreadable
project config).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config as config_module
import index_build


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, without
    the program name or the command name — the dispatcher declares no flags
    for us (that would be a second command catalog), so we parse our own."""
    parser = argparse.ArgumentParser(prog="visuals index", add_help=False)
    parser.add_argument("--json", action="store_true", help="emit a versioned JSON report")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2  # usage

    try:
        config_resolved = config_module.resolve_config(Path.cwd())
    except config_module.ConfigError as exc:
        print(f"visuals index: cannot index: {exc}", file=sys.stderr)
        return index_build.EXIT_UNAVAILABLE
    if config_resolved is None:
        print(
            "visuals index: not an adopted project — no visuals.toml found "
            f"walking up from {Path.cwd()}; run `visuals init` first "
            "(index never guesses a project)",
            file=sys.stderr,
        )
        return index_build.EXIT_UNAVAILABLE

    report = index_build.build_index(config_resolved)

    if args.json:
        print(json.dumps(report.to_json_dict(), indent=2))
    else:
        print(report.human())
    return index_build.EXIT_OK


if __name__ == "__main__":  # pragma: no cover - direct invocation aid
    raise SystemExit(main(sys.argv[1:]))