---
knowledge:
  version: 1
  id: dependencies
  summary: Select, pin, update, verify, and retire dependencies with supply-chain, licensing, compatibility, provenance, and maintenance evidence.
  routes: [dependency-build-change, technology-framework-choice]
  sources: [src-dependency-governance]
---

# dependencies.md — Dependencies, Supply Chain, and Link Rot

> **Purpose:** Reference for the discipline of borrowing other people's code, services, and content. Covers when to add a dependency, how to vet one, how to keep them safe over time, supply-chain attacks, license hygiene, and the slow rot of links and references.
>
> **Read this when:** considering a new library; reviewing the dependency tree; choosing between "write it yourself" vs "pull in a library"; auditing licenses; debugging a supply-chain incident; setting up an upgrade cadence.
>
> **Do NOT** treat dependencies as free. Each one creates a lifecycle obligation until it is removed
> or the product ends.

---

## The Premise

> _Every dependency is a hostage you've taken — and a hostage you've given._

You depend on upstream code, governance, distribution, and security behavior. A dependency decision
therefore needs an owner, update/response path, and exit strategy proportionate to its blast radius.

Three lenses for every prospective dependency:

1. **Today's value:** what does it do that I would otherwise have to write?
2. **Tomorrow's cost:** how much will I have to do to keep this safe, current, and integrated?
3. **The day it goes wrong:** what happens when it disappears, gets compromised, or breaks compatibility?

---

## The Cost of a Dependency — Not Just Code

| Cost                            | What it looks like                                                    |
| ------------------------------- | --------------------------------------------------------------------- |
| **Maintenance**                 | Upgrades, breaking changes, deprecations, security patches            |
| **Build / startup time**        | More install time, bigger images, slower cold starts                  |
| **Binary size / bundle weight** | Especially in frontend; affects every user                            |
| **Attack surface**              | More code = more vulnerabilities (yours or theirs)                    |
| **Cognitive load**              | One more thing the team needs to understand                           |
| **Onboarding burden**           | New devs learn this library instead of just the language              |
| **Versioning friction**         | One library's transitive dependencies conflict with another's         |
| **License obligation**          | Some licenses propagate to your code (copyleft)                       |
| **Lock-in**                     | The library's design imposes shape on your code; removal is a rewrite |
| **Hostage problem**             | Upstream abandons it; CVE is unpatched; you fork, you maintain        |

**Internalised:** the cost of dependency `X` is roughly the time you spend on `X` for the rest of the project's life, divided by the time you would have spent writing the equivalent yourself. The library wins more often than not — but not always, and not for trivial cases.

---

## When To Add a Dependency

Add when the expected value exceeds lifecycle risk and the applicable conditions are satisfied:

- The functionality is **non-trivial** to implement correctly (security, parsing, protocol implementation, anything with edge cases).
- The library is **well-maintained**, has a healthy community, and won't disappear in six months.
- The dependency is **bounded** (it does the one thing and stays there) — not a kitchen-sink framework imported for one function.
- The **license is compatible** with the project's distribution.
- The **API is stable** or you accept the cost of churn.
- You can **explain why** you didn't write it yourself in one sentence.

Treat these as risk signals, not automatic rejection:

- The functionality is one short, well-understood function (`leftpad`, "is even", trivial helpers).
- Maintenance status is unclear or known security/compatibility issues lack response. A mature,
  complete library can legitimately change rarely.
- The library brings **massive transitive deps** for a small feature (dragging in 50 packages to format a date).
- You need a small fraction and vendoring/rewriting would actually reduce total provenance,
  licensing, update, and vulnerability-management cost.
- Governance concentration creates unacceptable critical-path risk and no mirror/fork/replacement
  plan mitigates it.

---

## Vetting a Library — The Checklist

