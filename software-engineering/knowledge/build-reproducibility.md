---
knowledge:
  version: 1
  id: build-reproducibility
  summary: Make builds repeatable, reproducible, hermetic, and verifiable by declaring inputs, toolchains, environment, and provenance so artifact claims name their boundary and comparison method.
  routes: [dependency-build-change]
  sources: [src-supply-chain-standards]
---

# build-reproducibility.md — Reproducible, Hermetic, and Verified Builds

> **Purpose:** Reference for deciding how far to push build reproducibility and how to claim it
> honestly: declared inputs, toolchains, lockfiles, generated sources, caches, network dependence,
> environment capture, artifact identity, and provenance. It routes to project-native build graphs
> and integrates Dev Containers, SLSA/in-toto, and SBOM where they apply — without turning the skill
> into a build system.
>
> **Read this when:** a build "works on my machine" but not elsewhere; deciding what to lock in a
> lockfile; handling generated code; choosing between building locally and in CI; signing or
> attesting an artifact; explaining why two builds of the same source produced different binaries;
> answering "can you rebuild and compare this?"
>
> **Do NOT** assume every artifact needs bit-for-bit reproducible builds. Level of reproducibility is
> a decision priced by threat, release process, and rebuild value. And do NOT claim "same source ⇒
> same binary" — that is not what reproducibility means.

---

## Epistemic position

**Project default:** Decide the reproducibility level from the artifact's role and the cost of
rebuilding wrongly: what breaks if a rebuild differs, who reconstructs it, and how much the release
process can sustain. Match the mechanism to the project's native build graph rather than importing a
build system.

**Invariant (integrity):** Any claim that an artifact was built from a given source, or is
equivalent to a given build, must survive a concrete comparison — it must name the inputs,
environment, toolchain, artifact digest, and comparison method, and it must not overstate what the
evidence establishes. A build that "looks reproducible" is not a verified reproducible build.

**Anti-fabrication:** There is no universal "reproducible binary" guarantee. Whether a build is
bit-for-bit reproducible depends on the toolchain and inputs; asserting it without a demonstrated,
repeatable comparison is a claim the evidence does not support.

---

## Distinguish the four build promises

The words are often used interchangeably, and the differences materially change what you can claim:

| Term            | What it means                                                                    | What you can honestly claim / do                                |
| --------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| **Repeatable**  | Building the same inputs on the same machine/environment yields the same result  | "Rebuilding on this locked environment reproduces the artifact" |
| **Reproducible**| The same inputs yield equal results **across environments/machines/times**       | "The artifact is bit-for-bit reproducible across these tested environments" |
| **Hermetic**    | The build cannot reach beyond its declared inputs — declared remote inputs (a pinned registry/artifact) are allowed, but arbitrary/ambient network access and undeclared environment state are not | "The build fails fast if it cannot reach its declared inputs; it does not silently fetch unknown things" |
| **Verified**    | Someone ran a comparison and produced evidence of equality or provenance          | "Two independent builds matched / the provenance attestation is valid" |

Work left to right only as far as the artifact justifies. A **repeatable** build may still be
non-reproducible across machines because of timestamps or locale; a **hermetic** build may still be
non-reproducible if a toolchain embeds paths; a **reproducible** build is not **verified** until a
comparison was actually run.

**Counterexample to "reproducible is always better":** for a one-off local artifact that is never
rebuilt elsewhere, the extra effort to achieve cross-machine bit-for-bit equality can be pure cost.
Choose the level the artifact's rebuild/attestation actually needs.

---

## Declared inputs: what a build is actually a function of

A build takes more than source files as inputs. Every un-declared input is a reproducibility leak:

| Input class           | Examples                                                                        | Why it leaks                                                          |
| --------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| **Source**            | Tracked source files, vendored/declared dependencies                            | Untracked or generated-overwritten source changes output without review |
| **Dependency graph**  | The resolved transitive set, not just declared ranges                           | Floating ranges resolve different versions on different days          |
| **Toolchain**         | Compiler/interpreter, build tool, package-manager versions and flags            | A compiler minor version changes generated machine code               |
| **Environment**       | OS image, locale, timezone, `PATH`, clock, user, cwd                            | Timestamps, locale ordering, and paths embed into artifacts           |
| **Secrets/config**    | Keys, endpoints, feature flags injected at build time                           | A changed secret or flag changes the artifact (and leaks if embedded) |
| **Generated inputs**  | Codegen output, protobuf/proto gen, schema-derived code                          | May itself be environment-dependent or drift from the generator's pinned version |
| **Network state**     | Package registry contents and ordering                                          | Registry drift changes what is fetched                               |

