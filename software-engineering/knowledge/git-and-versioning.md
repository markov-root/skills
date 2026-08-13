---
knowledge:
  version: 1
  id: git-and-versioning
  summary: Use version control, commits, branches, tags, and release history as reviewable change evidence rather than ceremony.
  routes: [new-project, review-audit, deployment-operations]
---

# git-and-versioning.md — Version Control, Commits, Branches, Releases

> **Purpose:** Reference for using version control as a tool for _understanding_ — not just storing — code. Covers commit hygiene, conventional commits, branching strategy, semver, changelogs, code archaeology, and the discipline that makes `git log` a useful artefact ten years later.
>
> **Read this when:** writing a commit message; designing a branching strategy; planning a release; reviewing a PR; reading unfamiliar history; deciding whether to squash, merge, or rebase.
>
> **Do NOT** treat commits as save points. A commit is a unit of communication with your future self and your colleagues.

---

## The Premise

> The codebase is the answer. The git history is _why_.

Two corollaries:

1. **History is the audit trail.** When the question is "why is this here?", `git blame` + `git log` is the first place to look. If they don't answer, the engineering discipline failed at commit time.
2. **Published history is a shared contract.** Rewriting shared branches invalidates other clones,
   links, signatures, and audit context. Reserve it for an explicitly coordinated recovery such as
   reducing exposure after a secret has already been rotated.

---

## A Commit Is a Unit of Thought

A good commit:

| Property                                                                                 | Why                                                          |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Atomic** — one logical change                                                          | Reviewable in isolation; revertable in isolation; bisectable |
| **Self-contained** — the change builds, tests pass, runs                                 | `git bisect` only works if every commit is usable            |
| **Tells a story** — the message answers "why", not "what"                                | The diff is the "what"; you don't need a commit to repeat it |
| **Reviewable in five minutes** — small                                                   | Big commits accumulate enough unrelated noise to hide bugs   |
| **Has a stable interface** — public APIs, schema, config not broken by this commit alone | A green CI on this commit means it's actually green          |

**Anti-pattern:** "WIP" / "fixes" / "stuff" commits left in shared history. These are scratch work; squash before merging.

---

## Conventional Commits — A Practical Convention

Pick a commit message convention and apply it. The most widely used is **Conventional Commits**:

```
<type>(<scope>): <short summary>

<body — optional, but recommended for non-trivial changes>

<footer — optional: breaking changes, issue refs>
```

| Type       | Use                                            |
| ---------- | ---------------------------------------------- |
| `feat`     | New user-visible feature                       |
| `fix`      | Bug fix                                        |
| `docs`     | Documentation only                             |
| `style`    | Formatting, no code change                     |
| `refactor` | Code change that's neither feature nor bug fix |
| `perf`     | Performance improvement                        |
| `test`     | Adding or updating tests                       |
| `build`    | Build system, deps                             |
| `ci`       | CI configuration                               |
| `chore`    | Maintenance                                    |
| `revert`   | Reverts a previous commit                      |

Optional scope (`feat(auth): ...`) narrows the area.

**Breaking change** is flagged with `!` or a `BREAKING CHANGE:` footer:

```
feat(api)!: rename /orders/cancel to /orders:cancel

BREAKING CHANGE: callers using /orders/cancel must update to /orders:cancel.
```

**Why bother:** machine-readable commit history feeds changelog generators, semver decisions, and release notes. Even when you don't generate, the discipline of categorising is useful.

---

## The Commit Message — Format

```
<short summary in imperative mood — 50 chars or so>

<blank line>

<body — wrapped at ~72 chars; explains *why*; references issues; describes
trade-offs considered; calls out anything reviewers should know>

<blank line>

<footer — issue references, breaking changes, co-authors>
```

| Element             | Discipline                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Imperative mood** | "Add caching" (not "Added caching" or "Adds caching"). Reads like a command: "this commit will **\_**".        |
| **Subject**         | ≤ 50 chars; no period; specific, not "fix bug"                                                                 |
| **Body**            | Optional but expected for non-trivial changes; wrap at ~72; explain motivation, not mechanics                  |
| **References**      | Issue numbers (`Fixes #123`, `Refs #456`); platform-specific keywords (GitHub auto-closes on `Fixes`/`Closes`) |
| **Co-authors**      | `Co-Authored-By: Name <email>` lines — when a change involves pairing                                          |

**What to put in the body:**

- Why this change, not just what.
- What alternative was considered and rejected.
- What the reader should look for in the diff that isn't obvious.
- Any non-obvious context (a related bug, a Slack thread, an ADR).

**What not to put:**

- Restating the diff.
- "Fixed it" — fixed what, how, why now?
- Internal jargon or shorthand without expansion.

---

## Branching Strategy — Pick One, Stick

