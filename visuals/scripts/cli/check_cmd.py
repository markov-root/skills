# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10"]
# ///
"""`visuals check` adapter. Exit 1 only for the clipped-content blocker;
advisory findings never change the exit code (ADR 0004)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="visuals check", add_help=False)
    parser.add_argument("slug")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 2
    import check  # noqa: PLC0415
    import config  # noqa: PLC0415
    import measure  # noqa: PLC0415
    import render  # noqa: PLC0415
    try:
        result = check.check_visual(args.slug, Path.cwd(), args.output)
    except (check.CheckError, config.ConfigError, measure.MeasureError,
            render.RenderError, OSError) as exc:
        print(f"visuals check: error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, render.RenderUnavailable) else 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        counts = result["summary"]
        print(f"check {args.slug}: {counts['blocking']} blocking, "
              f"{counts['finding']} advisory findings, "
              f"{counts['not-measurable']} not measurable")
        for entry in result["blocking"]:
            print(f"  BLOCKING: {entry['condition']} {entry['frame']} {entry['selector']} "
                  f"({entry['content']!r}): overflow={entry['measured']}; {entry['to_satisfy']}")
        for entry in result["entries"]:
            if entry["outcome"] != "pass":
                print(f"  {entry['outcome']}: {entry['gate']} "
                      f"{entry['frame']} {entry['selector']}: "
                      f"measured={entry['measured']}, threshold={entry['threshold']}; "
                      f"{entry['to_satisfy']}")
        print("Not assessed: " + ", ".join(result["not_assessed"]) + ".")
        print("Ladder: " + json.dumps(result["ladder"]))
    return 1 if result["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
