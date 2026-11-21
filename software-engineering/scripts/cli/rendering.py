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


_NON_PASSING_STATUSES = frozenset({"failed", "timed_out", "unavailable"})
_CHECK_OUTPUT_TAIL_LINES = 5


def _status_detail(result: dict[str, Any]) -> str:
    exit_code = result.get("exit_code")
    if exit_code is not None:
        return f"exit {exit_code}"
    signal = result.get("signal")
    if signal is not None:
        return f"signal {signal}"
    return "no exit code"


def _check_output_tail(result: dict[str, Any]) -> tuple[str, ...]:
    combined = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
    lines = [line.rstrip() for line in combined.splitlines() if line.strip()]
    if not lines:
        return ()
    return tuple(lines[-_CHECK_OUTPUT_TAIL_LINES:])


def _check_failure_lines(payload: dict[str, Any]) -> list[str]:
    """Render one summary line plus a bounded output tail per failing check."""
    lines: list[str] = []
    results = payload.get("results")
    if not isinstance(results, list):
        return lines
    for result in results:
        if not isinstance(result, dict):
            continue
        status = result.get("status")
        if status not in _NON_PASSING_STATUSES:
            continue
        name = result.get("name") or "unknown"
        lines.append(f"{name}: {status} ({_status_detail(result)})")
        lines.extend(f"    {line}" for line in _check_output_tail(result))
    return lines


def emit(payload: dict[str, Any], *, json_output: bool, human: str | None) -> None:
    if json_output:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
        return
    if human is not None:
        print(human)
        return
    lines = [f"{payload['command']}: {payload['status']}"]
    for error in payload.get("errors") or ():
        if error:
            lines.append(f"error: {error}")
    if payload.get("reason"):
        lines.append(f"reason: {payload['reason']}")
    lines.extend(_check_failure_lines(payload))
    for next_command in payload.get("next_commands") or ():
        if next_command:
            lines.append(f"next: {next_command}")
    print("\n".join(lines))
