---
knowledge:
  version: 1
  id: security
  summary: Engineer security from assets, threats, trust boundaries, least privilege, secure defaults, dependency provenance, and risk-proportionate verification.
  routes: [api-event-contract, dependency-build-change, deployment-operations]
  sources: [src-security-standards]
---

# security.md — Security Reference

> **Purpose:** Reference for thinking about security across the lifecycle of a project — design, implementation, deployment, operation, and decommissioning. This is the document a CS security professor would expect you to have read before touching anything that crosses a trust boundary.
>
> **Read this when:** designing anything that touches user input, persistence, network, secrets, or other people's data; reviewing inherited code; preparing to deploy.
>
> **Do NOT** treat this as a compliance checklist. Security is a property of the whole system, not a feature you add at the end.

---

## The Five Foundational Principles

These are the load-bearing ideas. Every concrete control descends from one of them.

| Principle             | What it means                                                                                                                | What violating it looks like                                                                                             |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Least privilege**   | Every actor (user, process, service, key) has the minimum permissions required to do its job, for the minimum time           | The application connects to the database as a superuser; a service account has write access to everything "just in case" |
| **Defence in depth**  | Complementary controls reduce common-mode and single-control failure; not every layer must independently stop every threat   | "We have a firewall" as the only control; assuming the WAF removes the need for safe queries                             |
| **Fail securely**     | When something breaks, the failure mode is _closed_ (denied), not _open_ (permitted)                                         | An auth check that throws an exception and the catch block proceeds as if the user were authorised                       |
| **Zero trust**        | Network location alone grants no trust; protected access is explicitly authenticated/authorized and continuously constrained | "It's behind the VPN" as the rationale for an unprotected admin endpoint                                                 |
| **Secure by default** | The out-of-the-box configuration is the safe one. You have to _opt in_ to insecure behaviour                                 | A new bucket is public unless made private; debug mode ships in production                                               |

**Diagnostic:** When you make a security-relevant decision, name which of these five it serves. If you can't, the decision isn't doing security work.

---

## Threat Modeling — STRIDE

Before designing anything that crosses a trust boundary, enumerate threats. STRIDE is a checklist for finding them.

| Letter | Threat                 | What it looks like                   | Mitigation family                              |
| ------ | ---------------------- | ------------------------------------ | ---------------------------------------------- |
| **S**  | Spoofing               | Pretending to be someone else        | Authentication                                 |
| **T**  | Tampering              | Modifying data in transit or at rest | Integrity (signatures, hashes, TLS)            |
| **R**  | Repudiation            | "I didn't do that"                   | Audit logs, non-repudiation (signed actions)   |
| **I**  | Information disclosure | Reading data you shouldn't           | Encryption, access control, minimal collection |
| **D**  | Denial of service      | Making the system unavailable        | Rate limiting, quotas, capacity planning       |
| **E**  | Elevation of privilege | Becoming an admin from being a user  | Authorisation, sandboxing, isolation           |

**Method:**

1. Draw a data flow diagram with trust boundaries (lines between zones of different trust).
2. For each boundary crossing, ask: which STRIDE threats apply?
3. For each applicable threat, name the mitigation. If there isn't one, that's a finding.
4. For each mitigation, name how you'd test that it works.

---

## Discover the Actual Trust Boundaries

**Project default:** Draw the system's real actors, data flows, privilege zones, administrative
surfaces, build/release path, and third parties. A small offline tool may have fewer boundaries; a
multi-tenant service may have many more than edge/application/database.

Common boundaries include user input, tenant separation, application/persistence, service/service,
control plane/data plane, build/runtime, privileged operator/ordinary user, and organization/vendor.
Trust is contextual and least-privilege: two authenticated internal components can still have a
security vulnerability between them if one can exceed its intended authority or corrupt a protected
asset. Spend security effort according to assets, threats, and consequences—not merely whether a
diagram labels a component “trusted.”

---

## OWASP Top 10 (2025) — Operational Form

