"""Load + validate a debate run-spec — the small YAML an agent writes to pose a question.

A run-spec is deliberately minimal so an agent can author one from `debate -h` alone:

    id: bio-andgate            # REQUIRED: slug; names the run directory
    protocol: delphi           # delphi | idea  (CLI --delphi/--idea overrides this)
    question: |                # REQUIRED: what the panel debates
      Does the biorisk AND-gate assumption hold ...?
    context: |                 # optional: grounding the panel must reason within
      <relevant background, excerpts, framing>
    criteria: |                # optional: rules appended to every round
      Each option must be distinct and independently defensible.

The question and grounding live ENTIRELY in the spec, so the engine + prompts stay domain-free
(ADR-0002).
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_runspec(path: str) -> dict:
    from debate.input_contracts import InputContractError, load_runspec_input

    p = Path(path)
    if not p.exists():
        raise SystemExit(f"run-spec not found: {p}")
    try:
        return load_runspec_input(yaml.safe_load(p.read_text()) or {}, source=p).to_runtime()
    except InputContractError as exc:
        raise SystemExit(str(exc)) from exc
