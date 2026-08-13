---
knowledge:
  version: 1
  id: documentation-structure
  summary: Choose documentation roles, locations, authority, lifecycle, and navigation from actual users and project needs rather than a universal tree.
  routes: [documentation-repository-organization]
  sources: [src-documentation-structures]
---

# Documentation Structure Profile

A reusable, opt-in `/docs` profile for version-controlled repositories. Its purpose is to give each
adopted document role one discoverable home so decisions stay decisions, current specifications
remain identifiable, open work is trackable, and historical records do not masquerade as current
truth.

**Project default:** Adopt the role and lifecycle conventions that solve a real discoverability or
currency problem. Keep an ecosystem-native or existing layout when it already makes ownership,
authority, and verification clear. Only move files when the benefit exceeds migration and tooling
cost (see "Moving and maintaining"). Most of the value is in explicit contracts, not file moves.

## Authority before location

No repository-wide slogan such as “code is truth,” “the running system is authoritative,” or “the
spec always wins” is safe for every claim. Declare authority per role and, for important conflicts,
per claim or invariant.

| Role or question                   | Typical authority contract                                                                                                      | Conflict handling                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Executed behavior                  | The observed, versioned system is evidence of what it currently does, not automatically what it ought to do                     | Compare it with applicable contracts; fix the implementation, contract, or both through the owning change process |
| Product/protocol contract          | An adopted specification, API description, schema, type, or compatibility policy may define required behavior                   | Treat runtime divergence as a defect unless the contract is deliberately versioned or superseded                  |
| Durable data invariant             | The adopted schema and migration/data policy define allowed state; stored data is evidence that may expose a violated invariant | Reconcile through the data owner's recovery or migration procedure                                                |
| Safety, legal, or regulatory limit | Applicable law, regulation, approved safety case, or external standard constrains project documents and code                    | Record applicability and version; obtain qualified review where required                                          |
| Current project specification      | The project-designated current document describes present intent and supported behavior                                         | Update it with the owning change; do not rewrite historical evidence                                              |
| ADR                                | Preserves a decision, context, alternatives, and consequences at a point in time                                                | Keep the accepted body stable; link a correcting or superseding decision and update status metadata               |
| Task                               | Owns work state, linked acceptance criteria, blockers, and durable completion evidence                                          | Status changes in the task; indexes summarize rather than override it                                             |
| Audit or research record           | Preserves dated observations, methods, sources, and evidence limits                                                             | Add a correction or supersession notice; do not convert old observations into current truth                       |
| Lesson or thematic note            | Carries a reusable inference with provenance and stated scope                                                                   | Revise standing notes deliberately; supersede dated lessons when their conclusion no longer applies               |
| Handoff                            | Carries temporary continuation state for a named work boundary                                                                  | Keep exactly one current handoff per adopted scope and supersede it aggressively                                  |
| User documentation                 | Helps a defined audience learn, act, look up, or understand                                                                     | Version and test it against the contracts and product versions it claims to describe                              |
| Code comment or docstring          | Explains a nearby contract, invariant, rationale, unit, lifetime, or generated boundary                                         | Change it with its owner; generated reference remains subordinate to its source                                   |

**Project default:** Record the role owner, current/superseded states, current-truth pointer, review
trigger, and source of material claims where ambiguity would be costly. Task 0035's opt-in
documentation-currency diagnostics can enforce selected indexes and state cardinality, but the
project still decides which roles and documents have authority.

## Example layout

```
docs/
  context/     canonical specs + orientation -- the "how it works" reference
  adr/         architecture decision records -- one locked decision each
  tasks/       actionable open work -- decomposed out of ADRs and specs
  lessons/     dated learnings + standing thematic notes
  audits/      point-in-time deep-analysis / audit bundles
  templates/   templates for ADR, task, lesson, folder README
  runbooks/    optional operational response procedures
  privacy/     optional data map, processor inventory, retention policy
  README.md     index + this layout map
```

(Plus the usual repo-root `README.md` and `CONTRIBUTING.md` when those entry points fit the
ecosystem.)

Reader-facing tutorials, how-to guides, and generated/reference material may receive top-level
folders when volume warrants it. A project may instead keep user documentation beside a package,
in a documentation site source tree, or in another indexed home required by its toolchain.
Diátaxis is a useful user-need taxonomy, not a lifecycle-record schema: ADRs, tasks, audits,
research, lessons, and handoffs do not need to be forced into its four forms. See
[`documentation.md`](documentation.md).

