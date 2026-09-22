# Changelog

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
