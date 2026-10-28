"""`visuals measure` command adapter; measurement belongs to measure.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="visuals measure", add_help=False)
    parser.add_argument("slug")
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 2
    import measure  # noqa: PLC0415
    import render  # noqa: PLC0415
    try:
        report = measure.measure_visual(slug=args.slug, start=Path.cwd(),
                                        max_bytes=args.max_bytes)
    except (measure.MeasureError, render.RenderError) as exc:
        print(f"visuals measure: error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, render.RenderUnavailable) else 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
