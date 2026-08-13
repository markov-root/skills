"""Single stdout renderer for human and structured CLI results."""

from __future__ import annotations

import json
from typing import Any

from ..commands.contracts import Explanation


def render_explanations(explanations: tuple[Explanation, ...], *, detailed: bool) -> str:
    if not detailed:
        lines = [
            "# Engineering capability catalog",
            "",
            (
                "Coding ability is not the capability boundary. These controls make work "
                "repository-aware, repeatable, and evidence-bound."
            ),
            "",
        ]
        lines.extend(f"- `{item.id}` — {item.purpose}" for item in explanations)
        lines.extend(("", "Run `engineering explain IDENTIFIER` for the full contract."))
        return "\n".join(lines)
    lines: list[str] = []
    for item in explanations:
        lines.extend(
            (
                f"# {item.id} — {item.title}",
                "",
                item.purpose,
                "",
                "## Use when",
                "",
                *(f"- {value}" for value in item.use_when),
                "",
                "## Do not use when",
                "",
                *(f"- {value}" for value in item.do_not_use_when),
                "",
                "## Prerequisites",
                "",
                *(f"- {value}" for value in item.prerequisites),
                "",
                "## Effects",
                "",
                f"- Filesystem: {item.effects.filesystem}",
                f"- Network: {item.effects.network}",
                f"- Mutation: {item.effects.mutation}",
                f"- Cost: {item.effects.cost}",
                "",
                "## Evidence and limits",
                "",
                *(f"- Evidence: {value}" for value in item.evidence),
                *(f"- Limit: {value}" for value in item.limitations),
                "",
                "## Next commands",
                "",
                *(f"- `{value}`" for value in item.next_commands),
                "",
            )
        )
    return "\n".join(lines).rstrip()


def emit(payload: dict[str, Any], *, json_output: bool, human: str | None) -> None:
    if json_output:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
    elif human is not None:
        print(human)
    else:
        print(f"{payload['command']}: {payload['status']}")