**Project default:** The practical first step is a *locked* dependency graph (a committed
lock/resolution artifact for applications/deployments, and an explicit supported-range policy plus
locked CI/development resolution where the ecosystem convention requires it) and a pinned toolchain.
For libraries, follow ecosystem convention: test supported dependency ranges while controlling the
development/CI resolution. See [dependencies](dependencies.md) for the supply-chain view.

---

## Lockfiles, toolchains, and environment capture

There is a ladder of increasing commitment:

| Mechanism                    | What it pins                                                       | Cost / counterexample                                          |
| ---------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------- |
| **Lockfile / resolution**    | The resolved dependency graph                                       | Locks rounds; still needs a pinned toolchain to be stable       |
| **Pinned toolchain**         | Compiler/interpreter + build tool + package-manager versions        | A lockfile alone does not pin the toolchain; pin both for full stability |
| **Runtime/toolchain manifest** | The exact runtime with its SDK/tool versions                       | Adds maintenance burden; pick per ecosystem (e.g. `.tool-versions`, `rust-toolchain.toml`, `requirements` + lock) |
| **Dev Container / container image / nix / remote cache** | The full environment as a deterministic definition           | Higher complexity and coupling; adopt only where the artifact's rebuild value justifies it |
| **Locked CI runner image**    | The environment CI actually builds in                              | "ubuntu-latest" is a moving target; pin explicit runner images / digests |

**Project default:** Pin enough that the documented build path is the one environment that reproduces
— lockfiles + pinned toolchain as a baseline for applications/services, escalating to environment
capture (Dev Container / Nix / locked image) only where the artifact's rebuild, audit, or compliance
value justifies the added maintenance. A dev container reproduces the interactive environment, but
it does not by itself make the *build output* bit-for-bit reproducible; keep those two claims
separate.

---

## Generated sources and codegen

Generated code (protobuf/IDL output, code generators, schema-derived code, CSS/post-processing,
i18n bundles) has two failure modes specific to reproducibility:

1. **Drift between the generator and the committed output** — the committed file no longer matches
   what the current generator produces, so a rebuild silently changes behavior or the generated
   output is never actually regenerated.
2. **Environment-dependent generation** — a generator emits unstable or local-path-dependent code, causing
   "same source, different output" across machines.

Discipline, whichever convention a project chooses (commit-generated output vs build-from-source):

- Pin the **generator and its inputs** the same way you pin a dependency/toolchain; version the
  generator alongside the generated output.
- Record **which version of what** produced the committed output, and re-run/verify generation
  against that version in the same controlled environment (ideally in CI) so drift is detected.
- Make the generator **deterministic** (stable ordering, no timestamps/absolute paths embedded) when
  committed output is compared across machines.
- Do **not** overwrite generated output with locally-different generator versions without a review;
  generated-code diffs deserve the same scrutiny as hand-written diffs (see [code review](code-review.md)).

**Heuristic:** If generated output is committed, the CI build should regenerate it in a locked
environment and fail on a diff — that converts drift from a silent divergence into a caught, visible
error.

---

## Caches and network dependence

Build caches and network behavior both affect reproducibility and correctness.

- **Caches are not reproducibility proofs.** A successful cached build can hide that a fresh,
  offline, or cold build would fail or produce a different result. Periodically validate the path a
  *fresh* builder takes, including the failure you get when a cache/registry is unavailable.
- **Decide the hermeticity policy explicitly** and record it: may the build reach the network to
  fetch the locked graph, is it fully offline/vendored, or does it fall back? Vendoring is a real
  option but shifts reproducibility to the vendored copy (see [dependencies](dependencies.md)).
- **Remote caches** (Bazel/Nix-style, package-manager caches) improve speed but couple the build to a
  service; they should not be the *definition* of what the artifact is.
- **The CI/local divergence** is almost always an input: different lockfile state, floating
  toolchain version, ambient environment variable, or a cache/registry the other side does not have.
  Test the cold, clean build in CI, not just the warm cached one.

---

## Artifact identity and comparison

A reproducibility claim must be checkable. Name all five attributes:

1. **Inputs** — source revision(s) and dependency/toolchain resolution.
2. **Environment** — OS image, toolchain, locale, and relevant environment.
3. **Toolchain** — exact compiler/build tool/package-manager versions and flags.
4. **Artifact digest** — the cryptographic hash (e.g. SHA-256) that identifies the artifact content.
5. **Comparison method** — how equality was tested, and over which of (a) the whole artifact, (b) an
   unpacked/repacked form, or (c) specific content (ignoring allowed metadata).

