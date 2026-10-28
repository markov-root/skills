# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=10",
# ]
# ///
"""`visuals bump` — re-render a visual at an explicitly chosen version level.

A thin registered command adapter (registry.py), deliberately separate from
`render`'s adapter — two registered handlers must not import each other — yet
sharing every capability through the render domain (render.py, store.py).
Criterion 7: the level (patch|minor|major) is chosen, but the version STRING
is always derived from the existing version directories — never hand-supplied,
never written in a second place (audit F5).

Runs under the `uv` backend for the same reason `render` does (Pillow for
previews): PEP 723 header plus adjacent `bump_cmd.py.lock`.

Exit codes match `render`: 0 rendered, 1 blocking failure, 2 usage, 3
unavailable (no browser).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals bump", add_help=False,
        description=(
            "Re-render a visual into the next version derived from the existing\n"
            "version directories, at an explicitly chosen level. The version\n"
            "string itself is never a hand-supplied value."
        ),
    )
    parser.add_argument("slug", help="the visual's directory name under visuals/")
    parser.add_argument(
        "level", choices=("patch", "minor", "major"),
        help="which version component to advance",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="render twice and compare content hashes; report non-determinism "
             "loudly in the receipt (the exit code stays 0 — ADR 0004)",
    )
    parser.add_argument(
        "--readiness-timeout", type=float, default=None, metavar="SECONDS",
        help="how long to wait for the page's readiness signal before failing "
             "loudly (default 30)",
    )
    parser.add_argument(
        "--budget-ms", type=int, default=None, metavar="MS",
        help="virtual-time budget for the fallback path on pages that do not "
             "implement the readiness signal (default 6000)",
    )
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse usage error -> the usage exit code
        return exc.code or 2

    import render  # noqa: PLC0415  (capability domain, lazy per seam contract)

    kwargs: dict = {}
    if args.readiness_timeout is not None:
        kwargs["readiness_timeout"] = args.readiness_timeout
    if args.budget_ms is not None:
        kwargs["budget_ms"] = args.budget_ms
    try:
        outcome = render.render_visual(
            slug=args.slug, start=Path.cwd(), level=args.level,
            into=None, check=args.check, **kwargs,
        )
    except render.RenderError as exc:
        print(f"visuals bump: error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, render.RenderUnavailable) else 1

    receipt = outcome.receipt
    print(f"bumped {args.slug} -> {outcome.version_dir}")
    for frame in receipt["frames"]:
        print(
            f"  {frame['name']:<32} {frame['bytes']:>9} bytes  "
            f"{frame['sha256'][:12]}  {frame['readiness']}"
        )
    print(f"receipt: {outcome.version_dir / 'receipt.json'}")
    print(f"latest -> {outcome.version}")
    for warning in outcome.warnings:
        print(f"warning: {warning}")
    if outcome.deterministic is False:
        print(
            "warning: rendered content is NON-DETERMINISTIC — see the receipt's "
            "determinism note (reported, not blocked; ADR 0004)"
        )
    if outcome.deterministic is True:
        print("determinism check: identical hashes across two renders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))