## What each folder holds

**`context/`** -- The project's designated current specifications and explanations: optionally
numbered docs read in order, plus orientation, architecture, a plain-English FAQ, and scoped context
for collaborators. This is living _current design intent_, not an automatic subordinate of running
code. When implementation, specification, schema, or external constraint disagree, resolve the
conflict according to the declared authority for that claim. Avoid making `context/` an unowned
catch-all.

**`adr/`** -- Architecture Decision Records, often `NNNN-slug.md`. One decision per file. Records
Context -> Decision -> Consequences and enough alternatives to understand the choice. Keep an
accepted decision body stable; permit explicit status, correction, and supersession metadata under
the project's ADR policy. To reverse or materially re-scope a decision, write a new record and link
both directions. Preserve lengthy exploration, dissent, experiments, or unresolved questions in a
separate deliberation/research artifact when compressing them into the ADR would lose useful
history.

**`tasks/`** -- Actionable open work, one per file. ADRs record _decisions_; tasks record _work to do_.
The filename prefix encodes provenance:

| Prefix               | Means                                   | Links back to      |
| -------------------- | --------------------------------------- | ------------------ |
| `adr-NNNN-slug.md`   | Work a decision left to do              | `../adr/NNNN-*.md` |
| `audit-NNNN-slug.md` | Work an audit surfaced                  | `../audits/...`    |
| `task-NNNN-slug.md`  | Standalone work with no parent decision | (none)             |

Each task carries an explicit Status. Repositories using the
`engineering document query --role task` contract use
`todo` / `partial` / `blocked` / `done`, plus a “Done when” section and durable completion evidence
before `done`. `tasks/README.md` is the index, split by actionable and blocked state with a short
“not tracked here (decided against)” section so deliberate omissions are explained, not mistaken
for oversight. Use [requirements and traceability](requirements-and-traceability.md) when criteria
need stable identifiers or relationships beyond one task.

**`lessons/`** -- `YYYY-MM-DD-slug.md` dated learnings (optionally `YYYY-MM-DD-adr-NNNN-slug.md` /
`-task-NNNN-` when tied to one), plus _standing_ thematic notes without a date prefix (e.g.
`methodology.md`, `process-engineering.md`, `deliberately-rejected.md`). This is the reasoning that did
not fit in an ADR, and one possible place to look when a decision seems puzzling. A project may use
a dedicated `research/` or `deliberation/` role instead; index whichever role owns that history.

**`audits/`** -- Point-in-time audit and deep-analysis bundles: `YYYY-MM-<slug>/` (a folder when it spans
many files, with its own `00-INDEX.md`) or `YYYY-MM-DD-audit-NNNN-<slug>.md` (a single report). The full
worked artifact as produced. Learnings distilled from an audit go to `lessons/`; work it surfaces goes to
`tasks/` as `audit-NNNN-*`.

**`templates/`** -- Templates for new ADRs, tasks, lessons, and folder READMEs. These set the
going-forward standard; apply them to new artifacts, not retroactively to the back catalogue.

## Source discipline

Do not cite every sentence merely because it is non-obvious. That creates citation noise and an
unmaintainable freshness burden.

**Project default:** Cite a primary source close to a claim when the claim is material to a
decision, volatile, externally normative, legal/regulatory, safety-relevant, quantitatively
specific, or reasonably contested. Record the version/status, verification date, and re-verification
trigger when freshness matters. Project decisions, preferences, heuristics, and examples should be
labelled as such; they need rationale and override conditions rather than decorative citations.

An ADR's sources support its factual premises. They do not outsource the project decision to an
authority that never made that decision.

## Cross-linking conventions

- Link with **relative paths**; a link-checker must be able to resolve every `.md` link from its file's
  own directory.
- In repositories adopting this profile, **prefix-link** each derived task to its source, and give
  each source ADR a one-line pointer back:
  `## Open work` -> "Tracked as a task (this ADR remains the decision of record): `tasks/adr-NNNN-...`".
- **Do not gut an ADR to extract a task.** Duplicate the actionable item into `tasks/` and leave the
  decision, rationale, and consequences in the ADR. Consequences are part of the record, not a to-do
  list.
- **Decided-against work is recorded**, not silently dropped: note it in the relevant ADR and in
  `tasks/README.md` so the absence of a task is itself traceable.
