#!/usr/bin/env python3
"""Semantic contract checker for RAG query/evidence contract fixtures."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STAGES = {"rewrite", "decompose", "expansion", "answer"}
STATUSES = {"READY", "SUFFICIENT", "INSUFFICIENT_EVIDENCE", "CONFLICT", "IRRELEVANT"}
REQUIRED_CASES = {
    "standalone-literal-preservation",
    "multi-hop-decomposition",
    "hyde-not-evidence",
    "grounded-answer",
    "insufficient-evidence",
    "conflicting-sources",
    "retrieved-prompt-injection",
    "entity-attribution-mismatch",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
}


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) for item in value)
    )


def grounded_claim(claim_text: str, cited_text: str) -> bool:
    claim_tokens = [token.casefold() for token in TOKEN_RE.findall(claim_text)]
    cited_tokens = {token.casefold() for token in TOKEN_RE.findall(cited_text)}
    required_numbers = {token for token in claim_tokens if any(char.isdigit() for char in token)}
    if not required_numbers <= cited_tokens:
        return False
    content_tokens = {
        token for token in claim_tokens if len(token) > 3 and token not in STOPWORDS
    }
    return bool(content_tokens & cited_tokens)


def validate(payload: object) -> dict:
    errors: list[str] = []
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "cases"}:
        return {"ok": False, "errors": ["fixture fields do not match schema v1"]}
    if payload["schema_version"] != 1:
        errors.append("unsupported schema_version")
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        return {"ok": False, "errors": [*errors, "cases must be a non-empty array"]}
    seen = set()
    stages = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "stage", "input", "expected"}:
            errors.append("case fields do not match the contract")
            continue
        case_id = case["id"]
        if not non_empty_string(case_id) or case_id in seen:
            errors.append(f"invalid or duplicate case id: {case_id!r}")
            continue
        seen.add(case_id)
        stage = case["stage"]
        if not isinstance(stage, str) or stage not in STAGES:
            errors.append(f"case {case_id}: invalid stage")
            continue
        stages.add(stage)
        inputs = case["input"]
        expected = case["expected"]
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            errors.append(f"case {case_id}: input and expected must be objects")
            continue
        status = expected.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"case {case_id}: invalid status")
            continue
        if stage != "answer":
            if status != "READY" or expected.get("retrieval_only") is not True:
                errors.append(
                    f"case {case_id}: retrieval transformation must be READY/retrieval_only"
                )
            citable_source_ids = expected.get("citable_source_ids", [])
            if not string_list(citable_source_ids):
                errors.append(f"case {case_id}: citable_source_ids must be an array of strings")
                continue
            if citable_source_ids:
                errors.append(f"case {case_id}: generated retrieval text cannot be citable")
            must_match = expected.get("must_match")
            if must_match is not None:
                if not string_list(must_match, allow_empty=False):
                    errors.append(f"case {case_id}: must_match must be non-empty strings")
                    continue
                input_text = " ".join(
                    value for value in inputs.values() if isinstance(value, str)
                )
                for phrase in must_match:
                    if phrase not in input_text:
                        errors.append(f"case {case_id}: must_match phrase absent from input")
            continue
        sources = inputs.get("sources")
        if not isinstance(sources, list):
            errors.append(f"case {case_id}: answer case requires sources")
            continue
        source_texts = {}
        malformed_sources = False
        for source in sources:
            if (
                not isinstance(source, dict)
                or set(source) != {"id", "text"}
                or not non_empty_string(source["id"])
                or not non_empty_string(source["text"])
                or source["id"] in source_texts
            ):
                malformed_sources = True
                break
            source_texts[source["id"]] = source["text"]
        if malformed_sources:
            errors.append(f"case {case_id}: sources must have unique non-empty IDs and text")
            continue
        source_ids = set(source_texts)
        claims = expected.get("claims")
        missing = expected.get("missing")
        if not isinstance(claims, list) or not string_list(missing):
            errors.append(f"case {case_id}: answer result requires claims and missing arrays")
            continue
        for claim in claims:
            if (
                not isinstance(claim, dict)
                or set(claim) != {"text", "citations"}
                or not non_empty_string(claim["text"])
                or not string_list(claim["citations"], allow_empty=False)
                or not set(claim["citations"]) <= source_ids
            ):
                errors.append(f"case {case_id}: claim must cite existing source IDs")
                continue
            cited_text = " ".join(source_texts[source_id] for source_id in claim["citations"])
            if not grounded_claim(claim["text"], cited_text):
                errors.append(f"case {case_id}: claim is not grounded in cited sources")
        if status in {"INSUFFICIENT_EVIDENCE", "IRRELEVANT"} and claims:
            errors.append(f"case {case_id}: {status} cannot make claims")
        if status == "SUFFICIENT" and (not claims or missing):
            errors.append(f"case {case_id}: SUFFICIENT requires claims and no missing facts")
        if status in {"INSUFFICIENT_EVIDENCE", "CONFLICT", "IRRELEVANT"} and not missing:
            errors.append(f"case {case_id}: non-sufficient result must identify what is unresolved")
    absent = sorted(REQUIRED_CASES - seen)
    if absent:
        errors.append(f"missing required cases: {', '.join(absent)}")
    return {"ok": not errors, "cases": len(cases), "stages": sorted(stages), "errors": errors}


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
        print(f"rag-contract: ok · {result['cases']} cases · {len(result['stages'])} stages")
    else:
        for error in result["errors"]:
            print(f"rag-contract: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
