# Domain reference contract

This directory holds focused guidance for LLM-text task classes that materially change the shared
prompt-engineering method, such as judging, prompt evaluation, structured extraction, RAG, grounded
vision/OCR, and translation/localization.

Each domain module must:

- state its task boundary and the route ID that loads it;
- assume the shared method in `SKILL.md` rather than repeating it;
- separate durable guidance from provider/model-specific behavior;
- link to verified evidence in [`../references/SOURCES.md`](../references/SOURCES.md);
- include observable failure modes and an evaluation or regression-fixture contract;
- name neighboring capability skills when execution belongs elsewhere.

Adding a module is incomplete until its path appears in `routes.json`, routing fixtures cover the
new route and its neighbors, and `check-router.py` passes.
