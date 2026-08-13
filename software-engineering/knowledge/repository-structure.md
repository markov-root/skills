---
knowledge:
  version: 1
  id: repository-structure
  summary: Shape repository layout around artifact boundaries, ownership, ecosystem conventions, dependency direction, and executable structural checks.
  routes:
    [module-system-design, documentation-repository-organization, new-project]
  sources: [src-repository-ecosystems]
---

# Repository Structure and Ownership

> **Purpose:** Arrange code and artifacts so dependency direction, ownership, public contracts,
> generated material, and verification are discoverable.
>
> **Read this when:** starting a repository, reorganizing folders, splitting packages, creating a
> monorepo, or deciding where tests, migrations, scripts, assets, and generated code belong.

---

## Organize Around Change

**Project default:** Prefer boundaries that keep code changed for the same reason close together and
make important dependency directions visible, but do not optimize change locality in isolation.

Name the forces that actually constrain the repository:

| Force                            | Question                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------- |
| Ecosystem/tooling convention     | Which paths do compilers, package managers, frameworks, generators, and IDEs expect?              |
| Change locality                  | Which files repeatedly change together for one capability or contract?                            |
| Ownership and access             | Who reviews, operates, or may read each area, and can the hosting platform enforce that boundary? |
| Dependency/build graph           | Which edges are allowed, and can affected builds/tests be selected without hiding unsafe impact?  |
| Package/public contract          | What is published or imported by consumers, and which implementation remains private?             |
| Deployment and release unit      | Which artifacts version, migrate, roll back, and ship together or independently?                  |
| Generated/vendored material      | What is authored here, generated here, or imported under an external provenance/license?          |
| Discoverability                  | Can contributors find entry points, owners, contracts, and verification without tribal knowledge? |
| Migration and compatibility cost | Can consumers move atomically, or do paths/package names require shims and staged deprecation?    |

These forces can conflict. Co-locating everything that changes together may violate packaging or
access-control boundaries; mirroring organizational ownership can produce dependency cycles;
ecosystem conventions may look less elegant but eliminate custom build and contributor friction.
Record which force wins and when to revisit it.

Two legitimate starting shapes:

- **Domain/feature-oriented:** useful when product capabilities have distinct language, state, and
  ownership.
- **Technical layers:** useful when the application is small or layers are truly shared and stable.

Hybrid structures are common: top-level domains with explicit application/domain/infrastructure
boundaries inside each. Avoid a global `utils`, `helpers`, `common`, or `misc` directory becoming an
unowned dependency sink.

Follow strong ecosystem-native conventions unless they violate a project requirement. Tooling,
packagers, and new contributors understand conventional layouts with less custom configuration.

**Example:** Python's flat and `src` layouts have different import and editable-install behavior;
npm's `files` and `exports` fields control publication and public entry points; Bazel packages and
visibility can enforce dependencies independently of visual folder neatness. Choose against the
actual toolchain rather than a language-agnostic tree diagram.

## Make the Decision Reviewable

For a material layout or repository-boundary change, record:

1. the current pain or failed outcome;
2. ecosystem and build/package constraints;
3. candidate shapes, including keeping the current layout;
4. qualitative effects on the forces above;
5. migration/compatibility plan and rollback point;
6. observable evidence that would show improvement or regression.

**Heuristic:** A small qualitative table (`better`, `neutral`, `worse`, `unknown`) is often clearer
than a numeric score whose weights imply false precision. Use measured data where available:
changed-file history, build graph, import cycles, ownership gaps, package contents, release coupling,
navigation/task studies, or incident history. Do not reorganize solely because a folder tree looks
untidy.

## A Boundary Must Be More Than a Folder

A useful module/package boundary has:

- a documented responsibility and owner;
- an explicit public surface;
- internal implementation that consumers cannot casually import;
- declared dependency direction;
- tests at the boundary;
- a migration path for contract changes.

**Heuristic:** If everything imports everything despite tidy folders, the architecture is not
modular. Enforce important boundaries with language visibility, build graph rules, import linting,
or architectural fitness tests.

Folder ownership metadata is only as strong as its platform semantics. For example, GitHub
CODEOWNERS can request reviews and can participate in protected-branch requirements; a file alone
does not prove effective approval policy, operational ownership, or support coverage. Verify the
configured host and branch rules rather than assuming the filename creates authority.

## Public, Internal, Generated, and Vendored Material

Keep visibly distinct:

- public APIs and schemas;
- private implementation;
- generated outputs and their generators;
- vendored third-party code with source, version, license, and update process;
- database migrations and rollback/compatibility notes;
- static assets and their source files;
- operational scripts versus reusable product code;
- fixtures/test data versus production data.

