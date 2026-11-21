# Changelog

## 0.11.0 — 2026-11-19

- New `scripts/pangram.py`: an opt-in screen that sends a draft to the Pangram API and lists the
  most AI-like windows with line anchors. One detector's opinion; never a gate, never an authorship
  verdict. Each check is logged to a private local corpus, with provenance (who wrote the text) kept
  apart from the verdict. Responses are cached by text hash. `corpus stats`, `corpus mine`
  (contrastive log-odds candidate tells), `corpus terms` (whether each watch-list entry predicts
  AI-labelled windows), `corpus style` (topic-robust style features, including before/after
  pairs), `corpus pairs`, `corpus import` (earlier Pangram results, no API call), `corpus label`
  and `corpus list`. Reads `.md`, `.tex` and plain text; reports six categories (label ×
  confidence) with an OK/Review/Rewrite status. Exit 0 ok, 2 usage, 3 unavailable,
  4 credits/rate limit, 5 task failed.
- `ai-tells.md`: new "Detector signals are not tic lists" section. Rebuild sentences rather than
  launder words, and evolve the catalogue from corpus evidence.

## 0.10.0 — 2026-11-10

- New `scripts/revoice_check.py`: lossless re-voice preservation check. Compares two versions of a
  slide-sectioned script and reports every number, direct quotation and `## <slide-id>` heading lost
  or altered, plus stand-off annotation anchors orphaned by the new version. JSON or a one-line
  summary; exit 0 lossless, 1 loss found, 2 usage error.

## 0.9.4 — 2026-11-10

- Frame step opens with an explicit voice-discovery instruction, so a talk or presentation script
  picks up an installed presentation voice even when the task looks like folder setup.
- Genre routing gains a talk / presentation row.
- Private presentation-voice module: evidence path updated after a repository reorganisation.

## 0.9.3 — 2026-11-09

- Private presentation-voice module: coherence calibration from a read-aloud run-through.

## 0.9.2 — 2026-11-08

- Private presentation-voice module: timing treated as advisory; intro guidance refined.

## 0.9.1 — 2026-11-05

- Private presentation-voice module: re-voicing rules derived from paired written and spoken
  material.

## 0.9.0 — 2026-11-05

- Private presentation-voice module: distinguishes *drafting* new material from *re-voicing* a
  script whose content is fixed; adds a calibration from a multi-talk corpus (pacing, spoken
  structure, numbers). Supporting evidence lives in private reference files that are excluded from
  public export.

## 0.8.0 — 2026-11-04

- Private presentation-voice module: adds argument-shape, density and stance guidance with
  measured targets; private voice-baseline references ship alongside it and are excluded from
  public export.

## 0.7.0 — 2026-10-11

- **Report voice revised against external review of a published report.** The
  private report-voice module now records each reviewer-driven rule beside the
  feedback it came from, because a rule without its evidence drifts back to taste.
  Changes include: subject-anchored framing becomes a stated choice rather than
  the default; table emphasis follows "more salient is worse" consistently; bold
  is reserved for sentences that are themselves findings; small-denominator counts
  precede rates; one presentation and one visual channel per quantity; and
  substantial AI drafting is disclosed to reviewers. Two unresolved reviewer
  disagreements are recorded as per-report decisions. No public module changed.

## 0.6.1 — 2026-09-24

- **Duration governs how much mechanism survives.** The private spoken-voice
  module's advice to explain mechanisms through ordinary actions was calibrated
  on a briefing with room to breathe, and inverts under seven minutes. Added a
  rough per-duration guide and the failure mode it prevents: mechanism passages
  are usually the best-written part of a draft, so they survive editing on
  quality while the argument they serve gets squeezed. Cut by duration budget,
  not by paragraph quality.

## 0.6.0 — 2026-09-24

- **Spoken-voice calibration from a second evidence set.** A locally-installed,
  private voice module for spoken talks gained a dated calibration section drawn
  from seven further passages (five rehearsal transcripts, two the author had
  polished for reading). It records mechanics a written-prose profile does not
  cover — chiefly that a dash has no spoken realisation, so scripts should carry
  none — plus six explanation moves the earlier distillation missed, and two
  caveats for measuring a spoken voice with `voice_fingerprint.py`: contraction
  rates read low in any transcript-derived baseline because speech-to-text
  expands them, and the fingerprint's hedge metric disagrees with
  `scripts/hedges.py` on the same draft. No public module changed.

## 0.5.1 — 2026-09-22

- **`voice-default.md`: describe the voice modules by role, not by name.** The
  fallback voice module named two `visibility: private` modules (the writer's
  default voice and a house style) in its summary and its "Using your own voice"
  section, and linked to both. On export those modules are dropped, so the public
  artifact carried a house token and two pointers to files that do not ship — the
  publish token gate refused the release. The paragraph now names the _convention_
  (`knowledge/` voice modules that `SKILL.md` routes to by genre), which is true
  both in-house and published. First release of this skill to the public mirror.

