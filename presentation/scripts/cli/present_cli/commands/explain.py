"""`present explain [noun [verb]]` — the self-describing command surface."""
from __future__ import annotations

from ..console import REGISTRY, Effects, Result, leaf


def _describe(lf) -> dict:
    return {"command": " ".join(lf.path), "summary": lf.summary, "implemented": lf.handler is not None,
            "task": lf.task, "effects": lf.effects.as_dict()}


def _configure(p):
    p.add_argument("target", nargs="*", help="a command, e.g. `deck build`; omit for the whole surface")


@leaf("explain", summary="describe commands: purpose, effects, implementation state",
      effects=Effects(description="Reads only the command registry."), task="0003", configure=_configure)
def explain(ns, res: Result) -> Result:
    target = tuple(ns.target)
    matches = [lf for lf in REGISTRY if lf.path[: len(target)] == target] if target else list(REGISTRY)
    if not matches:
        return res.error("unknown_command", f"no command matches `{' '.join(target)}`", repairable=True,
                         next="present explain")
    res.data = {"commands": [_describe(lf) for lf in matches]}
    for lf in matches:
        state = "built" if lf.handler else f"not built (task {lf.task})"
        e = lf.effects
        fx = ",".join(k for k in ("reads", "writes", "network", "spend") if getattr(e, k)) or "none"
        res.text.append(f"present {' '.join(lf.path):<20} {lf.summary}  [{state}; effects: {fx}]")
    return res
