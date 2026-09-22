# Changelog

This changelog records changes to the installable `situational-awareness` Agent Skill artifact.

## 0.2.2 — 2026-09-06

- Prefer a verified PATH launcher; resolve portable fallback scripts from the loaded SKILL.md location without assuming an installation directory.

## 0.2.1 — 2026-09-06

- Declare optional CLI entry points for skill-manager PATH exposure; portable invocation stays available.

## 0.2.0 — 2026-08-19

- `usage-check`/`budget` now relax the quota stop threshold as a reset approaches: the effective
  max used% that still returns `continue` ramps linearly from the configured max (90%) toward a
  99.9% ceiling over the final ~43% of each window (72h weekly / ~2.1h five-hour). Near reset the
  tools no longer hard-stop (`wait_for_reset`/exit 10) at, e.g., 95% weekly with <24h to reset —
  the intent is to spend down to ~99.9% before an allocation is wasted at reset. Default-on; the
  warn→max band shifts up together so `warn` never drops below its configured value.
- Conservative by construction: relaxation is skipped when reset time is unknown, and the effective
  threshold is never below the configured max. Disable with `--no-reset-relax`; tune with
  `--relax-ceiling` and `--relax-fraction`.
- JSON output gains a `relaxation` object (`enabled`, `ceiling`, `fraction`, `effective`
  thresholds, `active`); the human view adds a `relax` line and targets the effective max in its
  ETA. Exit-code contract is otherwise unchanged.

## 0.1.1 — 2026-08-02

- Relocated to the per-skill workspace layout (`Skill-Situational-Awareness/situational-awareness/`
  plus a sibling `dev/` factory) with the Python runtime bundled under `scripts/situational_awareness/`;
  installed command behavior is unchanged.
- Bundled `THIRD_PARTY_NOTICES.md` inside the artifact so notices ship with the published skill.
- Moved dated cache-mechanics research into the artifact `references/` so SKILL.md routes stay
  self-contained.

## 0.1.0 — 2026-07-26

- Provider-aware context, subscription quota (5h + weekly), prompt-cache, and continuity budgeting
  with `context-check`, `usage-check`, `budget`, and `cache-check`; stdlib-only runtime.
