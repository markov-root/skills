"""Scoring metrics for the validation harness (task-0026) — pure-stdlib, no engine/task imports.

Two families, both keyed on a target id so predictions and truth align by item:
- DISCRIMINATION (primary): does the protocol track truth? — `accuracy` (categorical) / `pearson`
  (numeric correlation).
- CALIBRATION (secondary): `rmse` + `overestimation` (signed bias — the Ashokkumar et al. ~2×
  overestimation is a calibration failure, not a discrimination one, so they're reported apart).

Plus the Cluster-3-mandated honesty metrics (`docs/research/2026-07-26-cluster3-synthesis.md`): a
binary verifiable task reports `binary_rates` (TPR/TNR + false-acceptance — accuracy alone hides a
lenient judge: majority vote scored TNR 19.2%), and `coverage_risk_curve` for selective judging
(abstain below a confidence → trade coverage for risk).
"""

from __future__ import annotations

import math


def _aligned(pred: dict, truth: dict) -> list:
    """(pred[k], truth[k]) for every target present in BOTH — the comparable subset."""
    return [(pred[k], truth[k]) for k in truth if k in pred]


def accuracy(pred: dict, truth: dict) -> float | None:
    """Fraction of shared targets the prediction got exactly right (categorical); None if none."""
    pairs = _aligned(pred, truth)
    if not pairs:
        return None
    return round(sum(1 for p, t in pairs if p == t) / len(pairs), 6)


def pearson(pred: dict, truth: dict) -> float | None:
    """Pearson correlation of numeric predictions with truth — the discrimination signal for a
    numeric task (Ashokkumar et al.'s primary: correlation with the known effect). None if <2 points
    or zero variance (undefined, not 0 — never fake a signal)."""
    pairs = _aligned(pred, truth)
    if len(pairs) < 2:
        return None
    xs, ys = [float(p) for p, _ in pairs], [float(t) for _, t in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return round(sxy / math.sqrt(sxx * syy), 6)


def rmse(pred: dict, truth: dict) -> float | None:
    pairs = _aligned(pred, truth)
    if not pairs:
        return None
    return round(math.sqrt(sum((float(p) - float(t)) ** 2 for p, t in pairs) / len(pairs)), 6)


def overestimation(pred: dict, truth: dict) -> float | None:
    """Signed mean bias (pred - truth): positive = the protocol systematically OVER-estimates."""
    pairs = _aligned(pred, truth)
    if not pairs:
        return None
    return round(sum(float(p) - float(t) for p, t in pairs) / len(pairs), 6)


def binary_rates(pred: dict, truth: dict, *, positive=True) -> dict:
    """Confusion-derived rates for a binary accept/reject judgment (`positive` = the ACCEPT label).

    Accuracy alone flatters a lenient judge, so report both: `tpr` (sensitivity — accepts a true
    claim), `tnr` (specificity — rejects a false one), and `false_acceptance` = FP/(FP+TN) = 1-TNR,
    the rate at which a FALSE claim is wrongly accepted (the scalable-oversight failure mode)."""
    tp = fp = tn = fn = 0
    for k in truth:
        if k not in pred:
            continue
        p, t = pred[k] == positive, truth[k] == positive
        tp += p and t
        fp += p and not t
        tn += (not p) and (not t)
        fn += (not p) and t

    def _rate(num, den):
        return round(num / den, 6) if den else None

    return {
        "tpr": _rate(tp, tp + fn),
        "tnr": _rate(tn, tn + fp),
        "false_acceptance": _rate(fp, fp + tn),
        "n": tp + fp + tn + fn,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
    }


def coverage_risk_curve(pred: dict, truth: dict, confidence: dict) -> list[dict]:
    """Selective-judging curve: sort targets by descending confidence and, at each coverage level,
    report the error rate (risk) over the answered subset. A useful judge's risk should FALL as it
    abstains on its least-confident items; a flat/rising curve says confidence is uninformative."""
    keys = [k for k in truth if k in pred and k in confidence]
    keys.sort(key=lambda k: confidence[k], reverse=True)
    curve, wrong = [], 0
    for i, k in enumerate(keys, start=1):
        wrong += pred[k] != truth[k]
        curve.append({"coverage": round(i / len(keys), 6), "risk": round(wrong / i, 6)})
    return curve
