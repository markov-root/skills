"""`eval/` — the protocol-validation harness (task-0026): turn the design from argued into measured.

Runs the engine over GROUND-TRUTH questions and asks whether the protocol actually helps —
debate vs consultancy vs direct — and whether judge accuracy rises with panel strength (the
scalable-oversight success criterion). Its job is to make the effect (and the NEGATIVE result —
debate can lose to a strong baseline, more rounds can hurt) VISIBLE per profile, never to confirm
that debate helps. It only ever scores VERIFIABLE proxies; a fuzzy steelman task is validated only
indirectly through them (ADR-0014; the supporting evidence remains in the development factory).

Layout (this landing = the tested measurement core; the live sweep is agent+human, deferred):
- `scoring.py`   — pure-stdlib metrics: discrimination (accuracy/correlation), calibration
                   (RMSE/overestimation), TPR/TNR + false-acceptance, coverage–risk (selective).
- `datasets.py`  — the ground-truth item model + loaders (a small built-in set + JSON).
- `profiles.py`  — the baseline profiles (`direct`, `consultancy`, `steelman`) as Plans, so a
                   baseline REUSES the same config the tool runs (a degenerate plan, not a fork).
- `harness.py`   — score predictions per profile into a comparison table, the contamination
                   (novel-vs-published) split, and the judge-accuracy-vs-panel-strength curve.

Consumes the L0–L5 trace (task-0031) via predictions extracted from a run's `result.json` +
ground-truth labels (the L4 label store). Pure-stdlib; imports engine `plan` only for the profiles.
"""
