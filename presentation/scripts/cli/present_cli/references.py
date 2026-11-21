"""Typed `research:` and `dataset:` references (task 0022; portfolio ADR 0006 decision 2).

A ledger `Source` cell, or a deck data value, may cite

- `research:<ref>[@<version>]`: a corpus record, resolved by the research-database `research` CLI;
- `dataset:<id>[@<release>][/<table>[#<row-ref>]]`: a dataset release, table or row, resolved by
  the Datasets `datasets` CLI.

Both CLIs are neighbours: they are found by an environment override, then PATH, then the skill
directories, and never by an assumed install path. Each is run read-only with `--json`; a missing
or unreachable CLI is `capability_unavailable`, never a pass (portfolio ADR 0004 D1).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# One reference ends at whitespace, a table pipe, a list separator, a closing bracket or a
# backtick; a trailing full stop belongs to the sentence, not to the reference.
_STOP = r"[^\s|,;)\]`<>\"']"
RESEARCH = re.compile(rf"(?<![\w:])research:(?P<body>{_STOP}+)")
DATASET = re.compile(
    r"(?<![\w:])dataset:(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)"
    r"(?:@(?P<release>[A-Za-z0-9_-]+))?"
    rf"(?:/(?P<table>[A-Za-z0-9_]+)(?:#(?P<row>{_STOP}+))?)?"
)
LATEST = "latest"


@dataclass(frozen=True)
class Ref:
    kind: str  # "research" | "dataset"
    raw: str  # the exact text as written
    start: int  # span of `raw` in the text it was parsed from
    end: int
    target: str  # research: the record ref; dataset: the dataset id
    version: str | None = (
        None  # research version / dataset release; None or "latest" = unpinned
    )
    table: str | None = None
    row: str | None = None

    @property
    def pinned(self) -> bool:
        return self.version not in (None, LATEST)

    def text(self, version: str | None = None) -> str:
        """The reference written out, optionally with another version."""
        v = self.version if version is None else version
        if self.kind == "research":
            return f"research:{self.target}" + (f"@{v}" if v else "")
        out = f"dataset:{self.target}" + (f"@{v}" if v else "")
        if self.table:
            out += f"/{self.table}"
            if self.row:
                out += f"#{self.row}"
        return out


def _research(m: re.Match) -> Ref:
    body = m.group("body").rstrip(".")
    target, version = body, None
    at = body.rfind("@")
    if at > 0 and re.fullmatch(r"\d+|latest", body[at + 1 :]):
        target, version = body[:at], body[at + 1 :]
    return Ref(
        "research",
        f"research:{body}",
        m.start(),
        m.start() + 9 + len(body),
        target,
        version,
    )


def _dataset(m: re.Match) -> Ref:
    row = (m.group("row") or "").rstrip(".") or None
    raw = m.group(0).rstrip(".") if m.group("row") else m.group(0)
    return Ref(
        "dataset", raw, m.start(), m.start() + len(raw), m.group("id"), m.group("release"),
        m.group("table"), row,
    )


def parse(text: str) -> list[Ref]:
    """Every typed reference in `text`, in order of appearance."""
    refs = [_research(m) for m in RESEARCH.finditer(text)]
    refs += [_dataset(m) for m in DATASET.finditer(text)]
    return sorted(refs, key=lambda r: r.start)


def parse_one(text: str) -> Ref | None:
    """`text` as exactly one reference, or None."""
    refs = parse(text.strip())
    return refs[0] if len(refs) == 1 and refs[0].raw == text.strip() else None


# --------------------------------------------------------------------------- discovery

CLIS = {
    # name: (environment override, skill folder and launcher, install hint)
    "research": (
        "PRESENT_RESEARCH_CLI",
        ("research-database", "scripts/research"),
        "npx skills add ~/Skills --full-depth --skill research-database --agent '*', "
        "or set PRESENT_RESEARCH_CLI",
    ),
    "datasets": (
        "PRESENT_DATASETS_CLI",
        None,
        "put the Datasets `datasets` CLI on PATH (its repository's installer), "
        "or set PRESENT_DATASETS_CLI",
    ),
}


def find_cli(name: str) -> Path | None:
    """A neighbour CLI: the override (empty = disabled), then PATH, then the skill directories."""
    env, skill, _ = CLIS[name]
    override = os.environ.get(env)
    if override is not None:
        p = Path(override) if override else None
        return p if p is not None and p.is_file() and os.access(p, os.X_OK) else None
    hit = shutil.which(name)
    if hit:
        return Path(hit)
    if skill is not None:
        from .commands.doctor import find_neighbour

        return find_neighbour(*skill)
    return None


def neighbour_env() -> dict[str, str]:
    """The caller's environment for a neighbour CLI, minus the virtualenv and interpreter that
    `uv run` put first on PATH for `present` itself: a neighbour's `python3` is the machine's."""
    env = dict(os.environ)
    ours_venv = env.get("VIRTUAL_ENV") == sys.prefix
    if not ours_venv and "UV_RUN_RECURSION_DEPTH" not in env:
        return env
    exe = Path(sys.executable)
    ours = {str(Path(sys.prefix) / "bin"), str(exe.parent), str(exe.resolve().parent)}
    ours -= {"/bin", "/usr/bin", "/usr/local/bin"}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if p not in ours)
    env.pop("UV_RUN_RECURSION_DEPTH", None)
    if ours_venv:
        env.pop("VIRTUAL_ENV")
    return env


def install_hint(name: str) -> str:
    return CLIS[name][2]


# --------------------------------------------------------------------------- resolution


@dataclass
class Resolution:
    status: str  # "ok" | "unresolved" | "unavailable"
    current: str | None = None  # the current version or release
    cited: str | None = None  # the version the reference names (pinned or resolved)
    newer: bool = False  # the cited version is older than the current one
    message: str = ""


@dataclass
class Resolver:
    """Resolves references through the neighbour CLIs, once per distinct reference."""

    timeout: int = 60
    unavailable: dict[str, str] = field(default_factory=dict)  # cli -> why
    _paths: dict[str, Path | None] = field(default_factory=dict)
    _cache: dict[tuple, Resolution] = field(default_factory=dict)

    def cli(self, name: str) -> Path | None:
        if name not in self._paths:
            self._paths[name] = find_cli(name)
            if self._paths[name] is None:
                self.unavailable.setdefault(name, f"`{name}` CLI not found")
        return self._paths[name]

    def call(self, name: str, *args: str) -> tuple[int, dict[str, Any] | None]:
        """(exit code, JSON envelope or None). Marks the CLI unavailable when it cannot answer."""
        path = self.cli(name)
        if path is None:
            return -1, None
        try:
            proc = subprocess.run(
                [str(path), *args, "--json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
                env=neighbour_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.unavailable.setdefault(name, f"`{name}` could not run: {exc}")
            self._paths[name] = None
            return -1, None
        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError:
            env = None
        if env is None or proc.returncode not in (0, 1, 2, 3, 8):
            tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
            self.unavailable.setdefault(
                name,
                f"`{name}` did not answer (exit {proc.returncode})"
                + (f": {tail[0][:200]}" if tail[0] else ""),
            )
            self._paths[name] = None
            return -1, None
        return proc.returncode, env

    def resolve(self, ref: Ref) -> Resolution:
        key = (ref.kind, ref.target, ref.version, ref.table, ref.row)
        if key not in self._cache:
            fn = self._research if ref.kind == "research" else self._dataset
            self._cache[key] = fn(ref)
        return self._cache[key]

    # research: `research cite <ref> [--version N]` names the current (or given) exact version.
    def _research(self, ref: Ref) -> Resolution:
        code, env = self.call("research", "cite", ref.target)
        if env is None:
            return Resolution(
                "unavailable", message=self.unavailable.get("research", "")
            )
        if code != 0:
            return Resolution(
                "unresolved", message=_diagnostic(env, f"{ref.target} did not resolve")
            )
        current = str(((env.get("data") or {}).get("result") or {}).get("version", ""))
        if not current:
            return Resolution(
                "unresolved", message=f"{ref.target}: no version in the citation"
            )
        if not ref.pinned or ref.version == current:
            return Resolution("ok", current, current)
        if int(ref.version) > int(current):
            return Resolution(
                "unresolved",
                current,
                ref.version,
                message=f"{ref.target}: version {ref.version} is newer than "
                f"the current {current}",
            )
        code, env = self.call("research", "cite", ref.target, "--version", ref.version)
        if env is None:
            return Resolution(
                "unavailable", message=self.unavailable.get("research", "")
            )
        if code != 0:
            return Resolution(
                "unresolved",
                current,
                ref.version,
                message=f"{ref.target}: version {ref.version} is not retained",
            )
        return Resolution("ok", current, ref.version, newer=True)

    # dataset: `datasets releases <id>` lists every release (newest first) with its tables;
    # a row reference is confirmed with `datasets get`.
    def releases(self, dataset: str) -> tuple[str, list[dict[str, Any]] | str]:
        code, env = self.call("datasets", "releases", dataset, "--limit", "1000")
        if env is None:
            return "unavailable", self.unavailable.get("datasets", "")
        if code not in (0, 8):
            return "unresolved", _diagnostic(env, f"dataset {dataset} did not resolve")
        items = [
            i.get("record") or {} for i in (env.get("data") or {}).get("items") or []
        ]
        return "ok", [i for i in items if i.get("release")]

    def _dataset(self, ref: Ref) -> Resolution:
        status, got = self.releases(ref.target)
        if status != "ok":
            return Resolution(status, message=str(got))
        rels: list[dict[str, Any]] = got  # type: ignore[assignment]
        current = next((r["release"] for r in rels if r.get("current")), None)
        if current is None:
            return Resolution(
                "unresolved", message=f"dataset {ref.target} has no current release"
            )
        cited = ref.version if ref.pinned else current
        rec = next((r for r in rels if r["release"] == cited), None)
        if rec is None:
            return Resolution(
                "unresolved",
                current,
                cited,
                message=f"dataset {ref.target} has no release {cited}",
            )
        if ref.table and ref.table not in (rec.get("rows") or {}):
            return Resolution(
                "unresolved",
                current,
                cited,
                message=f"dataset {ref.target}@{cited} has no table {ref.table}",
            )
        if ref.row:
            code, env = self.call("datasets", "get", row_ref(ref, cited))
            if env is None:
                return Resolution(
                    "unavailable", message=self.unavailable.get("datasets", "")
                )
            if code != 0:
                return Resolution(
                    "unresolved",
                    current,
                    cited,
                    message=_diagnostic(env, f"row {ref.row} did not resolve"),
                )
        order = [r["release"] for r in rels]
        newer = order.index(cited) > order.index(current)  # newest first
        return Resolution("ok", current, cited, newer=newer)


def row_ref(ref: Ref, release: str) -> str:
    """The Datasets row reference grammar: data:<dataset>@<release>.<table>#<key>."""
    return f"data:{ref.target}@{release}.{ref.table}#{ref.row}"


