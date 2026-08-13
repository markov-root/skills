---
knowledge:
  version: 1
  id: privacy
  summary: Engineer personal-data handling with minimization, purpose, lawful authority, retention, sovereignty, access, deletion, and verifiable boundaries.
  routes: [database-schema-migration, user-facing-interaction]
  sources: [src-privacy-law]
---

# privacy.md — Privacy and Data Sovereignty Reference

> **Purpose:** Reference for thinking about privacy as a first-class architectural concern. Covers data minimisation, lawful basis, retention, subject rights, and **where data should physically live**.
>
> **House preference:** Minimize collection and third-party disclosure. Prefer architectures whose
> operators cannot access user content, and evaluate provider role, jurisdiction, data location,
> contract, security, operations, and exit together. Geography or self-hosting alone does not
> establish privacy.
>
> **Read this when:** the system handles personal data, makes hosting decisions, integrates a third party, designs analytics, or determines retention.
>
> **Do NOT** treat this as legal advice. Treat it as engineering hygiene that _also_ makes legal compliance achievable.

---

## The Premise

Privacy is not a compliance checkbox. It is a property of the system's architecture, the data it collects, the third parties it talks to, and where the bytes physically sit. By the time you are asking "are we GDPR-compliant?", the architectural decisions have already been made — for or against you.

**The single most important question:** _Do we need this data at all?_ Data you don't have cannot leak, be subpoenaed, be sold, or harm a user.

---

## The Seven Privacy-by-Design Principles (Cavoukian)

These are the foundation. Each subsequent section is an operational form of one of these.

| #   | Principle                         | Operational form                                                            |
| --- | --------------------------------- | --------------------------------------------------------------------------- |
| 1   | Proactive, not reactive           | Threat model privacy before coding; not after a complaint                   |
| 2   | Privacy as the default            | Opt-in for non-essential collection, not opt-out                            |
| 3   | Privacy embedded in design        | Architectural enforcement, not policy documents                             |
| 4   | Full functionality — positive-sum | Reject the false trade-off "you can have features OR privacy"               |
| 5   | End-to-end security               | Encrypt in transit, at rest, and in use where the threat model justifies it |
| 6   | Visibility and transparency       | Users (and auditors) can verify what you claim                              |
| 7   | Respect for user privacy          | The user's interest is the system's interest                                |

---

## Data Minimisation — The Cheapest Defence

A hierarchy of best-to-worst:

1. **Don't collect it.** Best.
2. **Collect, but compute and discard.** Aggregate at ingest; never persist the raw value.
3. **Collect and pseudonymise immediately.** Replace identifier with a token; keep the mapping separately or never.
4. **Collect and anonymise immediately.** k-anonymity, differential privacy where applicable.
5. **Collect, encrypt at rest, restrict access, log access, expire on a schedule.** The baseline if you must.
6. **Collect and keep forever in plaintext, with broad access.** Wrong.

**Examples:**

| Tempting                          | Better                                                                                                                                      |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Store the user's full IP          | Store the /24 (IPv4) or /48 (IPv6) network, or just the country                                                                             |
| Store the user agent string       | Store the browser family + major version                                                                                                    |
| Store every page view             | Store aggregate counts per page per day                                                                                                     |
| Reuse account email for marketing | Store purpose-specific permission and contact data only when needed; a predictable email hash remains personal and is dictionary-attackable |
| Store DOB for age check           | Store `is_over_18: bool` after verification                                                                                                 |
| Store the photo for moderation    | Store a perceptual hash; discard the photo                                                                                                  |
| Store the audio recording         | Transcribe, summarise, discard the audio                                                                                                    |

---

## Categories of Personal Data — Treat Each Differently

