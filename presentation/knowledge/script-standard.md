# Script standard: what a spoken script must do

`script-format.md` says what the file may contain. This file says what the words must do.

## Before drafting a word

**Load the voice first.** Before drafting or revising any spoken text (scripts, speaker notes,
talk prose), load the `writing` skill and its presentation-voice profile if one is installed.
Never invent a register. If no voice profile exists, ask for transcripts of the speaker's own
talks and work from those.

## The speaker reads `speaking.md`

The speaker reads `vX.Y.Z/speaking.md` from the latest version, which holds only what they will
say. Point them at that file, never at `src/`.

## Content rules

- **Say it straight.** Each spoken sentence carries its full weight. Do not caveat every line.
  Caveats, method limits and source detail go in `note` annotations and Q&A preparation.
- **No shoehorning.** An example, number or section appears only where it proves the point at
  that moment. Each step of a module answers the question the previous step raised. Cut what only
  exists to show data.
- **Evidence is the backbone, not a feature.** Results run through every module where they fit.
  They are never staged as a special "someone measured it" moment.
- **Newest evidence first.** At the pace of AI, results go stale within months. Prefer this
  month's measurement to last year's, and say which year each study ran and which model generation
  it used.
- **Inform, don't tailor.** Show the range of options and what other jurisdictions or
  organisations actually do, with concrete examples. Do not prescribe institution by institution.
  Do not explain the audience's own country, laws or institutions to them.
- **Advice by who it is for.** Organise practical advice by the audience's roles: "if you are an
  agency that does X, do Y, because otherwise Z; here is who tried it." Back it with several
  sources saying the same thing.
- **Never read the slide aloud.** The slide and the speaker carry different halves of the point.
- **Translate terms at first use,** and explain a mechanism in ordinary actions.
- **Timing is advisory** (`protocol.md`).

## Before approving

Run `present script check`. It reports:

- format findings;
- orphaned or ambiguous anchors;
- claim concerns (`claims.md`);
- with writing's re-voice check installed, any number, quotation or slide heading lost since the
  previous version. A re-voice that loses a number is a defect even when the sentence reads better.
