# Vale style pack — writing skill

A custom, offline, markup-aware **style pack** for [Vale](https://vale.sh) plus a
thin wrapper. It flags AI-tell stock phrases, universal clichés/corporate
filler, and overused constructions as **review notes only** — it is never an
AI-text detector, never an autofixer, and never produces a single quality
score.

## Layout

```
vale/
  writing_pack/
    .vale.ini                 Vale config; points at the bundled style.
    styles/writing/
      TierA.yml               Tier-A exact AI-tell stock phrases (warning / review)
      TierB.yml               Tier-B overused connectives (warning / review)
      Cliche.yml              clichés / stock phrases / corporate filler (warning / review)
      NotOnlyButAlso.yml      correlative "not only … but also" (warning / review)
      ItsNotAbout.yml         construction "it's not about X, it's about Y" (warning / review)
      Integrity.yml           unresolved source markers (error / blocking)
  fixtures/                   Markdown fixtures proving the correctness contracts.
  tests/test_vale_pack.py     stdlib unittest, offline.
  wrapper.py                  thin CLI wrapper (stdlib only).
```

## Prerequisite: the Vale binary

Vale is a **Go binary**, not a pip package — this repo cannot install it. Install
it from the [Vale release binaries](https://github.com/errata-ai/vale/releases)
or via a package manager (`apt`, `vale` in some distros, or the Homebrew CLI).
The wrapper detects the binary and, when it is missing, **reports the unmet
prerequisite and exits code 3** instead of fabricating results.

## Invocation

```bash
# list the review contract (non-blocking):
python3 wrapper.py fixtures/fixture-tier-a.md

# include the opt-in profile stats (still never a score):
python3 wrapper.py --profile fixtures/fixture-profile.md

# machine-readable JSON, all files:
python3 wrapper.py --json fixtures/*.md
```

The wrapper resolves the `writing_pack/.vale.ini` from its own location, so it
runs from any working directory. Point `--vale` (or the `VALE_BIN` env) at the
binary if it is not on `PATH`.

Exit codes: `0` clean (or review-only findings), `1` when the **integrity**
contract is non-empty (blocking), `2` on invalid input, `3` when the `vale`
binary is missing. Use `$?` to gate a pipeline on unresolved source markers.

**Division of labor:** this wrapper is a *lint screen*. The authoritative gate for
unresolved source markers is `source_wall.py --final` — it counts a blockquoted
`[[SOURCE NEEDED …]]` marker and blocks on it, whereas this Vale layer **masks**
quoted/blockquoted markers (a quotation of someone else's words must not fire
here). That divergence is intentional: the lint layer avoids false positives on
cited/blot-quoted prose, and the fact-integrity gate reads the raw document.

## The three never-merged contracts

The pack ships **one** style (`writing`) whose rules are split by severity into
three **never-merged** report groups. The wrapper separates them by level:

| Group        | Level        | What is shown                      |
| ------------ | ------------ | ---------------------------------- |
| integrity    | `error`      | unresolved `[[SOURCE NEEDED …]]` markers — **blocking** |
| review       | `warning`    | Tier-A exact phrases, Tier-B connectives, clichés/corporate filler — visible, **non-blocking** |
| profile      | `suggestion` | opt-in usage stats — **never combined**, only with `--profile` |

Every rule `message` says “review”, never “AI-written”.

## Correctness contracts (fixture-proven)

`tests/test_vale_pack.py` proves these offline (no Vale binary required):

1. **Inline-quotation mask** — a banned phrase inside `"double quotes"` MUST NOT
   fire; the same phrase unquoted MUST fire. Vale does not mask inline quotes, so
   the wrapper computes protected spans and drops any finding inside them.
2. **Blockquote scoping** — every rule scopes **out of** blockquote lines
   (`> …`); a finding inside a blockquote is dropped, and post-blockquote prose is
   left audible.
3. **Graceful absence** — a missing `vale` binary returns exit 3 with a clear
   message and no JSON output (no faked results).
4. **Never merged** — `integrity`, `review`, and `profile` findings stay in separate
   groups.
5. **Anchored integrity** — a bare prose mention of "SOURCE NEEDED" does NOT
   fire; only a real `[[SOURCE NEEDED …]]` marker blocks (Vale strips the `[[`
   opener, so the wrapper re-anchors against the raw text).
6. **Blocking exit** — a non-empty integrity group returns exit 1 so a pipeline
   can act; review-only output returns 0.
7. **Paragraph-boundary quote reset** — an unpaired opening quote in one
   paragraph never masks fully-unquoted prose in a later paragraph.
8. **Per-file masking** — multi-file runs mask each file against its own text,
   never merged offsets.
9. **Cliché screen (task 0023)** — an unquoted stock phrase fires; the same
   phrase inside an inline quote or blockquote does not; word-boundary near
   misses ("delved", "the game changed", "scaling") stay silent; no autofix,
   review-only messages.

Integration assertions (Tier-A fires, inline-quote counts, blockquote dropping,
integrity blocking, the cliché screen and its near-miss probes, and the
exit-code contracts) invoke the real Vale binary and are **skipped** when `vale`
is not installed, with an explanatory skip reason rather than a pass.

## Never an AI detector

This pack flags exact strings and constructions — it cannot and does not claim to
detect AI authorship, nor does it print a single aggregate number. It reports
only lexical divergences for a human to judge in context.