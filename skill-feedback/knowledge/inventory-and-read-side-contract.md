# Inventory and read-side contract

This document defines how Skill Feedback discovers capabilities, reports
coverage, locates state, and behaves in read-only execution environments.

## Inventory authority

```text
installed skill dirs + SKILLS_HOME/<name>/public artifacts
  -> Feedback filesystem inventory (SKILL.md name discovery)
  -> coverage + onboard + source resolution
  -> stats coverage snapshot
```

Normal execution never invokes an external manager or scans a presumed Skill
Manager checkout registry. Discovery reads each harness skill directory (Claude,
Agent Skills, Codex and `.system`) plus writable source artifacts under
`SKILLS_HOME/<name>/public`. `SKI_REGISTRY` is an explicit test/operator
override; an explicit `SKILL_MANAGER_COMMAND` is honoured only when set, for
compatibility with an instrumented manager. Inventory is ready only when its
discovered source is valid and contains at least one capability.

`coverage --check` and `onboard --check` fail for unavailable inventory.
Human-readable notes remain discoverable through installed harness roots and
the private outbox even when inventory is unavailable.

## Read-side behavior

`list`, `review`, `events`, `stats`, `privacy-check`, and `doctor` do not create
lock files, directories, or change permissions while reading. When an existing
private lock is present and readable, a reader opens it without write access and
takes a shared `flock`. A legacy store without a usable lock is read best-effort
and validated; the next writer creates or repairs the lock before mutation.

Permission repair is explicit through `doctor --fix-permissions`. A plain
doctor invocation reports any mode that differs from the required `0700`
directory or `0600` file contract but does not repair it.

Writers use exclusive private locks and atomic replacement where a complete
artifact must become visible at once. In particular, the session HMAC key is
written to a private temporary file, flushed, and atomically published while
holding a dedicated key lock. No process can observe the key filename before
all 32 bytes are durable.

Privacy migration uses the portfolio-private notes lock. It does not leave a
`.feedback.lock` artifact in capability repositories.

## State-root resolution

`SKILL_FEEDBACK_HOME` always wins. Without it:

1. an existing legacy local store is retained in place so an upgrade never
   strands events or the session key;
2. new Linux installations use
   `${XDG_STATE_HOME:-~/.local/state}/skill-feedback`;
3. macOS uses `~/Library/Application Support/Skill Feedback`;
4. Windows uses `%LOCALAPPDATA%\Skill Feedback`.

Moving an existing legacy store is an explicit future migration, not an
automatic side effect.

## Statistics

Every stats response includes:

- inventory readiness, source, contract version, and count;
- strict portfolio and declared-CLI completeness;
- coverage counts and a per-skill status map;
- a coverage state beside each result group.

When inventory or automatic coverage is incomplete, the limitations list says
that usage denominators are incomplete. Rates remain descriptive and cannot be
used as causal rankings.