**Standard/fact:** Treat a digest as identifying the artifact's recorded content, not as proof of
*what the artifact does* or *who built it*, and not as a guarantee of correctness or security. A
digest verifies byte equality within the recorded comparison boundary; it does not verify provenance
or intent.

**Heuristic – comparing reproducibility:** the robust general tool is diffing the two build trees
and inspecting the differences (a diff-based comparison of the two artifacts, letting you classify
each difference as "allowed metadata" or "real divergence") rather than blithely asserting full
bit-for-bit equality. When full equality is required and fails only on permitted fields (timestamps,
ordering, build paths), define *which* differences are acceptable and verify no *other* differences
exist.

---

## Provenance: who built it, and how

Reproducibility answers "same inputs ⇒ same artifact (under what boundary)?" Provenance answers "who
and what process produced this artifact, and can the claim be verified?" They are complementary.

**Project default:** Add provenance where the artifact is release/audit/compliance-relevant and the
ecosystem/tooling supports it at a sustainable cost. Levels are a range, not an all-or-nothing.

| Mechanism                         | What it provides                                                        | When it applies                                             |
| --------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------- |
| **Signed release / provenance attestation** | A verifiable claim about who/what produced the artifact and the build inputs | Release/audit-relevant artifacts where tooling supports it |
| **Software Bill of Materials (SBOM)**      | An inventory of the components in a build (SPDX or CycloneDX format)  | When you must answer "what's in this build?" for a CVE/audit |
| **Supply-chain levels (SLSA)**             | A supply-chain integrity ladder describing how a build was produced and verified (**heuristic shorthand** — see [security](security.md) for the current source of truth on levels/naming) | Where the artifact's integrity threat justifies the rigor  |
| **In-toto / attestations**                 | Machine-readable statements (predicate + subject) about a build        | Where a configurable attestation framework is already in play |

**Heuristic:** These controls are the *provenance* surface of the build. The build-input side of
supply-chain control — SBOM generation, vulnerability scanning, signing, and the SLSA/in-toto
mechanics and their exact current wording — is owned by [dependencies](dependencies.md) (supply
chain) and [security](security.md) (threat model); route detail there. This file keeps only what
these controls mean for the *build-input/evidence boundary*: an attestation or SBOM documents the
inputs that were built and who/what performed the build; it does not by itself make the build
reproducible or prove correctness.

Integrate them only where they apply: a hobby script rarely needs SLSA L3, while a signed release
artifact that others consume may warrant level and SBOM decisions made deliberately. These are
vocabulary and controls an agent routes toward, not requirements every project inherits. Verify the
SLSA/SBOM wording against the current standard before making a conformance claim.

**Heuristic:** add provenance *after* reproducibility is settled and the tooling is already native to
the project. Provenance on top of a non-reproducible build can still document *what was built*, but
it does not make the build reproducible; keep the claims separate.

---

## Evidence and failure boundaries: local vs CI

- **Local build success is weak evidence** for the artifact anyone else will get. It proves the local
  environment can build; it does not prove the build is reproducible, hermetic, or the same as CI's.
- **CI build success is stronger evidence** for the canonical environment, but still scoped: it
  proves the CI environment builds from the recorded inputs at that time. It is not proof of
  cross-environment reproducibility or of provenance unless separately tested.
- **A "rebuilt and matched" comparison is the positive evidence** for reproducibility: two
  independent builds (different machines/CI runs, or a controlled rebuild) that produce equal
  digests within the declared comparison boundary.
- **Say what is untested:** state which environments, toolchains, and inputs have *not* been
  compared, so a reproducibility claim cannot be read as broader than it is.

---

## Scenario notes

### Application / service

- Lock the dependency graph; pin the toolchain and the base image/runtime; decide hermeticity and a
  cold-build check in CI; define the artifact digest and how a rebuild is compared.
- Environmental capture (container image, Dev Container, Nix) is often worth it here because the
  artifact is deployed and must be rebuilt/patchable.

### Library / package

- Follow ecosystem convention for dependency ranges vs lockfiles; the published package's
  reproducibility and provenance may be constrained by the registry's rules.
- Reproduce the development/CI resolution and test a supported range; document the supported
  toolchain. SBOM/provenance may be registry-dependent features rather than universally available.

### Generated-code / build-from-source project

