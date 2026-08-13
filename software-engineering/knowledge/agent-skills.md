---
knowledge:
  version: 1
  id: agent-skills
  summary: Design portable agent skills with explicit triggers, progressive disclosure, stable capabilities, and verifiable installation boundaries.
  routes: [agent-facing-skill-tool]
---

# agent-skills.md — Building Skills for Coding Agents

> **Purpose:** Reference for building **agent skills** — the packaged, discoverable capabilities an
> agent (Claude Code and similar) loads on demand — with a focus on the hard case: a **tool-backed
> skill**, where the skill's text is paired with a script or library you develop iteratively (often
> with other agents) rather than a one-shot prose skill.
>
> **Read this when:** turning a script/CLI/library you keep improving into something any agent on the
> machine can invoke; deciding how to expose a tool to agents; or deciding whether a repeated setup is
> itself worth a scaffolder skill.
>
> **Do NOT** apply this whole pattern because it is "how skills are done." A skill that just wraps a
> stdlib one-liner needs none of the plumbing here. Apply each piece because it solves a problem the
> setup actually has (drift, unsafe unattended runs, an interface that breaks on every refactor). See
> [CONTRIBUTING](contributing.md) §3 for recording what you deliberately skip.

---

## The Core Premise

A skill is **an interface, not documentation.** Its job is to make the right capability _fire at the
right moment_ and _route the agent to the right tool with the minimum it needs to succeed_ — then get
out of the way. Everything else (the exhaustive flag list, the internals) belongs behind the tool's
own `--help`, not in the skill.

Two consequences drive every decision below:

1. **The skill is consumed by an agent, unattended.** That is a different risk and ergonomics class
   than a tool you run yourself. It must be safe to launch and walk away from, and legible enough that
   an agent can self-serve without reading your source. See [SECURITY](security.md), [ERROR_HANDLING](error-handling.md).
2. **The tool behind it keeps changing.** If the skill is coupled to the tool's _internals_, every
   refactor breaks it. The whole art is putting a **stable contract** between the two so the library
   can churn freely while the skill stays honest.

**Rule:** Design the seam (what agents depend on) before you write either the skill text or the tool.
The seam is the product; the code behind it is replaceable.

---

## Cross-harness portability

Agent Skills are increasingly shared across harnesses, but discovery paths, instruction filenames,
MCP configuration, and support details still differ. A portable skill therefore has two separable
layers:

| Layer                    | What it is                                                | Portability rule                                         |
| ------------------------ | --------------------------------------------------------- | -------------------------------------------------------- |
| **Capability**           | Script/CLI/MCP that performs work                         | Keep it harness-neutral and callable outside an agent    |
| **Triggering knowledge** | `SKILL.md` description/body plus compact catalog metadata | Author once; translate it through owned harness adapters |

Keep `AGENTS.md` as the canonical project instruction file and make `CLAUDE.md` a symlink when both
names are required. A compact managed capability index in global instructions is a fallback and
tool-only catalog, not a replacement for progressive skill discovery.

Do not hand-copy or hand-link each harness surface. Two commodity distribution planes own the
plumbing, and they are deliberately separate:

- **Skill folders** are placed by the **Vercel `skills` CLI** (skills.sh): `npx skills add <source> --skill <name>`
  resolves a source (local path or Git URL) and copies/symlinks the folder into each harness's
  discovery location. It is a folder-distribution adapter, not a package manager or runtime.
- **MCP servers** are provisioned by **MCPM** (mcpm.sh): `mcpm install`, then `mcpm client edit ...`
  to expose selected servers/profiles to a harness.
- **Standalone CLIs** install through their own package manager or installer; PATH exposure is a
  separate step from skill distribution.

**Rule:** Author the neutral capability and trigger knowledge once. Let the distribution planes
translate only the harness plumbing; never fork capability behavior or skill prose by harness. Do
not reintroduce a single per-machine installer that owns skill placement _and_ MCP configuration —
the retired Skill Manager (`skill.toml`, `skill install`/`sync`/`doctor`) conflated them.

