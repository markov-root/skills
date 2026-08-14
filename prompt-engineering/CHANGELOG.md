# Changelog

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
