---
summary: How writeup-specific voices work and how to add one — the skill ships one general default voice and discovers local, writeup-specific voice/style profiles dynamically by their `voice_scope` frontmatter; this explains the convention and gives a repeatable method for extracting and authoring a new reusable voice module (kept local/private by default).
status: standing
role: knowledge
---

# Writeup-specific voices — discovery and authoring

The skill ships exactly **one** voice publicly: the general default
([`voice-default.md`](voice-default.md)) — plain, specific, and tuned to avoid
AI "tells" (see [`ai-tells.md`](ai-tells.md)). Everything past that — a personal
default voice, a publication's house style, a genre/format profile — is a
**writeup-specific voice** that lives **locally** and is **never shipped** in a
public export. There is no hardcoded list of them in `SKILL.md`; they are
**discovered dynamically** from what is installed.

## The discovery convention

A writeup-specific voice is a knowledge module that carries two frontmatter keys:

```yaml
visibility: private # local-only; dropped from any public export
voice_scope: <writeup type> # what it applies to, e.g. "house — company reports"
```

To resolve voice at **Frame**:

1. List `knowledge/` and read each module's frontmatter.
2. The modules carrying a `voice_scope:` key are the writeup-specific voices
   **available in this install**. Match the current writeup (from the reader
   contract and [`genres.md`](genres.md)) to a `voice_scope`.
3. If one matches, load it and apply it as an **override on the default voice**
   (it refines the default; it does not discard the AI-tell discipline).
4. If none matches — including a fresh public install, which has **only** the
   general default — write in the default voice. That is expected, not an error.

The harness's own file tools do this listing; no dedicated tool is required.

## Authoring a new reusable voice

When you find yourself re-specifying the same voice for a recurring kind of
writeup, capture it once as a module so the skill applies it automatically next
time.

1. **Name the scope.** One phrase for the writeup type it governs (the
   `voice_scope` value) — a publication, a genre, a format, a persona.
2. **Extract the voice from evidence, not vibes.** Prefer 2–3 _accepted_
   passages the target voice actually produced. Derive concrete, checkable
   traits: sentence rhythm, diction, stance/hedging, contraction and
   person policy, formatting and punctuation habits, and explicit
   do/don't examples. `scripts/voice_fingerprint.py` can baseline the samples so
   the voice is measurable, not impressionistic. Where only reference documents
   (a style guide, brand guidelines) exist, decompose those into the same
   traits.
3. **Distinguish voice from format.** Voice = how it sounds (diction, rhythm,
   stance). Format/genre obligations belong in a genre module (see
   [`genres.md`](genres.md)); a single writeup profile may carry both, but label
   which is which.
4. **Write it as a module** under `knowledge/`, with the frontmatter above plus
   the standard `summary`/`status`/`role`. Keep it faithful to the source and
   free of anything you would not want in a public repo — that is what
   `visibility: private` guarantees.
5. **For the LLM-facing distillation** — turning accepted samples into crisp,
   generalizing voice instructions — use the `prompt-engineering` skill's method
   (state the job, prefer positive instructions with the reason behind each,
   give examples). This skill owns _human-facing prose quality_; that skill owns
   _authoring the instruction_ that captures the voice.

A writeup-specific voice never overrides the fact-integrity floor or the
AI-tell discipline; it shapes surface and stance within them.
