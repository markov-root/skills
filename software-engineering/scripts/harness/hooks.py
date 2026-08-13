"""Idempotent, merge-safe installation of the shipped hook scripts into harness configs.

Three harness dialects are supported, each with its own merge strategy:

* ``claude`` — structured JSON merge into ``settings.json`` ``hooks.<event>`` arrays.
* ``codex`` — marker-delimited TOML array-of-tables blocks appended to ``config.toml``.
* ``opencode`` — a dedicated managed plugin ``.ts`` file per hook.

Every strategy is idempotent (re-running is a no-op), removes only the entries this installer added
on ``--uninstall``, and never leaves a partial write: the complete replacement content is built and
validated in memory, then written once atomically. A malformed or foreign target is refused rather
than clobbered.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..resources import resource_path

HOOKS: tuple[str, ...] = ("consult", "lifecycle")
HARNESSES: tuple[str, ...] = ("claude", "codex", "opencode")

# Filenames of the shipped hook scripts; the actual path is resolved through the sole resource
# locator so this domain does not scatter its own parent-index discovery.
_SCRIPT_FILENAME = {
    "consult": "se-consult-gate.sh",
    "lifecycle": "se-lifecycle-hook.sh",
}


class HookInstallError(ValueError):
    """A target config is malformed, foreign, or otherwise unsafe to modify."""


@dataclass(frozen=True)
class UnitOutcome:
    """One (hook, target) decision produced by planning."""

    hook: str
    action: str  # create | add | already-present | remove | absent | refused
    detail: str


@dataclass
class InstallPlan:
    """A fully-resolved, still-unwritten plan for one harness invocation."""

    harness: str
    operation: str  # install | uninstall
    apply: bool
    target: Path
    units: list[UnitOutcome] = field(default_factory=list)
    # Pending writes: path -> new text content (only files that actually change).
    writes: dict[Path, str] = field(default_factory=dict)
    # Pending deletions: whole managed files removed on uninstall.
    deletes: list[Path] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.writes) or bool(self.deletes)

    def commit(self) -> list[str]:
        """Apply the pending changes atomically. Returns the paths touched."""

        touched: list[str] = []
        for path, content in self.writes.items():
            _atomic_write(path, content)
            touched.append(str(path))
        for path in self.deletes:
            path.unlink(missing_ok=True)
            touched.append(str(path))
        return touched

    def to_dict(self) -> dict[str, object]:
        return {
            "harness": self.harness,
            "operation": self.operation,
            "mode": "apply" if self.apply else "dry-run",
            "target": str(self.target),
            "changed": self.changed,
            "units": [
                {"hook": unit.hook, "action": unit.action, "detail": unit.detail}
                for unit in self.units
            ],
            "pending_writes": {str(path): content for path, content in self.writes.items()},
            "pending_deletes": [str(path) for path in self.deletes],
        }


def _script(hook: str) -> str:
    return str(resource_path("scripts", _SCRIPT_FILENAME[hook], required=False))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.se-install-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def default_target(harness: str, home: Path | None = None) -> Path:
    """The conventional config file (or plugin directory) for a harness."""

    base = home if home is not None else Path.home()
    if harness == "claude":
        return base / ".claude" / "settings.json"
    if harness == "codex":
        return base / ".codex" / "config.toml"
    if harness == "opencode":
        return base / ".config" / "opencode" / "plugins"
    raise HookInstallError(f"unknown harness: {harness}")


def plan_installation(
    harness: str,
    hooks: tuple[str, ...],
    *,
    apply: bool,
    uninstall: bool,
    target: Path | None = None,
) -> InstallPlan:
    """Resolve a merge/uninstall plan without writing unless ``apply`` is set."""

    if harness not in HARNESSES:
        raise HookInstallError(f"unknown harness: {harness}")
    unknown = tuple(hook for hook in hooks if hook not in HOOKS)
    if unknown:
        raise HookInstallError(f"unknown hooks: {list(unknown)}")
    resolved_target = target if target is not None else default_target(harness)
    plan = InstallPlan(
        harness=harness,
        operation="uninstall" if uninstall else "install",
        apply=apply,
        target=resolved_target,
    )
    planner = {
        "claude": _plan_claude,
        "codex": _plan_codex,
        "opencode": _plan_opencode,
    }[harness]
    planner(plan, hooks, uninstall=uninstall)
    if apply:
        plan.commit()
    return plan


# --------------------------------------------------------------------------- claude (JSON)

_CLAUDE_EVENTS: dict[str, tuple[tuple[str, str | None], ...]] = {
    "consult": (("PreToolUse", "Write|Edit|MultiEdit"),),
    "lifecycle": (("PostToolUse", "Write|Edit|MultiEdit"), ("Stop", None)),
}


def _claude_command(hook: str) -> str:
    return _script(hook)


def _entry_is_ours(entry: object, hook: str) -> bool:
    """A dedicated entry we authored: every inner hook command references our script."""

    if not isinstance(entry, dict):
        return False
    inner = entry.get("hooks")
    if not isinstance(inner, list) or not inner:
        return False
    needle = _SCRIPT_FILENAME[hook]
    commands = [item.get("command", "") for item in inner if isinstance(item, dict)]
    return len(commands) == len(inner) and all(needle in str(command) for command in commands)


def _plan_claude(plan: InstallPlan, hooks: tuple[str, ...], *, uninstall: bool) -> None:
    path = plan.target
    raw = None
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HookInstallError(
                f"{path} is not valid JSON; refusing to modify it: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise HookInstallError(f"{path} is not a JSON object; refusing to modify it")
    config: dict = raw if isinstance(raw, dict) else {}
    hooks_section = config.get("hooks")
    if hooks_section is not None and not isinstance(hooks_section, dict):
        raise HookInstallError(f"{path} has a non-object 'hooks' section; refusing to modify it")
    hooks_section = dict(hooks_section) if isinstance(hooks_section, dict) else {}

    changed = False
    for hook in hooks:
        for event, matcher in _CLAUDE_EVENTS[hook]:
            events = list(hooks_section.get(event, []))
            present = any(_entry_is_ours(entry, hook) for entry in events)
            if uninstall:
                if not present:
                    plan.units.append(UnitOutcome(hook, "absent", f"{event}: nothing to remove"))
                    continue
                events = [entry for entry in events if not _entry_is_ours(entry, hook)]
                changed = True
                plan.units.append(UnitOutcome(hook, "remove", f"{event}: removed managed entry"))
            else:
                if present:
                    plan.units.append(
                        UnitOutcome(hook, "already-present", f"{event}: managed entry present")
                    )
                    continue
                events.append(_claude_entry(matcher, _claude_command(hook)))
                changed = True
                plan.units.append(UnitOutcome(hook, "add", f"{event}: added managed entry"))
            if events:
                hooks_section[event] = events
            else:
                hooks_section.pop(event, None)

    if not changed:
        return
    if hooks_section:
        config["hooks"] = hooks_section
    else:
        config.pop("hooks", None)
    plan.writes[path] = json.dumps(config, indent=2) + "\n"


def _claude_entry(matcher: str | None, command: str) -> dict:
    entry: dict = {}
    if matcher is not None:
        entry["matcher"] = matcher
    entry["hooks"] = [{"type": "command", "command": command, "timeout": 10}]
    return entry


# --------------------------------------------------------------------------- codex (TOML)


def _codex_markers(hook: str) -> tuple[str, str]:
    start = (
        f"# >>> software-engineering install-hooks: {hook} (managed) — do not edit inside markers"
    )
    end = f"# <<< software-engineering install-hooks: {hook} (managed)"
    return start, end


def _codex_block(hook: str) -> str:
    start, end = _codex_markers(hook)
    if hook == "consult":
        command = json.dumps(f"{_script('consult')} --json")
        status = json.dumps("software-engineering gate")
        event = "PreToolUse"
    else:
        command = json.dumps(f"{_script('lifecycle')} codex")
        status = json.dumps("engineering lifecycle reminder")
        event = "PostToolUse"
    matcher = json.dumps("^(Edit|Write|apply_patch)$")
    return (
        f"{start}\n"
        f"[[hooks.{event}]]\n"
        f"matcher = {matcher}\n\n"
        f"[[hooks.{event}.hooks]]\n"
        f'type = "command"\n'
        f"command = {command}\n"
        f"timeout = 10\n"
        f"statusMessage = {status}\n"
        f"{end}\n"
    )


def _strip_codex_block(text: str, hook: str) -> tuple[str, bool]:
    start, end = _codex_markers(hook)
    lines = text.splitlines()
    if start not in lines or end not in lines:
        return text, False
    begin = lines.index(start)
    finish = lines.index(end, begin)
    remaining = lines[:begin] + lines[finish + 1 :]
    # Drop a single blank separator left behind, if any.
    if begin < len(remaining) and remaining[begin].strip() == "":
        del remaining[begin]
    rebuilt = "\n".join(remaining)
    if rebuilt and not rebuilt.endswith("\n"):
        rebuilt += "\n"
    return rebuilt, True


def _plan_codex(plan: InstallPlan, hooks: tuple[str, ...], *, uninstall: bool) -> None:
    path = plan.target
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if text.strip():
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise HookInstallError(
                f"{path} is not valid TOML; refusing to modify it: {exc}"
            ) from exc

    new_text = text
    changed = False
    for hook in hooks:
        start, _ = _codex_markers(hook)
        present = start in new_text.splitlines()
        if uninstall:
            if not present:
                plan.units.append(UnitOutcome(hook, "absent", "no managed block to remove"))
                continue
            new_text, _ = _strip_codex_block(new_text, hook)
            changed = True
            plan.units.append(UnitOutcome(hook, "remove", "removed managed TOML block"))
        else:
            if present:
                plan.units.append(
                    UnitOutcome(hook, "already-present", "managed TOML block present")
                )
                continue
            block = _codex_block(hook)
            separator = (
                ""
                if not new_text or new_text.endswith("\n\n")
                else ("\n" if new_text.endswith("\n") else "\n\n")
            )
            new_text = f"{new_text}{separator}{block}"
            changed = True
            plan.units.append(UnitOutcome(hook, "add", "appended managed TOML block"))

    if not changed:
        return
    if new_text.strip():
        try:
            tomllib.loads(new_text)
        except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
            raise HookInstallError(f"refusing to write invalid TOML to {path}: {exc}") from exc
    plan.writes[path] = new_text


# --------------------------------------------------------------------------- opencode (TS plugin)

_OPENCODE_FILE = {"consult": "se-consult-gate.ts", "lifecycle": "se-lifecycle.ts"}
_OPENCODE_MARKER = "// software-engineering install-hooks: managed plugin"

_CONSULT_TS = """import { Plugin } from "@opencode-ai/plugin";
export default Plugin.define({
  id: "local.se-consult-gate",
  setup: async (ctx) => {
    const consulted = new Set<string>();
    await ctx.tool.hook("execute.before", (e) => {
      if (
        e.tool === "skill" &&
        String(e.input?.name ?? "").includes("software-engineering")
      ) {
        consulted.add(e.sessionID);
        return;
      }
      const CODE =
        /\\.(py|js|mjs|cjs|ts|tsx|jsx|go|rs|c|h|cc|cpp|hpp|java|kt|rb|php|sh|sql)$/;
      const path = String(e.input?.filePath ?? e.input?.path ?? "");
      if (
        ["edit", "write", "apply_patch"].includes(e.tool) &&
        CODE.test(path) &&
        !consulted.has(e.sessionID)
      ) {
        throw new Error(
          "Consult the software-engineering skill before editing code files (non-optional; run its engineering inspect).",
        );
      }
    });
  },
});
"""

_LIFECYCLE_TS_TEMPLATE = """import { Plugin } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
const HOOK = __HOOK_PATH__;
export default Plugin.define({
  id: "local.se-lifecycle",
  setup: async (ctx) => {
    await ctx.tool.hook("execute.after", (e) => {
      const payload = JSON.stringify({
        hook_event_name: "PostToolUse",
        tool_name: e.tool,
        tool_input: {
          file_path: String(e.input?.filePath ?? e.input?.path ?? ""),
        },
        session_id: e.sessionID,
        cwd: process.cwd(),
      });
      // Fire-and-forget; a hook failure must never interrupt the session.
      const child = execFile("bash", [HOOK], () => {});
      child.stdin?.end(payload);
    });
  },
});
"""


def _opencode_content(hook: str) -> str:
    header = f"{_OPENCODE_MARKER} ({hook}) — remove via engineering install-hooks --uninstall\n"
    if hook == "consult":
        body = _CONSULT_TS
    else:
        body = _LIFECYCLE_TS_TEMPLATE.replace("__HOOK_PATH__", json.dumps(_script("lifecycle")))
    return header + body


def _plan_opencode(plan: InstallPlan, hooks: tuple[str, ...], *, uninstall: bool) -> None:
    plugins_dir = plan.target
    for hook in hooks:
        path = plugins_dir / _OPENCODE_FILE[hook]
        exists = path.exists()
        managed = exists and _OPENCODE_MARKER in path.read_text(encoding="utf-8")
        if exists and not managed:
            raise HookInstallError(
                f"{path} exists but was not created by this installer; refusing to overwrite it"
            )
        if uninstall:
            if not exists:
                plan.units.append(UnitOutcome(hook, "absent", f"{path.name}: nothing to remove"))
                continue
            plan.units.append(UnitOutcome(hook, "remove", f"{path.name}: removing managed plugin"))
            plan.deletes.append(path)
            continue
        content = _opencode_content(hook)
        if managed and path.read_text(encoding="utf-8") == content:
            plan.units.append(UnitOutcome(hook, "already-present", f"{path.name}: up to date"))
            continue
        action = "add" if managed else "create"
        plan.units.append(UnitOutcome(hook, action, f"{path.name}: writing managed plugin"))
        plan.writes[path] = content
