#!/usr/bin/env python3
"""`visuals data` — dataset provenance command adapter (task 0008).

Subcommands:

  data snapshot <slug> --input PATH ... --source-page URL --description TEXT
                       --limitation TEXT [--limitation TEXT ...]

A thin adapter over the `snapshot` capability domain, which owns every rule.
This module owns argument parsing and presentation only.

`--limitation` is required and repeatable, and there is deliberately no flag
that waives it (task 0008 criterion 5). A dataset whose limitations are unstated
does not snapshot: the reference corpus records limitations in 7 of 25 visuals
(audit F9), and making the best-practised case mandatory is the point.

Exit codes: 0 snapshotted (including when an upstream digest changed — the
change is REPORTED, which is the contract, not a failure of the command),
2 usage or a contract violation that wrote nothing, 3 unavailable (not an
adopted project).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import snapshot  # capability domain (same package, not a command adapter)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3

#: Where a visual keeps its data, matching the reference corpus's own layout
#: (`<visual>/source/data/`). Overridable per invocation with --data-dir.
DEFAULT_DATA_SUBDIR = ("source", "data")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals data",
        description="Record dataset provenance for a visual.",
        add_help=False,
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="subcommand")

    p_snap = sub.add_parser("snapshot", add_help=False)
    p_snap.add_argument(
        "slug", help="the visual whose data directory receives the snapshot"
    )
    p_snap.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="PATH",
        required=True,
        help="a file to snapshot; repeatable. Already retrieved — this does not fetch",
    )
    p_snap.add_argument(
        "--source-page",
        required=True,
        help="the https page identifying where this data came from",
    )
    p_snap.add_argument(
        "--data-url", help="the direct https URL of the payload, when there is one"
    )
    p_snap.add_argument(
        "--description",
        required=True,
        help="what this dataset measures, in the publisher's terms",
    )
    p_snap.add_argument(
        "--limitation",
        action="append",
        default=[],
        metavar="TEXT",
        help="what this data cannot support; REQUIRED and repeatable",
    )
    p_snap.add_argument(
        "--transform", help="what was done to the upstream payload, if anything"
    )
    p_snap.add_argument(
        "--retrieved-at",
        metavar="TIMESTAMP",
        help="when the input was obtained upstream, if earlier than now (ISO-8601)",
    )
    p_snap.add_argument(
        "--data-dir",
        metavar="PATH",
        help="override the destination; defaults to <visual>/source/data",
    )
    p_snap.add_argument("--json", action="store_true")

    return parser


def _resolve_data_dir(args: argparse.Namespace) -> tuple[Path | None, str]:
    """(destination, error). --data-dir wins; otherwise the adopted project's
    root joined with the slug and the corpus's own data layout."""
    if args.data_dir:
        return Path(args.data_dir).expanduser(), ""
    try:
        import config as config_module  # noqa: PLC0415 - lazily; 0003 owns this module
    except ImportError:  # pragma: no cover - config ships with the artifact
        return None, "project config is unavailable; to pass: pass --data-dir PATH"
    try:
        resolved = config_module.resolve_config(Path.cwd())
    except Exception as exc:  # noqa: BLE001 - any config failure degrades the same way
        return (
            None,
            f"project config could not be resolved ({exc}); to pass: run visuals init",
        )
    if resolved is None:
        return None, (
            "not an adopted project (no visuals.toml found walking up from the "
            "working directory); to pass: run visuals init, or pass --data-dir PATH"
        )
    visual_dir = resolved.root / args.slug
    if not visual_dir.is_dir():
        return None, (
            f"no visual {args.slug!r} under {resolved.root}; to pass: create it "
            "with visuals new, or pass --data-dir PATH"
        )
    return visual_dir.joinpath(*DEFAULT_DATA_SUBDIR), ""


def _report(result: snapshot.SnapshotResult, as_json: bool) -> int:
    changes = [
        {"name": change.name, "previous": change.previous, "current": change.current}
        for change in result.changes
    ]
    if as_json:
        print(
            json.dumps(
                {
                    "command": "data snapshot",
                    "data_dir": str(result.data_dir),
                    "provenance": str(result.provenance_path),
                    "inputs": list(result.inputs),
                    "first_snapshot": result.first_snapshot,
                    "digest_changes": changes,
                },
                indent=2,
            )
        )
        return EXIT_OK

    print(f"snapshotted {len(result.inputs)} input(s) into {result.data_dir}")
    for name in result.inputs:
        print(f"  {name}")
    print(f"provenance: {result.provenance_path}")
    if result.changes:
        # Criterion 7: prominent, and on stderr so a pipeline sees it even when
        # stdout is being captured.
        print(file=sys.stderr)
        print(
            f"UPSTREAM DATA CHANGED — {len(result.changes)} input(s) differ from the "
            "previous snapshot:",
            file=sys.stderr,
        )
        for change in result.changes:
            print(
                f"  {change.name}\n    was {change.previous}\n    now {change.current}",
                file=sys.stderr,
            )
        print(
            "A dataset that moved underneath a published graphic is a finding about "
            "that graphic: re-check the claims it supports, and re-render if they moved.",
            file=sys.stderr,
        )
    return EXIT_OK


def main(argv: list[str]) -> int:
    """Handler entry point. `argv` is this command's own arguments, with no
    program name and no command name (the dispatcher's handler contract)."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_USAGE
    if not args.subcommand:
        parser.print_usage(sys.stderr)
        print(
            "visuals data: error: a subcommand is required (snapshot)", file=sys.stderr
        )
        return EXIT_USAGE

    data_dir, error = _resolve_data_dir(args)
    if data_dir is None:
        if args.json:
            print(
                json.dumps(
                    {
                        "command": "data snapshot",
                        "status": "unavailable",
                        "error": error,
                    },
                    indent=2,
                )
            )
        else:
            print(f"error: {error}", file=sys.stderr)
        return EXIT_UNAVAILABLE

    try:
        result = snapshot.snapshot(
            data_dir=data_dir,
            input_paths=[Path(item).expanduser() for item in args.input],
            source_page=args.source_page,
            description=args.description,
            limitations=args.limitation,
            data_url=args.data_url,
            transform=args.transform,
            retrieved_at=args.retrieved_at,
        )
    except snapshot.SnapshotError as exc:
        if args.json:
            print(
                json.dumps(
                    {"command": "data snapshot", "written": False, "error": str(exc)},
                    indent=2,
                )
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    return _report(result, args.json)


if __name__ == "__main__":  # pragma: no cover - dispatched by main.py
    raise SystemExit(main(sys.argv[1:]))
