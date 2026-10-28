#!/usr/bin/env python3
"""`visuals sources` — the attribution registry's command adapter (task 0008).

Subcommands:

  sources list             every declared source with its verification status
  sources verify           re-hash every declared asset and re-check the contract
  sources add <id> ...     add one entry, refusing prose provenance

A thin adapter over the `sources` capability domain, which owns every rule; this
module owns argument parsing and presentation only. Nothing here decides what a
valid registry is.

ADR 0004: source-registry findings are **advisory**. `verify` therefore reports
findings and still exits 0 — a registry defect is a provenance problem worth
seeing, not a broken artifact, and the four blocking conditions are fixed
skill-wide. `add` is the exception and it is not a gate: it exits 2 because the
caller asked to write something the contract rejects, so nothing was written.

Exit codes: 0 ok (including findings), 2 usage or a refused add, 3 unavailable
(not an adopted project, or no source registry declared).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import sources  # capability domain (same package, not a command adapter)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals sources",
        description="Inspect, verify and extend the attribution source registry.",
        add_help=False,
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        help="registry path; defaults to paths.source_registry from visuals.toml",
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="subcommand")

    p_list = sub.add_parser("list", add_help=False)
    p_list.add_argument("--json", action="store_true")

    p_verify = sub.add_parser("verify", add_help=False)
    p_verify.add_argument("--json", action="store_true")

    p_add = sub.add_parser("add", add_help=False)
    p_add.add_argument("source_id")
    p_add.add_argument("--name", required=True, help="the organisation's display name")
    p_add.add_argument("--homepage", required=True, help="https homepage")
    p_add.add_argument("--logo", required=True, help="path to the asset as rendered")
    p_add.add_argument("--logo-kind", required=True, choices=("mark", "wordmark"))
    p_add.add_argument("--logo-width", required=True, type=int)
    p_add.add_argument("--logo-height", type=int)
    p_add.add_argument("--logo-render", choices=("mask", "image"))
    p_add.add_argument(
        "--logo-source",
        required=True,
        help="the https page the asset came from — a URL, never a description",
    )
    p_add.add_argument("--retrieved", required=True, metavar="YYYY-MM-DD")
    p_add.add_argument(
        "--original-logo",
        help="the untransformed original, retained alongside the asset",
    )
    p_add.add_argument(
        "--transform", help="prose description of what was done to the original"
    )
    p_add.add_argument(
        "--force",
        action="store_true",
        help="write despite findings, or replace an existing entry",
    )
    p_add.add_argument("--json", action="store_true")

    return parser


def _resolve_registry(explicit: str | None) -> tuple[Path | None, str]:
    """(registry path, error message). An explicit --registry wins; otherwise the
    project config's paths.source_registry, resolved by walking up from cwd.

    config.py is imported lazily so this command degrades honestly rather than
    failing to load when a project has not been adopted.
    """
    if explicit:
        return Path(explicit).expanduser(), ""
    try:
        import config as config_module  # noqa: PLC0415 - lazily; 0003 owns this module
    except ImportError:  # pragma: no cover - config ships with the artifact
        return None, "project config is unavailable; to pass: pass --registry PATH"
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
            "working directory); to pass: run visuals init, or pass --registry PATH"
        )
    declared = resolved.registry_paths.get("source_registry")
    if not declared:
        return None, (
            "the project config declares no paths.source_registry; to pass: "
            "declare it in visuals.toml, or pass --registry PATH"
        )
    return Path(declared), ""


def _fail_unavailable(message: str, as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                {"command": "sources", "status": "unavailable", "error": message},
                indent=2,
            )
        )
    else:
        print(f"error: {message}", file=sys.stderr)
    return EXIT_UNAVAILABLE


def _cmd_list(args: argparse.Namespace, registry: Path) -> int:
    try:
        rows = sources.list_entries(registry)
    except sources.RegistryError as exc:
        return _fail_unavailable(str(exc), args.json)
    if args.json:
        print(
            json.dumps(
                {"command": "sources list", "registry": str(registry), "sources": rows},
                indent=2,
            )
        )
        return EXIT_OK
    if not rows:
        print(f"{registry}: no sources declared")
        return EXIT_OK
    width = max(len(row["id"]) for row in rows)
    for row in rows:
        mark = "ok " if row["ok"] else "!! "
        flag = " (transformed)" if row["transformed"] else ""
        print(
            f"  {mark}{row['id']:<{width}}  {row['retrieved']}  {row['homepage']}{flag}"
        )
        for code in row["findings"]:
            print(f"       - {code}")
    bad = sum(1 for row in rows if not row["ok"])
    print(f"\n{len(rows)} source(s), {bad} with findings")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace, registry: Path) -> int:
    findings, count = sources.verify_registry(registry)
    if args.json:
        print(
            json.dumps(
                {
                    "command": "sources verify",
                    "registry": str(registry),
                    "sources": count,
                    "findings": [
                        {"code": f.code, "location": f.location, "message": f.message}
                        for f in findings
                    ],
                    "severity": "advisory",
                },
                indent=2,
            )
        )
        return EXIT_OK
    for finding in findings:
        print(f"  [{finding.code}] {finding.location}\n      {finding.message}")
    verb = "source" if count == 1 else "sources"
    if findings:
        print(
            f"\n{count} {verb} verified, {len(findings)} finding(s) — advisory, never blocking"
        )
    else:
        print(
            f"{count} {verb} verified, every declared asset matches its recorded digest"
        )
    return EXIT_OK


def _cmd_add(args: argparse.Namespace, registry: Path) -> int:
    logo = Path(args.logo).expanduser()
    original = Path(args.original_logo).expanduser() if args.original_logo else None
    if not logo.is_file():
        print(f"error: --logo {args.logo} does not exist", file=sys.stderr)
        return EXIT_USAGE
    if original is not None and not original.is_file():
        print(
            f"error: --original-logo {args.original_logo} does not exist",
            file=sys.stderr,
        )
        return EXIT_USAGE

    entry = sources.build_entry(
        name=args.name,
        homepage=args.homepage,
        logo=logo,
        logo_kind=args.logo_kind,
        logo_width=args.logo_width,
        logo_source=args.logo_source,
        retrieved=args.retrieved,
        registry_dir=registry.parent,
        logo_height=args.logo_height,
        logo_render=args.logo_render,
        original_logo=original,
        transform=args.transform,
    )
    try:
        findings = sources.add_entry(registry, args.source_id, entry, force=args.force)
    except sources.RegistryError as exc:
        return _fail_unavailable(str(exc), args.json)

    written = args.force or not findings
    if args.json:
        print(
            json.dumps(
                {
                    "command": "sources add",
                    "registry": str(registry),
                    "id": args.source_id,
                    "written": written,
                    "findings": [
                        {"code": f.code, "location": f.location, "message": f.message}
                        for f in findings
                    ],
                },
                indent=2,
            )
        )
        return EXIT_OK if written else EXIT_USAGE
    if written:
        if findings:
            for finding in findings:
                print(f"  [{finding.code}] {finding.message}", file=sys.stderr)
            print(
                f"warning: wrote {args.source_id} despite {len(findings)} finding(s) (--force)",
                file=sys.stderr,
            )
        print(f"added {args.source_id} to {registry}")
        return EXIT_OK
    print(f"refused to add {args.source_id} — nothing was written:", file=sys.stderr)
    for finding in findings:
        print(f"  [{finding.code}] {finding.message}", file=sys.stderr)
    return EXIT_USAGE


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
            "visuals sources: error: a subcommand is required (list, verify, add)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    registry, error = _resolve_registry(args.registry)
    if registry is None:
        return _fail_unavailable(error, getattr(args, "json", False))

    if args.subcommand == "list":
        return _cmd_list(args, registry)
    if args.subcommand == "verify":
        return _cmd_verify(args, registry)
    return _cmd_add(args, registry)


if __name__ == "__main__":  # pragma: no cover - dispatched by main.py
    raise SystemExit(main(sys.argv[1:]))
