"""The console contract (ADR 0005): one registry, one envelope, frozen exit codes, declared effects.

`run(argv) -> Result` performs no terminal I/O; `main()` renders the Result and exits.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable

from . import __version__

ENVELOPE = "present.command-result"
ENVELOPE_VERSION = 1


class Exit(IntEnum):
    OK = 0
    ERROR = 1
    USAGE = 2
    NOT_IMPLEMENTED = 3


@dataclass(frozen=True)
class Effects:
    reads: bool = True
    writes: bool = False
    network: bool = False
    spend: bool = False
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"reads": self.reads, "writes": self.writes, "network": self.network,
                "spend": self.spend, "description": self.description}


@dataclass
class Result:
    command: str
    status: str = "ok"  # ok | error | usage | not_implemented
    exit: Exit = Exit.OK
    data: dict[str, Any] = field(default_factory=dict)
    text: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    effect: Effects = field(default_factory=Effects)
    stability: str = "experimental"

    def error(self, code: str, message: str, *, repairable: bool = False, next: str | None = None) -> "Result":
        self.errors.append({"code": code, "message": message, "repairable": repairable, "next": next})
        self.status, self.exit = "error", Exit.ERROR
        return self

    def warn(self, code: str, message: str, *, repairable: bool = True, next: str | None = None) -> None:
        self.warnings.append({"code": code, "message": message, "repairable": repairable, "next": next})

    def envelope(self) -> dict[str, Any]:
        return {"envelope": ENVELOPE, "version": ENVELOPE_VERSION, "present": __version__,
                "command": self.command, "status": self.status, "exit_code": int(self.exit),
                "exit_class": self.exit.name, "stability": self.stability, "data": self.data,
                "warnings": self.warnings, "errors": self.errors, "effect": self.effect.as_dict()}


Handler = Callable[[argparse.Namespace, Result], Result]


@dataclass(frozen=True)
class Leaf:
    path: tuple[str, ...]  # ("deck", "build") or ("doctor",)
    summary: str
    effects: Effects
    task: str  # the dev task that implements it, shown while unimplemented
    handler: Handler | None = None
    configure: Callable[[argparse.ArgumentParser], None] | None = None

    @property
    def name(self) -> str:
        return ".".join(self.path)


REGISTRY: list[Leaf] = []


def leaf(*path: str, summary: str, effects: Effects, task: str,
         configure: Callable[[argparse.ArgumentParser], None] | None = None):
    def register(fn: Handler | None) -> Handler | None:
        REGISTRY.append(Leaf(path, summary, effects, task, fn, configure))
        return fn
    return register


def declare(*path: str, summary: str, effects: Effects, task: str) -> None:
    """Declare a leaf that is not built yet: it is visible, explains itself, and exits 3."""
    REGISTRY.append(Leaf(path, summary, effects, task, None, None))


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # route usage errors into the envelope
        raise _UsageError(message)


class _UsageError(Exception):
    pass


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("-j", "--json", action="store_true", default=argparse.SUPPRESS,
                   help="emit the present.command-result JSON envelope")


def build_parser() -> _Parser:
    from . import commands  # noqa: F401 — registers every leaf

    root = _Parser(prog="present", description="Presentation standard CLI. Every command declares "
                   "its effects; `present explain` shows the full surface.")
    _add_json(root)
    root.add_argument("--version", action="version", version=f"present {__version__}")
    subs = root.add_subparsers(dest="_noun", metavar="<command>", parser_class=_Parser)
    groups: dict[str, Any] = {}
    for lf in REGISTRY:
        if len(lf.path) == 1:
            p = subs.add_parser(lf.path[0], help=lf.summary, description=_leaf_help(lf))
        else:
            noun, verb = lf.path
            if noun not in groups:
                g = subs.add_parser(noun, help=f"{noun} commands", description=_noun_help(noun))
                _add_json(g)
                groups[noun] = g.add_subparsers(dest="_verb", metavar="<verb>", parser_class=_Parser)
            p = groups[noun].add_parser(verb, help=lf.summary, description=_leaf_help(lf))
        _add_json(p)
        p.set_defaults(_leaf=lf)
        if lf.configure:
            lf.configure(p)
        elif lf.handler is None:  # declared leaves accept anything, then explain themselves (exit 3)
            p.add_argument("_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return root


def _effects_text(e: Effects) -> str:
    parts = ["reads" if e.reads else None, "writes" if e.writes else None,
             "network" if e.network else None, "spends money" if e.spend else None]
    head = ", ".join(x for x in parts if x) or "no effects"
    return f"Effects: {head}." + (f" {e.description}" if e.description else "")


def _leaf_help(lf: Leaf) -> str:
    built = "implemented" if lf.handler else f"declared, not implemented yet (task {lf.task}; exits 3)"
    return f"{lf.summary}\n\n{_effects_text(lf.effects)} Status: {built}."


def _noun_help(noun: str) -> str:
    verbs = [lf for lf in REGISTRY if len(lf.path) == 2 and lf.path[0] == noun]
    lines = [f"  {lf.path[1]:<10} {lf.summary}{'' if lf.handler else '  [not implemented]'}" for lf in verbs]
    return f"{noun} commands:\n" + "\n".join(lines)


def run(argv: list[str]) -> Result:
    """Parse and execute; never prints and never exits."""
    try:
        parser = build_parser()
        ns = parser.parse_args(argv)
    except _UsageError as exc:
        res = Result(command="usage", status="usage", exit=Exit.USAGE)
        res.errors.append({"code": "usage", "message": str(exc), "repairable": True,
                           "next": "present --help"})
        res.text.append(f"present: {exc}\nTry 'present --help' or 'present explain'.")
        return res
    lf: Leaf | None = getattr(ns, "_leaf", None)
    if lf is None:
        res = Result(command="help")
        res.text.append(parser.format_help())
        res.data = {"commands": [x.name for x in REGISTRY]}
        return res
    res = Result(command=lf.name, effect=lf.effects)
    if lf.handler is None:
        res.status, res.exit = "not_implemented", Exit.NOT_IMPLEMENTED
        res.errors.append({"code": "not_implemented", "message": f"`present {' '.join(lf.path)}` is "
                           f"declared but not implemented yet (task {lf.task}).", "repairable": False,
                           "next": f"present explain {' '.join(lf.path)}"})
        res.text.append(f"present {' '.join(lf.path)}: declared but not implemented yet (task {lf.task}).\n"
                        f"{_effects_text(lf.effects)}")
        return res
    try:
        return lf.handler(ns, res)
    except Exception as exc:  # an unexpected failure is still an envelope, never a traceback dump
        return res.error("internal_error", f"{type(exc).__name__}: {exc}", repairable=False)


def _wants_json(argv: list[str]) -> bool:
    return "-j" in argv or "--json" in argv


def _record_leaf(res: Result, started: float) -> None:
    """Record the resolved leaf name and exit class for skill-feedback (task 0021). Fail-open."""
    try:
        from . import feedback

        feedback.record_leaf(res.command, res.exit.name, int((time.monotonic() - started) * 1000))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    started = time.monotonic()
    res = run(argv)
    if _wants_json(argv):
        sys.stdout.write(json.dumps(res.envelope(), sort_keys=True, ensure_ascii=False) + "\n")
    else:
        out = sys.stdout if res.exit in (Exit.OK,) else sys.stderr
        for line in res.text:
            out.write(line.rstrip("\n") + "\n")
        for w in res.warnings:
            out.write(f"warning [{w['code']}]: {w['message']}" + (f" → {w['next']}" if w.get("next") else "") + "\n")
        for e in res.errors:
            if e["code"] not in ("not_implemented", "usage"):
                sys.stderr.write(f"error [{e['code']}]: {e['message']}" + (f" → {e['next']}" if e.get("next") else "") + "\n")
    sys.stdout.flush()
    sys.stderr.flush()
    _record_leaf(res, started)  # after the output, so the caller never waits on telemetry to read it
    return int(res.exit)
