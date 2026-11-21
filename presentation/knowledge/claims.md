# Claims: advisory tiers, licence, and flag-don't-fix

## The ledger

One ledger per talk, `research/claims.md`: a Markdown table `ID | Claim | Source | Status | Notes`.
IDs match the repository's pattern (`[claims] id_pattern`, default `C-\d+[a-z]?`).

| Status | Meaning | May be spoken? |
| --- | --- | --- |
| `VERIFIED` | read at the primary source; figure or quotation checked verbatim | yes |
| `SECONDARY` | a reliable secondary source only | yes |
| `SOFT` | judgement, estimate or characterisation, deliberately not a fact | yes, worded as a view |
| `UNVERIFIED` | asserted but not yet checked | reported as a high concern |

A **load-bearing claim** is any number, date, quotation, attribution, named institution or
factual assertion about a third party. Each one gets a row, and the script cites it through an
annotation anchor, never inline.

Keep one table, or repeat the header after any blank line: a blank line ends a Markdown table, and
rows after it are reported as unread. `[enforced: present claims list — every unread row reported
by line]`

## Citing by reference

A `Source` cell may cite the evidence by a typed reference instead of, or beside, free text.
The reference then resolves through its owner's CLI:

| Reference | Cites | Resolved by |
| --- | --- | --- |
| `research:<ref>[@<version>]` | a corpus record, e.g. `research:deepmind/frontier-safety@1` | `research cite` |
| `dataset:<id>[@<release>][/<table>[#<row-ref>]]` | a dataset release, table or row | `datasets releases`, `datasets get` |

- **Draft without a version; pin before you approve.** `present claims pin` lists the exact
  version each unpinned reference resolves to. Add `--apply` to write them into the ledger. It
  rewrites only the reference text and leaves every other byte alone. `[enforced: present claims
  pin — dry run unless --apply]`
- **`claims check` resolves every reference.** A reference that does not resolve is
  `source_unresolved` (medium). A pinned reference older than the current version or release is
  `source_newer_available` (low). Treat that as a prompt to re-read the newer evidence, which
  serves the recency rule.
- **A missing CLI is reported, never passed.** The check still runs and reports
  `capability_unavailable` once per missing CLI, naming how many references went unchecked.
  Neither CLI is consulted for a ledger that holds no references of its type. `present doctor`
  shows where each CLI was found. Set `PRESENT_RESEARCH_CLI` or `PRESENT_DATASETS_CLI` to point
  at one explicitly, or to an empty value to switch it off.
- **Deck data uses the same references.** In `slides.yaml`, `"dataset:<id>[@<release>]/<table>"`
  stands for the table's rows and `…#<row-ref>` for one row. `{from: "dataset:…", column: <name>}`
  stands for one column. `deck build` snapshots each one into `src/data/` with its release, every
  row's reference and its sha256, records it in `src/data/datasets.lock.json`, and lists it in the
  receipt under `inputs.datasets`. Later builds read the snapshot and never query `datasets`, so a
  rebuild works without it. An unpinned reference keeps its first release until you delete its
  lock entry. Commit the snapshot with the deck. `[enforced: present deck build — an edited
  snapshot is refused]`

## The check is advisory

`present claims check` detects numbers, quotations and names in the spoken text and matches them
to `claim` anchors:

| Tier | Concern |
| --- | --- |
| high | a number, quotation or named attribution with no anchor; a cited `UNVERIFIED` row |
| medium | an orphaned or ambiguous anchor; an anchor to a missing row or a malformed ID; a source reference that does not resolve |
| low | a `SOFT` row worded as fact; a ledger row no script cites; a ledger row that cannot be read; a source that cites an older version than the current one |

- **Concerns never block** unless the repository sets `blocking_tiers` (e.g. `["high"]`).
  Approval records the counts either way.
- **Licence is legitimate.** A speaker may round, simplify or dramatise to land a point. Record it
  as `licence:` on the claim anchor. A licensed span is listed as licensed and never reported as a
  concern.
- The detectors are heuristics. They miss spelled-out numbers and unknown single-word
  organisations, and they report some names that are not attributions. Read the concern, do not
  just count it.

## Flag, don't fix

**Report a claim concern to the speaker; never rewrite their framing for technical correctness
unless they ask.**

- Do not soften a strong statement into a hedged one. Qualifiers belong in notes and Q&A
  preparation, not in the spoken sentence. Keep an in-line hedge only where leaving it out would
  make the sentence false.
- Do not re-litigate how the speaker describes their own organisation or role.
- When a claim is wrong, say what is wrong and what the source says. The speaker decides the
  wording.