| Strategy                           | Description                                                                                             | Use when                                                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Trunk-based development**        | Everyone commits to `main` (or small short-lived branches); feature flags hide unfinished work          | Continuous deployment; mature CI; teams comfortable with feature flags                            |
| **Short-lived branch/review flow** | Short branch from trunk; forge merge/pull request or equivalent review; integrate after selected checks | Common default when direct trunk commits are not appropriate                                      |
| **GitFlow**                        | `main` + `develop` + `feature/*` + `release/*` + `hotfix/*`                                             | Versioned products with parallel release lines; ceremonial; usually too heavy for modern web work |
| **Release branches**               | `main` for current dev; long-lived branches per release stream                                          | Libraries supporting multiple major versions                                                      |

**Project default:** Use trunk or short-lived branches with the repository's Forgejo/GitLab/GitHub/
other review surface. Select review and check requirements by risk, team size, and segregation needs.

### Branch hygiene

- **Short-lived branches.** Hours or days, not weeks. Long branches are merge-conflict factories and diverge from `main`'s reality.
- **Rebased onto current `main`** before merging, when allowed by the team's policy.
- **One concern per branch.** If you find yourself fixing an unrelated thing, do it in a separate branch.
- **Delete merged branches.** Stale branches accumulate; the UI gets cluttered.
- Protect release/trunk branches to the degree the project's consequence and team model require.
  Direct pushes, review count, and required checks are explicit repository policy rather than a
  universal workflow.

---

## Merge, Rebase, Squash — Pick a Default

| Mode                      | What it does                                             | Trade-off                                |
| ------------------------- | -------------------------------------------------------- | ---------------------------------------- |
| **Merge commit**          | Preserves the entire branch history, with a merge commit | Honest history; messy log                |
| **Rebase + fast-forward** | Linear history; branch's commits replayed atop `main`    | Clean log; rewrites the branch's history |
| **Squash and merge**      | Branch collapses to one commit on `main`                 | Cleanest log; loses intermediate commits |

**Choosing:**

- **Squash and merge** for most PRs in fast-moving application repos. The PR is the unit; the branch's micro-commits are scratch.
- **Rebase + merge** when commit-level history matters (libraries, long-lived projects, when bisecting matters).
- **Merge commit** when you want to preserve the fact that a feature was developed on a branch (rare benefit).

The discipline is to **pick one and apply consistently** — heterogeneous history is harder to read than any single style.

---

## Force-Push — The Permanent Boundary

