# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=10",
# ]
# ///
"""`visuals render` — the authored-render command adapter.

This file is a registered command adapter (registry.py): it owns `render`'s
argv parsing and reporting only. All capability lives in the render domain
(render.py, store.py), imported lazily so a usage error never pays for it.
Previews and the contact sheet need Pillow at runtime, so this command runs
under the `uv` backend — the PEP 723 header above plus the adjacent
`render_cmd.py.lock` (from `uv lock --script`) pin that dependency; the
dispatcher re-execs this script under `uv run --script`.

Exit codes: 0 rendered, 1 blocking render failure (the message names the
cause), 2 usage, 3 the environment cannot render (no browser — Unavailable).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals render", add_help=False,
        description=(
            "Render every frame of a visual's manifest into a new immutable\n"
            "version directory: hashed receipt, previews, repointed latest."
        ),
    )
    parser.add_argument(
        "slug",
        help="the visual's directory name, discovered under the project root "
             "the same way `visuals index` and `visuals validate` walk the tree",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="render twice and compare content hashes; report non-determinism "
             "loudly in the receipt (the exit code stays 0 — ADR 0004)",
    )
    parser.add_argument(
        "--unpublished", action="store_true",
        help="keep the new immutable version for review without repointing latest",
    )
    parser.add_argument(
        "--into", metavar="VERSION",
        help="explicit target version (vX.Y.Z); by default the version is "
             "derived from existing directories, never hand-supplied",
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
            slug=args.slug, start=Path.cwd(), level="patch",
            into=args.into, check=args.check, publish=not args.unpublished, **kwargs,
        )
    except render.RenderError as exc:
        print(f"visuals render: error: {exc}", file=sys.stderr)
        return 3 if isinstance(exc, render.RenderUnavailable) else 1

    receipt = outcome.receipt
    print(f"rendered {args.slug} -> {outcome.version_dir}")
    for frame in receipt["frames"]:
        print(
            f"  {frame['name']:<32} {frame['bytes']:>9} bytes  "
            f"{frame['sha256'][:12]}  {frame['readiness']}"
        )
    print(f"receipt: {outcome.version_dir / 'receipt.json'}")
    if args.unpublished:
        print("unpublished: latest unchanged")
    else:
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
