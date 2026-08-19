# Automatic CLI instrumentation

## Causal path

```text
capability repository owns generated adapter
  -> portable [cli] manifest publishes that ordinary executable
  -> Skill Installer links the public command without Feedback knowledge
  -> public CLI symlink targets the repository adapter
  -> wrapper execs `skill-feedback run`
  -> privacy + global/per-skill opt-out gate
  -> content-free invocation.started append
  -> original target runs with inherited I/O, argv, environment, and cwd
  -> target exit or signal becomes invocation.finished
  -> events become input to date-filtered outcomes and later policy evaluation
```

The adapter does not make event storage part of the skill's domain
implementation. Feedback owns the generated adapter contract and emission
semantics; Installer only links the executable declared by the source.

## Generation and manifest contract

```bash
skill-feedback wrapper software-engineering \
  --feature cli \
  --target skill/scripts/engineering \
  --output skill/scripts/engineering-feedback \
  --apply
```

Commit the adapter and publish it as an ordinary executable:

```toml
[cli]
executables = { engineering = "scripts/engineering-feedback" }
```

The command is dry-run-first and idempotent. It updates only files carrying its
managed marker and refuses unmanaged paths. Targets are stored relative to the
adapter so fresh checkouts can move. `skill-feedback` cannot instrument itself.

Use repeatable `--success-exit-code` for documented nonzero control states. For
example, context-aware codes 10 and 11 mean successful stop/wind-down
decisions; treating them as failures would corrupt downstream evidence.

## Dynamic coverage

```bash
skill-feedback onboard <skill>
skill-feedback onboard --check --json
skill-feedback coverage --json
skill-feedback coverage --check --declared-only
skill-feedback coverage --check
```

Coverage consumes the discovered skills.sh/filesystem inventory on every
process run, so a newly installed or added skill is classified without a
Feedback code change. `SKI_REGISTRY` is an explicit test/operator override only.
Inventory failure is distinct from an empty portfolio and makes both
`coverage --check` and `onboard --check` fail. `--declared-only` verifies every
already-declared CLI crosses a managed adapter. Strict `--check` also fails on
skills with no declared reliable boundary. Those skills must choose a CLI,
MCP/server emission, explicit start/finish, or a future harness activation
callback; they are never silently counted as automatic.

`onboard` uses the same live inventory to explain the next work after skill
creation or installation. It reports adapter readiness and operator privacy
readiness separately. The Feedback skill's routing trigger covers that moment;
Installer remains unaware of Feedback and performs no hidden mutation.

## Privacy and opt-outs

Automatic events require:

1. explicit retention (`--forever` or `--days N`);
2. `skill-feedback collection --manifest-opt-in`;
3. execution through a generated adapter published by the skill manifest.

Disable globally with `skill-feedback collection --off` or temporarily with
`SKILL_FEEDBACK_DISABLE=1`. Disable selected skills with
`SKILL_FEEDBACK_DISABLE_SKILLS=name,...`. All disabled paths directly exec the original command.

Events never include command arguments, prompt/output content, environment values, or the working
directory. Session identifiers remain keyed hashes.

## Lifecycle and idempotency

Normal invocations get unique identities and use locked O(1) JSONL appends. A resumable caller may
set `SKILL_FEEDBACK_IDEMPOTENCY_KEY` or pass `--idempotency-key`; start and finish event identifiers
then become deterministic and duplicate retry emissions are suppressed.

Exit zero records `success`; non-zero exit records `failure`; signal termination records
`abandoned`. None of those facts is praise. SIGKILL or host loss can leave only the start event,
which is an explicit incomplete invocation.

## Behavioral boundary

The target inherits stdin, stdout, stderr, argv, environment, and working directory. The runner
returns the same ordinary exit code and re-signals itself when the child dies by signal. The runner
does become the target's parent process, and universal equivalence for process-tree/job-control
behavior is not claimed. Keep a command uninstrumented if it depends on exact parent identity or
unusual process-group semantics. A pseudo-terminal fixture confirms stdin/stdout/stderr remain TTYs
through the wrapper; it does not prove arbitrary terminal job-control behavior.

## System-level review

The implementation was reviewed against:

- boundary values: empty command, invalid manifest references, collection off;
- invalid transitions: finish absent after SIGKILL, duplicate retry events;
- partial completion: interrupted adapter writes, install reconciliation, and wrapper tampering;
- retry/idempotency: stable keys suppress duplicate start and finish;
- concurrency/ordering: ledger and notes use process locks; start precedes target spawn;
- degraded dependencies: telemetry failure fails open to the original target;
- stale state: versioned inventory validation fails closed; `coverage` reports
  direct declared CLIs and missing boundaries when inventory is valid;
- rollback/removal: the installer manages only the public link; repository adapters
  remain source-owned;
- component interaction: the installer never generates adapters or writes events;
  Feedback never edits installer state.

A live macro-level pass found one semantic interaction that syntax and ordinary
exit-preservation tests missed: context-aware uses nonzero codes as successful
control decisions. The adapter contract now records declared expected exits as
success while preserving the exact process code.

## Measured local overhead

On the development VM on 2026-07-29, 50 instrumented `/bin/true` runs averaged `112.1 ms ± 3.6 ms`.
A second 50-run cohort after the ledger had grown by more than 100 events averaged
`112.3 ms ± 5.3 ms` (range `102.5–132.0 ms`). This supports the intended bounded-history property:
ordinary automatic appends do not scan the ledger. Most cost is Python startup plus two durable
locked appends. The overhead is suitable for human-scale skill CLIs, not for tight inner-loop or
latency-sensitive commands; leave those uninstrumented or measure a more appropriate boundary.

Residual unknowns are provider-specific paid/resume identity, interactive TTY job control beyond
basic TTY inheritance, arbitrary descendant signal trees, and harness-specific pure-text activation
hooks. Those require representative external systems rather than more synthetic wrapper logic.