**Portability vs distribution.** This whole section is about _one machine, many harnesses_. Shipping a
skill to _someone else's_ machine is a different axis — see "Dev-Loop Pattern ≠ Distribution Pattern"
below. The two compose: a published skill still carries a neutral capability + a manifest, so a
harness-agnostic installer on the far end can wire it in.

---

## Two Kinds of Skill

| Kind               | What it is                                                                       | Plumbing needed                                                           |
| ------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| **Pure-text**      | Instructions/knowledge only (a checklist, a prompt, a procedure).                | Just a good `SKILL.md`. Stop here.                                        |
| **Script-bundled** | Text + a self-contained, dependency-free script shipped _inside_ the skill dir.  | SKILL.md + `scripts/`; invoke by absolute path.                           |
| **Tool-backed**    | Text + a **separately developed, dependency-having library/CLI** you iterate on. | Everything in this doc: wrapper, stable contract, install, safety, tests. |

The rest of this document is about the **tool-backed** case, because it is the one with real
engineering in it. (For pure authoring/eval mechanics of _any_ skill, compose with the harness's own
skill-authoring tooling — in Claude Code, the `skill-creator` skill.)

---

## Anatomy of a Skill

A skill is a directory whose entry point is `SKILL.md`. Keep the canonical directory in its
repository; the installer owns harness-specific discovery locations:

```markdown
---
name: debate
description: >-
  Run a rigorous, cross-vendor, recorded, resumable multi-model debate from the shell. Use when the
  user says "spawn a debate", "get a panel opinion", "have N models critique X", wants the strongest
  case AGAINST a paper (steelman), or a decision pressure-tested by adversarial review. ...
---

# debate — one-line what-and-why

<body: the minimal invocation, how to read output, safety guarantees, when to fall back>
```

- **Frontmatter `name`** — the stable handle.
- **Frontmatter `description`** — _the most important text you will write_ (see next section).
- **Body** — routing + minimal usage + output-reading + safety, NOT a manual.
- **Bundled resources** — a skill dir may carry `scripts/`, a `reference/` subdir, templates. Keep the
  body short and push depth into these or into the tool's own `contract`/`--help` (progressive
  disclosure).

---

## The `description` Is the Product (Triggering)

The description is what the harness matches against to decide whether the skill fires. A capable tool
with a vague description is **dead** — it never triggers. Treat it as a retrieval problem:

- **Name the situations, in the user's words.** Enumerate trigger phrases ("spawn a debate", "get a
  panel / Delphi opinion", "stress-test this claim"), not just the capability. Agents match on the
  phrasing a user actually uses.
