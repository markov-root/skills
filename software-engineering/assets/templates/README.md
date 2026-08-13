# Core document templates

These templates adopt the v2 queryable frontmatter core (ADR-0002 §1), so every governed doc is
first-class queryable: `schema_version, id, uid, title, role, status, summary, created, updated`,
plus `owner` / `supersedes` / `superseded_by` where the role needs them. There is one template per
`role`, covering all 16 roles of the closed vocabulary (ADR-0002 §3).

## Record roles (v2 flat core + `engineering_document` extension)

The six record roles carry the v2 flat core at top level AND preserve the `engineering_document`
extension block below it (authority, `state`, transition history, relationships, role-specific
`details`). Top-level `status` must equal the nested `engineering_document.state`. Create an adopted
record only through `engineering document new ROLE --title TITLE`; the allocator reserves the
number, mints `uid`, and stamps dates without generating approval, ownership, criteria, evidence, or
substantive prose.

| Template                     | Authority                    | Use for                                                  |
| ---------------------------- | ---------------------------- | -------------------------------------------------------- |
| [task](task.md)              | Bounded work state           | Problem, authorized scope, criteria, and completion      |
| [adr](adr.md)                | Accepted decision            | Chosen direction, consequences, and concise alternatives |
| [audit](audit.md)            | Point-in-time evidence       | Bounded method, observations, limits, and disposition    |
| [research](research.md)      | Decision input, not decision | Question, sources, uncertainty, and conclusion           |
| [lesson](lesson.md)          | Bounded reusable inference   | Transferable learning with evidence and exceptions       |
| [handoff](handoff.md)        | Current continuation state   | Revision-bound completed/open work and safe resume       |

## Living / reference / meta roles (v2 flat core only)

The ten remaining roles carry the v2 flat core with no `engineering_document` block.

| Template                         | Use for                                                |
| -------------------------------- | ------------------------------------------------------ |
| [specification](specification.md) | How a component currently behaves (contracts/boundaries) |
| [knowledge](knowledge.md)       | Durable knowledge with routing and sources             |
| [reference](reference.md)       | Lookup-oriented material with authoritative sources    |
| [standard](standard.md)         | Required practice and conventions for a scope          |
| [guide](guide.md)               | Task/workflow walkthrough with ordered steps           |
| [roadmap](roadmap.md)           | Planned direction, phases, and priorities              |
| [changelog](changelog.md)       | Notable dated changes in reverse-chronological order   |
| [runbook](runbook.md)           | Operational procedure with steps and troubleshooting   |
| [index](index.md)               | Pointers for navigating a body of knowledge            |
| [template](template.md)         | Reusable blank form other documents fill in            |

An ADR may stand alone. When material deliberation deserves its own research record, add one
`derived-from` edge from the ADR to the research record. Do not duplicate an inverse `decided-by`
edge.

Use `engineering document roles` to inspect adopted role contracts, `engineering document new` to
create one record without overwriting an existing path, and `engineering document validate` to
validate records. `roles` and `validate` are read-only; `new` creates exactly one adopted record.

## Experimental authoring aids

The [test-strategy template](test-strategy.md) maps risks and criteria to scenarios, inputs,
oracles, environments, fixtures, enforcement, evidence, and omissions. It is deliberately **not** an
adopted document role (no frontmatter core). Task 0038 owns the guidance artifact; Task 0049 may
promote an operational role only after at least two reviewed real examples and an explicit
disposition.
