# Sources

Annotated bibliography for the `prompt-engineering` skill. **Every citation here was run through a
source-verification pass**; the initial corpus was checked 2026-07-26 and later additions carry their
own review date. The status tag records the result:

- **✓ verified** — URL resolves and title/authors/date match.
- **✎ corrected** — resolves, but the original research draft had a wrong title/author/date; the
  corrected metadata is shown here.
- Anything that **could not be verified is quarantined** in the last section and is _not_ relied upon.

Every entry carries an explicit URL so it is one click to rediscover.

> Why the fuss: the automated literature sweep (GPT-5.5 + web search) produced several plausible-looking
> but **fabricated** citations in the surveys/taxonomies facet (invented ScienceDirect/IEEE papers,
> arXiv IDs that actually point to unrelated math papers). Verification caught them. This is the whole
> reason the skill treats citations as leads-until-verified. Re-apply this discipline on every refresh.

## Primary provider guides (foundation)

The artifact publishes synthesis and citations, not mirrored copies of provider documentation.

- ✓ **Anthropic — Prompt engineering overview.**
  <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview>
- ✓ **Google — Prompt Engineering**, Lee Boonstra, Feb 2025.
  <https://www.kaggle.com/whitepaper-prompt-engineering>
- ✓ **IBM — Prompt engineering.** <https://www.ibm.com/think/prompt-engineering>

## Official provider docs (online, current)

