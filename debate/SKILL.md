---
name: debate
description: >-
  Run a cross-vendor, recorded, resumable multi-model debate via the `debate` CLI. Use when the user
  says "spawn a debate", "get a panel / Delphi opinion", "have N models debate / critique / score X",
  wants the strongest case against a paper or claim (steelman), wants a decision or design
  pressure-tested by independent adversarial review, or wants multi-perspective feedback with
  surfaced disagreement. It runs propose → blinded critique → revise → (dialectical adversary) →
  arbitrate across LLMs from DIFFERENT vendors (Claude + GPT + others), writes every call to disk,
  and caches completed calls. Prefer this when independent model/vendor perspectives and an
  inspectable trace justify the cost. Pre-alpha: exact resume identity and hostile-materials
  security are incomplete; all real backends are remote and OpenRouter can incur charges. Scope:
  set-generation / steelman debates are live; numeric three-point (IDEA) estimation is not wired
  yet — don't reach for this for a single point-estimate + CI.
license: Apache-2.0
compatibility: Requires Python 3.11+ and uv; the first uncached invocation needs package-index network access. Real debates require remote provider CLIs or OpenRouter credentials and may incur charges.
metadata:
  author: markov-root
  version: "0.2.0"
---

# debate — cross-vendor multi-model debate, from the shell

Run the bundled launcher from the directory containing this `SKILL.md`:

```bash
DEBATE_SKILL=/path/to/the/installed/debate-skill
bash "$DEBATE_SKILL/scripts/debate" contract
```

An installer may additionally expose that launcher as the bare `debate` command. In the examples
below, `debate` means either invocation. **Shell out to it instead of role-playing a debate
in-context** when the added cost is warranted — a
single-model, in-conversation "panel" shares one set of priors, so its agreement is weak evidence.
`debate` gives you independent voices from different vendors, a recorded trace, and a resumable run.

## Safety boundary

- **Dry-run first.** `debate cost` makes no model call. A later run may cost money: OpenRouter is
  metered, and Claude/Codex CLI voices use remote vendor subscriptions.
- **Claude console-billing guard.** The `claude_code` adapter strips `ANTHROPIC_API_KEY` from the
  child process so the CLI does not silently switch from subscription auth to API billing.
- **Quota parking exists, but exact resume identity is still pre-alpha.** A recognized subscription
  limit records a pause and cached calls can be reused. Do not treat this as a complete crash-
  consistency or no-recharge guarantee until the run-integrity roadmap lands.
- **Tolerates a failing/refusing voice.** A voice that errors or refuses is dropped with a recorded
  note and the debate continues on the rest (as long as ≥2 remain); shown in `debate show`.
- **Do not submit sensitive data.** Questions, materials, prior outputs, and prompts go to the
  selected remote providers and are retained in a detailed local trace.

## Where debates live

One self-contained directory per debate under `$DEBATE_HOME` (or `--out DIR`) holds _both_ the
inputs (`items/`, `debate.yaml`, `cast.yaml`, `materials/`, `prompts/`) and outputs
(`runs/<run-name>/result.json`, `metrics.json`, per-call traces). The current compatibility default
is `~/Skills/exported-data/debates`; do not assume it is private or appropriate on another machine.

## The workflow

```bash
debate panels                          # list configured panels (pick one)
debate new  <slug> --panel <p> [--item paper.md] [--question "…"]   # scaffold ~/Skills/exported-data/debates/<slug>/
# edit items/v0.1.0.md (the debated item) and debate.yaml (question + criteria)
debate cost <slug>                     # DRY RUN — resolved plan/reducer + token estimate, NO spend
debate plan <slug> --json              # exact immutable task, policy, provenance, and hashes
debate run  <slug> [--run-name R] [--lean]     # run → runs/<R>/ (default R = panel name); resumable
debate resume <slug>                   # continue a paused/crashed run from cache (no re-charge)
debate show <slug>/runs/<R>            # options, disagreements, gate, metrics, dropped voices
debate status                          # every recorded debate + its stop reason
```

A bare `<slug>` resolves against the debates home, so `debate run steelman-x` just works. If a run
paused (`PAUSED` on a quota hit) or crashed, **`debate resume <slug>`** finishes it from cache — or
just re-run the same `<slug> --run-name R`. Exact reuse validation is still pre-alpha. To compare panels
or drafts on the same item, fork a run: `--panel P --run-name P` or `--item items/v0.2.0.md
--run-name v2`. `debate cost` makes no model call — run it first to validate the config and see the
resolved phases, aggregator, planned calls, and token estimate. `debate plan --json` emits the exact
immutable task, prompts, schemas, roles, policies, budgets, provenance, and hashes a run will use.

New scaffolds are strict version `1.0.0` inputs. Keep the `schema_id` and `schema_version` at the top
of `debate.yaml`, `cast.yaml`, and `materials/manifest.yaml`; do not remove or hand-bump them.
Unversioned projects created by older Debate releases still load through an in-memory compatibility
path. Unknown or misspelled fields, unsafe/duplicate IDs, incompatible backend knobs, and paths that
escape the project fail before a run directory or backend is created.

## Choosing a panel

- **Research exploration:** a **cross-vendor** panel can reduce shared-provider correlation, but
  agreement is still not proof or calibrated truth. Inspect the trace and residual disagreement.
