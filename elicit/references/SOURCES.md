# Sources

Provenance for the elicit rubric, elicitation techniques, precision/
speed triage, and teaching guidance. A row records that the source was reviewed
on the accessed date, not that every synthesized claim is permanently true.
Re-verify before changing the caps, triggers, techniques, or claims the knowledge
files assert.

## Clarify-before-act tooling (market scan)

| Source                                                                    | Publisher / Author | URL                                                                        | Accessed   | Status   | Informs            | Groups      | Re-verify when                              |
| ------------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------- | ---------- | -------- | ------------------ | ----------- | ------------------------------------------- |
| Spec Kit `/clarify` template (≤5 questions, ranked by impact/uncertainty) | GitHub             | https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md | 2026-08-18 | verified | elicitation-rubric | src-speckit | Spec Kit changes its clarify caps/flow      |
| AWS Kiro — requirements-first + EARS + gap/conflict clarification         | AWS / Kiro         | https://kiro.dev/docs/specs/feature-specs/requirements-first/              | 2026-08-18 | verified | reverification     | src-kiro    | Kiro changes its clarification model        |
| BMAD-METHOD — advanced (post-generation) elicitation                      | BMAD Code          | https://docs.bmad-method.org/explanation/advanced-elicitation/             | 2026-08-18 | verified | forward-questions  | src-bmad    | BMAD revises its methods                    |
| Claude Code — plan mode & AskUserQuestion                                 | Anthropic          | https://code.claude.com/docs/en/agent-sdk/user-input                       | 2026-08-18 | verified | SKILL              | src-harness | the harness question/plan primitive changes |

## Latent / tacit knowledge and elicitation techniques

| Source                                                                                                           | Publisher / Author                                   | URL                                                                         | Accessed   | Status   | Informs          | Groups    | Re-verify when                         |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------- | ---------- | -------- | ---------------- | --------- | -------------------------------------- |
| Tacit knowing — "we can know more than we can tell"                                                              | Polanyi Society                                      | https://polanyisociety.org/glossary-of-polanyis-terminology/                | 2026-08-18 | verified | latent-knowledge | src-tacit | —                                      |
| SECI model (socialization→externalization)                                                                       | Nonaka (via PMC)                                     | https://pmc.ncbi.nlm.nih.gov/articles/PMC6914727/                           | 2026-08-18 | verified | latent-knowledge | src-tacit | —                                      |
| Contextual inquiry (observe in context; confirm interpretation)                                                  | GOV.UK                                               | https://www.gov.uk/guidance/contextual-inquiry                              | 2026-08-18 | verified | latent-knowledge | src-re    | —                                      |
| Eliciting and analyzing unstated requirements                                                                    | CMU SEI                                              | https://www.sei.cmu.edu/blog/eliciting-and-analyzing-unstated-requirements/ | 2026-08-18 | verified | latent-knowledge | src-re    | —                                      |
| Cognitive Task Analysis / Critical Decision Method / think-aloud / laddering / repertory grid (technique family) | research synthesis (codex research pass, 2026-08-18) | dev/docs/research/0002-knowledge-elicitation-techniques.md                  | 2026-08-18 | verified | latent-knowledge | src-cta   | a primary CTA source is cited directly |

## Question design without distortion (survey + expert elicitation)

| Source                                                   | Publisher / Author | URL                                                       | Accessed   | Status   | Informs          | Groups     | Re-verify when |
| -------------------------------------------------------- | ------------------ | --------------------------------------------------------- | ---------- | -------- | ---------------- | ---------- | -------------- |
| Writing survey questions (open vs closed, order effects) | Pew Research       | https://www.pewresearch.org/writing-survey-questions/     | 2026-08-18 | verified | latent-knowledge | src-survey | —              |
| Best practices (neutral wording, one concept at a time)  | AAPOR              | https://aapor.org/standards-and-ethics/best-practices/    | 2026-08-18 | verified | latent-knowledge | src-survey | —              |
| Sheffield Elicitation Framework (SHELF)                  | Univ. of Sheffield | https://shelf.sites.sheffield.ac.uk/home                  | 2026-08-18 | verified | latent-knowledge | src-expert | —              |
| Cooke's classical method (calibration-weighted)          | Cooke (REEP)       | https://www.journals.uchicago.edu/doi/10.1093/reep/rex022 | 2026-08-18 | verified | latent-knowledge | src-expert | —              |
| Delphi method (anonymous, iterative)                     | RAND               | https://doi.org/10.7249/TLA3082-1                         | 2026-08-18 | verified | latent-knowledge | src-expert | —              |

## Finding the real task + precision/speed

