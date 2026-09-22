# Changelog

## 0.1.2 — 2026-09-19

- Stop refusing a sync when a harness root holds a symlink into a managed placement. Codex and
  OpenCode read only their own skills directory, so `~/.codex/skills/<name>` → `~/.agents/skills/<name>`
  is the supported way to expose the shared copy, not an override of it. Such a link is now reported
  as `linked-to-placement` instead of blocking the plan; an independent copy, or a link resolving
  anywhere else, still conflicts. (task: 0008)

## 0.1.1 — 2026-09-06

- Prefer a verified PATH launcher; resolve portable fallback scripts from the loaded SKILL.md location without assuming an installation directory.


## 0.1.0 — 2026-09-06

- Add cross-harness filesystem inventory, content diffs and reviewed local sync.
- Delegate folder placement and managed removal to Vercel skills.
- Add optional declared PATH launchers, ownership checks and development finish.