- Pin the generator and its version; make generation deterministic; regenerate-and-diff in CI so the
  committed output never silently drifts from the generator.
- Decide and record whether output is committed or always generated at build time, and the exactly
  pinned generator that defines it.

### CLI / local tool

- Usually needs repeatability and idempotency more than cross-machine bit-for-bit equality. Pin the
  toolchain and lock the graph so "build elsewhere" has a fighting chance; a cheap reproducibility
  check (rebuild + hash in a clean env) is often enough.

---

## Costs and portability limits

Achieving higher reproducibility levels costs real effort; be honest about the price and the ceiling:

| Cost                                                   | Notes                                                                  |
| ------------------------------------------------------ | ---------------------------------------------------------------------- |
| **Locking discipline is ongoing**                      | Every toolchain/upgrade re-opens the reproducibility question            |
| **Pinning the toolchain, not just the graph**          | Often the overlooked step between "locked" and "reproducible"            |
| **Removing non-determinism** (timestamps, paths, order) | Requires cooperating toolchains; some embed environment facts you cannot strip cheaply |
| **Environment capture (containers/Nix) adds coupling** | Improves capture but introduces its own maintenance and portability costs |
| **Provenance/SBOM/SLSA tooling**                       | Adds process and verification burden; not free to run in CI             |
| **Portability ceiling**                                | Some ecosystems/toolchains make cross-platform bit-for-bit equality impractical or unsupported |

**Counterexample to "pin everything":** an ecosystem where bit-for-bit cross-platform reproducibility
is unsupported makes higher levels impractical regardless of effort; the honest posture is to state
the level the ecosystem supports, choose a sustainable one, and document the ceiling rather than
claiming more.

---

## Anti-patterns

| Pattern                                                         | Why it fails                                                                              |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Claiming "reproducible" without a comparison**                | No evidence; assertion outruns the method                                                 |
| **"Same source ⇒ same binary"**                                 | Reproducibility does not mean determinism across un-declared inputs                      |
| **Locked deps, floating toolchain**                             | A lockfile alone does not make builds stable across environments                         |
| **"ubuntu-latest" / moving runner image**                       | The CI environment drifts                                                            |
| **Committed generated output never re-verified**                | Silent drift between generator and committed file                                    |
| **Generator run with local-only environment**                   | Codegen embeds paths/locale; "works here" everywhere else                        |
| **Cached build success treated as fresh-build proof**           | Hides cold/offline failures                                                      |
| **Local build success claimed as CI equivalence**               | Different inputs/environments; weak evidence                                        |
| **Digest quoted as "secure"/"correct"/"provenance"**            | A digest verifies byte equality within the boundary, not correctness or who built it  |
| **Provenance/SLSA/SBOM adopted before reproducibility baseline** | Adds machinery and process on top of unclear inputs; claims still unsupported      |
| **Importing a build system for one artifact**                   | Reimplementing Bazel/Nix for a case that needed a lockfile and a pinned toolchain     |

---

## Diagnostic framework

| Symptom                                                        | Likely cause / first check                                                            |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| "Works on my machine, fails in CI"                             | Different lockfile/toolchain/image/env; compare declared inputs on both sides           |
| Two machines, same source, different binary                    | Timestamps/locale/path embedding, toolchain version, or a moving dependency resolution |
| Build succeeds only with a warm cache                          | Undeclared network/cache dependence; test a cold/clean build                           |
| Generated output changed without source change                 | Generator version drift; pin and regenerate-and-diff                                 |
| Rebuild is not bit-for-bit but I wanted it                    | Identify which fields differ (timestamps/paths/order) and decide which are acceptable  |
| No reproduction of what "the build was"                       | Capture inputs + toolchain + digest + comparison method to make the claim checkable    |

---

## Meta-Question

For this artifact, what would a wrong or unknowable rebuild cost, and does the recorded claim name
the inputs, environment, toolchain, artifact digest, and comparison method — while saying what has
and has not been verified?

---

_See [DEPENDENCIES](dependencies.md) for lockfiles, supply chain, and vendoring._
_See [CONFIGURATION](configuration.md) for pinning build tools/runtime versions and build-time config._
_See [GIT AND VERSIONING](git-and-versioning.md) for reproducible source revisions and release tags._
_See [SECURITY](security.md) for supply-chain and signed-artifact provenance in the threat model._
_See [DATA](data.md) for generated/persisted schemas that cross into build inputs._
_See [CODE REVIEW](code-review.md) for reviewing lockfile and generated-code diffs._