| Source                            | Publisher / Author      | URL                                                                               | Accessed   | Status   | Informs            | Groups        | Re-verify when |
| --------------------------------- | ----------------------- | --------------------------------------------------------------------------------- | ---------- | -------- | ------------------ | ------------- | -------------- |
| The XY problem                    | meta.stackexchange      | https://meta.stackexchange.com/questions/66377/what-is-the-xy-problem             | 2026-08-18 | verified | latent-knowledge   | src-realtask  | —              |
| Five Whys (root cause)            | IHI                     | https://www.ihi.org/library/tools/5-whys-finding-root-cause                       | 2026-08-18 | verified | latent-knowledge   | src-realtask  | —              |
| Means-ends analysis               | UC Berkeley (Kihlstrom) | https://www.ocf.berkeley.edu/~jfkihlstrom/IntroductionWeb/thinking_supplement.htm | 2026-08-18 | verified | latent-knowledge   | src-realtask  | —              |
| Jobs To Be Done                   | Christensen Institute   | https://www.christenseninstitute.org/theory/jobs-to-be-done/                      | 2026-08-18 | verified | latent-knowledge   | src-realtask  | —              |
| Bounded rationality / satisficing | Stanford Encyclopedia   | https://plato.stanford.edu/entries/bounded-rationality/                           | 2026-08-18 | verified | precision-vs-speed | src-satisfice | —              |

## LLM clarifying-question literature

| Source                                                                              | Publisher / Author                 | URL                                                                                                                 | Accessed   | Status     | Informs            | Groups | Re-verify when                 |
| ----------------------------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------- | ---------- | ------------------ | ------ | ------------------------------ |
| Specific-over-generic clarifying questions                                          | Rahmani et al., EACL Findings 2024 | https://aclanthology.org/2024.findings-eacl.84/                                                                     | 2026-08-18 | verified   | elicitation-rubric | src-cq | a stronger study supersedes it |
| MIMICS (clarification data; 2–5 candidate answers)                                  | Microsoft Research                 | https://www.microsoft.com/en-us/research/publication/mimics-a-large-scale-data-collection-for-search-clarification/ | 2026-08-18 | verified   | elicitation-rubric | src-cq | —                              |
| Ask-when-Needed / NoisyToolBench (missing-arg questions)                            | (paper)                            | https://huggingface.co/papers/2409.00557                                                                            | 2026-08-18 | verified   | elicitation-rubric | src-cq | —                              |
| Task vs referential uncertainty (humans ask about task; LLMs over-ask on referents) | CRAC 2025                          | https://aclanthology.org/2025.crac-1.1/                                                                             | 2026-08-18 | verified   | elicitation-rubric | src-cq | —                              |
| Efficient multi-turn info gathering / stop rule                                     | AskBench                           | https://github.com/jialeuuz/askbench                                                                                | 2026-08-18 | unverified | elicitation-rubric | src-cq | repo/paper confirmed           |

## Teaching (learning science)

| Source                                                                              | Publisher / Author              | URL                                                                                                                      | Accessed   | Status   | Informs  | Groups    | Re-verify when |
| ----------------------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------- | -------- | -------- | --------- | -------------- |
| Socratic questioning taxonomy (review)                                              | Frontiers in Education          | https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2019.00126/full                                    | 2026-08-18 | verified | teaching | src-teach | —              |
| Zone of Proximal Development / scaffolding                                          | NYSED brief                     | https://www.nysed.gov/bilingual-ed/topic-brief-4-zone-proximal-development-affirmative-perspective-teaching-ells-and-mls | 2026-08-18 | verified | teaching | src-teach | —              |
| Cognitive apprenticeship (model/coach/scaffold/articulate/reflect/explore)          | Collins, Brown & Holum (AFT)    | https://www.aft.org/ae/winter1991/collins_brown_holum                                                                    | 2026-08-18 | verified | teaching | src-teach | —              |
| Worked & faded examples                                                             | Frontiers in Education          | https://www.frontiersin.org/journals/education/articles/10.3389/feduc.2024.1293516/full                                  | 2026-08-18 | verified | teaching | src-teach | —              |
| Desirable difficulties                                                              | Bjork Learning & Forgetting Lab | https://bjorklab.psych.ucla.edu/research/                                                                                | 2026-08-18 | verified | teaching | src-teach | —              |
| Metacognitive demands & opportunities of generative AI                              | Microsoft Research              | https://www.microsoft.com/en-us/research/publication/the-metacognitive-demands-and-opportunities-of-generative-ai/       | 2026-08-18 | verified | teaching | src-teach | —              |
| Prompting as a poor end-user interface (shape intent, don't demand perfect prompts) | Google DeepMind                 | https://deepmind.google/research/publications/90773/                                                                     | 2026-08-18 | verified | teaching | src-teach | —              |

## Notes

- Sources were gathered via live web research passes on 2026-08-18 (a market scan
  plus three parallel literature passes, ~54 web searches total). The scans are
  recorded in `dev/docs/research/0001` (market) and `dev/docs/research/0002`
  (techniques/literature).
- Product-behavior and empirical claims are dated — re-verify against the linked
  page before changing this skill's contract. `unverified` rows need a confirmed
  primary source before load-bearing use.