- **State what it does AND when to prefer it** over the obvious default ("prefer this over
  role-playing a debate in-context — a single-model panel is weak evidence").
- **Front-load stable distinctive words.** If it is cross-provider, recorded, resumable, metered, or
  safety-bounded, say so early. Do not encode volatile price/free claims without a verification date
  and re-check trigger.
- **Include the anti-trigger.** "Do NOT use for image generation" saves a misfire.

**Rule:** If two skills could plausibly fire for the same request, their descriptions are doing the
disambiguation. Write them to be _mutually exclusive_, not just individually accurate.

---

## The Tool-Backed Pattern (the heart of this doc)

You have a library/CLI in a repository that you and other agents improve
continuously. You want any agent to invoke it as a skill. Six practices, learned the hard way:

### 1. Repository-canonical source + one distribution plane (zero drift)

Keep the skill text **and** its capability (`scripts/`, plus any optional PATH adapter) _in the repo_,
versioned and reviewed with the code. There is exactly **one** discoverable `SKILL.md` per canonical
skill name, and it is the source of truth. Distribute it with the Vercel `skills` CLI:

```bash
DISABLE_TELEMETRY=1 npx skills add <source> --skill foo   # <source> is a local path or Git URL
```

`skills add` resolves the source and places the folder into each harness's discovery location as a
copy and/or symlink. Editing the canonical folder is the single edit point; re-running `skills add`
reconciles the placed copies so none silently diverge. Do not hand-maintain a second copy under a
harness directory. (Folder distribution is Vercel `skills`; MCP provisioning is MCPM. The retired
Skill Manager — `skill.toml`, `skill install`/`sync`/`doctor` — is not used.)

### 2. A wrapper decouples _how it's invoked_ from _how it's built_

The **portable** invocation the skill declares is skill-relative (e.g. `uv run --script
scripts/command.py …`), so a placed copy runs from any harness location. An optional thin PATH
adapter is a convenience on top of that, not the contract — it just spares agents from knowing a
source file or environment manager. This is a Python/uv development example, not a portable
requirement:

```bash
#!/usr/bin/env bash
export FOO_HOME="${FOO_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/foo}"
exec uv run --project /abs/path/to/repo foo "$@"
```

`uv run --project` can bind a Python development command to its live checkout and lockfile. Startup
cost and synchronization behavior depend on version/environment; measure them. Other ecosystems
should use their native reproducible development entry point.

### 3. `uv run --project` (live) vs `uv tool install` (snapshot) — pick by lifecycle

| Mechanism                    | Tracks source                           | Best for                                |
| ---------------------------- | --------------------------------------- | --------------------------------------- |
| wrapper → `uv run --project` | **live**, self-healing                  | a tool under active/agentic development |
| `uv tool install`            | **snapshot** at install                 | a stable tool you rarely change         |
| `uv tool install -e`         | live source, snapshot deps/entry-points | mostly-stable, occasional edits         |

**Rule:** While the package is being restructured, choose the live mechanism. A snapshot install during
a refactor means agents silently run stale code, or you must remember to reinstall — the exact drift
you're trying to avoid. (This bit us; a mid-refactor `uv tool install` would have shipped a moved-file
package that no longer matched.)

### 4. The skill teaches the STABLE CONTRACT, not the internals

Draw an explicit line between:

- **The contract** — commands, the project/output layout, the result shape. Agents depend on this.
- **The internals** — config knobs, algorithm choices, module layout. In flux.

