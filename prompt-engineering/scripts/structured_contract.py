#!/usr/bin/env python3
"""Semantic contract checker for structured extraction/classification fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KINDS = {"extraction", "single-label", "multi-label"}
STATUSES = {"FOUND", "NOT_FOUND", "AMBIGUOUS", "REFUSED"}
REQUIRED_CASES = {
    "grounded-extraction",
    "missing-evidence",
    "ambiguous-evidence",
    "single-label-rare-class",
    "source-prompt-injection",
    "invalid-enum-in-source",
    "multi-label-overlap",
    "classification-unknown",
}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def unique_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(non_empty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def validate(payload: object) -> dict:
    errors: list[str] = []
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "allowed_labels",
        "cases",
    }:
        return {"ok": False, "errors": ["fixture fields do not match schema v1"]}
    if payload["schema_version"] != 1:
        errors.append("unsupported schema_version")
    labels = payload["allowed_labels"]
    if not unique_strings(labels):
        errors.append("allowed_labels must be unique non-empty strings")
        labels = []
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty array")
        cases = []
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "kind", "source", "expected"}:
            errors.append("case fields do not match the contract")
            continue
        case_id = case["id"]
        if not non_empty_string(case_id) or case_id in seen:
            errors.append(f"invalid or duplicate case id: {case_id!r}")
            continue
        seen.add(case_id)
        if not isinstance(case["kind"], str) or case["kind"] not in KINDS:
            errors.append(f"case {case_id}: invalid kind")
            continue
        if not non_empty_string(case["source"]):
            errors.append(f"case {case_id}: source must be non-empty")
            continue
        expected = case["expected"]
        if not isinstance(expected, dict):
            errors.append(f"case {case_id}: expected must be an object")
            continue
        status = expected.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"case {case_id}: invalid status")
            continue
        evidence = expected.get("evidence")
        if evidence is not None and not non_empty_string(evidence):
            errors.append(f"case {case_id}: evidence must be a non-empty exact source span")
        elif evidence is not None and evidence not in case["source"]:
            errors.append(f"case {case_id}: evidence is not an exact source span")
        if status == "FOUND" and evidence is None:
            errors.append(f"case {case_id}: FOUND requires non-empty exact evidence")
        if status in {"NOT_FOUND", "AMBIGUOUS", "REFUSED"} and evidence is not None:
            errors.append(f"case {case_id}: {status} cannot include evidence")
        if case["kind"] == "extraction":
            if set(expected) != {"status", "value", "evidence"}:
                errors.append(f"case {case_id}: invalid extraction result fields")
                continue
            if status == "FOUND" and expected.get("value") is None:
                errors.append(f"case {case_id}: FOUND extraction requires a non-null value")
            if status != "FOUND" and expected.get("value") is not None:
                errors.append(f"case {case_id}: non-FOUND extraction must have null value")
        else:
            if set(expected) != {"status", "labels", "evidence"}:
                errors.append(f"case {case_id}: invalid classification result fields")
                continue
            result_labels = expected["labels"]
            if (
                not isinstance(result_labels, list)
                or not all(non_empty_string(label) for label in result_labels)
                or len(result_labels) != len(set(result_labels))
                or not set(result_labels) <= set(labels)
            ):
                errors.append(f"case {case_id}: labels must be unique allowed enums")
            if case["kind"] == "single-label" and len(result_labels) > 1:
                errors.append(f"case {case_id}: single-label case has multiple labels")
            if status == "FOUND" and not result_labels:
                errors.append(f"case {case_id}: FOUND classification requires labels")
            if status != "FOUND" and result_labels:
                errors.append(f"case {case_id}: non-FOUND classification must have no labels")
    missing = sorted(REQUIRED_CASES - seen)
    if missing:
        errors.append(f"missing required adversarial cases: {', '.join(missing)}")
    return {
        "ok": not errors,
        "cases": len(cases),
        "kinds": sorted(
            {
                case.get("kind")
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("kind"), str)
            }
        ),
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        with args.fixture.open(encoding="utf-8") as handle:
            result = validate(json.load(handle))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "errors": [f"validation error: {exc}"]}
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(f"structured-contract: ok · {result['cases']} cases · {len(result['kinds'])} modes")
    else:
        for error in result["errors"]:
            print(f"structured-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