| Category                             | Examples                                                                                                             | Handling                                                                                                                        |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Identifying**                      | Name, email, phone, address, account ID                                                                              | Pseudonymise where possible; encrypt at rest; access-log                                                                        |
| **Special categories (GDPR Art. 9)** | Health, qualifying biometrics/genetics, sexual orientation, political opinion, religion, race/ethnicity, trade union | Processing is prohibited unless an Art. 9(2) condition applies; explicit consent is one of several conditions, not the only one |
| **Financial**                        | Card numbers, bank accounts, transactions                                                                            | PCI-DSS scope; tokenise; never store raw card; minimum retention                                                                |
| **Government identifiers**           | Passport, national ID, SSN, tax ID                                                                                   | Hash for matching; do not store unless legally required                                                                         |
| **Behavioural**                      | Page views, clicks, dwell time, scroll depth                                                                         | Aggregate; do not link to identity unless strictly necessary                                                                    |
| **Location**                         | GPS, IP-derived, Wi-Fi triangulation                                                                                 | The most privacy-invasive class. Coarse-grain aggressively; never persist precise                                               |
| **Communications content**           | Messages, emails, voice, video                                                                                       | End-to-end encryption where possible; the operator should not be able to read                                                   |
| **Children's data**                  | Anything from users under the GDPR age threshold (13–16 by member state)                                             | Special regime; parental consent; default to refuse                                                                             |

---

## Lawful Basis (GDPR) — Pick One Per Purpose

Under GDPR every processing of personal data needs a lawful basis. Pick the most appropriate, not the easiest, and **document which** for each data flow.

| Basis                    | When                                                  | Pitfalls                                                                                          |
| ------------------------ | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Consent**              | The user has actively chosen                          | Must be granular, revocable, freely given. "Accept all cookies" walls are usually invalid consent |
| **Contract**             | Processing is necessary to deliver the service        | Marketing emails are not "necessary for the service"                                              |
| **Legal obligation**     | A law requires you to process                         | Cite the law                                                                                      |
| **Vital interests**      | Life or death                                         | Narrow                                                                                            |
| **Public task**          | Public authority work                                 | Narrow                                                                                            |
| **Legitimate interests** | A balancing test against the data subject's interests | Requires written Legitimate Interests Assessment; not a catch-all                                 |

**Project default:** Select the appropriate basis for each purpose and record the analysis. A single
processing operation should not use ambiguous interchangeable bases; distinct purposes may
legitimately use different bases.

---

## Data Subject Rights — Engineering Implications

A user can demand the following. The system must be able to answer.

| Right                                     | What it means                                   | Engineering requirement                                                               |
| ----------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Access**                                | "Give me everything you have on me"             | Be able to export. Means knowing where the data is.                                   |
| **Rectification**                         | "Fix this incorrect data"                       | Single source of truth; cascading updates to derived data                             |
| **Erasure (right to be forgotten)**       | "Delete me"                                     | Real deletion, not soft-delete; including backups (within retention) and derived data |
| **Restriction**                           | "Stop processing this, but don't delete it yet" | A flag the system honours, not a TODO                                                 |
| **Portability**                           | "Give me my data in a portable format"          | Machine-readable export (JSON, CSV)                                                   |
| **Objection**                             | "Stop processing for marketing / profiling"     | A consent state the system reads on every relevant action                             |
| **Not be subject to automated decisions** | "A human must decide if it's serious"           | Logged decision provenance; appeal path                                               |

**The data map.** If you cannot locate a person's data across primary stores, caches, queues, logs,
backups, derived stores, analytics, and recipients, rights handling will be unreliable. Build and
test the map before a request arrives.

Verify the requester's identity proportionately without collecting unnecessary new identity data or
exposing whether another person has an account. Record search scope, exceptions, approvals,
delivery/deletion actions, and completion evidence.

---

## Hosting, Transfers, and Provider Evaluation

**Legal note:** The EEA includes the EU member states plus Iceland, Liechtenstein, and Norway.
Adequacy decisions, transfer mechanisms, surveillance law, and regulator guidance can change.
Static country or vendor league tables become stale and obscure the facts of the processing.

For each processing activity and provider, evaluate:

