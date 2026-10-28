# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10"]
# ///
"""Bounded author-led iteration: one unpublished render and probe per invocation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="visuals improve", add_help=False)
    parser.add_argument("slug")
    parser.add_argument("--execute", action="store_true",
                        help="render and send previews/questions to fresh Codex agents; spends quota")
    parser.add_argument("--new-run", action="store_true",
                        help="start another bounded run while retaining earlier evidence")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code or 2
    import improve
    try:
        report = improve.run(args.slug, Path.cwd(), execute=args.execute,
                             new_run=args.new_run)
    except improve.ImproveUnavailable as exc:
        print(f"visuals improve: unavailable: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"improve {args.slug}: {report['phase']}; iteration "
              f"{report['iteration']}/{report['max_iterations']}; cost: {report['cost']}; "
              f"estimated agent calls: {report['estimated_agent_calls']}")
        if report.get("current"):
            print(f"  unpublished version: {report['current']['version']}")
            for criterion in report["current"]["criteria"]:
                print(f"  {criterion['outcome']}: {criterion['frame'] or '-'} "
                      f"{criterion['criterion']}: {criterion['reason']}")
            if report["current"]["mechanical_check"] is not None:
                print("  mechanical check: "
                      + json.dumps(report["current"]["mechanical_check"]))
        if report["phase"] == "revise":
            print("Revise the source against the disagreements, inspect every frame, "
                  "then run improve --execute again.")
        elif report["phase"] == "agreement":
            print("Probe agreement is evidence, not approval. Inspect every frame "
                  "at full and delivery size before choosing a version to publish.")
        elif report["phase"] == "cap-reached":
            print("Iteration cap reached. Review remaining disagreements and unknowns; "
                  "choose a version explicitly. No version was published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
