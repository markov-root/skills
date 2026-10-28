#!/usr/bin/env python3
"""`visuals theme` — inspect and validate theme token files.

Subcommands:

  theme list              every theme visible to the four resolution steps
  theme show <name>       every resolved token WITH the step that supplied it
                          (criterion 1); --json for the receipt, --css for the
                          derived CSS custom-property block, --palette for the
                          derived machine-readable palette
  theme check [<name>]    palette validation: adjacent-pair perceptual
                          distance (CIEDE2000) and WCAG contrast for every
                          declared foreground/background pair. Findings are
                          ADVISORY and this command never blocks (ADR 0004):
                          pass/fail is reported per pair, and the exit code is
                          0 even when findings fail. Without a name, the
                          project config's theme reference is used.

Exit codes: 0 ok (including advisory findings), 2 usage (bad arguments, or a
theme that exists but is schema-invalid), 3 unavailable (the named theme is
found in none of the four ADR 0005 locations). Reading the user registry
(`~/.config/visuals/themes/`) is read-only; no command here writes it.
"""

from __future__ import annotations

import argparse
import json
import sys

import theme  # capability domain (same package, not a command handler)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals theme", description="Inspect and validate theme tokens.",
        add_help=False,
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="subcommand")

    p_list = sub.add_parser("list", add_help=False, help="list visible themes")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", add_help=False, help="report tokens with their resolution steps")
    p_show.add_argument("name", nargs="?", help="theme name (or a path reference from the project config)")
    fmt = p_show.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="machine-readable: tokens, steps, palette")
    fmt.add_argument("--css", action="store_true", help="derived CSS custom-property block")
    fmt.add_argument("--palette", action="store_true", help="derived machine-readable palette")

    p_check = sub.add_parser("check", add_help=False, help="validate the palette (advisory; never blocks)")
    p_check.add_argument("name", nargs="?", help="theme name; defaults to the project config's reference")
    p_check.add_argument("--json", action="store_true")

    return parser


def _resolve(name: str) -> tuple[theme.ResolvedTheme | None, int, str]:
    """(resolved_theme, exit_code, message) for a name, honoring exit codes."""
    try:
        return theme.resolve_theme(name, _current_config()), EXIT_OK, ""
    except theme.ThemeUnavailable as exc:
        return None, EXIT_UNAVAILABLE, str(exc)
    except theme.ThemeSchemaError as exc:
        return None, EXIT_USAGE, f"error: {exc}"


def _current_config():
    """The project config for the working directory, resolved lazily so this
    module never hard-depends on task 0003's config.py. Honest degradation
    (the seam contract's own pattern): while config.py is absent or the walk-up
    finds no adopted project, resolution still works by name, path, or inline
    table, and `check`/`show` without a name degrade to a usage error."""
    try:
        import config as config_module  # noqa: PLC0415 - lazily; 0003 owns this module
    except ImportError:
        return None
    return config_module.resolve_config(_cwd())


def _cwd():
    import pathlib

    return pathlib.Path.cwd()


def _print_unavailable(payload: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"command": "theme", "status": "unavailable", "error": payload}, indent=2))
    else:
        print(f"error: {payload}", file=sys.stderr)
    return EXIT_UNAVAILABLE


def _print_schema_error(payload: str, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"command": "theme", "error": payload}, indent=2))
    else:
        print(payload, file=sys.stderr)
    return EXIT_USAGE


def _cmd_list(args: argparse.Namespace) -> int:
    rows = []
    for step, path in _visible_theme_paths():
        rows.append({"name": path.stem, "step": step, "path": str(path)})
    if getattr(args, "json", False):
        print(json.dumps({"command": "theme list", "themes": rows}, indent=2))
        return EXIT_OK
    if not rows:
        print("no themes found (bundled default: neutral)")
        return EXIT_OK
    width = max(len(r["name"]) for r in rows)
    for row in sorted(rows, key=lambda r: (r["step"], r["name"])):
        print(f"  {row['name']:<{width}}  [{row['step']}]  {row['path']}")
    return EXIT_OK


def _visible_theme_paths():
    """(step, path) for every theme file visible to resolution, in step order."""
    import pathlib

    cwd = pathlib.Path.cwd()
    found: list[tuple[str, pathlib.Path]] = []

    config = None
    try:
        config = _current_config()
    except Exception:  # noqa: BLE001 - an unresolvable config still lists themes
        config = None

    root = getattr(config, "root", None) if config is not None else None
    if root is not None:
        project_dir = pathlib.Path(root) / theme.PROJECT_THEMES_DIRNAME
        if project_dir.is_dir():
            found.extend((theme.STEP_PROJECT_DIR, p) for p in sorted(project_dir.glob(f"*{theme.THEME_SUFFIX}")))
    user_dir = theme.user_themes_dir()
    if user_dir.is_dir():
        found.extend((theme.STEP_USER_REGISTRY, p) for p in sorted(user_dir.glob(f"*{theme.THEME_SUFFIX}")))
    if theme.BUNDLED_THEMES_DIR.is_dir():
        found.extend((theme.STEP_BUNDLED, p) for p in sorted(theme.BUNDLED_THEMES_DIR.glob(f"*{theme.THEME_SUFFIX}")))
    return found