def _diagnostic(env: dict[str, Any], fallback: str) -> str:
    diags = list(env.get("diagnostics") or [])
    for item in (env.get("data") or {}).get("items") or []:
        diags += item.get("diagnostics") or []
    for d in diags:
        if d.get("code") not in ("served_by",) and d.get("message"):
            return f"{fallback}: {d['message']}"
    return fallback


# --------------------------------------------------------------------------- the claims ledger


def ledger_refs(ledger) -> list[tuple[Any, Ref]]:
    """(row, reference) for every typed reference in the ledger's Source cells."""
    return [(row, ref) for row in ledger.rows.values() for ref in parse(row.source)]


def source_concerns(ledger, resolver: Resolver) -> list[dict[str, Any]]:
    """`source_unresolved` and `source_newer_available` concerns for the ledger's references."""
    from .claims import _concern

    where_file = ledger.path.name if ledger.path else "ledger"
    out = []
    for row, ref in ledger_refs(ledger):
        r = resolver.resolve(ref)
        where = f"{where_file}:{row.line}"
        if r.status == "unresolved":
            out.append(
                _concern(
                    "source_unresolved",
                    where,
                    f"{row.id}: {ref.raw} — {r.message}",
                    claim=row.id,
                    reference=ref.raw,
                )
            )
        elif r.status == "ok" and r.newer:
            out.append(
                _concern(
                    "source_newer_available",
                    where,
                    f"{row.id}: {ref.raw} cites {r.cited}; the current is {r.current}",
                    claim=row.id,
                    reference=ref.raw,
                    cited=r.cited,
                    current=r.current,
                )
            )
    return out