| Check                             | What "good" looks like                                                                                            |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **Release/maintenance cadence**   | Appropriate to maturity; active response to security/platform changes matters more than arbitrary annual releases |
| **Open issues vs closed**         | Closing rate keeps up                                                                                             |
| **Governance continuity**         | Maintainers, succession, funding, mirrors/forks, or replacement plan match criticality                            |
| **Funding / corporate backing**   | Helpful but not required                                                                                          |
| **Security policy**               | A `security.md` with a disclosure email                                                                           |
| **Vulnerability history**         | Past CVEs handled responsively                                                                                    |
| **Test coverage**                 | Tests exist, run in CI, on multiple platforms                                                                     |
| **Documentation**                 | Clear, complete, current                                                                                          |
| **Public CI**                     | Passing                                                                                                           |
| **Releases versioned and signed** | Semver; release notes; ideally signed artefacts                                                                   |
| **Dependency tree**               | Inspect it (`npm ls`, `pip-deptree`, `cargo tree`). Is it bloated?                                                |
| **License**                       | Permissive (MIT, BSD, Apache 2.0, ISC) or compatible copyleft                                                     |
| **Source available**              | Yes — and on a platform you can mirror                                                                            |
| **Replaceable**                   | If it disappeared, what's the alternative?                                                                        |
| **Community signals**             | Stars are noise; downloads are noisier; ecosystem references and recommendations matter                           |
| **Provenance**                    | Is this published by who I think it is? — see typosquatting below                                                 |

---

## Supply Chain — The Hostile Reality

A dependency is a code execution channel from the upstream's machine into yours. Attackers know this.

### The categories of attack

| Category                                                | Example                                                                           | Mitigation                                                                                                   |
| ------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Typosquat**                                           | `reqeusts` instead of `requests`; `loadash` instead of `lodash`                   | Verify the exact package name; restrict installation to allowlists; read the published source the first time |
| **Maintainer account takeover**                         | Phished or weakly-passworded maintainer publishes malicious version               | Pin versions; review diffs on upgrade; trusted publishers                                                    |
| **Compromised maintainer (insider)**                    | Maintainer turns hostile, or sells the package, or the package is silently bought | Pin; review diffs; watch for ownership transfers                                                             |
| **Compromised dependency of dependency**                | Your direct dependency is fine; one of its transitive deps is hostile             | Inspect transitive deps; SBOM; vulnerability scanning                                                        |
| **Build / CI compromise**                               | Attacker compromises the upstream's CI; publishes via the legitimate pipeline     | Reproducible builds; signed releases (Sigstore); package provenance attestations                             |
| **Lockfile injection**                                  | An attacker modifies the lockfile in a PR to pull a different package             | Code review of lockfile diffs; signature verification on install                                             |
| **`postinstall` / `install` scripts**                   | Package runs arbitrary code on install                                            | Disable install scripts where possible; review scripts on first install; use sandboxed installation          |
| **Dependency confusion**                                | Internal package name resolves to a public one because of registry order          | Scope private packages; configure the registry order explicitly; use an internal proxy                       |
| **Malicious update through copy-pasted "curl pipe sh"** | `curl https://... \| sh` runs arbitrary code with no signature                    | Use a package manager; read the script before running; pin the version                                       |

### Discipline

- **Applications/deployments:** Commit the ecosystem's lock/resolution artifact and build from that
  reviewed graph. **Published libraries:** follow ecosystem convention; test supported dependency
  ranges while locking development/CI resolution where appropriate.
- Manifest ranges can express compatibility; the lock/resolution and artifact provenance determine
  what is deployed. Exact manifest pins are not a substitute for a reviewed transitive graph.
- **Inspect transitive dependencies.** What's actually getting installed? Trim what you don't need.
- **Mirror or vendor critical dependencies.** When the registry, network, or upstream goes away, you keep working.
- **Disable install-time scripts** in your package manager (npm: `--ignore-scripts`; pnpm config). Audit before enabling.
- Run vulnerability analysis in CI or release workflow. Triage severity with affected version,
  reachability/exploitability, asset exposure, available fix, compensating controls, and uncertainty.
  A suppression has owner, rationale, evidence, and expiry; policy may still block critical findings.
- **SBOM (Software Bill of Materials).** Generated per build, archived per release. CycloneDX or SPDX format. You can't respond to a CVE if you don't know what's in your build.
- **Provenance attestations.** Where the registry supports it (npm provenance, Sigstore, SLSA), use packages that publish provenance.
- **Periodic dependency review.** Schedule it (monthly, quarterly). What's new? What's unused? What's risky?

---

## Updates — Cadence and Discipline

