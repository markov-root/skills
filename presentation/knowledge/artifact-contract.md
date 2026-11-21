# The artifact contract: versions, semver, pins, approval, delivery

Scripts and decks share one contract. Visuals follow the same shape through the visuals skill.

## Shape

```
<artifact>/
  <kind>.yaml       identity, pins, kind settings
  src/              the ONLY editable place
  vX.Y.Z/           frozen outputs + receipt.json — never modified after creation
  latest -> vX.Y.Z  moved only by the CLI, by atomic rename
  approvals.yaml    approval records, separate from versions
  CHANGELOG.md      one line per version
```

## Edit, then bump

Change `src/`, then `present <kind> bump --level … --note "…"` (scripts) or `present deck build`
(decks). Never edit a version folder, never repoint `latest` by hand, never copy a version to
make a variant. `[enforced: present validate — receipts re-hashed]`

| Level | Meaning | Examples |
| --- | --- | --- |
| MAJOR | the audience sees a different structure | sections or slides added, removed or reordered; a new visual language |
| MINOR | the content changes | a claim, number, example, quotation or data refresh; wording that changes meaning |
| PATCH | nothing changes in meaning | typos, alignment, a colour fix, a re-render with identical content |

When unsure between two levels, choose the higher one.

## Receipts

Every version holds `receipt.json`, with repository-relative paths only:

- the sha256 of every input file and output file;
- every resolved pin;
- the tool versions;
- the git commit and whether the sources were dirty.

`present <kind> show --verify` recomputes the hashes.

If a bump is interrupted, the next bump refuses: either `version_incomplete` (the folder still
holds `.incomplete`) or `latest_behind`. **Inspect the version folder before removing or
repointing anything.**

## Pins

A deck names its inputs with selectors: `latest` (the default) or an exact version. At build time
every selector is resolved to an exact version and written into the receipt, which is the lockfile
pattern. The manifest states intent; the receipt states fact.

- Reuse another talk's visual by pinning its repository-relative path. Never copy it.
- An adapted or recoloured visual is a **new** visual whose brief records
  `derived_from: <path>@<version>`.

## Approval

Approval is a separate act from creating a version: `present <kind> approve`.

- It needs a version built from **committed** sources (`dirty_build` otherwise). The workflow is
  commit `src/`, bump, approve, commit.
- It records the receipt's digest. If the receipt later changes, the approval stops counting.
- It records the claim-concern counts. Concerns never block unless the repository sets
  `blocking_tiers`.
- A fix after approval is a new (PATCH) version and a new approval. The old approval stays on
  record for the old version.

## Delivery

`present delivery record <talk>` writes what `latest` was at delivery: each module's script and
deck version, their approval state, and their receipt digests. The record is written once and never
edited, because `latest` keeps moving after the talk.

- Delivering a draft is allowed, and recorded as `approved: false`.
- `--materialize <dir>` copies the speaking copies and deck files to a directory **outside** the
  repository, for a USB stick or a printer.
