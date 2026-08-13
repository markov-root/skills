---
knowledge:
  version: 1
  id: principles
  summary: Apply cohesion, information hiding, explicit contracts, simple dependencies, and evidence-calibrated trade-offs without turning heuristics into laws.
  routes: [module-system-design, refactor-rewrite, technology-framework-choice]
---

# principles.md — Software Design Reference

> **Purpose:** This is a reference document, not an operational guide. Read it when you are:
>
> - Designing a new system or module
> - Debugging why something feels wrong
> - Deciding between two approaches
> - Learning the vocabulary of design
>
> **Do NOT** apply principles from this document retroactively to existing code without a specific problem to solve. See `contributing.md` Section 3 for what this project actually applies.

---

## How to read this reference

These are **decision lenses**, not laws. Almost every principle below is a _heuristic_ in the sense
of `epistemic-contract.md`: it names a force worth checking, and it carries a domain of validity, a
cost, and a counterexample where applying it makes the design worse. A few are stronger — where a
statement protects a **safety, security, privacy, or data-integrity invariant** it is marked as such
and is not optional.

Read the rest as questions to ask, not structures to impose:

- **Name the paradigm first.** Object-oriented, functional, data-oriented, capability-oriented,
  procedural, pipeline, and embedded designs each expose different invariants. A lens that clarifies
  one can add ceremony to another. Pick the lens that surfaces _this_ system's dominant risk.
- **Treat every ordering as a gradient, not a ranking to maximize.** The coupling and cohesion lists
  below are rough gradients with heavy context dependence, not a scoreboard; a "worse" position is
  often the right, deliberate choice.
- **Project policy wins.** `contributing.md` and accepted ADRs override anything here (_house
  preference_ / _project default_ at most); this file supplies vocabulary and trade-offs, not this
  project's adopted rules.

---

## The Four Levels of Design Thinking

Most confusion comes from mixing levels. A class-level mistake can lock in an architectural pattern.

```
Level 1: Local Design                ← Objects, functions, values, data, effects
Level 2: Module & Component Design   ← SOLID, GRASP, coupling/cohesion
Level 3: System Architecture         ← Patterns, layers, services
Level 4: Cross-Cutting Concerns      ← Security, failure, observability, ops
```

**Diagnostic:** When you have a design problem, identify the level first. Don't solve a Level 3 problem with a Level 1 pattern.

---

## Part 1 — Local Design

Object-oriented vocabulary is one useful lens, not the foundation of all software. Also consider:

