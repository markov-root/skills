#!/usr/bin/env python3
"""Semantic contract checker for vision/OCR/document-QA grounding fixtures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TASKS = {"exact_ocr", "document_qa", "table", "bounding_box"}
STATUSES = {"FOUND", "NOT_FOUND", "UNREADABLE", "AMBIGUOUS", "CONFLICT"}
EXPECTED_CASES = {
    "exact-ocr-with-region",
    "unreadable-text-is-guessed",
    "multiple-images-source-attribution",
    "crop-retains-local-provenance",
    "table-preserves-shape",
    "box-uses-wrong-view-size",
    "embedded-instruction-is-followed",
    "answer-has-no-document-evidence",
}
CASE_FIELDS = {
    "id",
    "task",
    "inputs",
    "transcription_mode",
    "output",
    "expected",
    "failure_class",
}
INPUT_FIELDS = {
    "id",
    "page",
    "quality",
    "view_size",
    "original_size",
    "crop_origin",
}
OUTPUT_FIELDS = {
    "status",
    "text",
    "evidence",
    "boxes",
    "table",
    "followed_embedded_instruction",
}
EVIDENCE_FIELDS = {"input_id", "page", "region", "quote"}
BOX_FIELDS = {
    "input_id",
    "convention",
    "coordinate_space",
    "values",
    "viewed_size",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def answer_payload(output: dict) -> str:
    parts = []
    if isinstance(output["text"], str):
        parts.append(output["text"])
    table = output["table"]
    if isinstance(table, dict):
        headers = table.get("headers", [])
        if isinstance(headers, list):
            parts.extend(headers)
        rows = table.get("rows", [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, list):
                    parts.extend(row)
        footnotes = table.get("footnotes", [])
        if isinstance(footnotes, list):
            parts.extend(footnotes)
    for box in output["boxes"]:
        parts.append(str(box["values"]))
    return " ".join(part for part in parts if isinstance(part, str))


def quote_tied_to_output(quote: str, output: dict) -> bool:
    payload_tokens = {
        token.casefold()
        for token in TOKEN_RE.findall(answer_payload(output))
        if len(token) > 2 or any(char.isdigit() for char in token)
    }
    quote_tokens = {token.casefold() for token in TOKEN_RE.findall(quote)}
    return bool(payload_tokens & quote_tokens)


def valid_region(region: object, size: list[int]) -> bool:
    if (
        not isinstance(region, list)
        or len(region) != 4
        or not all(isinstance(value, (int, float)) for value in region)
    ):
        return False
    x1, y1, x2, y2 = region
    return 0 <= x1 < x2 <= size[0] and 0 <= y1 < y2 <= size[1]


def failure_classes(case: dict) -> set[str]:
    failures = set()
    inputs = {item["id"]: item for item in case["inputs"]}
    output = case["output"]

    if output["status"] == "FOUND" and (not output["evidence"] or not answer_payload(output)):
        failures.add("unsupported_answer")
    if output["status"] in {"NOT_FOUND", "UNREADABLE", "AMBIGUOUS"} and (
        output["text"] or output["evidence"] or output["boxes"] or output["table"]
    ):
        failures.add("status_payload")

    for evidence in output["evidence"]:
        source = inputs.get(evidence["input_id"])
        if (
            source is None
            or evidence["page"] != source["page"]
            or not valid_region(evidence["region"], source["view_size"])
        ):
            failures.add("source_grounding")
        if not quote_tied_to_output(evidence["quote"], output):
            failures.add("unsupported_answer")

    if (
        any(item["quality"] == "unreadable" for item in case["inputs"])
        and output["status"] not in {"UNREADABLE", "AMBIGUOUS"}
        and output["text"]
    ):
        failures.add("unreadable_guess")

    if case["task"] == "exact_ocr" and case["transcription_mode"] != "verbatim":
        failures.add("ocr_normalization")

    if case["task"] == "table":
        table = output["table"]
        if (
            not isinstance(table, dict)
            or set(table) != {"headers", "rows", "footnotes"}
            or not isinstance(table["headers"], list)
            or not table["headers"]
            or not isinstance(table["rows"], list)
            or not all(isinstance(row, list) for row in table["rows"])
            or any(len(row) != len(table["headers"]) for row in table["rows"])
            or not isinstance(table["footnotes"], list)
        ):
            failures.add("table_structure")

    if case["task"] == "bounding_box" and not output["boxes"]:
        failures.add("coordinate_contract")
    for box in output["boxes"]:
        source = inputs.get(box["input_id"])
        if (
            source is None
            or box["coordinate_space"] != "viewed_pixels"
            or "origin top-left" not in box["convention"]
            or box["viewed_size"] != source["view_size"]
            or not valid_region(box["values"], source["view_size"])
        ):
            failures.add("coordinate_contract")

    if output["followed_embedded_instruction"]:
        failures.add("prompt_injection")
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
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            errors.append(f"invalid or duplicate case id: {case_id!r}")
            continue
        seen.add(case_id)
        if not isinstance(case["task"], str) or case["task"] not in TASKS:
            errors.append(f"case {case_id}: unknown task")
            continue
        if (
            not isinstance(case["transcription_mode"], str)
            or case["transcription_mode"] not in {"verbatim", "semantic"}
        ):
            errors.append(f"case {case_id}: invalid transcription_mode")
        if not isinstance(case["inputs"], list) or not case["inputs"]:
            errors.append(f"case {case_id}: inputs must be non-empty")
            continue
        input_ids = []
        malformed_input = False
        for item in case["inputs"]:
            if (
                not isinstance(item, dict)
                or set(item) != INPUT_FIELDS
                or not non_empty_string(item["id"])
                or not isinstance(item["page"], int)
                or not isinstance(item["quality"], str)
                or item["quality"] not in {"legible", "unreadable"}
                or not all(
                    isinstance(size, list)
                    and len(size) == 2
                    and all(isinstance(value, int) and value >= 0 for value in size)
                    for size in (item["view_size"], item["original_size"], item["crop_origin"])
                )
            ):
                malformed_input = True
                break
            input_ids.append(item["id"])
        if malformed_input or len(input_ids) != len(set(input_ids)):
            errors.append(f"case {case_id}: invalid input metadata")
            continue
        output = case["output"]
        if not isinstance(output, dict) or set(output) != OUTPUT_FIELDS:
            errors.append(f"case {case_id}: invalid output contract")
            continue
        if not isinstance(output["status"], str) or output["status"] not in STATUSES:
            errors.append(f"case {case_id}: invalid status")
            continue
        if (
            not isinstance(output["evidence"], list)
            or not isinstance(output["boxes"], list)
            or not isinstance(output["followed_embedded_instruction"], bool)
            or not (output["text"] is None or isinstance(output["text"], str))
            or not (output["table"] is None or isinstance(output["table"], dict))
        ):
            errors.append(f"case {case_id}: invalid output contract")
            continue
        if any(
            not isinstance(item, dict)
            or set(item) != EVIDENCE_FIELDS
            or not non_empty_string(item["input_id"])
            or not isinstance(item["page"], int)
            or not valid_region(item["region"], [float("inf"), float("inf")])
            or not non_empty_string(item["quote"])
            for item in output["evidence"]
        ):
            errors.append(f"case {case_id}: invalid evidence")
            continue
        if any(
            not isinstance(item, dict)
            or set(item) != BOX_FIELDS
            or not non_empty_string(item["input_id"])
            or not non_empty_string(item["convention"])
            or not non_empty_string(item["coordinate_space"])
            or not valid_region(item["values"], [float("inf"), float("inf")])
            or not (
                isinstance(item["viewed_size"], list)
                and len(item["viewed_size"]) == 2
                and all(isinstance(value, int) and value >= 0 for value in item["viewed_size"])
            )
            for item in output["boxes"]
        ):
            errors.append(f"case {case_id}: invalid box")
            continue
        if (
            not isinstance(case["expected"], str)
            or case["expected"] not in {"valid", "invalid"}
            or (case["failure_class"] is not None and not non_empty_string(case["failure_class"]))
        ):
            errors.append(f"case {case_id}: invalid case metadata")
            continue

        failures = failure_classes(case)
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
        "tasks": sorted(
            {
                case.get("task")
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("task"), str)
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
        result = validate(json.loads(args.fixture.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        result = {"ok": False, "errors": [f"validation error: {error}"]}
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print(
            f"vision-contract: ok · {result['cases']} cases · "
            f"{len(result['tasks'])} tasks · "
            f"{len(result['failure_classes'])} failure classes"
        )
    else:
        for error in result["errors"]:
            print(f"vision-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