- House voice: short, plain sentences and consistent punctuation. Do not impose a punctuation ban
  that the corpus itself does not follow.

## Voice and hygiene -- what does not belong in a repo

Everything committed—docs, comments, config, sample data—may be read by collaborators, auditors,
automation, or future maintainers. Public artifacts may later become public; access-controlled
repositories can legitimately contain bounded operational context. Write for the artifact's real
audience and keep credentials and private keys out of Git. There are two kinds of cleanup:
**content and voice** (reword) and **must-never-commit** (remove from the current tree). If a secret
entered history, rotate/revoke it first; then use an approved, coordinated history-rewrite procedure
when reducing historical exposure is warranted. Rewriting history does not make an exposed secret
trustworthy again. Run the current-tree sweep before a repo is first pushed or shared outside the
team, and apply the content rules on every PR thereafter.

### Write as the institution, not the author or the tool

- **Institutional voice for institutional decisions.** State project decisions as the project's,
  while preserving authorship, testimony, accountability, or tool/model provenance when it is
  materially relevant.
  Bad: "an agent (me) declared the data fabricated"; "I reached the wrong conclusion." Good: "an
  earlier review treated the data as unsourced; that was incorrect."
- **Avoid transcript debris.** Remove irrelevant session narration. Keep agent/model/tool identity,
  prompts, versions, and limitations when the artifact evaluates an agent product, records generated
  provenance, or needs reproducibility/auditability.
- **Commit attribution is the project owner's only.** Do not add an AI co-author trailer
  (`Co-Authored-By: <model>`) unless the owner asks for it. Set a per-repo `user.name` / `user.email`
  so commits are not mis-attributed to a global identity.
- **House voice:** short, plain sentences with consistent punctuation.

### Roles, not people

Prefer durable roles and role inboxes for long-lived operational ownership. Preserve named authors,
deciders, approvers, copyright holders, contacts, or accountable individuals when attribution is
required or useful; add dates/roles so the record can age honestly.

| Place                                         | Bad                    | Good                             |
| --------------------------------------------- | ---------------------- | -------------------------------- |
| ADR `Deciders:`                               | `Jane Doe (CTO)`       | `<Org> (tech lead)`              |
| Task `Owner:`                                 | `Jane`                 | `<Org> tech lead` / `unassigned` |
| README maintainer, `pyproject` authors        | `Jane <jane@personal>` | `<Org> (contact@org)`            |
| Dataset provenance / validator / review notes | `validator (jane)`     | `validator (<Org>)`              |
| Code docstrings, comments, fixture data       | `# ask Jane`           | `# ask the tech lead`            |

Keep a real contact reachable. A role inbox is usually more durable; a consented personal address
may be appropriate for an individual-maintained/open-source project.

### Naming other organisations

Avoid borrowed prestige as marketing. Preserve required license/copyright attribution and honest
design provenance, inspiration, compatibility, benchmark, or comparison evidence. Never scrub a
copying/source admission when doing so would conceal intellectual-property obligations or mislead
readers; instead clarify what was reused and under what permission.

### No internal-environment leakage

Public distributable docs use placeholders and omit private IPs, usernames, hostnames, and internal
topology. Access-controlled operational runbooks may require exact endpoints/topology to be usable;
classify them, restrict access, avoid credentials, and keep a sanitized public counterpart when one
is needed.

### Reversed decisions and loaded words

When a decision is reversed, record a clean **superseding** decision in institutional voice while
preserving the original decision body and its provenance. Add a prominent neutral correction or
supersession notice when a title or claim could cause present harm if read out of context. Rename a
misleading slug only through a reviewed migration that preserves redirects or updates inbound
links; history preservation does not require keeping a harmful current index label.

### Stale records of discarded work

A frozen audit or note about code that no longer exists keeps a prominent banner at the very top --
"SUPERSEDED -- none of this still applies" -- so it cannot be mistaken for the current system. Keep
it for history; do not let it read as live.

### Secrets, and what must never reach git

This is non-negotiable and separate from voice: these are **removed entirely and kept out of
history**, not reworded.

- **Never commit a real secret of any kind:** API keys, tokens, passwords, private keys, production
  database credentials, `.env` files, or anything held in a secrets manager. Config reads secrets
  from the environment; settings carry **no hardcoded fallback secret** and default production
  `DEBUG` to false. A read-only/public app should hold no secrets at all.
