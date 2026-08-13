# prompts/personas/ — optional per-debater expert lenses (task-0008)

A **persona** is a short system-prompt fragment prepended to ONE voice's prompts, giving it a
distinct expert lens so a panel can be composed of complementary specialists. Personas are **off by
default** — a debate with none is byte-identical to a plain run.

## The one rule: expertise, not interest

> **Domain-expert personas only. Never stakeholder or ideological ones.**

A domain lens ("you are a threat-modeller", "you are a measurement statistician") _raises_ validity —
it makes a voice notice failure modes a generalist misses. A stakeholder/ideological persona ("argue
as a privacy activist", "argue for industry") _injects bias_ — it is advocacy, precisely what a
steelman must avoid. Keep personas about how someone _reasons_, never what they _want_.

## Using one

In a panel (`configs/panels.yaml`) or a project `cast.yaml`, add a `persona` to a voice spec — either
inline text or the **name** of a file here (without `.md`):

```yaml
proposers:
  - id: tm
    backend: openrouter
    model: anthropic/claude-opus-4.8
    persona: threat-modeller # → prompts/personas/threat-modeller.md
  - id: stat
    backend: codex_cli
    persona: "You are a measurement statistician; scrutinise estimators, power, and confounds."
```

The persona shapes that voice only and is **never shown to peers or the arbitrator** — blinding is
preserved (a persona is a lens, not an identity label). Each voice's persona is recorded in
`result.json` provenance so a run is self-describing.