- **Dev / smoke work:** `smoke-cc` / `dev-cc` use one remote Claude CLI subscription. They avoid an
  OpenRouter charge but are not local inference and monovendor agreement is weak evidence.

Optionally give a voice a **persona** in `cast.yaml` (`persona: threat-modeller`, or inline text) —
a domain-expert LENS that sharpens what it notices. Use expertise only, **never** a stakeholder or
ideological persona (that injects advocacy, exactly what a steelman must avoid). Off by default.
Backend-enforced per-voice knobs live under `call_policy`, for example
`call_policy: {reasoning_effort: high, timeout_s: 900.0}` on a `codex_cli` voice. Do not guess:
OpenRouter accepts per-voice `temperature`, Claude Code accepts `timeout_s`, and Codex accepts
`timeout_s` plus `reasoning_effort`; unsupported combinations are deliberately rejected.

## Grounding on sources (optional)

If the debate should cite a research corpus, add sources to
`$DEBATE_HOME/<slug>/materials/manifest.yaml`, then
`debate materials all <slug> --backend codex_cli --model gpt-5.5` to fetch + pin
them and cache abstracts. Modes (in `debate.yaml`): `context` (inject abstracts), `disk` (CLI voices
open files), `search` (voices search the web). During pre-alpha, fetch only trusted URLs:
redirect/private-network/size hardening and prompt-injection isolation are incomplete.

## Reading the result

`$DEBATE_HOME/<slug>/runs/<R>/result.json`:

- `options[]` — the generated set, each `{id, statement, rationale, confidence}` (for steelman: the
  distinct lines of argument, strongest single-source ones preserved, not voted down).
- `summary`, `disagreements[]` (cruxes the panel could not dissolve).
- `panel` — the voices + vendors + `monovendor` flag + any `dropped` voices.
- `gate` — deterministic checks; `dynamic_rounds` — stop reason + whether the run is complete.

`debate contract` prints the full input/output contract; `debate -h` teaches the whole surface.

## Keep to the simple surface

Edit the **minimal scaffolded** `debate.yaml` (`schema_id`, `schema_version`, `id`, `question`,
`criteria`, `item`) and **name a panel** (the `--panel` you scaffolded with). The panel supplies the
**cast** (voices/vendors); absent a `rounds:`
block the engine uses the **default plan** — floor (propose → critique → revise) + one adversarial
pass (red-team → respond), with a dynamic escalation pass that only fires if you raise the round cap
(see below). That default is the right choice for almost every debate — leave it alone unless you have
a specific reason. The command surface above, the project layout, and `result.json` are the stable
interface under active development. Treat it as pre-alpha: deliberate migrations are preferred, but
compatibility is not yet guaranteed.

## Tuning the protocol — the `rounds:` block (advanced)

The debate's shape is config, not code: add an optional top-level **`rounds:`** block to `debate.yaml`
to change it. This is an advanced surface — the default plan is fine for most work — but it is fully
wired. Read [round types](knowledge/0001-round-types.md) before changing it. The block:

```yaml
rounds:
  min: 3 # floor is always 3 (propose·critique·revise); min cannot go below it
  max:
    9 # CAP on phases run. Budget math: floor(3) + 2 per adversarial/escalation pass.
    # max MUST be ≥ the number of non-dynamic phases in `plan` or load fails fast.
  plan: # the ordered phases = the protocol. Omit `plan` to keep the default shape.
    - propose
    - critique
    - revise
    - { pass: adversarial } # → redteam · respond  (attacks the field; list N of these)
    - { pass: escalation, dynamic: true } # → escalate · respond (red-team may PROPOSE; repeats)
  referees: # optional; NAMES the deterministic checks to run at each injection point.
    before_revise: [near_duplicate, non_atomic, thin_rationale] # after critique
    before_respond: [unaddressed, overreach] # after the red-team
```

Key facts (all verifiable in `round-types.md`):

- **`aggregate` is appended automatically** as the closer — never list it. `propose` must be first.
- `cost` and `run` share the same resolver. Unknown keys/checkers, invalid bounds or pass shapes, and
  incompatible aggregators fail before a backend is constructed.
- **Two distinct adversarial mechanisms, independent axes:**
  - `{ pass: adversarial }` → `redteam · respond`: the adversary attacks the existing field. It does
    **not** repeat and does **not** need escalation — **list it as many times as you want more passes.**
  - `{ pass: escalation, dynamic: true }` → `escalate · respond`: the adversary is _licensed to propose
    a new option_ on the contested subset, and **repeats** until a stop rule (novelty exhausted / no
    contested focus / cap / token budget). Needs a red-team voice.
- **N independent adversarial passes, no escalation** — e.g. two clean red-team→rebuttal rounds:
  ```yaml
  rounds:
    max: 7 # floor(3) + 2 passes × 2 = 7 static phases; max must cover them
    plan:
      [propose, critique, revise, { pass: adversarial }, { pass: adversarial }]
  ```
- **`--lean`** (CLI) drops the whole adversarial/escalation surface → floor only (propose·critique·revise).
- There is **no CLI flag** for pass count — the round shape lives only in the `rounds:` block.

## Fallback

Only if `debate` is unavailable or the task is trivial, fall back to an in-conversation panel — and
label it explicitly as **weak, monovendor evidence**, not a substitute for a recorded cross-vendor run.
