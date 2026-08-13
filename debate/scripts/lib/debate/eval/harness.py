"""The harness (task-0026): score per-profile predictions against a ground-truth dataset.

Deliberately decoupled from EXECUTION: it takes `predictions_by_profile` = {profile: {item_id:
prediction}} (+ optional confidences), so the same scoring drives both a canned test and a real
sweep whose predictions come from each run's `result.json` × the L4 ground-truth labels (task-0031).
The live orchestration that spawns N engine runs across profiles/panels is the agent+human sweep —
deferred; this is the measured-comparison core it feeds.

Three outputs, matching the acceptance criteria:
- `compare()`            — the per-profile table (discrimination + calibration + binary rates).
- `contamination_split()`— the same, split novel-vs-published, to rule out memorization.
- `judge_accuracy_curve()` — does judge accuracy RISE with panel strength? (oversight criterion).
"""

from __future__ import annotations

from debate.eval import scoring
from debate.eval.datasets import Dataset


def _numeric(truth: dict) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in truth.values())


def score_profile(pred: dict, truth: dict, *, confidence: dict | None = None) -> dict:
    """Every applicable metric for one profile's predictions against `truth`. Numeric truth gets
    correlation + RMSE/overestimation; categorical/binary truth gets accuracy (+ TPR/TNR when the
    labels are boolean). Metrics that don't apply are omitted, never faked."""
    out: dict = {"n_scored": len({k for k in truth if k in pred})}
    if _numeric(truth):
        out["discrimination_pearson"] = scoring.pearson(pred, truth)
        out["rmse"] = scoring.rmse(pred, truth)
        out["overestimation"] = scoring.overestimation(pred, truth)
    else:
        out["accuracy"] = scoring.accuracy(pred, truth)
        if all(isinstance(v, bool) for v in truth.values()):
            out["binary_rates"] = scoring.binary_rates(pred, truth)
    if confidence:
        out["coverage_risk"] = scoring.coverage_risk_curve(pred, truth, confidence)
    return out


def compare(
    dataset: Dataset,
    predictions_by_profile: dict[str, dict],
    *,
    confidence_by_profile: dict[str, dict] | None = None,
) -> dict:
    """The per-profile comparison table over the dataset's ground truth. Reports the negative just
    as readily as the positive — a baseline out-scoring `steelman` is a finding, not an error."""
    truth = dataset.truth()
    conf = confidence_by_profile or {}
    return {
        "dataset": dataset.name,
        "n_items": len(dataset.items),
        "profiles": {
            name: score_profile(pred, truth, confidence=conf.get(name))
            for name, pred in predictions_by_profile.items()
        },
    }


def contamination_split(dataset: Dataset, predictions_by_profile: dict[str, dict]) -> dict:
    """Score each profile on the PUBLISHED and NOVEL strata separately (Ashokkumar et al.): a win
    that holds only on published items is memorization, not reasoning. Fails safe when a stratum is
    empty (reported as `null`, never a misleading 0)."""
    novel = dataset.novel_ids()
    truth = dataset.truth()
    pub_truth = {k: v for k, v in truth.items() if k not in novel}
    nov_truth = {k: v for k, v in truth.items() if k in novel}
    out: dict = {"n_published": len(pub_truth), "n_novel": len(nov_truth), "profiles": {}}
    for name, pred in predictions_by_profile.items():
        out["profiles"][name] = {
            "published": score_profile(pred, pub_truth) if pub_truth else None,
            "novel": score_profile(pred, nov_truth) if nov_truth else None,
        }
    return out


def judge_accuracy_curve(dataset: Dataset, predictions_by_strength: dict) -> list[dict]:
    """The scalable-oversight success criterion: judge accuracy as a function of PANEL STRENGTH.
    `predictions_by_strength` = {strength_label: {item_id: judged_answer}} where strength is ordered
    (e.g. 'weak-1voice' < 'strong-3voice-diverse'). Returns one row per strength with its accuracy —
    a RISING curve is the win condition; a flat/falling one is the reportable negative."""
    truth = dataset.truth()
    curve = []
    for strength, pred in predictions_by_strength.items():
        m = scoring.accuracy(pred, truth)
        if m is None:
            m = scoring.pearson(pred, truth)  # numeric fallback
        curve.append({"strength": strength, "accuracy": m})
    return curve