| Lens                          | Design question                                                                                                |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Functional / value-based**  | Can immutable values and pure transformations make effects and tests clearer?                                  |
| **Data-oriented**             | Does layout and batch access fit the dominant data/CPU/cache behavior?                                         |
| **Capability-oriented**       | Can authority be passed explicitly as a narrow capability rather than found globally?                          |
| **Composition / pipelines**   | Can small components/functions be connected without inheritance or hidden lifecycle?                           |
| **Dataflow**                  | Is the design better described as data moving through transforms than as objects calling methods?              |
| **State-machine**             | Are legal states/transitions explicit and invalid states unrepresentable?                                      |
| **Information hiding**        | Which decisions are most likely to change, and is each sealed behind one module that hides it?                 |
| **Change amplification**      | For the changes we actually expect, how many modules must be edited — can the design shrink that blast radius? |
| **Locality of behaviour**     | Can this unit be understood from what's in front of you, without tracing distant call sites or global state?   |
| **Type-driven**               | Can the type system make illegal states and misuse unrepresentable rather than merely documented?              |
| **Temporal coupling**         | Does correctness depend on a hidden call order, and can that ordering be made explicit or enforced?            |
| **Socio-technical ownership** | Do module boundaries match team/ownership boundaries (Conway's law), so changes avoid cross-team coordination? |

Choose the lens that exposes the important invariant; do not force domain behavior into classes or
pure functions merely to satisfy a paradigm.

Most of these are _heuristics_, and their counterexamples are the point:

- **Information hiding / deep modules** pays off when a decision is both volatile and widely used;
  sealing a stable, single-use decision behind an interface is just indirection — a YAGNI violation.
- **Type-driven** design is powerful where the type system is expressive; in a dynamically typed
  script or a thin data transform it can cost more than it protects.
- **Socio-technical ownership** describes a force (Conway's law), not a mandate — a single small team
  can and often should ignore service/module splits that only pay off across team boundaries.
- **Locality** and **change amplification** frequently pull against maximal decomposition: another
  layer that reduces textual duplication can raise the number of files touched per real change.

### The Object-Oriented Lens: Four Pillars

These four are the vocabulary of the _object-oriented_ lens specifically — one paradigm among those
above, not the foundation of all design. In a functional or data-oriented design the same forces
reappear under other names (encapsulation ≈ module information hiding; polymorphism ≈ sum types +
dispatch). Use the pillar if you are already thinking in objects; do not introduce a class hierarchy
just to have something to encapsulate.

#### Encapsulation

Bundle data and behavior. Hide implementation. Expose only what's necessary.

**Key question:** If I change how this data is stored, how many files break?

**Failure modes:**

- Anemic domain model (data bags with no behavior)
- Over-exposure (making things public "just in case")
- Leaky abstraction (implementation detail leaks through interface)

#### Abstraction

Expose the _what_, hide the _how_. Model essential features, suppress irrelevant detail.

**Key question:** If the underlying technology changed, would this interface still make sense?

**Failure modes:**

- Too low (code reads like implementation)
- Too high (`process(x)` with no domain meaning)
- Premature abstraction (abstract base class for one implementation)

#### Inheritance

Model _is-a_ relationships. Use sparingly. Prefer composition.

**Key questions:**

- Is this genuinely _is-a_, or _has-a_ / _can-do_?
- If I change the parent, how many subclasses break?
- Is the hierarchy >2 levels deep? (smell)

**Failure modes:** Fragile base class, diamond problem, inheritance for reuse.

#### Polymorphism

Different types treated uniformly through a common interface.

**Key question:** Are there `if isinstance(x, TypeA)` checks that should be polymorphic dispatch?

**Failure modes:** Type switching, overuse where simple conditionals suffice.

### Coupling and Cohesion

Two of the most useful forces to weigh — but the lists below are **rough gradients, not total
orderings to maximize.** Context routinely justifies a "worse" position, and the labels are a
vocabulary for naming a cost, not a scoreboard.

**Coupling gradient (looser → tighter, roughly):**

1. Message coupling (well-defined interfaces)
2. Data coupling (simple data passed)
3. Stamp coupling (whole structure, part used)
4. Control coupling (flag controls callee)
5. External coupling (same external format)
6. Common coupling (shared global state)
7. Content coupling (direct internal modification)

_Counterexample:_ performance- or safety-critical code sometimes accepts tighter coupling on purpose
— a shared ring buffer, a control flag on a hot path, a memory layout two components agree on. The
gradient flags a cost to justify with evidence, not a rule to obey.

**Cohesion gradient (more focused → less, roughly):**

1. Functional (serves one well-defined function)
2. Sequential (output of A is input to B)
3. Communicational (operates on same data)
4. Procedural (sequence but no shared data)
5. Temporal (grouped by when they happen)
6. Logical (grouped because "similar")
7. Coincidental (grouped for no reason — `Utils.py`)

_Counterexample:_ **temporal cohesion** is the right choice for genuine lifecycle groupings —
startup, shutdown, request setup/teardown — where "when it runs" _is_ the shared reason. A
`initialize()` that wires unrelated subsystems in order is cohesive for that purpose, not a smell.

---

## Part 2 — Module Design Principles

### SOLID

| Principle                 | Core Question                                          | When Violated                                 |
| ------------------------- | ------------------------------------------------------ | --------------------------------------------- |
| **S**ingle Responsibility | Can I describe this in one sentence without "and"?     | Merge conflicts on unrelated changes          |
| **O**pen/Closed           | Can I add behavior without editing existing code?      | Every new feature touches old files           |
| **L**iskov Substitution   | Can I swap a subclass anywhere the parent is expected? | Subclasses that throw or no-op parent methods |
| **I**nterface Segregation | Do clients depend on methods they don't use?           | Fat interfaces, painful mocking               |
| **D**ependency Inversion  | Do high-level modules depend on abstractions?          | Can't test without real database              |

**Domain of validity (_heuristic_):** SOLID is a module/interface-level set of heuristics grown from
class-based OO. It transfers only partially. SRP and DIP restate cohesion and dependency direction
and apply broadly. LSP is about behavioural subtyping and is moot where you use no subtype
polymorphism. OCP-via-inheritance can _add_ indirection in functional or data-oriented code where a
plain function, a new match arm, or a data table is simpler and clearer. Apply the underlying force,
not the acronym; on a one-file script most of SOLID is overhead.

### GRASP (Responsibility Assignment)

| Pattern              | Question                               | Answer                                      |
| -------------------- | -------------------------------------- | ------------------------------------------- |
| Information Expert   | Who should have this responsibility?   | The class with the information              |
| Creator              | Who creates instances of X?            | The class that aggregates or closely uses X |
| Controller           | Who coordinates events?                | A dedicated controller, not UI or domain    |
| Low Coupling         | How to reduce impact of change?        | Minimize dependencies                       |
| High Cohesion        | How to keep complexity manageable?     | Keep each class focused                     |
| Polymorphism         | How to handle type-based alternatives? | Polymorphic operations, not conditionals    |
| Pure Fabrication     | What doesn't fit the domain?           | A synthetic class (e.g., Repository)        |
| Indirection          | How to decouple two things?            | Intermediate object                         |
| Protected Variations | How to prevent change impact?          | Wrap unstable with stable interface         |

**Protected Variations** is the unifying idea: everywhere something is likely to change, wrap it in a stable boundary. _Counterexample:_ wrapping a variation that is _not_ actually likely to change is speculative indirection (YAGNI) — the "protection" costs a boundary and buys nothing.

**Domain of validity (_heuristic_):** GRASP assigns responsibilities to _classes_; in functional or
data-oriented designs read "class" as "module or function" and the assignment questions still help.
Pure Fabrication and Controller can manufacture ceremony in a small program — a counterexample where
_not_ introducing a dedicated object is the better call.

### Extended Principles

- **DRY:** Keep one owner for stable knowledge, not necessarily one textual occurrence. Do not
  abstract from one example. A second concrete case permits comparison; extract when the common
  knowledge is stable and expected change/defect cost justifies the indirection—often around the
  third occurrence.
- **YAGNI:** Do not implement speculative capability. Generalize when real cases, consumers, or a
  costly boundary supply evidence.
- **Law of Demeter** (_heuristic_): prefer talking to immediate collaborators; a long
  `a.b().c().d()` chain that reaches through objects whose internals you shouldn't depend on is a
  coupling smell. Counterexample: fluent builders, pipelines, and query DSLs chain deliberately, and
  walking a plain data structure you own (`config.server.port`) is not a violation.
- **Command-Query Separation:** Keep reads free of hidden mutation where practical; a command may
  return identity/status/result without becoming a query.
- **Composition Over Inheritance** (_house preference_): "I have an X" is usually more flexible than
  "I am a kind of X". Counterexample: a genuine, stable subtype relationship where LSP holds — an AST
  node type, a framework base class you are required to extend, a sealed hierarchy matched
  exhaustively — is where inheritance is the clearer, safer model.

---

## Part 3 — System Architecture

### Choosing a Pattern

Before picking a pattern, answer:

1. What quality attributes matter most? (Performance? Modifiability? Testability?)
2. What are the primary axes of change?
3. What is the team/operational context?
4. What is the cost of being wrong?

### Patterns

#### Layered Architecture

```
Presentation → Application/Service → Domain → Infrastructure
```

**Use when:** Clear separation needed, well-defined use cases, testability matters.
**Failure mode:** Layer bypass (presentation reaches directly into DB).

#### Hexagonal / Ports & Adapters

Domain at centre. Everything else is a port (interface) and adapter (implementation).
**Use when:** You need to swap presentation or persistence symmetrically.

#### Pipe and Filter

```
Input → [Filter A] → [Filter B] → [Filter C] → Output
```

**Use when:** Data processing pipelines, independent transformations.
**Failure mode:** Filters sharing state.

#### Event-Driven

```
Producer → [Event Bus] → Consumer A
                        → Consumer B
```

**Use when:** Time/space decoupling, multiple consumers, audit trails.
**Failure mode:** Hard to debug, eventual consistency by default.

#### Microservices vs Monolith

- **Start monolith** when: unclear boundaries, small team, ops constraints
- **Move to services** when: clear bounded contexts, independent scaling, large team
- **Failure mode:** Distributed monolith, chatty services, shared database

---

## Part 4 — Cross-Cutting Concerns

> These cross-cutting tables are a **map with pointers**, not the authority. The canonical owners
> define the rules: [security](security.md); [error handling](error-handling.md) and
> [reliability](reliability.md) for failure, resilience, and incident practice;
> [observability](observability.md); and [performance](performance.md) for scaling. Use these tables
> to reach the right reference, not as a substitute for it.

### Security

- Defence in depth
- Principle of least privilege
- Zero trust
- Security by default
- Attack surface minimization

### Failure and Resilience

| Pattern            | What It Does                     |
| ------------------ | -------------------------------- |
| Timeout            | Fail after N seconds             |
| Retry with backoff | Retry with increasing delay      |
| Circuit breaker    | Stop trying after N failures     |
| Bulkhead           | Isolate failures                 |
| Fallback           | Degraded but functional response |
| Health check       | Expose `/health`                 |
| Idempotency        | Safe to retry                    |

### Observability

- **Logs:** What happened. Structured, queryable.
- **Metrics:** How much / how often / how long.
- **Traces:** Path of a single request.

### Scalability

- **Vertical:** More CPU/RAM on one machine.
- **Horizontal:** More instances; state must be partitioned, replicated, shared, or routed with
  explicit consistency/failover semantics.
- **First bottleneck:** Workload-specific. In data-backed applications, investigate persistence and
  network round trips early; measure before deciding.

---

## Part 5 — The Diagnostic Framework

### Level 0: Before You Design

- What problem are we actually solving?
- What are the quality attributes? (Rank them — you can't have everything)
- What are the constraints? (Tech, ops, time, sensitivity)
- What will change? What won't?

### Level 1: Local Unit Design (value, function, object, or module)

- What is the single responsibility?
- What state does it own? Is it private?
- What invariants must always be true?
- Does it depend on abstractions or concretions?
- Can it be tested without the entire world?

### Level 2: Module Design

- What are the natural seams?
- What changes together? Independently?
- Are there dependency cycles?
- Does business logic contain framework/DB specifics?

### Level 3: System Architecture

- Which pattern fits the quality attributes?
- Where is the source of truth for each data item?
- What are the transaction boundaries?
- Synchronous or asynchronous communication?

### Level 4: Cross-Cutting

- What is the threat model?
- What are the failure modes of every dependency?
- Can you diagnose production problems from logs?
- How is it deployed, configured, rolled back?

---

## The Meta-Question

Good design is **fit for purpose**. The principles above are tools. The goals are:

1. Correctness — Does it do what it should?
2. Clarity — Can someone understand it quickly?
3. Changeability — Can it evolve without falling apart?
4. Testability — Can you verify it works confidently?
5. Operability — Can you run, monitor, and fix it?

When a principle doesn't serve any of these goals in your specific context, **skip it with a documented reason**. The worst outcome is dogma.

---

_This is reference material. Apply selectively. See contributing.md for what this project actually applies._
