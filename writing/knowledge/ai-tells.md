---
summary: The empirically-grounded catalogue of AI-writing "tells" (lexical, syntactic, tonal, structural) framed as review judgment — flag clusters, never single words; the real fix is specificity and stance, not synonym-swapping.
status: standing
role: knowledge
---

# AI-writing tells — as review judgment, not a banned list

As of 2026 the strongest evidence for "AI tells" is **lexical and corpus-level**;
the weakest is single-token folk detection. **A word is rarely proof — clusters
of words, uniform rhythm, over-scaffolded structure, and missing specificity are
the tell.** Use this catalogue as _review judgment_ (context decides), never as a
gate. The lexical subset is enforced only as a **non-blocking screen** by the Vale
pack (`scripts/vale/`); this file is the judgment behind it.

The skill never uses an AI-text _detector_ as a **gate** or an **authorship
verdict** about anyone: as detectors of _who_ wrote a text they are gameable,
biased against non-native writers, and flag good human prose. The primary,
detector-free signal is divergence from the author's _own_ accepted baseline
([`voice-default.md`](voice-default.md), `scripts/voice_fingerprint.py`), never an
"AI score."

A detector is legitimate in the _opposite_ direction: as an **opt-in
self-adversarial screen** on your _own_ AI-assisted draft — "where does this read
as AI, and how do I change it?" There, gameability is the point (ADR 0006). The
default response is still the real fix below — specificity and stance, not
laundering words; deliberate detector-evasion is an explicit mode you choose, not
the automatic behavior.

## Lexical tells (flag clusters; replace only when vague or decorative)

A recurring watch-list, useful only in aggregate: _delve, tapestry, realm,
landscape, boasts, testament to, navigate/navigating, in the realm of, it's worth
noting, crucial, pivotal, underscores, leverage, robust, seamless, elevate,
unlock, transformative, game-changer._ Corpus studies found sharp post-2022 rises
(e.g. "delves" ~28× expected frequency in biomedical abstracts). But vendor data
contradicts folk lists, so treat these as **style hygiene, not authorship proof**
— and never purge a word the author uses well.

A second, deliberately **universal** screen covers clichés, stock phrases, and
corporate filler — bad prose in any decade, not evidence of AI authorship. Its
seed vocabulary is: _in today's fast-paced world; delve; tapestry; a rich
tapestry; testament to; at the end of the day; it's worth noting; navigating the
landscape; in the realm of; plays a pivotal role; plays a vital role; when it
comes to; needle in a haystack; the fact of the matter; last but not least; first
and foremost; paradigm shift; game changer; low-hanging fruit; move the needle;
at scale; unlock the potential; in conclusion._ The broader screen also includes
familiar corporate and editorial placeholders such as _think outside the box;
circle back; touch base; boil the ocean; hit the ground running; going forward;
synergy; best-in-class; world-class; mission-critical; win-win; core competency;
actionable insight; key takeaway; holistic; take it to the next level; push the
envelope; raise the bar; at the forefront of; in a nutshell; needless to say; it
goes without saying; few and far between; each and every; only time will tell;
tip of the iceberg; the elephant in the room; leave no stone unturned; back to
the drawing board; a double-edged sword; level the playing field; at a
crossroads; when all is said and done; cut to the chase; a perfect storm;
reinvent the wheel._ The Vale pack screens this vocabulary across its lexical
rules with word-boundary matching and quoted-material masking. Same discipline
as above: this is a screen, not a banned list — the tell is clusters and
repetition; keep any phrase the author uses well and exactly.

## Syntactic / rhetorical tells

- **Uniformity is a stronger tell than any phrase.** Human writers vary sentence
  length more; model prose shows lower variation, more coordination and empty
  parallelism, fewer subordinate structures. Vary rhythm; read aloud — restore
  genuine variation, don't scatter random irregularity to beat a metric.
- **The decorative antithesis template** — "It's not just X, it's Y," "not only X
  but also Y," "more than X, it is Y" — is a tell _when the second clause merely
  restates the first in grander language_. Keep it only when Y adds real
  information.
- **Rule-of-three lists, "from X to Y" sweeps, "Firstly / Secondly / Finally"
  over-signposting** feel pre-scaffolded. Keep only distinctions that carry
  information.
- **Em dashes** are now culturally read as AI-ish but are _not_ reliable proof —
  a valid punctuation mark. Do not over-correct grammar to dodge a folk signal;
  over-correction is itself a failure mode.

## Tonal tells

- **Sycophancy is measured, not a vibe.** RLHF assistants over-agree; the "slop"
  tone is relentlessly agreeable, noncommittal, motivational, and over-explanatory
  — it validates, summarizes, and balances instead of taking a stance. Useful in
  support chat, deadening in essays, criticism, fiction, op-eds, serious
  nonfiction. Take a position and hold it (see the edge ledger in the loop).
- **The "curse of the summary":** compressing conflict, scene, and judgment into a
  neat abstract that sounds right but loses texture, causality, and stakes.

## Structural tells