## 0.5.0 — 2026-09-04

- **`ai-tells.md`: "AI editing leaves its own trace" (research 0002).** New note
  that AI-_edited_ human text is separable from both human and AI-generated text
  (EditLens), so this skill's own core act — editing — can _introduce_ the tell;
  the fix is to edit toward specificity and voice, not toward uniformity. Two
  provenance rows added to `references/SOURCES.md` (EditLens, DAMAGE). The
  post-training mechanism and vendor false-positive figures were reviewed but kept
  out of the shipped knowledge as non-actionable for a writing agent — provenance
  only, in the research record.

## 0.4.0 — 2026-08-21

- **Grammarly-class screen suite + writing-health panel (tasks 0019–0024).** Five
  stdlib, non-blocking, per-baseline screens — readability/length
  (`scripts/readability.py`), syntactic hedges + passive + nominalization
  (`scripts/hedges.py`), connective/AI-transition overuse
  (`scripts/connectives.py`), sentence-opener + expletive (`scripts/openers.py`),
  and the cliché Vale rule — composed by the **writing-health panel**
  (`scripts/writing_health.py`) into ONE diagnostic. Each metric is a divergence
  from the author's own baseline, **never an aggregate score**, never a gate; a
  failing sub-screen is reported-and-skipped and never crashes the panel. All
  cross-vendor red-teamed (precision / false-positive and contract).
- **Public-export safety (task 0033).** `scripts/publish.sh` stages the artifact,
  drops `visibility:private` modules by literal path, rejects symlinks, verifies
  the real staged tree (shared BOM-aware frontmatter classifier + link checker),
  and refuses to publish (fail-closed) on any private leak, dangling link, or
  denied token; `--dry-run` never mutates the destination.

## 0.3.0 — 2026-08-21

- **Dynamic writeup-specific voice discovery (task 0031, ADR 0008).** The skill
  ships only the general default voice publicly; personal / house / genre voices
  are local-only, discovered dynamically by a `voice_scope` frontmatter key
  (`SKILL.md` hardcodes no private links), so a public export is link-clean and the
  voice layer is extensible. New `knowledge/authoring-voices.md` documents the
  convention and how to author a new reusable voice.

## 0.2.0 — 2026-08-21

- **Vale pack:** new `Cliche` rule (task 0023) — a universal cliché /
  stock-phrase / corporate-filler screen (~48 word-boundary-anchored tokens),
  flag-not-assert at `warning` level, alongside Tier-A/Tier-B. Fixture-proven:
  unquoted phrases fire; the same phrase inside inline quotes or blockquotes is
  masked; near misses ("delved", "the game changed", "scaling") stay silent; no
  autofix; every message says "review". Also: the wrapper no longer reports a
  spurious "unexpected Vale JSON shape" notice on clean (zero-finding) runs.
- **Knowledge:** `ai-tells.md` lexical subset extended with the same cliché /
  corporate-filler phrases, framed as a screen (clusters, not a banned list).

## 0.1.0 — 2026-08-21

First release. A risk-calibrated editorial control loop, not a prose assembly line.

- **Loop:** `SKILL.md` — Frame → Make → Challenge → Deliver, a short default path
  with risk-triggered escalation; 3 gates + 2 screens; critics veto, never
  approve, the writer closes; an evidence-bound completion contract; an explicit
  uncertainty hatch.
- **Knowledge:** `voice.md` (default voice), `house-style.md` (house editorial
  stance, standards, tone, formatting, and the per-output voice map with the
  papers/reports no-contractions/"we" override), `genres.md`, `topics-page.md`,
  `learning-notes.md`, `ai-tells.md`, `specificity.md`, `revision.md`,
  `voice-default.md` (neutral fallback). Provenance in `references/SOURCES.md`.
- **Fact-integrity floor (the moat):** evidence modes, claim ledger, specificity
  ladder, `[[SOURCE NEEDED]]` markers + the source wall — specificity is never
  fabricated.
- **Measurement scripts (stdlib, offline, self-contained):** `source_wall.py`
  (marker/source-wall blocker, `--final` blocks unresolved markers),
  `voice_fingerprint.py` (baseline/compare screen vs. the writer's own accepted
  prose — never an AI score), `trace_map.py` (per-paragraph coherence renderer),
  `opening_pick.py` (blind alternative-opening picker), `eval_harness.py`
  (blind-pairwise eval stub with a separate answer channel), and `scripts/vale/`
  (a lexical, flag-not-assert style pack; three never-merged contracts; no
  autofix; requires the Vale binary).
- **Public/private:** general craft ships shareable; the writer's voice/house
  modules are tagged `visibility: private` — installed locally, excluded from any
  public export, guarded by the `tests/smoke.sh` token-gate.