def pin_changes(
    ledger, resolver: Resolver
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(changes, skipped): the exact version for every unpinned reference in the Source cells."""
    changes, skipped = [], []
    for row, ref in ledger_refs(ledger):
        if ref.pinned:
            continue
        r = resolver.resolve(ref)
        if r.status != "ok":
            skipped.append(
                {
                    "claim": row.id,
                    "line": row.line,
                    "reference": ref.raw,
                    "status": r.status,
                    "message": r.message,
                }
            )
            continue
        changes.append(
            {
                "claim": row.id,
                "line": row.line,
                "from": ref.raw,
                "to": ref.text(r.cited),
                "kind": ref.kind,
            }
        )
    return changes, skipped


def _cell_spans(line: str) -> list[tuple[int, int]]:
    """Character spans of each table cell's content in one raw Markdown table line."""
    body = line.rstrip("\r\n")
    seps = [m.start() for m in re.finditer(r"(?<!\\)\|", body)]
    spans = [(a + 1, b) for a, b in zip(seps, seps[1:])]
    tail = body.rstrip()
    if seps and (tail[-1:] != "|" or tail.endswith("\\|")):
        spans.append((seps[-1] + 1, len(body)))
    return spans


def apply_pins(text: str, changes: list[dict[str, Any]], source_col: int) -> str:
    """`text` with each change spliced into its row's Source cell; every other byte unchanged."""
    lines = text.splitlines(keepends=True)
    by_line: dict[int, list[dict[str, Any]]] = {}
    for c in changes:
        by_line.setdefault(c["line"], []).append(c)
    for n, items in by_line.items():
        line = lines[n - 1]
        spans = _cell_spans(line)
        if not 0 <= source_col < len(spans):
            continue
        a, b = spans[source_col]
        cell = line[a:b]
        for ref in sorted(parse(cell), key=lambda r: -r.start):
            hit = next((c for c in items if c["from"] == ref.raw), None)
            if hit is not None:
                cell = cell[: ref.start] + hit["to"] + cell[ref.end :]
        lines[n - 1] = line[:a] + cell + line[b:]
    return "".join(lines)


def source_column(text: str, line: int) -> int:
    """The Source column index of the claims table that holds `line` (-1 when none)."""
    from .claims import _cells, _plain

    lines = text.splitlines()
    for n in range(line - 1, -1, -1):
        heads = (
            [_plain(c).lower() for c in _cells(lines[n])]
            if lines[n].lstrip().startswith("|")
            else None
        )
        if heads is None:
            return -1
        if heads and heads[0] == "id":
            return next(
                (i for i, h in enumerate(heads) if h in ("source", "sources", "how")),
                -1,
            )
    return -1

