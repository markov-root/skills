#!/usr/bin/env python3
"""Semantic contract checker for reusable LLM-judge rubrics and bias fixtures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
MODES = {"pointwise", "pairwise", "ranking", "reference-based"}
AGGREGATE_VERDICTS = {"A", "B", "TIE", "UNKNOWN"}
REQUIRED_BIASES = {
    "position",
    "rubric_position",
    "verbosity",
    "style_authority",
    "self_preference",
    "prompt_injection",
    "abstention",
}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_rubric(rubric: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(rubric, dict):
        return ["rubric must be an object"]
    required = {
        "schema_version",
        "rubric_id",
        "version",
        "evaluation_mode",
        "task",
        "criteria",
        "abstention",
        "aggregate",
    }
    if set(rubric) != required:
        errors.append("rubric fields do not match the version-1 contract")
        return errors
    if rubric["schema_version"] != 1:
        errors.append("unsupported rubric schema_version")
    if not isinstance(rubric["rubric_id"], str) or not ID_RE.fullmatch(rubric["rubric_id"]):
        errors.append("invalid rubric_id")
    if not non_empty_string(rubric["version"]):
        errors.append("rubric version must be non-empty")
    if not isinstance(rubric["evaluation_mode"], str) or rubric["evaluation_mode"] not in MODES:
        errors.append("invalid evaluation_mode")
    if not non_empty_string(rubric["task"]):
        errors.append("rubric task must be non-empty")
    criteria = rubric["criteria"]
    if not isinstance(criteria, list) or not criteria:
        errors.append("criteria must be a non-empty array")
        return errors
    criterion_ids = set()
    weights = 0.0
    for criterion in criteria:
        expected = {"id", "name", "description", "weight", "critical", "anchors"}
        if (
            not isinstance(criterion, dict)
            or set(criterion) != expected
            or not non_empty_string(criterion["name"])
            or not non_empty_string(criterion["description"])
            or not isinstance(criterion["critical"], bool)
        ):
            errors.append("criterion fields do not match the contract")
            continue
        criterion_id = criterion["id"]
        if not isinstance(criterion_id, str) or not ID_RE.fullmatch(criterion_id):
            errors.append(f"invalid or duplicate criterion id: {criterion_id!r}")
            continue
        if criterion_id in criterion_ids:
            errors.append(f"invalid or duplicate criterion id: {criterion_id!r}")
        criterion_ids.add(criterion_id)
        if not isinstance(criterion["weight"], (int, float)) or criterion["weight"] <= 0:
            errors.append(f"criterion {criterion_id}: weight must be positive")
        else:
            weights += criterion["weight"]
        anchors = criterion["anchors"]
        if not isinstance(anchors, list) or len(anchors) < 2:
            errors.append(f"criterion {criterion_id}: at least two anchors required")
            continue
        scores = []
        for anchor in anchors:
            if (
                not isinstance(anchor, dict)
                or set(anchor) != {"score", "observable"}
                or not isinstance(anchor["score"], int)
                or not isinstance(anchor["observable"], str)
                or not anchor["observable"].strip()
            ):
                errors.append(f"criterion {criterion_id}: invalid anchor")
                continue
            scores.append(anchor["score"])
        if scores != sorted(set(scores)):
            errors.append(f"criterion {criterion_id}: anchor scores must be unique and ordered")
    if abs(weights - 1.0) > 1e-9:
        errors.append(f"criterion weights must sum to 1.0, got {weights:g}")
    abstention = rubric["abstention"]
    if (
        not isinstance(abstention, dict)
        or abstention.get("allowed") is not True
        or abstention.get("label") != "UNKNOWN"
        or not isinstance(abstention.get("when"), str)
        or not abstention["when"].strip()
    ):
        errors.append("rubric must define an explicit UNKNOWN abstention")
    aggregate = rubric["aggregate"]
    if (
        not isinstance(aggregate, dict)
        or aggregate.get("critical_failure_verdict") != "FAIL"
        or not isinstance(aggregate.get("verdicts"), list)
        or not all(isinstance(verdict, str) for verdict in aggregate.get("verdicts", []))
        or set(aggregate["verdicts"]) != AGGREGATE_VERDICTS
        or len(aggregate["verdicts"]) != len(set(aggregate["verdicts"]))
    ):
        errors.append("aggregate must define allowed verdicts and critical failure behavior")
    return errors


def validate_fixtures(fixtures: object, rubric_id: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(fixtures, list) or not fixtures:
        return ["fixtures must be a non-empty array"]
    seen = set()
    biases = set()
    for fixture in fixtures:
        expected_fields = {"id", "bias", "rubric_id", "task", "candidates", "variants"}
        if not isinstance(fixture, dict) or set(fixture) != expected_fields:
            errors.append("fixture fields do not match the contract")
            continue
        fixture_id = fixture["id"]
        if not non_empty_string(fixture_id) or fixture_id in seen:
            errors.append(f"invalid or duplicate fixture id: {fixture_id!r}")
            continue
        seen.add(fixture_id)
        if not isinstance(fixture["bias"], str) or fixture["bias"] not in REQUIRED_BIASES:
            errors.append(f"fixture {fixture_id}: unknown bias")
            continue
        biases.add(fixture["bias"])
        if fixture["rubric_id"] != rubric_id:
            errors.append(f"fixture {fixture_id}: rubric_id mismatch")
        if not non_empty_string(fixture["task"]):
            errors.append(f"fixture {fixture_id}: task must be non-empty")
        candidates = fixture["candidates"]
        if (
            not isinstance(candidates, dict)
            or len(candidates) != 2
            or not all(non_empty_string(key) for key in candidates)
            or not all(non_empty_string(value) for value in candidates.values())
        ):
            errors.append(f"fixture {fixture_id}: exactly two non-empty candidates required")
            continue
        variants = fixture["variants"]
        if not isinstance(variants, list) or len(variants) < 2:
            errors.append(f"fixture {fixture_id}: at least two presentation variants required")
            continue
        expected_results = set()
        orders = set()
        anchor_orders = set()
        for variant in variants:
            if not isinstance(variant, dict) or set(variant) != {
                "candidate_order",
                "anchor_order",
                "expected",
            }:
                errors.append(f"fixture {fixture_id}: invalid variant fields")
                continue
            if not isinstance(variant["candidate_order"], list) or not isinstance(
                variant["anchor_order"], list
            ):
                errors.append(f"fixture {fixture_id}: variant orders must be arrays")
                continue
            if not all(isinstance(item, str) for item in variant["candidate_order"]):
                errors.append(f"fixture {fixture_id}: candidate_order must contain strings")
                continue
            if not all(isinstance(item, int) for item in variant["anchor_order"]):
                errors.append(f"fixture {fixture_id}: anchor_order must contain integers")
                continue
            order = tuple(variant["candidate_order"])
            if set(order) != set(candidates) or len(order) != 2:
                errors.append(f"fixture {fixture_id}: candidate_order must be a permutation")
            orders.add(order)
            anchor_order = tuple(variant["anchor_order"])
            if set(anchor_order) != {0, 1, 2}:
                errors.append(f"fixture {fixture_id}: anchor_order must permute 0,1,2")
            anchor_orders.add(anchor_order)
            expected = variant["expected"]
            if not isinstance(expected, str):
                errors.append(f"fixture {fixture_id}: expected result must be a string")
                continue
            if expected not in candidates and expected not in {"UNKNOWN", "TIE"}:
                errors.append(f"fixture {fixture_id}: unknown expected result {expected!r}")
            expected_results.add(expected)
        if len(expected_results) != 1:
            errors.append(f"fixture {fixture_id}: expected result changes across presentations")
        if fixture["bias"] == "position" and len(orders) < 2:
            errors.append(f"fixture {fixture_id}: position fixture must swap candidate order")
        if fixture["bias"] == "rubric_position" and len(anchor_orders) < 2:
            errors.append(f"fixture {fixture_id}: rubric-position fixture must permute anchors")
    missing = sorted(REQUIRED_BIASES - biases)
    if missing:
        errors.append(f"missing required bias fixtures: {', '.join(missing)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rubric", type=Path)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    rubric: object = {}
    fixtures: object = []
    try:
        rubric = load(args.rubric)
        fixtures = load(args.fixtures)
        errors = validate_rubric(rubric)
        if not errors:
            errors.extend(validate_fixtures(fixtures, rubric["rubric_id"]))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors = [f"validation error: {exc}"]
    result = {
        "ok": not errors,
        "rubric_id": rubric.get("rubric_id") if isinstance(rubric, dict) else None,
        "criteria": len(rubric.get("criteria", [])) if isinstance(rubric, dict) else 0,
        "fixtures": len(fixtures) if isinstance(fixtures, list) else 0,
        "biases": sorted({item.get("bias") for item in fixtures if isinstance(item, dict)})
        if isinstance(fixtures, list)
        else [],
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    elif errors:
        for error in errors:
            print(f"judge-contract: {error}", file=sys.stderr)
    else:
        print(
            f"judge-contract: ok · {result['criteria']} criteria · "
            f"{result['fixtures']} fixtures · {len(result['biases'])} bias classes"
        )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
