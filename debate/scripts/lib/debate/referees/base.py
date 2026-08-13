"""The referee seam (ADR-0012; task-0013) — the `Finding` type + the `Checker` signature.

A referee is a pure, deterministic function over the current field that returns `Finding`s — FACTS,
never verdicts (ADR-0011 §referees). Each finding takes a DISPOSITION lane:

- `inject`      — rendered into the next round's prompt as one opaque FLAGS block (the default);
- `gate`        — a fail-closed check at the end (e.g. `arbitrator_invention`);
- `normalize`   — silently repaired, not shown to the panel;
- `out_of_loop` — recorded for audit only.

task-0013 designs the full flag taxonomy and writes the concrete checkers; this only fixes the shape
so the engine and the checkers agree on it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field

_DISPOSITIONS = ("inject", "gate", "normalize", "out_of_loop")
_SEVERITIES = ("info", "low", "medium", "high")


@dataclass
class Finding:
    """One deterministic referee fact about the field."""

    check: str  # the checker that produced it (e.g. "near_duplicate")
    target: str  # what it is about (an option id, a quote, a pair, …)
    fact: str  # the human/model-legible statement of the fact
    severity: str = "info"  # info | low | medium | high
    disposition: str = "inject"  # inject | gate | normalize | out_of_loop
    data: dict = field(default_factory=dict)  # structured payload for downstream use

    def __post_init__(self) -> None:
        if self.disposition not in _DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of {_DISPOSITIONS}, got {self.disposition!r}"
            )
        if self.severity not in _SEVERITIES:
            raise ValueError(f"severity must be one of {_SEVERITIES}, got {self.severity!r}")

    def to_dict(self) -> dict:
        return asdict(self)


# A Checker inspects the current field (a {label|id: set} mapping) and returns findings. Pure and
# deterministic — NO model call (that is the whole point: offload what code can compute).
Checker = Callable[[dict], list[Finding]]


def referee_report(findings: list[Finding]) -> str:
    """Render the INJECT-disposition findings as one opaque FLAGS block for the next round's
    prompt — FACTS the model shouldn't waste reasoning re-deriving, never verdicts (ADR-0011).
    Findings on the gate/normalize/out_of_loop lanes are recorded but NOT injected. Empty → ''."""
    inject = [f for f in findings if f.disposition == "inject"]
    if not inject:
        return ""
    lines = "\n".join(f"- [{f.check}] {f.target}: {f.fact}" for f in inject)
    return "REFEREE FLAGS (deterministic checks — address these, do not re-derive them):\n" + lines
