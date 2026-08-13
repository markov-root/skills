# Changelog

The project is pre-alpha; public contracts can still change before the first supported release.

## 0.2.0 — 2026-08-11

- Resolve cost, plan, run, and resume through one immutable `ResolvedRunPlan`, atomically record it
  before backend construction, and reconstruct resume from that record instead of mutable project
  configuration. Add `debate plan --json` for inspecting the exact resolved execution. (task: 0040)

## 0.1.0 — 2026-08-02

- Refactor Debate into a relocatable Agent Skill with a locked bundled runtime and installed-copy smoke test. (task: portfolio-0001-debate)

## Legacy source history

### Collaborator-alpha preparation

- Added a portable skill manifest and checkout-independent source wrapper.
- Included runtime prompts, panels, schemas, and skill metadata in built wheels.
- Made OpenRouter application attribution generic and user-controlled.
- Made newly created CLI artifacts private by default while restoring the caller's process umask.
- Added publication-readiness, privacy/data-flow, and security documentation.

### Known limitations

- License, public schema namespace, GitHub destination, and private vulnerability-reporting route
  still require owner decisions.
- Exact resume/fork integrity and hostile-materials hardening are not complete.
- The IDEA protocol and broader research framework remain roadmap work.
