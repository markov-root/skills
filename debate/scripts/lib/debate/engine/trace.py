"""Research-grade trace + derived metrics (ADR-0020; task-0031). Layered over the L0 `CallRecord`.

The engine is a PASSIVE research platform: capture enough per run that the research questions become
retrospective queries, not re-runs. The layers (ADR-0020 §Decision):

- **L0 `CallRecord`** — one per model call (backends/base.py; task-0017 Phase D). Already emitted.
- **L1 `RoleOutput`** — per call, tagged with its ROLE and CAPABILITY CLASS (G/D/C, ADR-0018) plus
  the candidate slate (all candidates, not just the winner; logits where a provider exposes them —
  null otherwise). Built here as a VIEW over L0 + the plan's stage→capability map (no new model
  calls, no threading role through the chokepoint).
- **L3 `Run`** — the run-level facts (plan hash, cast pools, materials mode, seeds, and an
  optional-typed GROUND-TRUTH slot). Written by the loop as `run.json`.
- **L4 label store** — a SEPARATE append-only `labels.jsonl` keyed to a target with a `source` enum;
  a label write NEVER mutates a prediction (predictions are immutable after write).
- **L5 derived metrics** — pure functions over L0–L4 that FAIL CLOSED (named) when a
  ground-truth-requiring metric is asked for on a `provenance = none` run.

Deferred (noted, not foreclosed): L2 phase-level order/position/swap diagnostics (derivable later
from L0 + blinding), real selection logits (provider-dependent; null today), and the harness's L5
experiment sweeps + GT-labelling workflow (task-0026). Artifact spill is task-0019.

Engine-owned + pure-stdlib: imports nothing from `tasks`/`cli` (ADR-0002 boundary).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

TRACE_SCHEMA_VERSION = "trace/L1-L5-1"

# Capability classes (ADR-0018): the generation–verification axis the G/D/C-gap research keys on.
G = "generate"  # a proposer producing/refining a candidate
D = "discriminate"  # an adversary finding the flaw / picking the weaker option
C = "critique"  # a reviewer/arbitrator assessing or merging

# stage → capability class. A stage the map doesn't know is tagged `None` (honest, not guessed).
CAPABILITY: dict[str, str] = {
    "propose": G,
    "revise": G,
    "respond": G,
    "critique": C,
    "redteam": D,
    "escalate": D,
    "aggregate": C,
}


def capability_of(stage: str | None) -> str | None:
    return CAPABILITY.get(stage) if stage else None


class GroundTruthRequired(RuntimeError):
    """A ground-truth-requiring L5 metric was asked for on a run whose GT `provenance = none`. Named
    + fail-closed (ADR-0020): a GT metric must never be silently computed against absent labels."""


@dataclass
class RoleOutput:
    """L1: one call viewed through its role + capability class, with the candidate slate."""

    schema_version: str
    round_name: str
    stage: str
    debater_id: str
    capability_class: str | None
    # All candidates the call produced — today providers return n=1, so the slate is the single
    # served output referenced by its <round>/<id>.json; `logits` is null unless a provider exposes
    # selection logits (captured then, unrecoverable later — ADR-0020).
    candidates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_role_outputs(call_records: list[dict]) -> list[dict]:
    """L1 as a view over the L0 `CallRecord` stream: tag each with its capability class + a
    single-candidate slate. Pure; derivable on demand so it never perturbs L0 or resume."""
    out: list[dict] = []
    for c in call_records:
        stage = c.get("stage")
        out.append(
            RoleOutput(
                schema_version=TRACE_SCHEMA_VERSION,
                round_name=c.get("round_name"),
                stage=stage,
                debater_id=c.get("debater_id"),
                capability_class=capability_of(stage),
                candidates=[
                    {
                        "output_ref": f"{c.get('round_name')}/{c.get('debater_id')}.json",
                        "model_version": c.get("model_version"),
                        "logits": None,  # null-not-absent (ADR-0019/0020)
                    }
                ],
            ).to_dict()
        )
    return out


class LabelStore:
    """L4: an append-only label store, SEPARATE from the prediction artifacts (ADR-0020). A label is
    keyed to a `target` (an item/option id) with a `source` ∈ {human, model, oracle}; writes append
    to `labels.jsonl` and NEVER touch aggregate.json/result.json (predictions are immutable)."""

    _SOURCES = ("human", "model", "oracle")

    def __init__(self, run_dir: str | Path):
        self.path = Path(run_dir) / "labels.jsonl"

    def add(self, target: str, value, source: str, *, note: str = "") -> None:
        if source not in self._SOURCES:
            raise ValueError(f"label source must be one of {self._SOURCES}, got {source!r}")
        rec = {"target": target, "value": value, "source": source, "note": note}
        with self.path.open("a") as fh:  # append-only — a label never rewrites a prior one
            fh.write(json.dumps(rec) + "\n")

    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def ground_truth(self) -> dict:
        """Latest label per target from the `oracle` source (the ground truth), target -> value."""
        gt: dict = {}
        for rec in self.all():
            if rec["source"] == "oracle":
                gt[rec["target"]] = rec["value"]
        return gt


def _accuracy(pred: dict, truth: dict) -> float | None:
    """Fraction of the truth-labelled targets the predictions got right, or None if no overlap."""
    keys = [t for t in truth if t in pred]
    if not keys:
        return None
    return round(sum(1 for t in keys if pred[t] == truth[t]) / len(keys), 6)


def derived_metrics(predictions: dict, *, gt_provenance: str) -> dict:
    """L5: derive the research metrics from per-capability predictions + ground truth.

    `predictions` = {"generate": {target: label}, "discriminate": {...}, "critique": {...},
    "ground_truth": {target: label}}. GT-FREE metrics (agreement across capabilities) are always
    returned; the G/D/C accuracies + the three gaps REQUIRE ground truth and FAIL CLOSED (named)
    when `gt_provenance == "none"` — a GT metric is never computed against absent labels (ADR-0020).
    Each metric names its inputs so a reader can trace its provenance.
    """
    caps = {k: predictions.get(k, {}) for k in ("generate", "discriminate", "critique")}
    targets = sorted({t for cap in caps.values() for t in cap})
    # GT-free: how often all three capabilities agree on a target (a diagnostic, not a truth claim)
    tri = [t for t in targets if all(t in cap for cap in caps.values())]
    agree = [t for t in tri if len({caps[k][t] for k in caps}) == 1]
    metrics = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "gt_provenance": gt_provenance,
        "agreement_rate": (round(len(agree) / len(tri), 6) if tri else None),
        "n_targets": len(targets),
        "inputs": {"agreement_rate": ["generate", "discriminate", "critique"]},
    }
    if gt_provenance == "none":
        # Fail closed: the caller asked for GT metrics on an unlabelled run. Signal loudly which are
        # unavailable rather than returning a misleading number.
        metrics["gt_metrics_available"] = False
        metrics["gt_metrics_reason"] = (
            "ground-truth provenance is 'none' — G/D/C + gaps require labels"
        )
        return metrics
    truth = predictions.get("ground_truth") or {}
    if not truth:
        raise GroundTruthRequired(
            f"gt_provenance={gt_provenance!r} but no ground_truth labels supplied"
        )
    g, d, c = (
        _accuracy(caps["generate"], truth),
        _accuracy(caps["discriminate"], truth),
        _accuracy(caps["critique"], truth),
    )

    def _gap(a, b):
        return round(a - b, 6) if (a is not None and b is not None) else None

    metrics.update(
        {
            "gt_metrics_available": True,
            "G": g,
            "D": d,
            "C": c,
            "gd_gap": _gap(g, d),
            "gc_gap": _gap(g, c),
            "cd_gap": _gap(c, d),
            "inputs": {
                **metrics["inputs"],
                "G": ["generate", "ground_truth"],
                "D": ["discriminate", "ground_truth"],
                "C": ["critique", "ground_truth"],
                "gd_gap": ["G", "D"],
                "gc_gap": ["G", "C"],
                "cd_gap": ["C", "D"],
            },
        }
    )
    return metrics