def _cmd_show(args: argparse.Namespace) -> int:
    name = args.name or ""
    resolved, code, message = _resolve(name)
    if resolved is None:
        if code == EXIT_USAGE:
            return _print_schema_error(message, getattr(args, "json", False))
        return _print_unavailable(_strip_prefix(message), getattr(args, "json", False))
    tokens = resolved.tokens
    if args.css:
        print(theme.emit_css(tokens))
        return EXIT_OK
    if args.palette:
        print(json.dumps(theme.emit_palette(tokens), indent=2))
        return EXIT_OK
    if args.json:
        print(
            json.dumps(
                {
                    "command": "theme show",
                    "name": resolved.name,
                    "steps_consulted": list(resolved.steps_consulted),
                    "tokens": tokens,
                    "resolution_steps": resolved.resolution_steps,
                    "palette": theme.emit_palette(tokens),
                    "css": theme.emit_css(tokens),
                },
                indent=2,
            )
        )
        return EXIT_OK
    steps = " -> ".join(resolved.steps_consulted)
    print(f"theme {resolved.name!r} — resolved through: {steps}")
    flat = theme.flatten_tokens(tokens)
    for key in sorted(resolved.resolution_steps):
        print(f"  {key:<52} {flat[key]!r:<24} [{resolved.resolution_steps[key]}]")
    return EXIT_OK


def _strip_prefix(message: str) -> str:
    return message.removeprefix("error: ")


def _cmd_check(args: argparse.Namespace) -> int:
    name = args.name or ""
    if not name:
        config = _current_config()
        name = getattr(config, "theme", "") or "" if config is not None else ""
        if isinstance(name, dict):
            name = ""
        if not name:
            print("error: no theme name given and the project config declares none", file=sys.stderr)
            return EXIT_USAGE
    resolved, code, message = _resolve(name)
    if resolved is None:
        if code == EXIT_USAGE:
            return _print_schema_error(message, getattr(args, "json", False))
        return _print_unavailable(_strip_prefix(message), getattr(args, "json", False))
    findings = theme.validate_tokens(resolved.tokens)
    failed = [f for f in findings if f.passed is False]
    undeclared = [f for f in findings if f.check == "distance" and f.passed is None]
    if args.json:
        print(
            json.dumps(
                {
                    "command": "theme check",
                    "name": resolved.name,
                    "findings": [
                        {
                            "check": f.check,
                            "subject": f.subject,
                            "value": round(f.value, 4),
                            "threshold": f.threshold,
                            "passed": f.passed,
                        }
                        for f in findings
                    ],
                    "failed": len(failed),
                    "blocking": False,
                },
                indent=2,
            )
        )
    else:
        print(f"theme check {resolved.name!r} — advisory findings (never blocks; ADR 0004)")
        for f in findings:
            verdict = {True: "pass", False: "FAIL", None: "report"}[f.passed]
            unit = ":1" if f.check == "contrast" else " dE00"
            threshold = f"  (min {f.threshold}{unit})" if f.threshold is not None else "  (no threshold declared)"
            print(f"  {f.check:9s} {f.subject:<40} {f.value:8.2f}{unit}{threshold}  {verdict}")
        if failed:
            print(f"summary: {len(findings) - len(failed)} pass, {len(failed)} FAIL — advisory, never blocks (ADR 0004)")
        else:
            print(f"summary: {len(findings)} pass, 0 fail")
        if undeclared:
            print("note: no distance threshold declared — distances are reported without a verdict (SOURCES.md)")
    return EXIT_OK  # findings are advisory and never affect the exit code


def main(argv: list[str]) -> int:
    """Handler entry point: argv is this command's own arguments, without the
    program name or the command name. Exit codes: 0 ok, 2 usage, 3 unavailable."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_USAGE
    if args.subcommand == "list":
        return _cmd_list(args)
    if args.subcommand == "show":
        return _cmd_show(args)
    if args.subcommand == "check":
        return _cmd_check(args)
    print("usage: visuals theme list | show <name> | check [<name>]", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":  # direct execution for manual inspection
    raise SystemExit(main(sys.argv[1:]))