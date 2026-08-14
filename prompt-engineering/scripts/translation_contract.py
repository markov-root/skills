#!/usr/bin/env python3
"""Semantic contract checker for translation/localization prompt-contract fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

MODES = {"translation", "localization", "transcreation"}
STATUSES = {"TRANSLATED", "NEEDS_CONTEXT", "CONSTRAINT_CONFLICT", "REVIEW_REQUIRED"}
EXPECTED_CASES = {
    "required-glossary-term",
    "required-glossary-term-missed",
    "icu-and-markup-preserved",
    "placeholder-dropped",
    "ambiguity-requests-context",
    "ambiguity-is-silently-guessed",
    "legal-copy-requires-review",
    "legal-copy-published-without-review",
    "source-instruction-is-followed",
    "wrong-target-locale",
    "source-segment-omitted",
}
CASE_FIELDS = {
    "id",
    "mode",
    "source_locale",
    "target_locale",
    "requires_context",
    "context",
    "glossary",
    "immutable_tokens",
    "source_segments",
    "high_stakes",
    "output",
    "expected",
    "failure_class",
}
GLOSSARY_FIELDS = {"source", "target", "policy"}
SEGMENT_FIELDS = {"id", "text"}
OUTPUT_FIELDS = {
    "status",
    "target_locale",
    "segments",
    "followed_source_instruction",
    "review_required",
}
OUTPUT_SEGMENT_FIELDS = {"source_id", "text"}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def failure_classes(case: dict) -> set[str]:
    failures = set()
    output = case["output"]
    translated = " ".join(segment["text"] for segment in output["segments"])
    source = " ".join(segment["text"] for segment in case["source_segments"])

    if output["target_locale"] != case["target_locale"]:
        failures.add("locale")

    if output["status"] != "NEEDS_CONTEXT":
        expected_ids = Counter(segment["id"] for segment in case["source_segments"])
        actual_ids = Counter(segment["source_id"] for segment in output["segments"])
        if actual_ids != expected_ids:
            failures.add("segment_coverage")

    for token in case["immutable_tokens"]:
        if source.count(token) != translated.count(token):
            failures.add("immutable_token")

    source_folded = source.casefold()
    translated_folded = translated.casefold()
    for term in case["glossary"]:
        source_term = term["source"].casefold()
        target_term = term["target"].casefold()
        if source_term not in source_folded:
            continue
        if term["policy"] in {"required", "preferred"} and target_term not in translated_folded:
            failures.add("terminology")
        if term["policy"] == "do_not_translate" and (
            source_term not in translated_folded or target_term in translated_folded
        ):
            failures.add("terminology")

    if (
        case["requires_context"]
        and not case["context"].strip()
        and output["status"] != "NEEDS_CONTEXT"
    ):
        failures.add("ambiguity_guess")

    if case["high_stakes"] and not (
        output["status"] == "REVIEW_REQUIRED" and output["review_required"]
    ):
        failures.add("missing_review")

    if output["followed_source_instruction"]:
        failures.add("prompt_injection")
    if output["status"] in {"NEEDS_CONTEXT", "CONSTRAINT_CONFLICT"} and output["segments"]:
        failures.add("status_payload")
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
        if not isinstance(case["mode"], str) or case["mode"] not in MODES:
            errors.append(f"case {case_id}: unknown mode")
        if not all(
            isinstance(case[field], str) and case[field].strip()
            for field in ("source_locale", "target_locale")
        ):
            errors.append(f"case {case_id}: locale must be non-empty")
        if not isinstance(case["glossary"], list):
            errors.append(f"case {case_id}: invalid glossary")
            continue
        if any(
            not isinstance(term, dict)
            or set(term) != GLOSSARY_FIELDS
            or not non_empty_string(term["source"])
            or not non_empty_string(term["target"])
            or not isinstance(term["policy"], str)
            or term["policy"] not in {"required", "preferred", "do_not_translate"}
            for term in case["glossary"]
        ):
            errors.append(f"case {case_id}: invalid glossary")
            continue
        if (
            not isinstance(case["source_segments"], list)
            or not case["source_segments"]
            or any(
                not isinstance(segment, dict)
                or set(segment) != SEGMENT_FIELDS
                or not non_empty_string(segment["id"])
                or not non_empty_string(segment["text"])
                for segment in case["source_segments"]
            )
        ):
            errors.append(f"case {case_id}: invalid source segments")
            continue
        source_ids = [segment["id"] for segment in case["source_segments"]]
        if len(source_ids) != len(set(source_ids)):
            errors.append(f"case {case_id}: source segment IDs must be unique")
            continue
        output = case["output"]
        if (
            not isinstance(output, dict)
            or set(output) != OUTPUT_FIELDS
            or not isinstance(output["status"], str)
            or output["status"] not in STATUSES
            or not non_empty_string(output["target_locale"])
            or not isinstance(output["review_required"], bool)
            or not isinstance(output["followed_source_instruction"], bool)
            or not isinstance(output["segments"], list)
            or any(
                not isinstance(segment, dict)
                or set(segment) != OUTPUT_SEGMENT_FIELDS
                or not non_empty_string(segment["source_id"])
                or segment["source_id"] not in source_ids
                or not isinstance(segment["text"], str)
                for segment in output["segments"]
            )
        ):
            errors.append(f"case {case_id}: invalid output")
            continue
        if (
            not isinstance(case["requires_context"], bool)
            or not isinstance(case["context"], str)
            or not string_list(case["immutable_tokens"])
            or not isinstance(case["high_stakes"], bool)
            or not isinstance(case["expected"], str)
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
        "modes": sorted(
            {
                case.get("mode")
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("mode"), str)
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
            f"translation-contract: ok · {result['cases']} cases · "
            f"{len(result['modes'])} modes · "
            f"{len(result['failure_classes'])} failure classes"
        )
    else:
        for error in result["errors"]:
            print(f"translation-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
