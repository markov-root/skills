#!/usr/bin/env python3
"""Semantic contract checker for tool/delegation/orchestration fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOPOLOGIES = {"single", "manager", "handoff", "code"}
EXPECTED_CASES = {
    "single-agent-baseline",
    "manager-bounded-workers",
    "handoff-transfers-ownership",
    "parallel-dependency-violation",
    "overlapping-tool-routing",
    "parallel-shared-writers",
    "external-effect-without-approval",
    "missing-termination-contract",
}
CASE_FIELDS = {
    "id",
    "topology",
    "workers",
    "dependencies",
    "parallel_groups",
    "merge_owner",
    "final_owner",
    "verification",
    "termination",
    "tools",
    "expected",
    "failure_class",
}
WORKER_FIELDS = {
    "id",
    "objective",
    "deliverable",
    "read_scope",
    "write_scope",
    "external_effects",
    "approval_required",
}
TOOL_FIELDS = {"name", "use_when", "do_not_use_when", "effects", "approval"}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) for item in value)
    )


def failure_classes(case: dict) -> set[str]:
    failures = set()
    workers = {worker["id"]: worker for worker in case["workers"]}
    dependencies = {tuple(edge) for edge in case["dependencies"]}
    for group in case["parallel_groups"]:
        members = set(group)
        if any(source in members and target in members for source, target in dependencies):
            failures.add("dependency")
        paths = {}
        for worker_id in group:
            for path in workers[worker_id]["write_scope"]:
                paths.setdefault(path, []).append(worker_id)
        if any(len(owners) > 1 for owners in paths.values()):
            failures.add("state_ownership")
    triggers = [tool["use_when"].strip().casefold() for tool in case["tools"]]
    if len(triggers) != len(set(triggers)):
        failures.add("tool_overlap")
    if any(
        worker["external_effects"] and not worker["approval_required"]
        for worker in case["workers"]
    ):
        failures.add("permission")
    if not case["verification"].strip() or not case["termination"].strip():
        failures.add("verification_termination")
    if case["topology"] == "handoff" and case["final_owner"] not in workers:
        failures.add("ownership_transfer")
    if case["topology"] == "manager" and (
        case["merge_owner"] != "manager" or case["final_owner"] != "manager"
    ):
        failures.add("manager_ownership")
    if case["topology"] in {"single", "code"} and (
        case["merge_owner"] not in workers or case["final_owner"] not in workers
    ):
        failures.add("ownership_transfer")
    return failures


def validate(payload: object) -> dict:
    errors = []
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "cases"}:
        return {"ok": False, "errors": ["fixture fields do not match schema v1"]}
    if payload["schema_version"] != 1:
        errors.append("unsupported schema_version")
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        return {"ok": False, "errors": [*errors, "cases must be non-empty"]}
    seen = set()
    observed_failures = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != CASE_FIELDS:
            errors.append("case fields do not match the contract")
            continue
        case_id = case["id"]
        if not non_empty_string(case_id) or case_id in seen:
            errors.append(f"invalid or duplicate case id: {case_id!r}")
            continue
        seen.add(case_id)
        if not isinstance(case["topology"], str) or case["topology"] not in TOPOLOGIES:
            errors.append(f"case {case_id}: unknown topology")
            continue
        workers = case["workers"]
        if not isinstance(workers, list) or not workers:
            errors.append(f"case {case_id}: workers must be non-empty")
            continue
        worker_ids = []
        malformed = False
        for worker in workers:
            if (
                not isinstance(worker, dict)
                or set(worker) != WORKER_FIELDS
                or not non_empty_string(worker["id"])
                or not non_empty_string(worker["objective"])
                or not non_empty_string(worker["deliverable"])
                or not string_list(worker["read_scope"])
                or not string_list(worker["write_scope"])
                or not isinstance(worker["external_effects"], bool)
                or not isinstance(worker["approval_required"], bool)
            ):
                malformed = True
                break
            worker_ids.append(worker["id"])
        if malformed or len(worker_ids) != len(set(worker_ids)):
            errors.append(f"case {case_id}: invalid worker contract")
            continue
        worker_id_set = set(worker_ids)
        dependencies = case["dependencies"]
        if not isinstance(dependencies, list):
            errors.append(f"case {case_id}: dependencies must be an array")
            continue
        for edge in dependencies:
            if (
                not isinstance(edge, list)
                or len(edge) != 2
                or not all(isinstance(worker_id, str) for worker_id in edge)
                or not set(edge) <= worker_id_set
            ):
                errors.append(f"case {case_id}: invalid dependency")
        parallel_groups = case["parallel_groups"]
        if not isinstance(parallel_groups, list):
            errors.append(f"case {case_id}: parallel_groups must be an array")
            continue
        for group in parallel_groups:
            if (
                not isinstance(group, list)
                or len(group) < 2
                or not all(isinstance(worker_id, str) for worker_id in group)
                or not set(group) <= worker_id_set
            ):
                errors.append(f"case {case_id}: invalid parallel group")
        tools = case["tools"]
        if not isinstance(tools, list) or any(
            not isinstance(tool, dict)
            or set(tool) != TOOL_FIELDS
            or not all(non_empty_string(tool[field]) for field in TOOL_FIELDS)
            for tool in tools
        ):
            errors.append(f"case {case_id}: invalid tool description")
            continue
        if not isinstance(case["merge_owner"], (str, type(None))) or not isinstance(
            case["final_owner"], str
        ):
            errors.append(f"case {case_id}: owner fields are invalid")
            continue
        if not isinstance(case["verification"], str) or not isinstance(
            case["termination"], str
        ):
            errors.append(f"case {case_id}: verification and termination must be strings")
            continue
        if not isinstance(case["expected"], str) or case["expected"] not in {"valid", "invalid"}:
            errors.append(f"case {case_id}: expected must be valid or invalid")
            continue
        if case["failure_class"] is not None and not non_empty_string(case["failure_class"]):
            errors.append(f"case {case_id}: invalid failure_class")
            continue
        failures = failure_classes(case)
        observed_failures.update(failures)
        actual = "invalid" if failures else "valid"
        if case["expected"] != actual:
            errors.append(f"case {case_id}: expected {case['expected']}, calculated {actual}")
        expected_failure = case["failure_class"]
        if actual == "valid" and expected_failure is not None:
            errors.append(f"case {case_id}: valid case cannot name a failure")
        if actual == "invalid" and expected_failure not in failures:
            errors.append(
                f"case {case_id}: failure_class {expected_failure!r} not in {sorted(failures)}"
            )
    missing = sorted(EXPECTED_CASES - seen)
    if missing:
        errors.append(f"missing required cases: {', '.join(missing)}")
    return {
        "ok": not errors,
        "cases": len(cases),
        "topologies": sorted(
            {
                case.get("topology")
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("topology"), str)
            }
        ),
        "failure_classes": sorted(observed_failures),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(json.loads(args.fixture.read_text()))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        result = {"ok": False, "errors": [f"validation error: {error}"]}
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(
            f"agentic-contract: ok · {result['cases']} cases · "
            f"{len(result['topologies'])} topologies · "
            f"{len(result['failure_classes'])} failure classes"
        )
    else:
        for error in result["errors"]:
            print(f"agentic-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
