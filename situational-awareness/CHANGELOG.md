# Changelog

This changelog records changes to the installable `situational-awareness` Agent Skill artifact.

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