| Dimension                 | Evidence to record                                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Role                      | Controller, joint controller, processor, subprocessor, recipient, or other role—by actual purposes and means |
| Data and purpose          | Fields/content/metadata, users, necessity, lawful basis, special-category condition                          |
| Access model              | Who holds keys; operator/admin/support access; end-to-end or client-side encryption                          |
| Location and jurisdiction | Storage, processing, support, backups, provider establishment, disclosure exposure                           |
| Transfer mechanism        | Adequacy, safeguards/clauses, derogation if applicable, and transfer-impact analysis                         |
| Contract and lifecycle    | DPA/terms, retention/deletion, subprocessors, breach notice, audit, model-training use, exit/export          |
| Operations                | Patch/access/backup/incident capability and staffing                                                         |

**House preference:** Prefer data minimization and effective end-to-end/client-side protection when
the product can support it. Self-hosting changes who operates the system; it can improve control or
make privacy/security worse if patching, access control, backups, incident response, or physical
security are weaker.

Keep volatile provider and country findings in a dated decision/source register. Re-verify before
purchase, renewal, architecture change, transfer, or handling a new data category.

---

## Cookies, Consent, and Tracking

**Legal note:** Consent and device-storage/access rules depend on jurisdiction, technology, purpose,
and current regulator/case-law guidance. The following are conservative EU-oriented defaults; verify
the actual deployment before relying on an exemption or banner design.