Generated files should declare their source and regeneration command. Do not hand-edit them unless
the generator contract explicitly supports a maintained patch layer.

Package/release manifests deserve direct tests. A clean source tree can still publish private files,
omit required schemas, or couple two supposedly independent release units.

## Tests

Co-locate tests when proximity helps ownership and ecosystem tooling; mirror production structure
when independent packaging or cross-component integration makes the map clearer. Either is valid if
the relationship is predictable.

Separate by execution contract when useful:

- fast component/unit tests;
- controlled integration/contract tests;
- system/E2E and compatibility suites;
- performance, security, accessibility, recovery, and migration evidence.

Do not encode “test level” only in a folder name while fixtures silently reach real networks,
clocks, global state, or production credentials.

## Nesting and Names

**Heuristic:** Each directory level should answer a real ownership, packaging, platform, or
dependency question. Deep repetition such as `src/app/modules/orders/order/` adds navigation cost
without information.

Use domain language. Avoid files named `manager`, `service`, or `processor` unless the qualifier says
what responsibility they own. Keep entry points obvious.

Barrel/re-export files can provide a stable public surface. They can also hide dependency cycles,
inflate bundles, and make symbol provenance ambiguous. Use them deliberately and test the exported
contract.

## Monorepositories

A monorepo needs more than one root:

- package/project boundaries and dependency graph;
- ownership and review rules;
- affected-test/build selection with a safe full fallback;
- shared-version versus independent-version policy;
- generated lockfile and toolchain ownership;
- release, migration, and compatibility rules;
- access controls if not every participant may read every component.

**Project default:** Share code through an owned package with a contract, not by reaching into a
sibling's internal directory. Prevent dependency cycles mechanically.

## Reorganization

Git stores snapshots and detects renames heuristically; `git mv` is convenient but does not create a
special history record. Keep structural moves separate from semantic edits when practical so review
and rename detection remain intelligible.

Before moving:

- map imports, build/package metadata, docs links, generated paths, CODEOWNERS, deployment inputs,
  and external consumers;
- preserve compatibility shims where consumers cannot migrate atomically;
- run affected and full boundary checks;
- update diagrams and ownership docs only when they describe the current structure.

## Fitness Evidence

Select checks that correspond to the decision; do not mandate the whole table.

| Intended property            | Useful evidence or fitness function                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| Dependency direction         | Import/build-graph rule rejects forbidden edges; cycle report is empty for the declared graph         |
| Public/internal separation   | Consumer contract test imports only supported entry points; package visibility/exports are explicit   |
| Ownership coverage           | Host-native ownership syntax validates; critical paths have effective reviewers and escalation        |
| Generated-source integrity   | Canonical regeneration is deterministic or a drift check explains tolerated differences               |
| Package contents             | Dry-run/archive inspection contains required files and excludes private, secret, or unlicensed data   |
| Release-unit independence    | Version, build, migration, and rollback can execute on the declared unit without hidden sibling state |
| Affected-build optimization  | A fixed change corpus compares affected selection with a safe full fallback                           |
| Discoverability              | A maintainer task study finds entry point, owner, public contract, and check within the stated target |
| Reorganization compatibility | Old imports/paths have tested shims or a versioned breaking-change and consumer migration evidence    |

A passing check establishes only its declared property. It does not prove that the overall layout
is maintainable, that ownership is socially real, or that future changes will follow today's
co-change pattern.

## Repository Root Hygiene

The root should make entry points discoverable: README, contribution/instruction contract, license
or explicit private/proprietary status, security/reporting policy where applicable, package/build
metadata, changelog/release notes, and links to current architecture and operations.

**Project default:** A public distribution needs an explicit license. A private repository may
instead record that no redistribution permission is granted; absence of a license should not be
misrepresented as open-source permission.

## Meta-Question

Can a new maintainer identify ownership, dependency direction, public contracts, generated or
third-party material, and the right verification path from the repository shape alone?

## Sources

- [Python Packaging User Guide: `src` layout vs flat
  layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) — ecosystem
  layout trade-offs; verified 2026-07-30; re-verify before Python packaging guidance.
- [npm `package.json`](https://docs.npmjs.com/cli/configuring-npm/package-json/) — `files`,
  workspaces, entry points, and `exports`; verified 2026-07-30; re-verify before npm publication
  guidance.
- [Bazel visibility](https://bazel.build/concepts/visibility) — enforceable package/public
  boundaries; verified 2026-07-30; re-verify against the adopted Bazel version.
- [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
  — ownership-file and review-enforcement semantics; verified 2026-07-30; re-verify before a
  GitHub-specific ownership policy. Other hosts require their own current documentation.