| Where                                        | Rule                                                                                                                 |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Your own branch, not yet merged**          | Allowed — rebase, fix typos, clean commits                                                                           |
| **Shared branch (collaborator's PR branch)** | Coordinate; warn before                                                                                              |
| **`main` / `master` / release branches**     | **Never** without an explicit, recorded reason (e.g., a force-push to remove leaked secrets, with everyone notified) |

Force-pushing to `main` is a destructive operation. Many teams enforce this via branch protection rules — and should.

---

## Reading History — Tools Beyond `git log`

| Tool                               | Use                                                                |
| ---------------------------------- | ------------------------------------------------------------------ |
| `git log --oneline --graph --all`  | A visual picture of branch topology                                |
| `git log -p <file>`                | The history of changes to one file                                 |
| `git log -S '<string>'`            | "Pickaxe" — when was this string added or removed?                 |
| `git log -L '<line range>:<file>'` | Evolution of a specific function or block                          |
| `git blame -w -C -C -C <file>`     | Who last touched each line, ignoring whitespace and tracking moves |
| `git bisect`                       | Binary-search for the commit that broke a behaviour                |
| `git reflog`                       | Local recovery — find a commit you "lost"                          |
| `git diff <a>...<b>`               | Three-dot: changes from common ancestor onwards                    |
| `gitk`, `tig`, `lazygit`           | TUIs / GUIs for browsing                                           |

`git bisect` is one of the most underused power tools — when something used to work and now doesn't, run it. It works in proportion to commit hygiene; small atomic commits make it fast.

---

## Tags and Releases

| Concept                                          | Detail                                                                                             |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| **Tag**                                          | A named pointer to a specific commit; immutable in practice                                        |
| **Annotated tag** (`git tag -a v1.2.3 -m "..."`) | Includes message, tagger, date — preferred for releases                                            |
| **Lightweight tag**                              | Just a pointer; useful for in-flight marks                                                         |
| **Signed tag** (`-s`)                            | Binds a tag to a signing identity when keys/trust/verification are governed; one provenance signal |
| **Release**                                      | A tag + release notes + (sometimes) build artefacts attached                                       |

**Discipline:**

- Give distributable releases an immutable identifier resolvable to source.
- Annotated/signed tags are useful when the release and trust model consume their metadata; hosting
  releases or immutable commits may be the canonical identifier in another workflow.
- Production deploys are traceable to an immutable source revision plus build artifact/digest,
  configuration, and provenance—not a tag alone.
- Treat published tags/identifiers as immutable; correct mistakes with a new release where possible.

Release provenance can include signed commits/tags, artifact signatures, SBOMs, build attestations,
protected builders, and verified source-to-artifact linkage. Choose controls that a consumer
actually verifies.

Projects accepting outside contributions may use a Developer Certificate of Origin (`Signed-off-by`)
or a Contributor License Agreement when legal/governance needs justify it. They solve different
provenance/licensing questions and should not be added as ceremony without owner review.

---

## Semantic Versioning (Semver)

For libraries, public APIs, and anything that other code depends on by version:

```
MAJOR.MINOR.PATCH

MAJOR — breaking change
MINOR — backward-compatible feature
PATCH — backward-compatible fix
```

Pre-release: `1.0.0-rc.1`, `1.0.0-beta.3`.
Build metadata: `1.0.0+abc123` (ignored for precedence).

**Discipline:**

- **`0.x.y` means "no compatibility promise yet".** `0.2.0` may break `0.1.0`. Use during development, before the API is committed to.
- **`1.0.0` is a promise.** Cross it deliberately; the cost of a major bump is real.
- **Breaking change ⇒ major bump.** No exceptions. "Just this once" becomes the norm.
- **Pre-1.0 lifelong** is a smell — either commit to the API at 1.0, or admit the project isn't stable.
- **Calendar versioning (`YYYY.MM.DD`)** is an alternative — useful for applications, not libraries. Doesn't promise compatibility either way; the reader must check the changelog.

---

## Changelogs — The Human-Readable History

`CHANGELOG.md` at the repo root, edited per release. **"Keep a Changelog"** format is the de facto standard:

```markdown
# Changelog

## [Unreleased]

### Added

- New feature X

### Changed

- Behavior of Y now returns Z

### Deprecated

- Old endpoint /v1/foo — to be removed in 2.0

### Removed

- Removed support for Python 3.7

### Fixed

- Fixed a bug where ...

### Security

- Patched CVE-...

## [1.2.0] - 2025-09-12

### Added

- ...
```

| Discipline                                                                  | Detail                                                           |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **Updated in the PR**, not at release time                                  | Reviewers verify the changelog reflects the change               |
| **From the user's perspective**                                             | "Behavior X now works differently" — not "Refactored InnerClass" |
| **Categorised** (Added / Changed / Deprecated / Removed / Fixed / Security) | Easy scanning                                                    |
| **Linked to PRs / issues**                                                  | Cross-references for the curious                                 |
| **Generated changelogs** from conventional commits work                     | Useful when commit discipline is strong                          |

---

## Hooks — Local Enforcement

Git hooks run automatically at certain points. Useful for:

| Hook                 | Use                                                         |
| -------------------- | ----------------------------------------------------------- |
| `pre-commit`         | Lint, format, type-check, secret scan                       |
| `commit-msg`         | Validate commit message format (e.g., conventional commits) |
| `pre-push`           | Run tests before push                                       |
| `prepare-commit-msg` | Auto-insert ticket numbers from branch names                |

Tools:

- **`pre-commit`** framework (Python; multi-language) — most common.
- **Husky** (JavaScript ecosystem).
- **`lefthook`** (cross-language).

**Discipline:**

- Hooks are committed to the repo (via a tool that installs them); not optional per-developer.
- Hooks are fast. If they're slow, developers bypass.
- Hooks don't replace CI — CI is the authoritative gate. Hooks are the developer-friendly early signal.

---

## Pull Requests — The Unit of Review

| Element                  | Discipline                                                                                                                 |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **Reviewable**           | One coherent semantic change; separate generated/mechanical/semantic work and split where intermediate states remain valid |
| **Focused**              | One concern; not "and also"                                                                                                |
| **Description**          | What and _why_; how to test; risks; rollback plan if non-trivial                                                           |
| **Self-review first**    | Before requesting review, re-read the diff yourself                                                                        |
| **Labels**               | Type, area; helps triage and reporting                                                                                     |
| **Linked issue**         | When applicable                                                                                                            |
| **Required checks**      | CI green; required reviewers approved                                                                                      |
| **No merge with red CI** | "Just this once" is how the bar drops                                                                                      |

### Description template

```markdown
## What

One paragraph describing the change.

## Why

The motivation. What problem does this solve? Why now?

## How

Brief description of the approach; flag any non-obvious decisions.

## Testing

- [ ] Added unit tests for X
- [ ] Manually tested Y on staging
- [ ] No tests because: ...

## Risks / rollback

What could go wrong; how to revert.

## Related

- Closes #123
- See ADR-007
```

---

## Code Review — A Topic For Itself

Cross-reference [CODE_REVIEW](code-review.md).

---

## Working with Long-Lived Branches — Survival Tactics

When a branch must live for weeks (a big refactor, a slow feature):

| Tactic                                                                 | Why                                                                                |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| **Rebase from `main` regularly** (e.g., daily)                         | Conflicts are smaller; integration pain spread out                                 |
| **Land scaffolding behind feature flags** continuously                 | Avoid the big-bang merge; reduce ongoing rebase pain                               |
| **Stack PRs** — small PRs against the long-lived branch, each reviewed | Decomposes the review burden                                                       |
| **Keep the change set bounded**                                        | "Refactor while you're there" turns 200 lines into 2000                            |
| **Document the plan in an ADR**                                        | The branch is a one-way door for the next month; future readers need to understand |

**Best alternative:** _don't have long-lived branches._ Use feature flags. Land in pieces. Long branches are usually a process smell.

---

## Monorepo vs Polyrepo

The choice is a one-way door for the org. Briefly:

| Monorepo                              | Polyrepo                                |
| ------------------------------------- | --------------------------------------- |
| Atomic cross-project changes          | Independent release cadence per project |
| Shared tooling, consistent style      | Smaller, simpler repos                  |
| Heavy build tooling required at scale | Easier to bootstrap                     |
| All-team visibility                   | Better for autonomous teams             |
| The merge-queue and CI scale matter   | Easy to silo per repo                   |

Both work. Choose deliberately; document the choice.

---

## Anti-Patterns

| Pattern                                                                 | Why it fails                                                                     |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **"WIP" / "fixes" commits in shared history**                           | History becomes noise                                                            |
| **Commit messages that restate the diff**                               | No value beyond what `git diff` already says                                     |
| **Long-lived branches with no integration plan**                        | Merges become migrations                                                         |
| **Force-pushing shared branches**                                       | Destroys context; rewrites collaborator's local history                          |
| **Publishing without a defined source/artifact provenance chain**       | Cannot establish which reviewed source and process produced the shipped artifact |
| **Skipping the changelog**                                              | Users don't know what changed; deprecations surprise everyone                    |
| **Reverts as "fix forward" only**                                       | When a revert is the right call, revert; "fix forward" can hide pressure         |
| **Big PRs reviewed in 90 seconds**                                      | The review serves the deploy queue, not the code                                 |
| **One commit per PR by default ("squash everything")** without thinking | Sometimes the commit-level history is the value                                  |
| **Tags moved or deleted**                                               | Cross-references break                                                           |
| **`main` is not always deployable**                                     | The deploy story becomes "wait for the right commit" instead of "deploy `main`"  |
| **History rewritten "for cleanliness" after the fact**                  | Outstanding PRs against the old history break                                    |
| **Different commit conventions across the org**                         | Tooling needs to handle all of them; readers lose intuition                      |
| **Generated files committed and modified by hand**                      | The next regeneration conflicts; "manually patched generated code" is permanent  |
| **Secrets in history**                                                  | Even after `git rm`, history is forever — assume public, rotate                  |

---

## Diagnostic Framework

| Symptom                                          | Likely cause                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Cannot tell when a behaviour was introduced      | Commits don't tell the story; bisect; consider improving commit hygiene               |
| "Who wrote this and why?" returns nothing useful | `git blame` points at a refactor commit — use `git blame -w -C -C -C` to follow moves |
| Conflicts every merge                            | Long-lived branches; convergence work overdue                                         |
| Release went wrong; not sure what was in it      | No tag, no changelog, no release notes                                                |
| Reverted commit "doesn't revert"                 | Subsequent commits depended on the reverted change                                    |
| `git bisect` is impossible                       | Some commits don't build; commit discipline failure                                   |
| Forced rebase broke other people's branches      | Communication and process gap; the rebase shouldn't have been done unilaterally       |
| Changelog and code disagree                      | Changelog wasn't updated in the PR                                                    |
| History is a single squashed commit per quarter  | Squash-everything-too-aggressively; consider squashing per PR instead                 |

---

## Meta-Question

Version control is the answer to: _if I need to understand why this code exists, can the repository tell me?_ Every commit, every PR, every changelog entry is a small investment in the answer being yes.

The shortest path to maintainable software is honest, atomic, well-described history. The longest path is "we'll clean it up later".

---

_See [CODE_REVIEW](code-review.md) for the review discipline at the PR boundary._
_See [API_DESIGN](api-design.md) for the deprecation discipline behind versioning._
_See [REFACTORING](refactoring.md) for how to land big changes without long-lived branches._
_See [CONTRIBUTING](contributing.md) for the project-specific commit/branch policy._
_See [DEPENDENCIES](dependencies.md) for upgrade hygiene and the version-pinning discipline._