- **Strictly necessary cookies:** No consent required (session, CSRF, language). Keep them.
- **Everything else** (analytics, marketing, personalisation, A/B testing): explicit, granular, prior consent. Pre-ticked boxes are not consent. "Accept all" walls are likely invalid.
- **Reject must be as easy as accept.** One click each.
- **Default state must be "no consent."**
- **No cookie wall.** Conditioning access on accepting non-essential cookies is generally not valid consent under GDPR.
- **Honour Global Privacy Control** (`Sec-GPC: 1`) header as an objection signal.
- **Honour Do Not Track** (`DNT: 1`) where local law treats it as expressed preference (e.g., California).
- **Cookie-less analytics** may avoid rules that specifically require consent for storing or
  reading non-essential information on the user's device. It does not remove the need for a lawful
  basis, minimisation, retention limits, transparency, and processor review when personal data such
  as IP addresses is processed. Verify the law that applies to the actual deployment; the
  [EDPB lawful-processing guide](https://www.edpb.europa.eu/sme/be-compliant/process-personal-data-lawfully_en)
  is a starting point, not project-specific legal advice.

---

## Third Parties and Embeds — The Hidden Leak

A browser request to a third party normally discloses network and request metadata and may disclose
URL/referrer or cookies depending on browser policy and configuration. Treat each request as a data
flow to evaluate, not automatically as the same legal relationship.

| Pattern                                 | Risk                                                  | Lower-disclosure option                                                       |
| --------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------- |
| Third-party font/script/style CDN       | Request metadata and page context leave the site      | Self-host or use a reviewed first-party delivery boundary                     |
| Behavioral analytics/advertising script | Persistent identifiers, detailed events, profiling    | Purpose-limited aggregate/server-side measurement or none                     |
| Video/social/map/comments embed         | Network request, cookies/storage, account linking     | Click-to-load proxy/thumbnail or locally hosted alternative                   |
| CAPTCHA/fraud SDK                       | Behavioral/device data and accessibility consequences | Risk-based first-party controls or a provider reviewed for data/accessibility |
| Payment/identity SDK on every page      | Provider observes unrelated journeys                  | Load only on the workflow that requires it                                    |
| Email-hash avatar lookup                | Predictable identifier disclosed to provider          | User-uploaded/local generated avatar                                          |

**Legal note:** An embedded party may be a processor, independent controller, joint controller,
recipient, or multiple roles for different processing. Determine roles from who actually decides
purposes and essential means; contracts cannot relabel the facts. Apply the corresponding
agreement, transparency, consent/lawful-basis, transfer, and rights obligations.

---

## Analytics — A Worked Example

The most common privacy mistake is overcollection in analytics.

| Approach                           | Disclosure profile               | Review                                                                |
| ---------------------------------- | -------------------------------- | --------------------------------------------------------------------- |
| Cross-site behavioral/ad-tech      | High and identity-linked         | Necessity, consent/basis, profiling, recipients, transfers, rights    |
| Server-side log analysis           | Lower client-party disclosure    | Request/IP metadata, purpose, access, retention, lawful basis         |
| Self-hosted aggregate analytics    | Potentially lower disclosure     | Identifiers, re-identification, security, consent, transparency       |
| Managed privacy-oriented analytics | Configuration/contract dependent | Cookies/storage, roles, locations/transfers, retention, subprocessors |

**House preference:** Measure only what supports a named decision. Start from aggregate page/time
buckets and omit location/referrer/identifiers unless their incremental value justifies collection,
accuracy limits, notice/basis, retention, and re-identification risk.

---

## Retention — The Default Should Be "Short"

Set a retention period for every piece of data. The default is the shortest period that satisfies the purpose.

| Data                             | Example starting question—not a universal period                                                         |
| -------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Authentication logs              | What investigation/detection window is evidenced and legally permitted?                                  |
| Application logs                 | What operational window is necessary after redaction/aggregation?                                        |
| Web access logs (with IP)        | Can IP be omitted/truncated quickly; how long is raw data truly necessary?                               |
| Analytics aggregates             | Purpose-based; confirm aggregation is genuinely non-identifying before treating it as non-personal       |
| Inactive account                 | Deactivate after N months, delete after M months, with notice                                            |
| Backups                          | The shortest period that satisfies the recovery objective                                                |
| Audit logs of privileged actions | Retain for the documented security/legal purpose with restricted access; they may still be personal data |

**Mechanisms:**

- **TTL on the data store** (e.g., `created_at + interval '30 days'`) — easiest, automated.
- **Scheduled deletion jobs** — verifiable, idempotent, logged.
- **Logical deletion** is not deletion. Soft-delete is fine as a usability feature, but real deletion must follow on a schedule.

**Legal note:** Design backup erasure handling with qualified review. Common controls suppress
restoration into active use and let immutable backups expire under a documented, justified
schedule; no universal 30–90-day period is created by GDPR.

---

## Encryption — At Rest, In Transit, In Use

Select controls from the threat model, platform support, recovery design, key holders, performance,
and governing standards; [security](security.md) owns cryptographic implementation guidance.

| Layer                           | Candidate control                                                   | Claim it can support                                           |
| ------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------- |
| In transit (network)            | Current platform TLS plus appropriate browser transport policy      | Resistance to network disclosure/tampering                     |
| In transit (internal)           | Authenticated service transport such as mTLS where warranted        | Workload identity and resistance to internal-path interception |
| At rest (disk/database/object)  | Platform volume/database/object encryption with governed keys       | Protection for named storage-media or provider-access threats  |
| Application-level (fields)      | Established envelope/field encryption with separated key access     | Limits exposure after a database-only compromise               |
| End-to-end                      | Client encryption with a designed identity/recovery model           | Limits operator access to content, not necessarily metadata    |
| In use (confidential computing) | An attested confidential-computing boundary where evidence warrants | Reduces selected host/operator exposure                        |

**Key management:**

- Keys live in a separate system from the data (HSM, KMS).
- Rotate on compromise/suspicion and according to the cryptoperiod, platform, regulation, and
  operationally tested policy.
- Distinct keys per environment, per tenant where meaningful.
- Don't roll your own envelope encryption — use established formats (age, libsodium sealed boxes).

---

## Pseudonymisation and Anonymisation — Different Things

| Technique            | Reversible?           | Still personal data under GDPR? |
| -------------------- | --------------------- | ------------------------------- |
| **Pseudonymisation** | Yes (with the key)    | Yes — still in scope            |
| **Anonymisation**    | No, even in principle | No — out of scope               |

**Most "anonymised" data is actually pseudonymised.** Removing the name and keeping the postcode + DOB + sex is famously re-identifiable. Tools:

- **k-anonymity** (every quasi-identifier combination appears in ≥k rows)
- **l-diversity** (variety within each equivalence class)
- **Differential privacy** (mathematically bounded re-identification probability)

If a row can be tied back to a person with auxiliary data, treat it as personal data.

---

## Logging and Personal Data — Tension Resolved

You need logs to operate the system. Logs may contain personal data. Resolve the tension:

1. **Don't log what you don't need.** Whole request bodies are rarely needed.
2. **Structured logs with explicit fields.** Easier to redact, easier to query without surfacing irrelevant fields.
3. **Redact at the source.** Centralise the redaction; never trust handlers to remember.
4. **Short retention for logs that contain personal data.** Longer retention for aggregated metrics that don't.
5. **Access-log access to logs.** Who looked at the logs is also a security event.

See [OBSERVABILITY](observability.md) for the operational form.

---

## AI / LLM Use — Privacy Implications

If the system sends data to a third-party LLM provider:

- Treat each disclosed prompt, attachment, metadata field, and output as a data flow to the actual
  service parties and locations; terms and technical handling can change.
- Model provider training or secondary use as a threat scenario, then verify the actual service
  terms, product setting, retention, human access, subprocessors, region, deletion, and contractual
  commitments. A pessimistic assumption is not a substitute for this review.
- **Strip PII before sending.** Replace identifiers with placeholders; reinsert client-side.
- **Prefer self-hosted models** when the threat model justifies it (Ollama, vLLM, llama.cpp).
- Select hosted inference through the dated role/location/access/contract/transfer/operations
  analysis above; headquarters alone is not a privacy control.
- **Disclose in your privacy notice.** The user has a right to know.

---

## Third-Party Processor Inventory

For every external service, maintain a record:

| Field              | Example                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------- |
| Service            | Plausible (self-hosted)                                                                         |
| Purpose            | Page-view analytics                                                                             |
| Categories of data | URL, referrer, country (from IP, then discarded), user agent family                             |
| Lawful basis       | Legitimate interest (aggregated, no cookies, no personal data)                                  |
| Provider HQ        | n/a (self-hosted)                                                                               |
| Data location      | Frankfurt (Hetzner)                                                                             |
| Sub-processors     | Hetzner (DE)                                                                                    |
| DPA in place       | Yes, including the hosting subprocessor where the controller/processor relationship requires it |
| Retention          | 24 months aggregate                                                                             |
| Exit plan          | Postgres export → import to alternative                                                         |

This inventory supports a Record of Processing Activities; it is not automatically a complete
Article 30 record. Role, categories of recipients/data subjects, transfer safeguards, security
measures, and controller/processor-specific required fields may also apply.

---

## Privacy Engineering Lifecycle

### Purpose limitation and role mapping

For each processing activity, record the specific purpose before collection. New use is a new
decision: assess compatibility, lawful basis, notice/consent, recipients, retention, and user
expectations. Determine controller, joint-controller, processor, subprocessor, and recipient roles
from actual purposes and means.

### Privacy threat modeling

Use data-flow mapping plus a privacy method such as LINDDUN to examine linkability, identifiability,
non-repudiation, detectability, disclosure, unawareness, and non-compliance. Also model inference,
group harms, power imbalance, chilling effects, and misuse by authorized insiders where relevant.
Tie each threat to a control, owner, and verification method.

### DPIA and DPO triggers

**Legal note:** Under GDPR, a Data Protection Impact Assessment is required for processing likely
to result in high risk, with Article 35 naming examples such as certain systematic evaluation,
large-scale special-category/criminal data, and large-scale public monitoring. Supervisory
authority lists and current guidance matter. Start the DPIA early enough to change the design;
consult the DPO where designated and escalate residual high risk as required.

DPO designation depends on the organization's status and core processing activities, not the
software stack. Record the role assessment and qualified advice.

### Breach readiness

Maintain data/recipient maps, detection, containment, evidence preservation, risk assessment,
controller/processor escalation, communication, and notification paths. Under GDPR Article 33, a
controller may need to notify the supervisory authority without undue delay and, where feasible,
within 72 hours unless the breach is unlikely to risk people's rights and freedoms; processors
notify controllers without undue delay. Article 34 may require communication to affected people for
high risk. Preserve facts, decisions, timing, and remediation even when notification is not made.

### Rights operations

Exercise access, correction, restriction, objection, portability, and erasure workflows with:

- proportionate identity verification;
- search across primary and derived systems, recipients, and subprocessors;
- exception and legal-hold handling;
- secure delivery and audit trail;
- propagation and reconciliation after partial failure;
- service-level tracking without exposing another person's data.

---

## Decommissioning — The Forgotten Phase

Most leaks happen after a project is "done". Discipline:

- Decommission has the same rigour as deployment.
- **Data inventory before shutdown.** What exists, where, who has access?
- **Notify subjects** if retention is being cut short or data is being transferred.
- **Verifiable deletion.** Snapshot evidence; rotate keys to render any leftover encrypted data unrecoverable.
- **Revoke credentials** to all third parties.
- **Remove tracking codes** from any front-end the project shipped.
- **Tombstone the records** so re-creation is intentional, not accidental.

---

## Diagnostic Framework

| Symptom                                                | Likely cause                                                       |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| Cannot answer "where does data X live?"                | No data map; rights of subjects are aspirational                   |
| "We'll add the privacy banner before launch"           | Privacy is bolted on; the architecture has already decided         |
| Different teams each integrated their own tracker      | No processor inventory; the privacy notice is wrong                |
| Multiple analytics/session-replay SDKs load by default | Overlapping collection, recipients, purposes, and consent controls |
| "It's anonymised" with no re-identification analysis   | Probably pseudonymised; still in GDPR scope                        |
| Retention is "forever"                                 | No deletion schedule; storage will eventually become liability     |
| Logs contain emails, IPs, request bodies               | Operational convenience traded against privacy without a decision  |
| Third-party SDK added without a DPA                    | Processor relationship is unrecorded                               |

---

## The Three Questions to Ask of Any New Feature

1. **What new personal data does this collect?**
2. **What purpose, appropriate lawful basis, and—where relevant—special-category condition apply?**
3. **What is the retention, and who is responsible for enforcing it?**

If the answer to any of these is "I don't know" or "we'll figure it out", the feature is not ready to ship.

---

## Meta-Question

Privacy is the answer to: _if a user, an auditor, or a journalist asked us exactly what we know about a person, how we know it, who else has it, and how long we'll keep it — could we answer, and would we be comfortable with the answer?_

If the answer is no on either count, the engineering has more work to do.

## Primary Sources

**Standard/fact and legal notes verified 2026-07-30:**

- [GDPR official text on EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679)
  for Articles 5–6, 9, 13–22, 25, 28, 30, 32–39, and 44–49.
- [EDPB Guidelines 07/2020, final version](https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en)
  for functional controller/processor/joint-controller analysis.
- [EUR-Lex EEA glossary](https://eur-lex.europa.eu/EN/legal-content/glossary/european-economic-area-eea.html)
  for EEA membership.

Re-verify against the applicable regulator, jurisdiction, processing facts, and current transfer
mechanism before making a legal or provider decision.

---

_See [SECURITY](security.md) for the controls that protect what you do collect._
_See [OBSERVABILITY](observability.md) for logging discipline that respects retention._
_See [DEPENDENCIES](dependencies.md) for supply-chain privacy implications._
_See [CONFIGURATION](configuration.md) for jurisdiction and provider as configuration._
_See [CONTRIBUTING](contributing.md) Section 4 for the project-specific processor inventory._
