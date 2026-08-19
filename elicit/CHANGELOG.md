# Changelog

## 0.2.0 — 2026-08-18

Broadened scope from coding-specific requirements to **domain-general
latent-knowledge elicitation**, informed by a literature pass (research 0002;
ADR 0002).

- Reframed `SKILL.md` around eliciting tacit knowledge from novice/imprecise
  users, with an up-front answer/ask/assume triage and a precision-vs-speed mode.
- New `knowledge/latent-knowledge.md` — tacit-knowledge technique catalog
  (laddering, CDM, scenarios, think-aloud, teach-back), anti-distortion question
  design (Pew/AAPOR/SHELF/Delphi), and finding the real task (XY problem, 5
  Whys, JTBD).
- New `knowledge/precision-vs-speed.md` — precision-first default, override to
  speed, probe-triage table, satisficing stopping rule.
- New `knowledge/teaching.md` — teach the user mid-task without derailing
  (permissioned better-way note, ZPD calibration, Socratic types, worked
  examples, metacognitive nudge).
- Added question-hygiene rules to `SKILL.md`; expanded `references/SOURCES.md`
  with the elicitation, survey-methodology, expert-elicitation, LLM
  clarifying-question, and learning-science literature. (task: 0001)

## 0.1.0 — 2026-08-18

Initial scaffold. Instruction-only skill: comprehend a task before acting,
re-verify comprehension on evidence, close with forward-looking questions.

- `SKILL.md` routing the three moments (comprehend / re-verify / advance) with an
  explicit trigger table and stopping rule.
- `knowledge/elicitation-rubric.md` — impact×uncertainty ranking, the ≤5 cap,
  question-quality bar, task frame, and assumption-log format.
- `knowledge/reverification.md` — evidence-triggered, single-question re-checks;
  no timed check-ins.
- `knowledge/forward-questions.md` — the task-exit pass and named techniques
  (pre-mortem, inversion, Socratic laddering, stakeholder framing).
- `references/SOURCES.md` — provenance from the 2026-08-18 market scan (Spec Kit,
  Kiro, BMAD, OpenAI model spec, clarifying-question research). (task: 0001)