The default sandwich (broad opener, balanced middle, tidy conclusion restating the
prompt); listicles where every item is bold-label + colon + generic explanation
with no example; over-scaffolding; throat-clearing openers ("In today's
fast-paced world," "As we navigate," "Let's dive in"); "In conclusion";
bold-first bullets and lists where prose belongs. **In flowing prose, bold should
be rare** — if a sentence needs bold to carry its importance, rewrite it so the
words do (the deliberate exception is a structural format like a scannable
learning note, [`learning-notes.md`](learning-notes.md)).

More specific, high-signal patterns:

- **Participial-tail pseudo-analysis** — sentences trailing off with
  ", highlighting the importance of…", ", underscoring the significance of…",
  ", demonstrating the enduring relevance of…". The participle gestures at meaning
  without arguing anything. Give the point its own sentence with a real argument,
  or cut the tail.
- **Significance / legacy inflation** — puffing up importance indiscriminately: a
  minor change "marks a pivotal moment," a routine publication "underscores the
  transformative impact." If something matters, show why with evidence; if it
  doesn't, don't dress it up.
- **"Despite its [positive], [subject] faces challenges…"** followed by vaguely
  optimistic speculation. State real limitations directly — don't cushion them
  with praise or resolve them with hand-waving.
- **Surface/punctuation tells** (aware, don't over-correct): rigidly consistent
  Oxford commas, flawless spelling across thousands of words, and consistent
  American English from a non-American context are weak signals — never something
  to break deliberately, but part of the cluster.

## AI editing leaves its own trace (this skill's own hazard)

Detection is not only about text generated from scratch. **AI-_edited_ human text
is separable from both human-written and fully AI-generated text.** This is the
failure mode closest to home, because editing is exactly what this skill does: "I
only lightly cleaned it up" is not a defense — a smoothing edit that regularizes
rhythm, neutralizes idiom, and tidies structure _is_ the tell being introduced.
Edit toward the author's specificity and voice (add a real detail, keep an odd
true phrase), not toward frictionless uniformity.

## Detector signals are not tic lists

A detector reads the whole distribution of a passage, not its banned words. In a
model-report corpus (2026-11, Pangram 4.1), agent-drafted sections averaged 78% of
words flagged while containing almost none of the lexical watch-list above. In
human-rated windows, parentheses, dashes, semicolons, and "we" were two to four
times more common. Elliptical back-references ("did so", "the same") and
possessives were more common in AI-rated windows. In one case, sections an agent
drafted scored 54–92% AI even after tic removal. The lead editor's hand rewrites of the same facts scored 0–3%.
The rewrites broke enumerating sentences into lists, cut chains of numbers, used
"we", explained for a lay reader, and kept colons and asides. Some of those moves
broke the house conventions then in use. What moved the detector was **human-built
sentences over agent-supplied facts**, not a cleaner word list. So when the opt-in
screen (`scripts/pangram.py`) flags a window:

- treat the window as a place to rebuild the sentences: reorder by the reader's
  question, vary length and shape, and add the specific claim, stance, or example
  the passage is missing;
- don't swap synonyms or delete tics and re-check; that is laundering, and it
  fails twice (meaning drifts and detectors still catch it; DAMAGE);
- keep the house conventions unless the writer chooses otherwise. A detector score
  never overrides voice or genre rules on its own;
- log the before and after with `--pair-of`, so the corpus learns which moves
  worked.

This catalogue is meant to be measured over time, not to grow without limit. The
corpus is a private log of detector checks (ADR 0009):

- `pangram.py corpus terms` reports whether each watch-list entry above actually
  predicts AI-labelled windows;
- `corpus style` compares topic-robust features (punctuation, "we", rhythm,
  back-references) between AI-rated and human-rated text, or between the before
  and after of real rewrites (`--by pairs`);
- `corpus mine` proposes candidate words and phrases by contrastive log-odds.
  Within a single document it picks up topic rather than style, so treat its
  output as a lead to read, not a tell.

Add, demote, or retire an entry only on that evidence plus a read of the
examples in context. Note the corpus size and the detector version behind the
change.

## The real fix (not synonym-swapping)

Next-token prediction favors high-probability continuations (safe transitions,
familiar metaphors, balanced antithesis, mid-register vocabulary); instruction
tuning infers "helpful = visibly organized." **The fix is not laundering words to
hide traces. It is making the prose more accountable to reality, voice, and
intent:**

- **Specificity** — names, dates, numbers, scene, sensory detail, causal claims,
  real tradeoffs, examples that could fit _no other piece_. But specificity is
  **evidence-bounded** — never invent a study, number, or date to get it (see
  [`specificity.md`](specificity.md)).
- **Stance** — say the thing; cut the hedging and the both-sides balance where a
  judgment belongs.
- **Varied rhythm**, cut throat-clearing, collapsed decorative antithesis, fewer
  headers, and conclusions that land without announcing themselves.

Frequencies drift as models are trained against their own tells — re-verify before
hard-coding any list. Provenance: [`references/SOURCES.md`](../references/SOURCES.md)
(§ AI-writing tells).
