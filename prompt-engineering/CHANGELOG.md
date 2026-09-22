# Changelog

## 0.2.0 — 2026-08-14

- Add a `prompt_security` route and `knowledge/prompt-security.md` module (task 0016): trusted-vs-untrusted
  context hierarchy, delimiter discipline for interpolated data, tool-output-as-data, exfiltration/URL/markdown
  sanitization, defense-in-depth controls, and an abuse-case regression matrix. Adds positive/neighbor/negative
  router fixtures and OWASP + Google layered-defense sources.
- Add a dated `knowledge/provider-matrix.md` and refresh `knowledge/model-era.md` to the current era (task 0017):
  Opus 4.8 + Claude 5 family (Fable 5, Sonnet 5, Haiku 4.5) with per-model thinking defaults, effort levels,
  sampling restrictions (non-default `temperature`/`top_p`/`top_k` → HTTP 400 on current thinking models),
  128k max output, `budget_tokens`/prefill removal, and structured-output knobs. Anthropic column verified against
  first-party docs + the `claude-api` skill; OpenAI/Google rows are web-researched and marked for spot-check.
  Registers the refresh in the `model-era` freshness domain with a dated review record.
- Honor the "every claim traces to `SOURCES.md`" contract (task 0018): add sourced entries for CFPO, HyDE,
  Query2doc, MQM, and ICU, and add a `check-publication` provenance gate that fails the build when a cited
  named method/standard has no `SOURCES.md` entry. Wired into the dev suite.

## 0.1.2 — 2026-08-14

- Harden the eight `scripts/*_contract.py` checkers (task 0014): reject empty/blank evidence on
  `FOUND`, enforce per-status invariants (non-`FOUND` states carry no labels/text/evidence), validate
  A/B changed-axis, judge-rubric fields, and glossary policy, and add type guards so malformed input
  returns a clean error instead of a traceback. Adds negative-mutation tests.
- Improve `scripts/prompt-lint.py` accuracy and robustness (task 0015): coercion now matches penalty
  phrasing (not the noun "threat model"), reasoning/self-verification ignore quoted/code spans and
  catch more real phrasings, the output-contract check needs real shape syntax, and non-UTF8 input
  returns a clean exit 2. Adds a benign+adversarial fixture suite.
- Make `scripts/agents-link` genuinely POSIX-`sh` clean and refuse a symlinked `AGENTS.md` (task 0019).

## 0.1.1 — 2026-08-14

- Fix a dangling reference in `knowledge/context-engineering.md`: the cache-measurement helper lives
  in the `situational-awareness` skill (the retired `context-aware` name was still referenced).

## 0.1.0 — 2026-08-02

- Establish the self-contained skills.sh artifact with portable knowledge, runtime helpers,
  source provenance, schema assets, and release metadata.