**Standard/fact (verified 2026-07-30):** OWASP Top 10:2025 is an awareness document for web
application security, not a complete verification standard. Source:
[OWASP Top 10:2025](https://owasp.org/Top10/). Re-verify before using the list for a current audit.

| #   | Category                               | One-line description                                                                 | Mitigation                                                                                      |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| A01 | Broken Access Control                  | Actions or data are available outside intended authority                             | Default-deny; object/function authorization; tenant and privilege tests                         |
| A02 | Security Misconfiguration              | Unsafe defaults, exposed surfaces, or inconsistent hardening                         | Minimal surface; configuration schema; hardened, tested deployment baseline                     |
| A03 | Software Supply Chain Failures         | Compromised, vulnerable, or ungoverned build/dependency path                         | Inventory/SBOM; provenance; vulnerability triage; protected release path                        |
| A04 | Cryptographic Failures                 | Missing, weak, or misapplied protection of confidentiality/integrity                 | Platform security APIs; current approved suites; key lifecycle and misuse-resistant design      |
| A05 | Injection                              | Untrusted data is interpreted as code, query, template, path, or command             | Structured APIs/argument arrays; parameterization; context-aware encoding                       |
| A06 | Insecure Design                        | The system design does not address a credible threat                                 | Threat and abuse-case modeling; security requirements; design review                            |
| A07 | Authentication Failures                | Identity, authenticator, recovery, or session controls fail                          | Phishing-resistant MFA where warranted; secure recovery/session lifecycle; throttling           |
| A08 | Software or Data Integrity Failures    | Updates, data, or deserialization cross an integrity boundary without adequate trust | Signed/provenanced artifacts; schema validation; authenticated integrity controls               |
| A09 | Security Logging and Alerting Failures | Attacks cannot be detected, investigated, or acted upon                              | Governed audit/security events; tested alerts; protected retention and response                 |
| A10 | Mishandling of Exceptional Conditions  | Error, resource, failover, or abnormal-state handling becomes exploitable            | Explicit failure modes; bounded resources; secure defaults; tests for partial/exceptional paths |

---

## Input Validation — The Permanent Battle

Every byte from outside is hostile until proven otherwise.

### Where to validate

| Layer              | What to check                                                                        | Why                                                         |
| ------------------ | ------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| **Edge (parsing)** | Structural: is it valid JSON / a valid date / a valid email syntactically?           | Reject malformed early                                      |
| **Application**    | Semantic: does this user exist? Is this date in the future? Is this amount positive? | Reject impossible domain values                             |
| **Domain**         | Business invariants: can this account afford this transaction?                       | Reject business-illegal values                              |
| **Persistence**    | Constraints: NOT NULL, foreign keys, CHECK constraints                               | Last line of defence; protects against bugs in layers above |

**Rule:** Validation at one layer does not replace validation at lower layers. Defence in depth.

### How to validate

- **Allowlist over denylist.** Define what is valid; reject everything else. Denylists are always incomplete.
- **Canonicalise before validation.** `../`, URL-encoded characters, Unicode normalisation forms — attackers exploit "validate before canonicalise" gaps.
- **Validate length, type, format, range, and character set** — in that order, cheap to expensive.
- **Reject, don't sanitise.** Sanitising silently changes data; the next bug will be confusion about why the stored value differs from the input.

### Encoding — context-aware, always

You are not "escaping for safety". You are _encoding for the target interpreter_. Each interpreter has its own rules:

| Target             | Encoding                                                      | Tool                                  |
| ------------------ | ------------------------------------------------------------- | ------------------------------------- |
| HTML body          | HTML entity-encode `< > & " '`                                | Templating engine in auto-escape mode |
| HTML attribute     | Different rules; quote and entity-encode                      | Same                                  |
| JavaScript context | Different again; usually generate via JSON, not string concat | `JSON.stringify`                      |
| URL                | Percent-encode                                                | Language stdlib URL builder           |
| Shell              | Don't. Use exec with argv array, never `shell=True`           | Language stdlib                       |
| SQL                | Parameterised queries. Always.                                | Driver-supported placeholders         |
| Log line           | Escape control characters and newlines                        | Log injection is a real category      |

---

## Authentication

**Authentication answers: "who are you?"** Not "what are you allowed to do?" — that's authorisation.

| Concern            | Default                                                                                                                                                                                                                            |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Password storage   | argon2id (preferred), scrypt, or bcrypt. Never MD5, SHA-1, SHA-256-unsalted.                                                                                                                                                       |
| Password policies  | Apply the product's governing standard. Under NIST SP 800-63B-4: minimum 15 for single-factor passwords, minimum 8 when used only within MFA, permit at least 64, block common/compromised values, and impose no composition rules |
| MFA                | TOTP (RFC 6238) for self-serve; WebAuthn/passkeys for serious cases; SMS only as a fallback because of SIM-swap                                                                                                                    |
| Session management | Server-side session store, opaque random token (≥128 bits), `HttpOnly; Secure; SameSite=Lax` cookie, rotate on auth state change, idle and absolute timeouts                                                                       |
| Sign-out           | Server-side invalidation, not just deleting the cookie                                                                                                                                                                             |
| Account recovery   | Treat as an authentication path with equivalent strength. Most breaches go through here.                                                                                                                                           |
| Federated identity | OIDC with current OAuth security BCPs and a maintained library. OAuth 2.1 is still an active Internet-Draft, not an RFC; verify the draft/status before relying on it                                                              |

**Anti-patterns:**

- Rolling your own crypto / token format.
- "Remember me" implemented as a long-lived cookie containing the user ID.
- Storing the password in a session.
- Returning different errors for "user not found" vs "wrong password" (account enumeration).

---

## Authorisation

**Authorisation answers: "may you do this thing to this resource?"**

| Model                          | When to use                                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------------------------------ |
| **RBAC** (role-based)          | Roles correspond to job functions; permissions are static per role                                     |
| **ABAC** (attribute-based)     | Decisions depend on attributes of the user, resource, and context                                      |
| **ReBAC** (relationship-based) | "May this user see this document?" depends on graph relationships (e.g., Google Drive's sharing model) |
| **PBAC** (policy-based)        | Externalised policy engine (OPA, Cedar) for cross-system rules                                         |

### The unbreakable rules

- **Authorise server-side.** Client-side authorisation is UX, not security.
- **Check authorisation on every request.** Not once at login.
- **Check at the data access boundary**, not just at the route. A correctly authorised route that calls an internal function that bypasses checks is a real and common bug.
- **Default deny.** If the answer is "I don't know", the answer is no.
- **Avoid IDOR.** When a request includes a resource ID, verify the _current user_ owns or is permitted on _that specific resource_. Tests for this are non-negotiable.

---

## Cryptography — Platform and Protocol First

| Need                 | Use                                                                                                             | Avoid                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| TLS                  | Maintained platform defaults implementing currently approved protocol profiles                                  | Obsolete protocols or application-defined cipher negotiation             |
| Symmetric encryption | A maintained high-level authenticated-encryption API with nonce/key handling specified by the platform/protocol | Raw block ciphers, unauthenticated encryption, nonce reuse               |
| Asymmetric           | The algorithm and parameters required by the current protocol/standard and supported security library           | Ad hoc key exchange/signature formats                                    |
| Hash                 | A current cryptographic hash selected for the actual integrity/signature/KDF protocol                           | Collision-broken algorithms for security decisions                       |
| Password hash        | A current memory-hard password hashing scheme and calibrated parameters where the governing standard permits it | General-purpose fast hashes                                              |
| Random               | OS CSPRNG (`/dev/urandom`, `crypto.randomBytes`, `secrets.token_bytes`)                                         | `Math.random()`, `random.random()`, `rand()`                             |
| JWT                  | If you must — verify signature, validate `iss`/`aud`/`exp`, accept only the algorithm you expect, never `none`  | Trusting the `alg` field; using JWTs as sessions when a session would do |

**Project default:** Prefer the operating system, language, protocol, or regulated platform's
maintained high-level security API. Record algorithm agility, key/nonce lifecycle, interoperability,
and the exact standard/profile. A library does not make a mis-specified protocol safe; obtain
specialist review for novel cryptographic protocol design.

**Standard/fact (verified 2026-07-30):** NIST SP 800-63B-4 is final and supplies the password
requirements summarized above:
[NIST SP 800-63B-4 authenticators](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/).
OAuth 2.1 was
[draft-ietf-oauth-v2-1-15](https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/) and an active
Internet-Draft last updated 2026-03-02. Re-verify both before adopting identity policy.

---

## Secrets Management

A secret in source code is a leak the moment it's committed. `git rm` doesn't help — assume the secret is public and rotate.

| Where to store                                                                  | When                                                           |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `.env` (gitignored)                                                             | Local development only                                         |
| OS keyring / secret manager (`pass`, macOS keychain)                            | Developer secrets                                              |
| Cloud secret manager (Vault, AWS/GCP/Azure Secrets Manager, Doppler, Infisical) | Production                                                     |
| Encrypted-at-rest config (SOPS, age) committed to repo                          | When secret manager is overkill but env vars are inappropriate |

**Discipline:**

- **Never log secrets.** Add explicit redaction in your logger.
- **Never include secrets in error messages, even when the error is rare.**
- **Rotate on suspicion.** A secret seen on a screenshare is a leaked secret.
- **Secret scanning:** use a reviewed local/CI scanner and the hosting provider's detection where
  available; verify findings and rotate exposed credentials.
- **Short-lived credentials > long-lived.** Prefer OIDC federation, IAM roles, or workload identity over static API keys.

---

## The Supply Chain

> Your code is a thin shell on top of a dependency graph you do not own.

| Risk                                                                | Mitigation                                                                                             |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Compromised package (typosquat, account takeover, malicious update) | Pin versions; use a lockfile; commit it; review high-impact updates                                    |
| Vulnerable dependency                                               | Automated scanning (`pnpm audit`, `pip-audit`, `cargo audit`, `dependabot`, `renovate`, `osv-scanner`) |
| Build pipeline compromise                                           | Reproducible builds; pinned tool versions; signed releases (Sigstore, in-toto)                         |
| Unverified install scripts                                          | Read what `curl \| sh` does before running it; prefer package managers                                 |
| Transitive bloat                                                    | Periodic dependency audit; remove what isn't used                                                      |

See [DEPENDENCIES](dependencies.md) for the operational form.

---

## Web-specific Hardening

If the project has a web interface, the baseline:

| Control                                            | What it does                                                      |
| -------------------------------------------------- | ----------------------------------------------------------------- |
| TLS + HSTS                                         | Encryption in transit, prevents downgrade                         |
| Content-Security-Policy                            | Defence against XSS even if the encoder fails                     |
| `X-Content-Type-Options: nosniff`                  | Stops MIME-sniffing attacks                                       |
| `Referrer-Policy: no-referrer` (or stricter)       | Doesn't leak URLs to third parties                                |
| `Permissions-Policy`                               | Disable browser features you don't use (camera, mic, geolocation) |
| `SameSite` cookies (Lax or Strict)                 | Mitigates CSRF                                                    |
| CSRF tokens for state-changing requests            | Belt-and-braces with SameSite                                     |
| Subresource Integrity (SRI) on third-party scripts | Pinned hashes                                                     |
| Rate limiting                                      | Auth, password reset, expensive endpoints                         |
| CORS — restrictive                                 | Allowlist origins; don't use `*` with credentials                 |

---

## API Hardening

| Control                                                                     | Default                                                  |
| --------------------------------------------------------------------------- | -------------------------------------------------------- |
| Authentication on every protected endpoint                                  | Yes; classify public endpoints explicitly                |
| Authorisation for every protected action and resource                       | Yes — authentication alone does not prevent IDOR         |
| Input size limits                                                           | Yes (body, fields, arrays) — prevent resource exhaustion |
| Rate limits per user and per IP                                             | Yes                                                      |
| Pagination with bounded page size                                           | Yes                                                      |
| Output schema validation                                                    | Yes — prevents accidental data exposure                  |
| Distinguish authentication failures (401) from authorisation failures (403) | Yes                                                      |

| Generic external errors with protected diagnostic detail | Usually; preserve actionable public error codes without leaking sensitive internals |
| Version/evolve the contract | Yes; choose the mechanism in [API design](api-design.md) |

Public health probes, static assets, discovery documents, and deliberately anonymous flows are
legitimate. Record them as public, expose only the minimum response, and apply appropriate abuse,
input, and output controls. “Unauthenticated” must be a design decision, not forgotten middleware.

---

## Specific Vulnerabilities Worth Knowing By Name

| Name                                 | What it is                                                   | Defence                                                               |
| ------------------------------------ | ------------------------------------------------------------ | --------------------------------------------------------------------- |
| **SQL injection**                    | Untrusted input concatenated into a query                    | Parameterised queries only                                            |
| **XSS (stored / reflected / DOM)**   | Untrusted input rendered as HTML/JS                          | Context-aware encoding; CSP                                           |
| **CSRF**                             | A request forged by another origin                           | SameSite cookies + CSRF tokens                                        |
| **SSRF**                             | Server makes attacker-chosen requests                        | Allowlist; refuse internal addresses; disable risky URL schemes       |
| **XXE**                              | XML parser resolves external entities                        | Disable external entities in the parser                               |
| **Path traversal**                   | `../` in user-supplied filenames                             | Canonicalise; allowlist; refuse anything not within a known root      |
| **Open redirect**                    | Login flow redirects to attacker-supplied URL                | Allowlist of redirect destinations                                    |
| **Insecure deserialisation**         | Pickle/Java/PHP deserialisation of untrusted data            | Don't; use a data format (JSON, MessagePack), not a code format       |
| **TOCTOU**                           | Time-of-check ≠ time-of-use                                  | Atomic operations; capability-based checks                            |
| **Race condition in business logic** | Two requests interleave to violate an invariant              | Pessimistic locking, transactions, atomic counters, idempotency keys  |
| **Mass assignment**                  | A form parameter sets a field it shouldn't (`is_admin=true`) | Explicit allowlist of bindable fields                                 |
| **Prototype pollution**              | (JS) An attacker mutates `Object.prototype`                  | Avoid recursive merge of untrusted data; use `Map`; freeze prototypes |
| **Server-side template injection**   | Untrusted input rendered as a template                       | Don't render untrusted input as templates; sandbox the engine         |
| **Regex denial of service (ReDoS)**  | Pathological input + backtracking regex                      | Linear-time engines (RE2); timeouts; avoid catastrophic patterns      |
| **HTTP request smuggling**           | Discrepancy between front and back proxies                   | Use modern HTTP servers; keep proxies in sync; HTTP/2+                |
| **CRLF injection / log injection**   | Newlines in user input forge log entries                     | Encode control characters in logs                                     |

---

## Logging — for Security, Specifically

Log enough to investigate, not so much that the log itself becomes a vulnerability.

**Log (with timestamps and a correlation ID):**

- Authentication: success, failure, lockout, MFA challenge, MFA success/failure
- Authorisation failures
- Privilege changes
- Account changes (email, password, MFA enrolment)
- Significant business events (payment, deletion, export, share)
- Security-relevant errors (rate-limit triggers, signature failures)

**Do NOT log:**

- Passwords. Anywhere. Ever.
- Full payment card numbers, full national IDs, full health records.
- Session tokens, JWTs, API keys, OAuth tokens.
- The whole request body when it contains the above.

**Protect the logs:**

- Append-only where it matters (audit logs).
- Tamper-evident (hash chain) for high-stakes systems.
- Retention aligned with [PRIVACY](privacy.md) obligations.

See [OBSERVABILITY](observability.md) for the rest of the logging story.

---

## Operations and Deployment

| Control                                | Why                                                                      |
| -------------------------------------- | ------------------------------------------------------------------------ |
| Reproducible builds                    | "It works on my machine" is a security problem too                       |
| Pinned base images and dependencies    | Drifting bases reintroduce CVEs                                          |
| Minimal, supported runtime images      | Smaller reviewed surface without trading away patchability/debuggability |
| Run as non-root                        | Container escape ⇒ unprivileged shell, not a root shell                  |
| Read-only filesystems where possible   | Limits post-exploitation                                                 |
| Network policies (egress allowlist)    | A compromised pod shouldn't be able to phone home                        |
| Backups, encrypted, restored regularly | A backup you've never restored is a hope, not a backup                   |
| Patch cadence with an SLA              | "Critical CVE in production within N hours"                              |
| Incident response runbook              | Decisions made in a calm room are better than decisions made at 2 AM     |
| Tabletop the runbook                   | Drills find the gaps                                                     |

---

## Privacy is Part of Security (and Vice Versa)

Encryption protects against unauthorised access. **Privacy** is about whether you should have the data at all, who can see it, where it lives, and how long it persists. Security controls without privacy thinking lead to systems that are well-defended hoarders of data they should never have collected.

See [PRIVACY](privacy.md) for the full treatment, including provider/transfer analysis, data
minimisation, retention, and data-subject rights.

---

## Secure Development and Response Lifecycle

**Project default:** Security work continues from inventory and design through decommissioning.

| Lifecycle capability             | Minimum useful evidence                                                                       |
| -------------------------------- | --------------------------------------------------------------------------------------------- |
| Asset and data inventory         | Owners, exposure, criticality, versions, environments, identities, data classes, dependencies |
| Security requirements            | Threat/abuse cases, protected assets, trust boundaries, control and verification owners       |
| Secure design and implementation | Reviewed patterns, misuse-resistant APIs, code review, secrets and dependency controls        |
| Control verification             | Static/dynamic/interactive tests selected by threat; authorization and negative-path tests    |
| Vulnerability management         | Intake, reachability/exploitability triage, severity, owner, SLA, exception expiry, retest    |
| Coordinated disclosure           | Discoverable reporting route, safe-harbor/process statement, acknowledgment and remediation   |
| Incident response                | Detection, containment, evidence preservation, communication, recovery, notification, lessons |
| Decommissioning                  | Credential revocation, data disposition, DNS/integration removal, inventory closure           |

A scanner finding is an input to risk triage, not proof of exploitability or absence. Conversely, a
clean scan does not cover missing authorization, insecure workflow design, business-logic abuse, or
unknown assets. Preserve tool/version/configuration, scope, findings, dispositions, and retest
evidence.

Exercise incident and disclosure paths. A runbook that no one can access, an alert no one receives,
or a security address that bounces is not an operational control.

---

## Specific Smells in Code Review

- `eval`, `exec`, `Function()`, `setTimeout("string")` — almost always a vulnerability vector.
- String concatenation that builds a query, command, URL, or HTML.
- `shell=True`, `os.system`, `Runtime.exec` with a constructed string.
- Cryptographic primitives used directly (`AES.new`, `RSA.encrypt`) — likely a misuse.
- Comparison of secrets with `==` instead of constant-time comparison.
- Logging that includes `request.body`, `headers`, or whole objects.
- `verify=False` on TLS clients.
- Hardcoded credentials, even "test" ones.
- `try: ... except: pass` around anything that could be a security check.
- `// TODO: add auth check`.
- Roll-your-own session/token/encryption scheme.
- Custom URL parsing or HTML parsing.
- Regex for parsing structured data (HTML, URLs, JSON, addresses).

---

## Diagnostic Framework

| Symptom                                              | Likely cause                                                   |
| ---------------------------------------------------- | -------------------------------------------------------------- |
| Auth checks scattered through handlers, inconsistent | No central authorisation; ad-hoc checks                        |
| "It's behind the VPN, so..."                         | Zero-trust violated; the VPN is one layer, not the only one    |
| Different test and production behaviour for auth     | Different auth in dev — a recipe for "works locally" disasters |
| Long-lived credentials in CI                         | Should be short-lived OIDC tokens                              |
| Manual security review just before release           | Security wasn't designed in; you're hoping to bolt it on       |
| The team doesn't know what the threat model is       | There isn't one                                                |
| Logs contain personal data                           | Privacy + security failure                                     |
| No one has run a vulnerability scan in months        | The supply chain is rotting                                    |

---

## Meta-Question

Security is not "did we add the security feature?" Security is the answer to: _what is the worst thing an adversary could do if they got past our weakest control, and how would we know?_ If you can't answer that, you don't have security — you have hope.

---

_See [PRIVACY](privacy.md) for data residency, minimisation, retention, and subject rights._
_See [OBSERVABILITY](observability.md) for the logging and alerting infrastructure that makes detection possible._
_See [DEPENDENCIES](dependencies.md) for supply-chain hygiene._
_See [CONFIGURATION](configuration.md) for secrets management in practice._
_See [CONTRIBUTING](contributing.md) Section 3 for what this project deliberately does not apply, and why._