- **Baseline `.gitignore`:** env files (`.env`, `.env.*` except a sanitised `.env.example`);
  dependency dirs (`node_modules/`, `.venv/`); caches (`__pycache__/`, `.pytest_cache/`,
  `.ruff_cache/`, `.mypy_cache/`); build output (`dist/`, `.vite/`, `staticfiles/`); generated
  artifacts (compiled translations `*.mo`, coverage `.coverage` / `htmlcov/`, `*.egg-info/`); local
  databases (`db.sqlite3`); OS/editor noise (`.DS_Store`, `.idea/`, `.vscode/`, `*.swp`); merge
  leftovers (`*.orig`); a scratch dir for throwaways (e.g. `scripts/_scratch/`); and any fetched
  third-party source you are not licensed to redistribute.
- **Keep the source, ignore the build:** commit `.po`, ignore `.mo` (rebuilt on setup/deploy);
  commit source CSS/JS, ignore the bundled output. Commit a sanitised `.env.example`, never `.env`.
- **Scan before the first push or before sharing -- working tree _and_ full history.** A secret
  committed then deleted still ships in history. Confirm `.env`-style files were never committed;
  confirm no sensitive file types were ever added (`.pem`, `.key`, `.pfx`, `.p12`, `.sqlite3`); grep
  the tree and every commit for high-signal patterns (`SECRET_KEY=`, `BEGIN .* PRIVATE KEY`, `sk-`,
  `AKIA`, `ghp_`, `xoxb-`, bearer tokens). If a real secret ever landed in history, **rotate it** --
  a private repo does not undo exposure.

### One-off scripts and scratch

Throwaway scripts (one-time migrations, scrapers, mockups) do not accumulate in a shared `scripts/`.
Put them in a gitignored scratch dir, or mark them with a header (`# ONE-SHOT (date): <purpose>;
safe to delete once <X>`) and remove them once their output is committed. A `scripts/catalog.md`
records which scripts are durable and why.

## Moving and maintaining (when you reorganise)

1. Use `git mv` for convenience and keep moves separable from semantic edits where practical. Git
   stores snapshots and detects renames heuristically; the command does not create a special
   history-preservation record.
2. Files that move _as a block_ keep their relative cross-links for free; only cross-boundary links break.
3. After moving, run the link-checker and drive internal breakage to **zero** before committing.
4. **Sweep the whole repo, not just `docs/`** -- code, schemas, `CONTRIBUTING.md`, and configs reference
   docs paths too, and a docs-only check will miss them.
5. Do the **structural move** and any **interpretive edits** (e.g. task extraction) as **separate
   commits**, so the low-risk move is banked even if the interpretive pass needs rework.
6. On a solo/local repo, do the work on a branch (local isolation, trivial rollback) and keep an
   off-machine backup remote.

## Sources

- [Diátaxis](https://diataxis.fr/) — four user-documentation needs and forms; verified 2026-07-30;
  re-verify before changing this taxonomy.
- [Michael Nygard, “Documenting Architecture Decisions”](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
  and [MADR](https://adr.github.io/madr/) — decision context, status, supersession, and multiple
  legitimate storage/categorization choices; verified 2026-07-30.
- Ecosystem examples in [`repository-structure.md`](repository-structure.md) show why this profile
  cannot replace package, build, publication, or ownership conventions.

## Appendix: link-checker

A minimal resolver (stdlib Python). Reports every relative `.md` link that does not resolve from its
file's location. Skips http(s)/mailto/anchors and (intentionally) non-`.md` targets.

```python
import re
from pathlib import Path

ROOT = Path(".")  # repo root
files = sorted((ROOT / "docs").rglob("*.md")) + [ROOT / "README.md"]
link_re = re.compile(r"\]\(([^)]+)\)")
broken = []
for f in files:
    if not f.exists():
        continue
    for m in link_re.finditer(f.read_text(encoding="utf-8", errors="replace")):
        tgt = m.group(1).strip().split()[0]
        if tgt.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = tgt.split("#")[0]
        if not path or not path.endswith(".md"):
            continue
        if not (f.parent / path).resolve().exists():
            broken.append((str(f.relative_to(ROOT)), tgt))
for src, tgt in broken:
    print(f"BROKEN  {src} -> {tgt}")
print(f"\nbroken: {len(broken)}")
```

Pair it with a repo-wide stale-path sweep after any move, e.g.:

```
rg -nN --glob '!.git' --glob '!.venv/**' 'docs/<old-pattern>' | rg -v '<new-pattern>'
```