There is no winning strategy of "never update" — vulnerabilities pile up and re-integration becomes nightmare debt. The strategy is **continuous, small, reviewed updates**.

| Mechanism                                           | Detail                                                                                                                                      |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Automated PRs**                                   | Dependabot, Renovate, mend. Configured per repo.                                                                                            |
| **Grouped updates**                                 | Patch updates can be grouped; majors stay separate                                                                                          |
| **Automated merge for explicitly low-risk classes** | Only when provenance, changelog/diff policy, tests, rollback, ownership, and blast radius justify it; “patch” alone is not a trust boundary |
| **Manual review for major**                         | Major version bumps often include breaking changes                                                                                          |
| **Pinned dev tools** separately from runtime deps   | Different risk profile                                                                                                                      |
| **Security advisories** wired to alerts             | GitHub advisories, OSV, vendor mailing lists                                                                                                |
| **Patch SLA**                                       | E.g., "high-severity vuln in production within 7 days; critical within 24 h" — documented                                                   |

### Reading an upgrade diff

For an upgrade PR, look at:

- **What changed in the diff?** Even for patch versions, look. Real CVEs have been hidden in "fix typo" commits.
- **What's the changelog?** Read it. If there is none, treat the package with suspicion.
- **Run the tests.** Read the failures, even the ones that "look unrelated".
- **Check the maintainer.** Is this from the same publisher as before? Sudden ownership changes are red flags.

---

## License Hygiene

A license is a contract you accept by using the code. Categories:

| Category                        | Examples                                    | What you must do                                                                                                                                     |
| ------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Public domain / equivalent**  | CC0, Unlicense                              | Nothing                                                                                                                                              |
| **Permissive**                  | MIT, BSD, ISC, Apache 2.0                   | Preserve copyright + license notice; some require patent grants (Apache 2.0)                                                                         |
| **Weak copyleft**               | LGPL, MPL                                   | Modifications to the library itself must be open-sourced; your own code remains separate                                                             |
| **Strong copyleft**             | GPL, AGPL                                   | May require corresponding source for covered or combined works; AGPL adds obligations for certain network interaction with modified covered software |
| **Source-available / business** | SSPL, Commons Clause, Elastic License, BUSL | Often **not open source**; specific restrictions on cloud-hosting; read carefully                                                                    |
| **Custom / unclear**            | "Just contact me"                           | Don't use in production                                                                                                                              |

### Operational rules

- **License compatibility is a graph and integration problem.** Transitive presence alone does not
  determine the obligation; distribution, modification, linking, aggregation, process boundaries,
  and the specific licence all matter.
- **AGPL requires deliberate review for network services.** Network users of a modified covered
  program may be entitled to its corresponding source. Whether adjacent or linked proprietary code
  forms a combined work is fact-specific.
- **License of _every_ dependency, including transitive,** must be known. Automated tools: `license-checker`, `pip-licenses`, `cargo-license`, `go-licenses`.
- **Attributions file** generated and shipped. (`THIRD_PARTY_NOTICES.md`, `LICENSES/` directory.)
- **Source-available licenses are not open source.** Treat them with care, especially if your product is similar to theirs.

