#!/usr/bin/env python3
"""`visuals` CLI — parser construction, dispatch, help, and version, all derived
from the single static command registry (cli/registry.py).

Standard library only, so the dispatcher itself never needs a dependency
resolve. Commands whose handlers need dependencies are routed by the registry's
`backend` field and re-exec'd under `uv run --script` (PEP 723 header + adjacent
lock); the guard env var prevents re-exec loops.

Exit codes (architecture doc, "Command surface"): 0 ok, 2 usage, 3 unavailable.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry  # noqa: E402  (single command catalog)

REEXEC_GUARD = "VISUALS_UV_REEXEC"
CLI_DIR = Path(__file__).resolve().parent
SKILL_MD = CLI_DIR.parent.parent / "SKILL.md"


def read_version() -> str:
    """Read the version from SKILL.md metadata.version — the one place it lives."""
    try:
        text = SKILL_MD.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {SKILL_MD}: {exc}") from None
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if fm:
        lines = fm.group(1).splitlines()
        in_metadata = False
        for line in lines:
            if re.match(r"^metadata:\s*$", line):
                in_metadata = True
                continue
            if in_metadata:
                if re.match(r"^\S", line):  # left the metadata block
                    break
                vm = re.match(r'^\s+version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)', line)
                if vm:
                    return vm.group(1)
    raise SystemExit(f"error: no metadata.version found in {SKILL_MD}")


def build_parser() -> argparse.ArgumentParser:
    """Build the parser from COMMAND_SPECS — the registry is the only catalog."""
    version = read_version()
    parser = argparse.ArgumentParser(
        prog=registry.PROG,
        description=f"visuals — explanatory-graphics production envelope (v{version})",
        epilog=_command_listing(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version}",
        help="show the version read from SKILL.md at runtime and exit",
    )
    # Subparsers exist so `visuals --help` lists the commands. They declare NO
    # arguments: argv after the command name is split off before argparse ever
    # sees it (see `main`), because per-command argument knowledge in the
    # dispatcher would be a second command catalog — forbidden by the
    # architecture's dependency-direction section. The registry is the only
    # catalog; each handler owns its own flags.
    subparsers = parser.add_subparsers(metavar="command")
    for spec in registry.COMMAND_SPECS:
        subparsers.add_parser(
            spec.name,
            help=spec.summary,
            description=spec.help_text,
            usage=f"%(prog)s {spec.usage}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False,
        )
    return parser


def _command_listing() -> str:
    """Command table generated from COMMAND_SPECS (the registry's own words)."""
    rows = [f"  {spec.name:<10} {spec.summary}" for spec in registry.COMMAND_SPECS]
    return (
        "commands:\n"
        + "\n".join(rows)
        + "\n\nrun 'visuals <command> --help' for details."
    )


def _dispatch_uv(spec: registry.CommandSpec, argv: list[str]) -> None:
    """Re-exec a uv-weight command under `uv run --script` (PEP 723 + lock)."""
    if os.environ.get(REEXEC_GUARD) == "1":
        print(
            f"error: re-exec guard tripped for command '{spec.name}'", file=sys.stderr
        )
        raise SystemExit(3)
    script = CLI_DIR / registry.UV_ENTRYPOINTS[spec.name]
    if not script.is_file():
        print(f"error: uv entrypoint missing: {script}", file=sys.stderr)
        raise SystemExit(3)
    env = dict(os.environ, REEXEC_GUARD="1")
    try:
        os.execvpe("uv", ["uv", "run", "--script", str(script), *argv], env)
    except OSError:
        # `uv` absent from PATH. An absent prerequisite is exit 3 with a named
        # cause, never a traceback — the same contract `doctor` reports against.
        print(
            f"error: '{spec.name}' needs uv on PATH and it was not found — "
            "to pass: install uv (https://docs.astral.sh/uv/), or run "
            "'visuals doctor' to see every prerequisite's verdict",
            file=sys.stderr,
        )
        raise SystemExit(3) from None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    # Split the command out of argv ourselves rather than letting argparse parse
    # the tail: argparse would claim the handler's own flags as unrecognised
    # top-level arguments, and REMAINDER does not reliably capture a leading
    # `--flag`. Everything after the command name belongs to the handler.
    head = argv[0]
    if head in ("-h", "--help", "--version"):
        parser.parse_args(argv)  # argparse prints help/version and exits
        return 0
    spec = registry.COMMAND_BY_NAME.get(head)
    if spec is None:
        parser.print_usage(sys.stderr)
        print(f"{registry.PROG}: error: unknown command {head!r}", file=sys.stderr)
        print(f"commands: {', '.join(registry.COMMANDS)}", file=sys.stderr)
        return 2
    rest = argv[1:]

    # `visuals <cmd> --help` is answered from the registry, so the registry stays
    # the single source of help text even though handlers own their own flags.
    if rest and rest[0] in ("-h", "--help"):
        print(f"usage: {registry.PROG} {spec.usage}\n")
        print(spec.help_text)
        return 0

    if spec.backend == "uv":
        _dispatch_uv(spec, rest)
    handler = importlib.import_module(spec.handler)
    return handler.main(rest)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(0) from None
