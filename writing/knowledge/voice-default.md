---
summary: A deliberately neutral, domain-agnostic fallback voice — used only when neither the writer's default voice module nor a house-style module applies; also documents the SHAPE of a voice module so new ones can be added inside the skill.
status: standing
role: knowledge
---

# Default voice (replace with your own)

**This is a neutral placeholder, not a target to imitate.** It exists so the skill
runs usefully before you supply a voice, and so you can see the _shape_ of a voice
module. Replace it with your own (below). A committee-neutral voice is exactly the
flattening the skill fights — the point is _your_ voice, resolved per genre.

## What a voice module is

Voice = the persona the reader perceives; tone = the situational attitude;
register = the language variety for the situation. A voice module makes those
explicit so revision preserves them instead of sanding them off:

- **Persona & stance** — who the writer sounds like, and whether they take
  positions or stay neutral.
- **Register & formality** — where on the gradient (intimate ↔ institutional),
  and what moves it.
- **Lexical preferences** — words and constructions to favor; ones to avoid;
  contraction and jargon policy.
- **Rhythm** — sentence-length variation, paragraph length, punctuation habits.
- **Do / don't** — the two or three things that most define the voice.
- **Calibrated passages** — 3+ accepted samples per genre that _are_ the voice;
  these anchor the voice-fingerprint baseline (`scripts/voice_fingerprint.py`).

## The neutral default (illustrative only)

- **Persona:** a clear, competent explainer; friendly but not chummy; takes a
  position when the evidence supports one.
- **Register:** professional-plain — the register of a good documentation page or
  a well-edited trade article. Contractions allowed. Minimal jargon, defined on
  first use.
- **Favor:** concrete nouns, active verbs, one idea per sentence, examples over
  adjectives, varied sentence length.
- **Avoid:** throat-clearing openers, decorative antithesis, hedging where a
  judgment belongs, stock transitions, filler intensifiers.
- **Do / don't:** _Do_ lead with the point and earn every paragraph. _Don't_
  summarize what you just said or end by restating the prompt.

_Illustrative calibrated line:_ "The cache holds results for five minutes. After
that, the next request recomputes them — so a burst of traffic right after
expiry hits the database hardest." (Concrete, active, a real mechanism, no
decoration.)

## Using your own voice

The writer's default voice and any house style live **inside** the skill, as
`knowledge/` voice modules that `SKILL.md` routes to by genre; this neutral module
is only the fallback for when neither applies (ADR 0007). To add or change a voice,
edit the module that owns it (or add a genre-keyed voice module alongside this one)
— don't point at an external file. Build a fingerprint baseline from accepted passages with
`python3 scripts/voice_fingerprint.py baseline --genre <genre> passage1.txt …` so
the compare screen measures a draft against real accepted writing, not a generic
ideal.

Modules carrying a specific writer's voice/house material are tagged
`visibility: private` and excluded from any public export (the `tests/smoke.sh`
token-gate guards that boundary). See [`genres.md`](genres.md) for per-genre
routing and [`ai-tells.md`](ai-tells.md) for what erodes a voice.