> **Boundary:** This is dependency-screening guidance, not legal advice. Escalate unclear copyleft,
> patent, redistribution, embedded-device, or hosted-service cases to qualified counsel before
> committing to the dependency or distribution model. The
> [GNU licence FAQ](https://www.gnu.org/licenses/gpl-faq.en.html) illustrates why communication,
> linking, modification, distribution, and aggregation must be analysed rather than inferred from
> dependency-tree position alone.

---

## Vendoring, Forking, and "Inline"

When the dependency is risky or critical:

| Option                                     | When                                                                                                                                              |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Vendor** (copy into the repo)            | The upstream is small, stable, won't be updated often; you want reproducibility independent of the registry                                       |
| **Fork**                                   | You need to make changes the upstream won't accept; the upstream is abandoned but you depend on it                                                |
| **Inline** (rewrite the relevant function) | The dependency is tiny; the value of the standalone library is small; you'd rather own the code                                                   |
| **Wrapper / adapter**                      | The library is large and you want to isolate it behind your interface ([ARCHITECTURE](architecture.md) — Hexagonal); replacement becomes feasible |

Each has a cost: vendor copies stop receiving upstream fixes; forks fall behind; inline duplicates code; wrappers add a layer.
Copying a subset does not erase upstream license obligations or vulnerabilities and can make
provenance/update discovery worse. Record upstream URL/version/license, local modifications,
vulnerability monitoring, and refresh/removal process.

---

## The Build Itself Is a Dependency

| Build-time tool                                       | Same scrutiny                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Package manager (npm, pip, cargo, maven, gradle, ...) | Pin its version; install from trusted sources                                              |
| Build tool (webpack, vite, hatch, gradle, ...)        | Same                                                                                       |
| Compiler / interpreter                                | Pin major.minor; document why                                                              |
| Container base image                                  | Resolve deployments to an immutable digest and retain an intentional refresh/patch policy  |
| OS packages (`apt install`)                           | Build from a snapshot/lock or record resolved versions; keep a tested security-update path |
| CI runner                                             | Pin to a specific runner image; "ubuntu-latest" moves                                      |

**Standard/fact:** A reproducible build produces bit-for-bit identical output from the same source
and defined build inputs/environment, independent of who or when performs it. Pinning is one input;
timestamps, locale, ordering, toolchains, environment, and generated metadata also matter. Pursue
the level of reproducibility/provenance the threat and release process require.

---

## Internal Package Sourcing

For private / internal packages:

- **Scoped names** for internal packages (`@yourorg/...`) to avoid dependency-confusion attacks.
- **Internal registry** (Verdaccio, Artifactory, GitHub Packages) — proxy to the public registry, mirror what you use, can pin versions of public packages too.
- **Allow-list of upstream registries.** A request to a registry you don't know is a smell.
- **Code signing** of internal artefacts.

---

## Link Rot — The Hidden Decay

Code references the world via URLs: documentation links, badges, third-party scripts, external resources, image hotlinks, README references. The world moves. URLs die.

Symptoms of link rot:

- README links to a tutorial that 404s.
- A migration guide references a tool that no longer exists.
- An image embed points at a service that's been sold.
- Documentation refers to a third party whose domain expired.
- An ADR cites an article that's gone.

### Tools and discipline

| Tool                            | Use                                                                                                                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`lychee`**                    | Fast, parallel, multi-protocol link checker. Run in CI on docs (`lychee --offline --include-fragments docs/`) and on a schedule against the live web. |
| **`linkchecker`**, **`muffet`** | Alternatives                                                                                                                                          |
| **`markdown-link-check`**       | Specifically for Markdown                                                                                                                             |

### Practices

- Validate internal repository links in CI because they are deterministic. Treat live external-link
  checks as scheduled/advisory unless repeated confirmed failure violates a required contract;
  networks, rate limits, bot defenses, and transient servers should not randomly block merges.
- **Run a link checker periodically** (weekly/monthly) against external URLs, since CI usually skips them.
- **Use stable links when possible.** Forge/repository permalinks at immutable revisions; DOIs or
  standards-body canonical URLs for formal references.
- **Archive critical references** (`web.archive.org`, internal archive). When the linked content matters, snapshot it.
- **Prefer self-describing references.** "RFC 7231 §6.4" is robust; "this article I read once" isn't.
- **Discipline for badges.** README badges from third parties (Travis, sometimes-defunct services) are link-rot timebombs. Remove dead ones.
- **Periodic README review.** Once a year, read it as a new contributor would.

---

## Privacy and Jurisdiction of Dependencies

(Cross-reference [PRIVACY](privacy.md).) A dependency on a _service_ (versus a library) is a privacy decision.

- **A CDN serving the library** sees the user's IP on every request.
- **A telemetry-laden SDK** sends data to the SDK vendor.
- An analytics dependency introduces a personal-data flow whose controller/processor/recipient role
  must be determined from actual purposes and means.

Discipline:

- **Self-host front-end libraries** (don't load from `cdn.jsdelivr.net` on every page).
- **Strip telemetry** where the SDK supports it; reject the library where it doesn't and the data matters.
- Inventory third parties, roles, data, contracts, locations/transfers, retention, access, and exit
  as in [privacy](privacy.md).
- Evaluate self-hosted and managed services on actual privacy/security/operations evidence; neither
  headquarters nor hosting model is sufficient alone.

---

## Anti-Patterns

| Pattern                                                                           | Why it fails                                                                    |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Deployment resolves an unreviewed moving dependency graph**                     | CI and production may install different code                                    |
| **Application resolution/lock artifact absent or ignored**                        | Deployment inputs are not controlled; library publishing conventions may differ |
| **"Just use the latest" cadence**                                                 | Skipping the changelog read; surprise breakages                                 |
| **`postinstall` scripts unread**                                                  | Code execution channel ignored                                                  |
| **A dependency added "to try"** that stuck                                        | Cost compounds; remove if not used                                              |
| **Unused dependencies in lockfile**                                               | Attack surface for free; remove (`depcheck`, `cargo-udeps`, etc.)               |
| **Big framework for one feature**                                                 | Massive maintenance burden for small return                                     |
| **Library wraps another library wraps another library, you import the outermost** | Indirection without insulation; pin the inner anyway                            |
| **Vendor without documenting the upstream version and date**                      | Future contributors don't know what to update against                           |
| **Forking without documenting why**                                               | Future contributors don't know whether to merge upstream                        |
| **Building from a Git URL with no commit pin**                                    | Build is non-deterministic; supply-chain risk                                   |
| **Multiple lockfiles in conflict** (`yarn.lock` + `package-lock.json`)            | One is wrong; pick a package manager and commit                                 |
| **License unknown, "we'll check later"**                                          | "Later" is after launch and the audit                                           |
| **Trusting badges as a freshness signal**                                         | Badges lie; check the actual data                                               |

---

## Diagnostic Framework

| Symptom                                         | Likely cause                                                                                 |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Build works locally, fails in CI                | Different lockfile state; non-pinned dependency floated; environmental tool version differs  |
| Surprise breakage after `install`               | Floating range; transitive dep updated                                                       |
| Build takes longer over time                    | Dependency tree bloating; periodic prune required                                            |
| Vulnerability appears in scanner                | Patch path: minor/patch bump, or vendor's fork                                               |
| Library doesn't behave as documented            | Wrong version installed; check actual installed version, not declared                        |
| Dependency disappears from registry             | Mirror it, vendor it, find replacement                                                       |
| Maintainer publishes hostile code               | Pin and review every upgrade; revert and disclose                                            |
| Builds aren't reproducible                      | Something in the chain isn't pinned — dependency, base image, compiler, build tool, registry |
| Build pulls from a registry you don't recognise | Misconfiguration or attack — investigate immediately                                         |
| Docs link 404s in production                    | Link rot — add a CI check and a periodic crawl                                               |
| License audit raises questions                  | Check transitive; tooling needs to be permanent, not a one-off                               |

---

## The Three Questions for Every New Dependency

1. **What does it cost me, over the project's life, to keep this current?**
2. **What's the worst-case incident if this dependency is compromised, abandoned, or relicensed?**
3. **Can I exit cheaply — and if not, can I afford to be unable to exit?**

If the residual risk exceeds the project's tolerance, mitigate it, choose another dependency,
vendor a justified subset with provenance and update ownership, or implement the capability.

---

## Meta-Question

Dependencies are the answer to: _what is the cheapest way to get this functionality reliably?_ Sometimes that answer is a library; sometimes it's twelve lines of code. The discipline is to ask, not to default in either direction.

Every dependency is a tiny promise to the future: _we will keep this safe._ The cost of the promise is constant; the value of the dependency declines as the world moves on. Curate accordingly.

---

_See [SECURITY](security.md) for supply-chain attacks in the broader threat model._
_See [PRIVACY](privacy.md) for service dependencies as data processors._
_See [ARCHITECTURE](architecture.md) for wrapping external libraries behind owned interfaces._
_See [CONFIGURATION](configuration.md) for pinning build tools and runtime versions._
_See [GIT_AND_VERSIONING](git-and-versioning.md) for the semver discipline behind upgrades._
_Tools: `lychee` (link rot), `osv-scanner` / `trivy` / `pnpm audit` / `pip-audit` / `cargo audit` (vulnerabilities), `license-checker` / `pip-licenses` (licenses), `depcheck` / `cargo-udeps` (unused deps)._