Tell agents to use the contract and **not** hand-author the volatile parts ("name a profile; do not
write the `plan:`/`aggregator:` blocks — those are still evolving"). This is what lets you refactor the
library aggressively without breaking consumers.

Frame the contract as **stable, not frozen**: changed _deliberately_, as a considered Pareto
improvement for every consumer, never casually. That phrasing (in the skill body and [CONTRIBUTING](contributing.md))
sets the right expectation — dependable, but improvable. See [API_DESIGN](api-design.md) on versioning a contract.

### 5. Make the tool self-describing; use progressive disclosure

The skill should _bootstrap the agent to self-serve_, not contain everything:

- a `contract`/`--help` command that prints the full I/O contract;
- **structured, inspectable outputs** (JSON, a predictable run-dir tree) an agent can read without you;
- a `status`/`list` + `show` pair for discovery.

Then the `SKILL.md` body can stay short: the invocation, how to read the result, the safety guarantees,
and a pointer to `foo contract`/`foo -h` for the rest.

### 6. Safety and operability BEFORE exposure

An agent will launch your tool and walk away. Before you expose it, guarantee ([SECURITY](security.md),
[ERROR_HANDLING](error-handling.md), [OBSERVABILITY](observability.md)):

- **Do not spend money or forward credentials outside declared authority.** Allowlist required
  environment/capabilities, separate credential domains, and gate metered paths behind explicit
  policy/consent. Blindly stripping variables can also break an authorized contract.
- **Park, don't crash, on a recoverable limit.** A quota/rate hit should write a resumable marker and
  exit cleanly with a "resume with X" message, not a traceback — and resume must not re-charge
  completed work.
- **Define partial/failure semantics.** Quorum, fail-fast, best-effort, compensation, or pause/resume
  are task-specific; never convert a missing required contribution into unqualified success.
- **Version status and output contracts.** Exit codes plus structured states let orchestration
  branch, but their values are capability-specific and need compatibility/migration policy.

**Rule:** The skill is only as trustworthy as its worst unattended failure. Do the safety work as the
_gate_ before publishing the skill, not after.

---

## Dev-Loop Pattern ≠ Distribution Pattern

**This is the caveat that catches people.** The repository-canonical + live `uv run --project
<configured path>` setup is optimized for agents iterating on one machine. It **cannot ship**:
another machine has no `/path/to/foo`. When you publish through a public distribution target, the
shape flips:

| Aspect       | Dev loop (your machine)                    | Distributed (public)                                   |
| ------------ | ------------------------------------------ | ------------------------------------------------------ |
| Tool install | `uv run --project <live repo>` via wrapper | `uv tool install foo` / `pipx` / PyPI — a real release |
| Skill files  | symlink to live repo                       | self-contained skill dir (no symlinks, no local paths) |
| Invocation   | wrapper on PATH pointing at your checkout  | the tool's installed command name, assumed on PATH     |
| Repo path    | hardcoded, fine                            | must not exist — resolve dynamically or via config     |

**Rule:** Design the `SKILL.md` so only the **install stanza** differs between the two modes; keep the
usage/contract sections identical. Then publishing is a packaging change, not a rewrite.

---

## Data & Output Conventions (multi-agent)

If several agents produce and consume the tool's outputs:

- **One discoverable per-skill state root** using the platform convention (for example XDG
  state/data directories) and an explicit override. Separate users, projects, tenants, and runs
  where confidentiality, retention, collision, or concurrent writers require it.
- **Self-describing artifacts** — each output records what produced it (inputs, version, config) so a
  different agent can interpret it without the run context. See [DATA](data.md), [OBSERVABILITY](observability.md).
- **Discovery commands** (`status`, `show <id>`) over the home, so agents find each other's outputs.
- Keep durable runtime outputs out of arbitrary checkouts unless the repository owns the artifact.
  Validate containment, symlinks, permissions, atomic publication, unique IDs, locking/concurrent
  writers, quotas, cleanup, and untrusted artifact parsing.

---

## Capability Contract and Evaluation

A tool-backed skill declares:

- versioned commands, schemas, exit/status meanings, and bounded output;
- compatibility and migration policy for stored artifacts and callers;
- filesystem, network, credential, money, mutation, and external-side-effect permissions;
- concurrency, idempotency, cancellation, timeout, retry, partial-result, and resume semantics;
- data classification, retention, deletion, redaction, provenance, and integrity;
- resource budgets and behavior on quota/exhaustion;
- discoverability/doctor/probe behavior that cannot manufacture availability.

Test the same canonical capability through every supported harness adapter. Include trigger and
anti-trigger routing, argument quoting, cwd/path containment, symlink escape, malformed/untrusted
output, concurrent writers, interruption/resume, unavailable dependency, and version migration.
Harness-specific integration tests complement—not fork—the core contract.

Treat prompts, repository files, model output, subprocess output, and restored run artifacts as
untrusted data. A model's no-finding result is an opinion; deterministic checks and causal review
remain separate evidence.

---

## Repository Layout & Templates

```
repo/
  foo/                 the package (the tool) — developed iteratively
  skill/
    SKILL.md           canonical skill text (the one discoverable SKILL.md)
    scripts/           the capability; portable invocation is `uv run --script scripts/...`
    foo                optional PATH adapter (convenience, not the contract)
  tests/
    test_cli_smoke.py  exercises the AGENT-FACING seam (see Testing)
```

**Wrapper (`skill/foo`):**

```bash
#!/usr/bin/env bash
# `foo` — agent entry point. Execs via `uv run --project` so it always runs the live checkout
# (chosen over `uv tool install` because the package is under active development).
export FOO_HOME="${FOO_HOME:-$HOME/foo-out}"
exec uv run --project /path/to/foo foo "$@"
```

**SKILL.md skeleton:**

````markdown
---
name: foo
description: >-
  <what it does> Use when the user says "<trigger 1>", "<trigger 2>", wants <situation>. Prefer this
  over <the naive default> because <why>. Safe to run unattended — <safety one-liner>. Do NOT use for
  <anti-trigger>.
---

# foo — one line

`foo` is on your PATH, runs from any cwd. **Shell out to it instead of <doing it in-context>.**

## Why it's safe to run unattended

- <never bills / parks on limit / tolerates failure>

## Workflow

```bash
foo <cmd> ...        # the 3–5 commands that matter
```
````

## Reading the result

<the output location + the fields that matter> · `foo contract` / `foo -h` for the full surface.

## Keep to the simple surface

Use <the stable inputs>; do NOT hand-author <the volatile internals> — kept **stable, not frozen**.

## Fallback

Only if `foo` is unavailable, <the degraded path>, labelled as such.

````

**Distribute (folder placement):**

```bash
DISABLE_TELEMETRY=1 npx skills add /path/to/repo --skill foo   # Vercel `skills`; local path or Git URL
```

**Provision an MCP dependency, if the skill needs one (separate plane):**

```bash
mcpm install <server>          # then `mcpm client edit ...` to expose it to a harness
````

---

## Testing a Tool-Backed Skill

The tool's own unit tests are necessary but **not sufficient** — they don't exercise what agents touch.

- **Smoke-test the agent-facing seam.** Invoke the CLI end-to-end for the no-cost commands (via
  `main([...])` or a subprocess), asserting exit codes and key output. In our build this _immediately
  caught two real bugs_ a library refactor introduced (a broken re-export, a missing flag) that the
  unit tests never would. See [TESTING](testing.md).
- **Pin the contract.** A test that asserts the output schema / run-dir layout is your early-warning
  that a "harmless" refactor changed the thing agents depend on.
- **Eval the description's triggering** (does the skill fire on the intended prompts, and _not_ on
  neighbours?) — the harness's skill tooling (`skill-creator` in Claude Code) does this.

---

## Anti-Patterns & Gotchas

- **Two diverging copies.** A skill/wrapper copied into harness directories _and_ living in the
  repository, edited in one place. → repository-canonical source placed by Vercel `skills` (re-run
  `skills add` to reconcile), not a hand-maintained second copy.
- **Snapshot install mid-refactor.** `uv tool install` while restructuring → agents run stale code. →
  `uv run --project` wrapper.
- **Vague `description`.** The skill never triggers. → enumerate trigger phrases + anti-triggers.
- **Skill leaks internals.** It documents config knobs / module names → breaks on every refactor. →
  teach the stable contract only.
- **Hardcoded repo path in a "publishable" skill.** Works for you, breaks for everyone else. → keep the
  path only in the dev-loop wrapper; publish a real install.
- **No unattended-safety story.** First quota hit crashes a batch; an ambient key silently bills. → do
  safety as the gate before exposure.
- **Renaming a token that is a data/artifact key.** In the _tool_, a "vocabulary cleanup" that touches
  a JSON key or an output field is a contract change, not a rename — route task-specific keys through a
  hook and keep artifact keys stable. (A subtle one; see [REFACTORING](refactoring.md).)
- **Splitting a monkeypatched module** (in the tool's tests) silently breaks patch targets — repoint
  them to the submodule that now owns the object. See [TESTING](testing.md).

---

## Is the _Pattern Itself_ Worth a Skill? (the meta-question)

You will build more than one tool-backed skill. Tempting to extract a "scaffolder" skill that stamps
out the repo `skill/` dir + optional PATH adapter + `skills add` distribution + checklists. Decide
with the same discipline as any abstraction ([CONTRIBUTING](contributing.md) §3, [REFACTORING](refactoring.md)):

- **Do not abstract from one case.** A second concrete case enables comparison; extract when the
  common contract is stable and expected reuse/defect cost justifies it—often after a third
  occurrence. See [principles](principles.md).
- **Don't reinvent the harness's authoring tooling.** Generic “create/modify/evaluate a skill” is
  already covered by skill-authoring tooling. A worthwhile meta-skill would encode _your house
  conventions_ for tool-backed skills — repository layout, optional PATH-adapter template, Vercel
  `skills` distribution, stable-contract and safety checklists, and the **dev-vs-publish switch** —
  and compose with the
  authoring tool rather than replace it.
- **Cheap middle path:** capture learnings here; compare the second real instance; promote a
  scaffolder only when a stable common contract and measured repetition justify it.

**Heuristic:** A scaffolder earns its place when measured reuse and defect reduction exceed its
maintenance/migration cost. Two cases provide evidence, not an automatic extraction trigger.

---

## Checklists

**Authoring**

- [ ] `description` names trigger phrases + anti-triggers; distinct from neighbour skills.
- [ ] Body is routing + minimal usage + output-reading + safety; depth deferred to `contract`/`-h`.
- [ ] Stable contract vs volatile internals stated; agents told what NOT to hand-author.
- [ ] Fallback path labelled as degraded.

**Wiring (dev loop)**

- [ ] Skill text, capability (`scripts/`), and any optional PATH adapter live in the repository;
      exactly one discoverable `SKILL.md`.
- [ ] Vercel `skills` (`npx skills add`) places the folder into each harness's discovery location
      from the canonical source; no hand-maintained second copy. Any MCP dependency goes through MCPM.
- [ ] Invocation works from any cwd — a skill-relative `uv run --script scripts/...`, and/or a PATH
      adapter that supplies safe environment defaults.

**Safety (gate before exposure)**

- [ ] No money/credential leak; metered paths behind explicit opt-in.
- [ ] Parks-not-crashes on a recoverable limit; resume never re-charges.
- [ ] Tolerates a failing dependency; meaningful exit codes.

**Testing**

- [ ] Smoke test the agent-facing seam (not just library units).
- [ ] Contract/output-shape pinned by a test.

**Publish (when distributing)**

- [ ] Tool has a real install (`uv tool install`/PyPI); skill references the command name.
- [ ] No hardcoded local paths; skill dir self-contained.
- [ ] Only the install stanza differs from the dev-loop `SKILL.md`.

---

## Example — a Python/uv `debate` Skill

This illustrates one local implementation; its runtime, installer, output root, providers, and
failure policy are not corpus-wide requirements.

- **Tool:** a `uv`-managed Python package (`debate/`) with a `debate.cli:main` console script.
- **Skill text + optional PATH adapter** live at `repo/skill/{SKILL.md,debate}`; the Vercel `skills`
  CLI (`npx skills add`) places the folder into each harness's discovery location, and the `debate`
  adapter optionally exposes the command on `PATH`.
- **Wrapper:** enters the canonical live checkout and exports one `DEBATE_HOME`, so source changes
  are immediate and every agent writes to one shared, discoverable output home.
- **Contract:** commands (`panels/new/cost/run/show/status`), the project-dir layout, and
  `result.json` are stable; the internal `plan:`/`referees:`/`aggregator:` config is "still evolving"
  and agents are told not to hand-author it. `debate contract` prints the full I/O contract.
- **Safety (built before the skill shipped):** strips `ANTHROPIC_API_KEY` from the `claude -p` child;
  parks on a subscription-quota hit with a resumable marker; drops a failing/refusing voice with a
  recorded note (keeping a quorum).
- **Tests:** `tests/test_cli_smoke.py` drives the agent-facing commands and caught two real bugs a
  refactor introduced; `tests/test_import_boundaries.py` pins the layering.

The whole thing is the concrete instance this document generalizes from.

---

## Cross-References

- [API_DESIGN](api-design.md) — versioning and evolving a contract others depend on.
- [SECURITY](security.md), [ERROR_HANDLING](error-handling.md), [OBSERVABILITY](observability.md) — the unattended-safety story.
- [TESTING](testing.md) — smoke-testing the seam; contract tests.
- [REFACTORING](refactoring.md) — changing the tool without breaking the skill; data-key vs identifier renames.
- [DEPENDENCIES](dependencies.md) — `uv` project vs tool install; few/pinned/boring deps.
- [GIT_AND_VERSIONING](git-and-versioning.md), [DOCUMENTATION](documentation.md) — repo-canonical source; skill README.
- [CONTRIBUTING](contributing.md) §3 — recording what you deliberately do NOT apply; the second-case rule.
