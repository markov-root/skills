"""Command adapter for advisory cold-reader probes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="visuals probe", add_help=False)
    parser.add_argument("slug")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="dispatch fresh agents and spend Codex quota",
    )
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 2

    import config
    import probe

    try:
        resolved = config.resolve_config(Path.cwd())
    except config.ConfigError as exc:
        print(
            f"visuals probe: unavailable: invalid project config: {exc}",
            file=sys.stderr,
        )
        return 3
    if resolved is None:
        print(
            "visuals probe: unavailable: no adopted project (visuals.toml)",
            file=sys.stderr,
        )
        return 3
    try:
        visual_dir = probe.resolve_visual(resolved.root, args.slug)
        report = probe.run(visual_dir, execute=args.execute)
    except probe.ProbeUnavailable as exc:
        print(f"visuals probe: unavailable: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(
            f"probe {args.slug} ({report['version']}): {report['mode']}; cost: {report['cost']}"
        )
        print(f"intended claim: {report['claim']}")
        for frame in report["frames"]:
            print(f"  {frame['frame']}: {frame['preview']}")
            if args.execute:
                print(f"    cold reader: {frame['cold'].get('claim', frame['cold'])}")
                print(f"    comparison: {frame['comparison']}")
        for check in report["persisted"]:
            print(
                f"  persisted {check['frame']}/{check['id']}: {check['state']} — {check['reason']}"
            )
        if not args.execute:
            print(
                "dry-run only: no agent dispatched, no quota spent, nothing written; "
                "use --execute to run"
            )
    return 0  # findings, including failed comprehension, never block
