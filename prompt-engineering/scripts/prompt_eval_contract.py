#!/usr/bin/env python3
"""Semantic contract checker for prompt evaluation and regression plan fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPECTED_CASES = {
    "paired-heldout-prompt-ab",
    "overlapping-splits",
    "prompt-ab-has-runtime-confounds",
    "uncalibrated-llm-grader",
    "optimizer-selects-on-holdout",
    "single-stochastic-trial",
    "quality-only-plan",
    "no-release-or-provenance-gate",
}
CASE_FIELDS = {"id", "plan", "expected", "failure_class"}
PLAN_FIELDS = {
    "objective",
    "primary_metric",
    "operational_metrics",
    "development_ids",
    "validation_ids",
    "holdout_ids",
    "strata",
    "perturbations",
    "variants",
    "trials_per_case",
    "paired",
    "change_axis_count",
    "selection_split",
    "graders",
    "release_gate",
    "record_provenance",
}
METRIC_FIELDS = {"name", "direction", "threshold"}
VARIANT_FIELDS = {"id", "prompt_hash", "model", "settings_hash"}
GRADER_FIELDS = {"type", "criterion", "calibrated"}
GATE_FIELDS = {"primary_required", "operational_required", "holdout_required"}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def non_empty_string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(non_empty_string(item) for item in value)


def string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def failure_classes(plan: dict) -> set[str]:
    failures = set()
    splits = [
        set(plan["development_ids"]),
        set(plan["validation_ids"]),
        set(plan["holdout_ids"]),
    ]
    if (
        splits[0] & splits[1]
        or splits[0] & splits[2]
        or splits[1] & splits[2]
        or any(not split for split in splits)
    ):
        failures.add("split_leakage")

    if plan["selection_split"] != "validation":
        failures.add("holdout_misuse")

    models = {variant["model"] for variant in plan["variants"]}
    settings = {variant["settings_hash"] for variant in plan["variants"]}
    prompt_hashes = {variant["prompt_hash"] for variant in plan["variants"]}
    if (
        len(plan["variants"]) < 2
        or not plan["paired"]
        or plan["change_axis_count"] != 1
        or len(prompt_hashes) == 1
        or len(models) != 1
        or len(settings) != 1
    ):
        failures.add("comparison_confound")

    if plan["trials_per_case"] < 2:
        failures.add("insufficient_trials")

    if any(
        grader["type"] in {"llm", "human"} and not grader["calibrated"]
        for grader in plan["graders"]
    ):
        failures.add("uncalibrated_grader")

    if not plan["operational_metrics"]:
        failures.add("missing_operational_metrics")

    gate = plan["release_gate"]
    if (
        not gate["primary_required"]
        or not gate["operational_required"]
        or not gate["holdout_required"]
        or not plan["record_provenance"]
    ):
        failures.add("release_provenance")
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
        plan = case["plan"]
        if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
            errors.append(f"case {case_id}: plan fields do not match contract")
            continue
        if not non_empty_string(plan["objective"]):
            errors.append(f"case {case_id}: objective must be non-empty")
        metric = plan["primary_metric"]
        if (
            not isinstance(metric, dict)
            or set(metric) != METRIC_FIELDS
            or not non_empty_string(metric["name"])
            or not isinstance(metric["direction"], str)
            or metric["direction"] not in {"maximize", "minimize"}
            or not isinstance(metric["threshold"], (int, float))
        ):
            errors.append(f"case {case_id}: invalid primary metric")
            continue
        malformed_plan = False
        for field in ("development_ids", "validation_ids", "holdout_ids", "operational_metrics"):
            if not string_list(plan[field]):
                errors.append(f"case {case_id}: {field} must be an array of strings")
                malformed_plan = True
        for field in ("strata", "perturbations"):
            if not non_empty_string_list(plan[field]):
                errors.append(f"case {case_id}: {field} must be non-empty strings")
                malformed_plan = True
        if malformed_plan:
            continue
        if not isinstance(plan["variants"], list):
            errors.append(f"case {case_id}: variants must be an array")
            continue
        if any(
            not isinstance(variant, dict)
            or set(variant) != VARIANT_FIELDS
            or not all(non_empty_string(value) for value in variant.values())
            for variant in plan["variants"]
        ):
            errors.append(f"case {case_id}: invalid variants")
            continue
        if not isinstance(plan["graders"], list) or not plan["graders"]:
            errors.append(f"case {case_id}: graders must be non-empty")
            continue
        if any(
            not isinstance(grader, dict)
            or set(grader) != GRADER_FIELDS
            or not isinstance(grader["type"], str)
            or grader["type"] not in {"deterministic", "llm", "human"}
            or not non_empty_string(grader["criterion"])
            or not isinstance(grader["calibrated"], bool)
            for grader in plan["graders"]
        ):
            errors.append(f"case {case_id}: invalid graders")
            continue
        if (
            not isinstance(plan["release_gate"], dict)
            or set(plan["release_gate"]) != GATE_FIELDS
            or not all(isinstance(plan["release_gate"][field], bool) for field in GATE_FIELDS)
        ):
            errors.append(f"case {case_id}: invalid release gate")
            continue
        if (
            len(plan["variants"]) < 2
            or not isinstance(plan["trials_per_case"], int)
            or not isinstance(plan["paired"], bool)
            or not isinstance(plan["change_axis_count"], int)
            or not isinstance(plan["selection_split"], str)
            or not isinstance(plan["record_provenance"], bool)
            or not isinstance(case["expected"], str)
            or case["expected"] not in {"valid", "invalid"}
            or (case["failure_class"] is not None and not non_empty_string(case["failure_class"]))
        ):
            errors.append(f"case {case_id}: invalid evaluation plan metadata")
            continue

        failures = failure_classes(plan)
        observed_failures.update(failures)
        actual = "invalid" if failures else "valid"
        if case["expected"] != actual:
            errors.append(f"case {case_id}: expected {case['expected']}, calculated {actual}")
        named_failure = case["failure_class"]
        if actual == "valid" and named_failure is not None:
            errors.append(f"case {case_id}: valid case cannot name a failure")
        if actual == "invalid" and named_failure not in failures:
            errors.append(
                f"case {case_id}: failure_class {named_failure!r} not in {sorted(failures)}"
            )

    missing = sorted(EXPECTED_CASES - seen)
    if missing:
        errors.append(f"missing required cases: {', '.join(missing)}")
    return {
        "ok": not errors,
        "cases": len(cases),
        "failure_classes": sorted(observed_failures),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate(json.loads(args.fixture.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        result = {"ok": False, "errors": [f"validation error: {error}"]}
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(
            f"prompt-eval-contract: ok · {result['cases']} cases · "
            f"{len(result['failure_classes'])} failure classes"
        )
    else:
        for error in result["errors"]:
            print(f"prompt-eval-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