- ✓ **Anthropic Code with Claude 2026 — The prompting playbook**, Margot van Laar. Official
  [session page](https://claude.com/code-with-claude/session/ldn-the-prompting-playbook) and
  [recording](https://youtu.be/G2B0YWuJUgI). Reviewed 2026-07-31; claim-level synthesis
  and limits informed the installed knowledge modules.
- ◐ **Anthropic Code with Claude 2026 — How Metaview built self-improving prompts for application
  review**, Nick Mayhew. Exact [recording](https://youtu.be/A3rmSUp6Dxg?list=PLmWCw1CzcFilPJdvw6scjHjbBripZWFps)
  and [official session page](https://claude.com/code-with-claude/session/ldn-ext-how-metaview-built-self-improving-prompts-for-application-review).
  Reviewed 2026-07-31. YouTube subtitles are disabled; promoted claims were corroborated against
  first-party Metaview documentation.
- ✓ **DeepLearningAI — Full AI Prompting Course with Andrew Ng.**
  <https://youtu.be/8ib4Qnh2HFE>. Complete English transcript reviewed 2026-07-31; source-level
  synthesis and volatility notes informed the installed knowledge modules.
- ✓ **Confluent Developer — Prompt Engineering is dead**, Tim Berglund.
  <https://youtu.be/Cs7QiSi8KLY>. Complete English transcript reviewed 2026-07-31; architectural
  claims and unsupported utilization advice are separated in the practitioner synthesis.
- ✓ **IBM Technology — Context Engineering vs. Prompt Engineering: Smarter AI with RAG & Agents**,
  Martin Keen. <https://youtu.be/vD0E3EUb8-8>. Complete English transcript reviewed 2026-07-31;
  durable context-system guidance is separated from illustrative ratios and examples in the
  practitioner synthesis.
- ✓ **OpenAI — Prompt engineering** (API docs). <https://platform.openai.com/docs/guides/prompt-engineering>
- ✓ **OpenAI — Prompt engineering best practices for ChatGPT** (Help Center). <https://help.openai.com/en/articles/10032626-prompt-engineering-best-practices-for-chatgpt>
- ✎ **Anthropic — Prompting best practices** (title corrected from "Claude Prompting Best Practices"). <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
- ✎ **Google — Prompt design strategies** (Gemini API docs; updated 2026-06-10). <https://ai.google.dev/gemini-api/docs/prompting-strategies>
- ✓ **OpenAI Cookbook — GPT-4.1 Prompting Guide**, MacCallum & Lee, Apr 14 2025. <https://cookbook.openai.com/examples/gpt4-1_prompting_guide>
- ✓ **OpenAI Cookbook — GPT-5 prompting guide**, Aug 7 2025. <https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide>

## Surveys, taxonomies & "what is a good prompt"

- ✓ **The Prompt Report: A Systematic Survey of Prompting Techniques**, Schulhoff et al., Jun 2024 — _foundational-but-older_, still the canonical technique taxonomy. <https://arxiv.org/abs/2406.06608>
- ✎ **A Taxonomy of Single-Turn Textual Prompt Patterns for LLMs**, Vennila Sooben & Eugene Syriani, Jun 2026 _(author corrected)_. <https://arxiv.org/abs/2607.00043>
- ✎ **What Makes a Good Natural Language Prompt?**, Do Xuan Long et al., ACL 2025 (long) _(authors corrected — not "Yiming Zhang")_. <https://aclanthology.org/2025.acl-long.292/>
- ✎ **Prompt Engineering for LLMs: A Survey**, Banghao Chen et al. _(the draft's arXiv:2502.11564 was a wrong ID — an unrelated diffusion paper)_. arXiv: <https://arxiv.org/abs/2310.14735> · journal (_Patterns_ 2025): <https://doi.org/10.1016/j.patter.2025.101260>
- ✎ **Privacy-Preserving Prompt Engineering: A Survey**, Kennedy Edemacu & Xintao Wu, ACM Computing Surveys, May 6 2025 _(authors corrected)_. <https://dl.acm.org/doi/10.1145/3729219>

## Agentic prompting & context engineering (all verified)

- ✓ **Effective context engineering for AI agents**, Anthropic, Sep 29 2025. <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- ✓ **Writing effective tools for agents — with agents**, Anthropic, Sep 11 2025. <https://www.anthropic.com/engineering/writing-tools-for-agents>
- ✓ **Introducing advanced tool use** (tool search, programmatic calling, deferred loading), Anthropic, Nov 24 2025. <https://www.anthropic.com/engineering/advanced-tool-use>
- ✓ **Effective harnesses for long-running agents**, Anthropic, Nov 26 2025. <https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents>
- ✓ **New capabilities for building agents on the Anthropic API**, May 22 2025. <https://claude.com/blog/agent-capabilities-api>
- ✓ **New tools for building agents** (Responses API, Agents SDK), OpenAI, Mar 11 2025. <https://openai.com/index/new-tools-for-building-agents/>
- ✓ **New tools and features in the Responses API**, OpenAI, May 21 2025. <https://openai.com/index/new-tools-and-features-in-the-responses-api/>
- ✓ **The next evolution of the Agents SDK**, OpenAI, Apr 15 2026. <https://openai.com/index/the-next-evolution-of-the-agents-sdk/>
- ✓ **Gemini thinking** (thinking budgets, thought summaries), Google, updated Jul 21 2026. <https://ai.google.dev/gemini-api/docs/thinking>
- ✓ **Gemini 2.5: Updates to our family of thinking models**, Google DeepMind, Jun 2025. <https://developers.googleblog.com/en/gemini-2-5-thinking-model-updates/>
- ✓ **Advancing Gemini's security safeguards** (indirect prompt injection), Google DeepMind, May 2025. <https://deepmind.google/blog/advancing-geminis-security-safeguards/>
- ✓ **A Survey of Context Engineering for Large Language Models**, Mei et al., Jul 2025. <https://arxiv.org/abs/2507.13334>
- ✓ **Context Engineering for AI Agents in Open-Source Software** (studies `AGENTS.md` etc.), Mohsenimofidi et al., MSR 2026. <https://arxiv.org/abs/2510.21413>
- ✓ **Agentic Context Engineering: Evolving Contexts for Self-Improving LMs**, Zhang et al., ICLR 2026. <https://arxiv.org/abs/2510.04618>
- ✓ **PLAY2PROMPT: Zero-shot Tool Instruction Optimization**, Fang et al., ACL Findings 2025. <https://arxiv.org/abs/2503.14432>
- ✓ **A-MEM: Agentic Memory for LLM Agents**, Xu et al., NeurIPS 2025. <https://arxiv.org/abs/2502.12110>
- ✓ **Stop Overthinking: A Survey on Efficient Reasoning for LLMs**, Sui et al., 2025. <https://arxiv.org/abs/2503.16419>
- ✓ **Data-Centric Perspectives on Agentic RAG: A Survey**, Deng et al., ACL Findings 2026. <https://aclanthology.org/2026.findings-acl.78/>
- ✓ **The rise of "context engineering"**, Harrison Chase / LangChain, Jun 2025. <https://www.langchain.com/blog/the-rise-of-context-engineering>
- ✓ **Don't Build Multi-Agents**, Walden Yan / Cognition, Jun 2025. <https://cognition.com/blog/dont-build-multi-agents>
- ✓ **Multi-Agents: What's Actually Working**, Cognition, Apr 2026. <https://cognition.com/blog/multi-agents-working>
- ✓ **Context Engineering for AI Agents: Lessons from Building Manus**, "Peak" Ji / Manus, Jul 2025. <https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus>

## Empirical evidence — what works vs myths (all verified)

- ✓ **The Format Tax** (structured-output accuracy cost), Lee et al., Apr 2026. <https://arxiv.org/abs/2604.03616>
- ✓ **ReasonIF: Large Reasoning Models Fail to Follow Instructions During Reasoning**, Kwon et al., Oct 2025. <https://arxiv.org/abs/2510.15211>
- ✓ **When Thinking Fails: The Pitfalls of Reasoning for Instruction-Following**, Li et al., May 2025. <https://arxiv.org/abs/2505.11423>
- ✎ **Scaling Reasoning, Losing Control: Evaluating Instruction Following in Large Reasoning Models** (introduces MathIF), Fu et al., May 2025 _(full title restored)_. <https://arxiv.org/abs/2505.14810>
- ✓ **Prompting Science Report 2: The Decreasing Value of Chain of Thought**, Meincke, Mollick, Mollick, Shapiro, Jun 2025. <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5285532>
- ✎ **Prompting Science Report 3: "I'll pay you or I'll kill you — but will you care?"** (tipping/threats), Meincke et al., Aug 2025 _(full title restored)_. <https://arxiv.org/abs/2508.00614>
- ✎ **Mind Your Tone: Investigating How Prompt Politeness Affects LLM Accuracy** (short paper), Dobariya & Kumar, Oct 2025. <https://arxiv.org/abs/2510.04950>
- ✓ **Emotional prompting amplifies disinformation generation**, Vinay et al., _Frontiers in AI_, Apr 7 2025. <https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1543603/full>
- ✓ **Flaw or Artifact? Rethinking Prompt Sensitivity in Evaluating LLMs**, Hua et al., EMNLP 2025. <https://aclanthology.org/2025.emnlp-main.1006/>
- ✎ **When Punctuation Matters**, Seleznyov et al., Aug 2025 _(arXiv confirmed; the "EMNLP Findings" listing was not independently confirmed)_. <https://arxiv.org/abs/2508.11383>
- ✓ **A Single Character can Make or Break Your LLM Evals** (delimiters swing MMLU ±23%), Su et al., Oct 2025. <https://arxiv.org/abs/2510.05152>
- ✎ **What's in a Prompt?: A Large-Scale Experiment on Prompt Design vs Annotation Compliance/Accuracy**, Atreja et al., ICWSM 2025. <https://ojs.aaai.org/index.php/ICWSM/article/view/35807>
- ✓ **Distance between Relevant Information Pieces Causes Bias in Long-Context LLMs** (LongPiBench), Tian et al., ACL Findings 2025. <https://aclanthology.org/2025.findings-acl.28/>
- ✓ **On Positional Bias of Faithfulness for Long-form Summarization**, Wan, Vig, Bansal, Joty, NAACL 2025. <https://aclanthology.org/2025.naacl-long.442/>
- ✓ **On the Self-Verification Limitations of LLMs on Reasoning and Planning Tasks**, Stechly, Valmeekam, Kambhampati, ICLR 2025. <https://proceedings.iclr.cc/paper_files/paper/2025/hash/f3c5e56274140e0420baa3916c529210-Abstract-Conference.html>
- ✎ **Calibrating Large Language Models with Sample Consistency**, Lyu et al., AAAI 2025. <https://ojs.aaai.org/index.php/AAAI/article/view/34120>
- ✎ **Which Prompting Technique Should I Use? An Empirical Investigation for Software-Engineering Tasks**, Santana et al., Jun 2025. <https://arxiv.org/abs/2506.05614>
- ✓ **The Few-shot Dilemma: Over-prompting LLMs**, IEEE FLLM 2025. <https://doi.org/10.1109/FLLM67465.2025.11391015>

## Quarantined — could NOT be verified (NOT relied upon)

Appeared in the raw sweep but verification could not confirm them; **do not cite** without independently
confirming they exist. Recorded so a future refresh doesn't re-surface them as "new".

- ✗ _"A Comprehensive Survey of Prompt Engineering…"_, attributed to Debnath et al., _Computer Science Review_ — **not found**; appears fabricated. Claimed URL (dead/invalid): <https://www.sciencedirect.com/science/article/pii/S1574013726000761>
- ✗ _"How Prompt Engineering Methodologies Affect the Abilities of LLMs: A Systematic Review"_ — the claimed ID <https://arxiv.org/abs/2606.00559> is an **unrelated** paper; the review is unconfirmed.
- ✗ _"Prompt Engineering in Software Engineering: A Systematic Literature Review"_ — the claimed ID <https://arxiv.org/abs/2508.09842> is a **mathematics** paper (_Branched Covers of Open Manifolds_). Fabricated attribution.
- ✗ _"Prompt Engineering for Healthcare…"_ — claimed <https://ieeexplore.ieee.org/document/10839229> **not confirmed**.
- ℹ Real alternative if a broad 2024 survey is wanted: **Sahoo et al., "A Systematic Survey of Prompt Engineering in LLMs"** — verify before citing: <https://arxiv.org/abs/2402.07927>

---

_Initial corpus verified: 2026-07-26. Targeted additions are dated in place. Refresh records and
working notes remain in the sibling development workspace and are not part of the installed artifact._
