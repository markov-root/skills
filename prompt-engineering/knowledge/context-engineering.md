# Context engineering — prompting for agents, tools & long horizons

Prompt engineering is a _subset_ of **context engineering**: the systematic assembly of the whole
inference payload — system prompt, repo instructions, tool definitions, tool outputs, retrieval,
memory, recent history, and compacted summaries. "Failures often stem from missing or poorly-formatted
context rather than model limitations." Sources: Anthropic engineering (context/tools/harnesses 2025),
OpenAI GPT-5 & Agents SDK, Gemini, plus arXiv surveys — see the
[`source register`](../references/SOURCES.md).

## System prompts for agents

Structure into clear sections rather than a wall of imperatives:

- **Role / objective** — who the agent is, what "done" means.
- **Constraints** — hard rules, stated near where they apply; positive form.
- **Tool policy** — which tools, when to use vs not, permission/confirmation rules.
- **Context policy** — what to read, when to retrieve, how to treat untrusted content.
- **Output / stop / escalate** — response shape; when to ask, hand off, or stop.
- Add examples **only where they encode a measured behavior gap**, not decoratively.

Keep it explicit but not "procedural spaghetti." Newer models are literal and proactive — remove
redundant anti-laziness blocks if evals show over-triggering or overlong answers.

## Durable repo context (CLAUDE.md / AGENTS.md)

For coding agents, put stable project knowledge in **versioned instruction files** and maintain them
like code: build/test commands, architecture, style rules, unsafe operations, review expectations,
known traps. Research now studies these files directly (Context Engineering for AI Agents in OSS, MSR 2026) — treat context as an _evolving playbook_ updated from execution feedback (Agentic Context
Engineering, ICLR 2026), not a write-once doc.

## Tool and orchestration boundary

Tool descriptions, delegation packets, handoffs, manager/worker topology,
parallel ownership, merge, verification, and termination now have a focused
route: `agentic-tools.md` plus `agentic-contracts.md`. Load them
for tool-use or multi-agent work rather than expanding this general context
module.

## Retrieval & memory

- **Just-in-time retrieval** where possible: give the agent identifiers, paths, indexes, and search
  tools rather than stuffing whole corpora into context. Upfront retrieval only for narrow,
  latency-sensitive tasks (agentic RAG survey, ACL 2026).
- **Memory systems** (A-MEM, NeurIPS 2025): dynamic indexing/linking of evolving notes for long tasks.
- **Filesystem-as-context** and append-only context are practical patterns for long runs (Manus 2025).
- Keep **authoritative workflow state** distinct from memory and conversation history. A completed
  booking, approval status, current step, or retry count belongs in typed runtime state with provenance;
  do not ask the model to reconstruct it from a prose summary. Insert only the state needed for the
  current decision and update it through validated transitions.

## Long-horizon agents & compaction

- Manage the context lifecycle explicitly: compaction, structured notes, memory, recent-file carryover,
  artifacts for the next window (Anthropic harnesses 2025).
- **Compaction should preserve** decisions, unresolved bugs, assumptions, commands run, changed files,
  and next actions. **Start high-recall, then trim** — drop raw old tool outputs first; it's safer to
  keep too much critical state early than to lose a subtle decision.
- Prefer fresh-window + filesystem-state discovery over lossy compaction when feasible; on restart be
  prescriptive ("run `pwd`, read progress notes and the test file, run the integration test first").

## Cache-aware context construction

Prompt caches reuse an unchanged prefix. Optimize layout without sacrificing correctness:

1. Put stable instructions, tool schemas, output schemas, examples, and reusable context first.
2. Append the current task, timestamps, request IDs, retrieved results, and changing state last.
3. Update state with later messages or append-only artifacts instead of rewriting earlier context.
4. Keep model, effort/reasoning mode, tool definitions, and schema versions stable within a task
   phase. Change them when correctness requires it, accepting an intentional rebuild.
5. Place an explicit cache boundary immediately after stable bulk content only when the provider and
   workload support it. A boundary after volatile content protects little.
6. Compact at a task boundary. Preserve the parent system/tool prefix and record objective,
   decisions, files, verification, and unresolved work in the new tail.
7. Never serve stale facts merely to protect a cache hit. Security policy, permissions, current user
   intent, fresh retrieved evidence, and corrected instructions override reuse.

Measure rather than infer. Use `cache-check --json` from the `situational-awareness` skill to compare read,
write, and uncached tokens before and after one controlled layout change. Provider TTLs, prices,
minimums, and invalidators live in
the source register; re-verify provider-specific cache behavior before relying on it.

## Safety: treat retrieved content as untrusted

Web pages, repo files, emails, and tool outputs are **data, not instructions** — they must not override
system/developer rules (indirect prompt injection; Gemini security safeguards 2025). Gate write actions
and any sensitive exfiltration path; keep a clear trust boundary between instructions and content.

## Evaluate with realistic tasks

Test prompts and tools on multi-step tasks, not toy calls. Track: task success, tool-choice
correctness, invalid-argument rate, tool-call count, tokens, latency, cache-hit rate, and read the
_failure transcripts_.
