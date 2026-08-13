# skills

A small collection of portable **[Agent Skills](https://skills.sh)** — a _capability_ (a runnable CLI
under `scripts/`) plus authored _guidance_ (`SKILL.md`) that AI coding agents such as Claude Code,
Codex, and OpenCode can install and invoke. Each skill is a self-contained folder; the capability
also works from a plain shell, and the skill adds discovery, judgment, and workflow on top.

Everything here is Apache-2.0 licensed. Status varies per skill — check each skill's `SKILL.md` and
`CHANGELOG.md`.

## Skills

| Skill                                           | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`debate`](debate/)                             | Run a **cross-vendor, recorded, resumable multi-model debate** from the shell: propose → blinded critique → revise → (dialectical adversary) → arbitrate, across LLMs from _different_ vendors, with every call written to disk and cached. Reach for it to pressure-test a decision, steelman or critique a claim/paper, or get surfaced disagreement from an inspectable panel. **Pre-alpha (v0.2.x):** set-generation / steelman debates work; real runs use remote providers and can incur cost. |
| [`software-engineering`](software-engineering/) | Apply a **disciplined, repository-aware engineering workflow** to non-trivial code work: resolve local project authority, select the smallest relevant guidance from a bundled knowledge library, establish a baseline before editing, run architectural fitness checks, and bind completion claims to evidence. Ships a deterministic `engineering` CLI (policy, checks, classification, documentation, inspection) plus a curated knowledge corpus.                                                |

Each skill folder is self-describing — start with its `SKILL.md`.

## Installing

These are [skills.sh](https://skills.sh) skills, installed with the `skills` CLI via `npx` (no global
install required). Check `npx skills --help` for the current flag set.

### For humans

```bash
# add one skill from this monorepo
npx skills add markov-root/skills --full-depth --skill debate

# install into specific agents (repeatable)
npx skills add markov-root/skills --full-depth --skill software-engineering \
  --agent claude-code --agent codex --agent opencode
```

Manage installed skills with `npx skills list`, `npx skills update`, and `npx skills remove`. Prefer
a global symlink install so every supported agent shares one canonical copy. Set `DISABLE_TELEMETRY=1`
(or `DO_NOT_TRACK=1`) for a telemetry-free install.

**Prerequisites.** The code-bearing skills run on **Python 3.11+** through
[`uv`](https://docs.astral.sh/uv/) — install `uv` first; the first uncached invocation fetches locked
dependencies. `debate` additionally needs a provider CLI (`claude` or `codex`) or an OpenRouter key
for _real_ runs; offline/fake runs need neither.

### For agents

If you are an AI agent with shell access, install exactly as above — `npx skills add …` registers the
skill for your harness, after which its `SKILL.md` trigger surfaces it to you automatically. You do
not need to read a whole skill up front: match the task to the skill's `SKILL.md` description, then
invoke it. Re-run `npx skills update` to pick up new versions.

## MCP servers

These skills are plain CLIs and need **no** MCP server. If you separately run
[Model Context Protocol](https://modelcontextprotocol.io) servers, we recommend
**[mcpm.sh](https://mcpm.sh)** (MCPM) for MCP discovery, installation, profiles, updates, and
per-client configuration — the MCP-side complement to what `skills.sh` does for skills. Keep the two
concerns separate: `skills` for capabilities and guidance, `mcpm` for MCP server provisioning.

## License

Apache-2.0. See each skill's `LICENSE` and `THIRD_PARTY_NOTICES.md`.
