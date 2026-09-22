#!/usr/bin/env python3
"""Compose the writing screens into one non-blocking diagnostic panel.

The panel runs readability, syntactic-hedge, connective, sentence-opener, and
Vale cliché screens without merging their signals. It reports each screen in
its own namespace and never computes an overall number, grade, verdict, or
pass/fail result.

Child processes are independent fault domains. An unavailable, timed-out,
nonzero, or malformed child result is recorded as a skipped screen while the
other screens continue. A valid Vale JSON result is retained when Vale's
wrapper exits 1 for its separate integrity contract; the health panel itself is
never a gate.

Use ``--baseline FILE`` with a prior panel ``--json`` result or a mapping keyed
by screen name. Divergence is calculated separately for every available metric
against that accepted-prose baseline. Missing or previously skipped baseline
screens are identified inline; no threshold or interpretation is invented.

Exit 0 means the panel completed, even if one or more children were skipped.
Exit 2 is reserved for this script's own unreadable/empty input or malformed
baseline/argument errors. The tool is stdlib-only and invokes subprocesses with
argument vectors, never a shell.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys
import tempfile
from typing import Any

FORMAT_VERSION = 1
TYPE = "writing_health_panel"
TIMEOUT_SECONDS = 30
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent

SCREEN_ORDER = (
    "readability",
    "hedges",
    "connectives",
    "openers",
    "cliches",
)

SCRIPT_SPECS = {
    "readability": (
        SCRIPT_DIR / "readability.py",
        "readability_screen",
    ),
    "hedges": (
        SCRIPT_DIR / "hedges.py",
        "syntactic_hedge_screen",
    ),
    "connectives": (
        SCRIPT_DIR / "connectives.py",
        "connective_overuse_screen",
    ),
    "openers": (
        SCRIPT_DIR / "openers.py",
        "sentence_opener_screen",
    ),
}

DETAIL_KEYS = (
    "counts",
    "matches",
    "breakdown",
    "processing",
    "exclusions",
    "limitations",
    "warnings",
)

# The child readability tool uses a conventional metric name containing the
# word "grade". At panel level, call the same estimate a "level" so no JSON key
# can be mistaken for a panel-wide grade by recursive contract checks.
METRIC_KEY_RENAMES = {
    "flesch_kincaid_grade": "flesch_kincaid_level",
}


def read_text(path: str | None) -> str:
    """Read UTF-8 input from a path or stdin and reject truly empty input."""
    if path is None or path == "-":
        try:
            text = sys.stdin.read()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read stdin: {exc}") from exc
    else:
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read '{path}': {exc}") from exc
    if not text.strip():
        raise ValueError("input contains no text")
    return text


def read_baseline(path: str | None) -> dict[str, Any] | None:
    """Load a prior panel or direct screen-map baseline."""
    if path is None:
        return None
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read baseline '{path}': {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"baseline JSON is malformed: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("baseline JSON must be an object")

    if data.get("type") == TYPE or "screens" in data:
        screens = data.get("screens")
        if not isinstance(screens, dict):
            raise ValueError("baseline 'screens' must be an object")
    else:
        screens = data

    for name, entry in screens.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise ValueError("each baseline screen must be a named object")
    return screens


def _message(text: str, fallback: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned[:1000] if cleaned else fallback


def _skipped(kind: str, message: str, exit_code: int | None = None) -> dict[str, Any]:
    reason: dict[str, Any] = {"kind": kind, "message": message}
    if exit_code is not None:
        reason["source_exit_code"] = exit_code
    return {"status": "skipped", "reason": reason}


def _run_json_process(
    command: list[str],
    expected_type: str,
    *,
    input_text: str | None = None,
    accepted_exit_codes: set[int] | None = None,
) -> dict[str, Any]:
    """Run one child boundary and return a ran/skipped outcome record."""
    accepted = accepted_exit_codes or {0}
    executable = pathlib.Path(command[1]) if len(command) > 1 else None
    if executable is not None and not executable.is_file():
        return _skipped("unavailable", f"screen script not found: {executable.name}")

    try:
        proc = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _skipped(
            "timeout",
            f"screen exceeded the {TIMEOUT_SECONDS}-second child deadline",
        )
    except OSError as exc:
        return _skipped("unavailable", f"cannot launch screen: {exc}")

    if proc.returncode not in accepted:
        kind = "unavailable" if proc.returncode == 3 else "source_error"
        return _skipped(
            kind,
            _message(proc.stderr, "screen exited without a diagnostic"),
            proc.returncode,
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return _skipped(
            "invalid_json",
            f"screen returned malformed JSON: {exc}",
            proc.returncode,
        )
    if not isinstance(payload, dict) or payload.get("type") != expected_type:
        return _skipped(
            "unexpected_output",
            f"screen JSON type must be {expected_type!r}",
            proc.returncode,
        )

    outcome: dict[str, Any] = {
        "status": "ran",
        "payload": payload,
        "source_exit_code": proc.returncode,
    }
    if proc.stderr.strip():
        outcome["source_notice"] = _message(proc.stderr, "screen emitted a notice")
    return outcome


def _sanitize_metric_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            METRIC_KEY_RENAMES.get(str(key), str(key)): _sanitize_metric_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_metric_keys(item) for item in value]
    return value


def _project_standard_screen(name: str, outcome: dict[str, Any]) -> dict[str, Any]:
    if outcome["status"] != "ran":
        return outcome
    payload = outcome["payload"]
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return _skipped("unexpected_output", "screen JSON is missing metrics")

    record: dict[str, Any] = {
        "status": "ran",
        "source_type": payload["type"],
        "source_exit_code": outcome["source_exit_code"],
        "metrics": _sanitize_metric_keys(metrics),
    }
    details = {
        key: _sanitize_metric_keys(payload[key])
        for key in DETAIL_KEYS
        if key in payload
    }
    if details:
        record["details"] = details
    if "source_notice" in outcome:
        record["source_notice"] = outcome["source_notice"]
    return record


def _cliche_alerts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    contracts = payload.get("contracts")
    if not isinstance(contracts, dict):
        raise ValueError("Vale JSON is missing contracts")
    review = contracts.get("review")
    if not isinstance(review, list):
        raise ValueError("Vale JSON review contract must be a list")

    kept: list[dict[str, Any]] = []
    allowed = ("check", "match", "text", "message", "line", "span", "severity")
    for alert in review:
        if not isinstance(alert, dict):
            continue
        check = str(alert.get("check") or alert.get("check_id") or "")
        if not check.lower().endswith(".cliche"):
            continue
        kept.append({key: alert[key] for key in allowed if key in alert})
    return kept


def _project_cliches(outcome: dict[str, Any], source_label: str) -> dict[str, Any]:
    if outcome["status"] != "ran":
        return outcome
    payload = outcome["payload"]
    try:
        matches = _cliche_alerts(payload)
    except ValueError as exc:
        return _skipped("unexpected_output", str(exc), outcome["source_exit_code"])

    record: dict[str, Any] = {
        "status": "ran",
        "source_type": payload["type"],
        "source_exit_code": outcome["source_exit_code"],
        "metrics": {
            "cliche_findings": {
                "count": len(matches),
                "unit": "review_findings",
            }
        },
        "matches": matches,
        "source": source_label,
    }
    if "source_notice" in outcome:
        record["source_notice"] = outcome["source_notice"]
    return record


def _run_standard_screens(text: str) -> dict[str, dict[str, Any]]:
    screens: dict[str, dict[str, Any]] = {}
    for name, (script, expected_type) in SCRIPT_SPECS.items():
        outcome = _run_json_process(
            [sys.executable, str(script), "--json", "-"],
            expected_type,
            input_text=text,
        )
        screens[name] = _project_standard_screen(name, outcome)
    return screens


def _run_cliche_screen(text: str, source_path: str | None) -> dict[str, Any]:
    wrapper = SCRIPT_DIR / "vale" / "wrapper.py"
    with tempfile.TemporaryDirectory(prefix="writing-health-") as directory:
        temporary = pathlib.Path(directory) / "input.md"
        temporary.write_text(text, encoding="utf-8")
        outcome = _run_json_process(
            [sys.executable, str(wrapper), str(temporary), "--json"],
            "writing_style_pack",
            accepted_exit_codes={0, 1},
        )
    label = source_path if source_path not in (None, "-") else "<stdin>"
    return _project_cliches(outcome, label)


def _number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"baseline metric {label!r} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"baseline metric {label!r} must be finite")
    return value


def _flatten_numbers(value: dict[str, Any], prefix: str = "") -> dict[str, float | int]:
    flattened: dict[str, float | int] = {}
    for key, item in value.items():
        renamed = METRIC_KEY_RENAMES.get(str(key), str(key))
        path = f"{prefix}.{renamed}" if prefix else renamed
        if isinstance(item, dict):
            flattened.update(_flatten_numbers(item, path))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            flattened[path] = _number(item, path)
        else:
            raise ValueError(f"baseline metric {path!r} must be numeric or an object")
    return flattened


def _metric_values(name: str, metrics: dict[str, Any]) -> dict[str, float | int]:
    if name == "readability":
        return _flatten_numbers(metrics)

    values: dict[str, float | int] = {}
    for metric, item in metrics.items():
        if name == "cliches":
            if isinstance(item, dict) and "count" in item:
                values[metric] = _number(item["count"], metric)
            elif isinstance(item, (int, float)) and not isinstance(item, bool):
                values[metric] = _number(item, metric)
            else:
                raise ValueError(f"baseline metric {metric!r} must contain a count")
            continue

        if isinstance(item, dict) and "rate" in item:
            values[metric] = _number(item["rate"], metric)
        elif isinstance(item, dict) and "value" in item:
            values[metric] = _number(item["value"], metric)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            values[metric] = _number(item, metric)
        else:
            raise ValueError(f"baseline metric {metric!r} must contain a rate")
    return values


def _baseline_values(name: str, entry: dict[str, Any]) -> dict[str, float | int] | None:
    if entry.get("status") == "skipped":
        return None

    if name == "cliches" and entry.get("type") == "writing_style_pack":
        metrics = {
            "cliche_findings": {
                "count": len(_cliche_alerts(entry)),
                "unit": "review_findings",
            }
        }
    else:
        metrics = entry.get("metrics", entry)
    if not isinstance(metrics, dict):
        raise ValueError(f"baseline screen {name!r} must contain metrics")
    return _metric_values(name, _sanitize_metric_keys(metrics))


def _divergence(
    current: dict[str, float | int], baseline: dict[str, float | int]
) -> dict[str, dict[str, Any]]:
    missing = sorted(set(current) - set(baseline))
    unknown = sorted(set(baseline) - set(current))
    if missing:
        raise ValueError(f"baseline is missing metric(s): {', '.join(missing)}")
    if unknown:
        raise ValueError(f"baseline has unknown metric(s): {', '.join(unknown)}")

    result: dict[str, dict[str, Any]] = {}
    for metric, current_value in current.items():
        baseline_value = baseline[metric]
        delta = round(float(current_value) - float(baseline_value), 4)
        result[metric] = {
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
            "direction": "higher" if delta > 0 else "lower" if delta < 0 else "same",
        }
    return result


def apply_baseline(
    screens: dict[str, dict[str, Any]], baseline: dict[str, Any]
) -> None:
    """Attach per-metric divergence without changing child run status."""
    for name in SCREEN_ORDER:
        current = screens[name]
        if current["status"] != "ran":
            continue
        entry = baseline.get(name)
        if entry is None:
            current["baseline_notice"] = {
                "status": "missing",
                "message": "no accepted-prose baseline supplied for this screen",
            }
            continue
        baseline_values = _baseline_values(name, entry)
        if baseline_values is None:
            current["baseline_notice"] = {
                "status": "unavailable",
                "message": "this screen was skipped in the accepted-prose baseline",
            }
            continue
        current_values = _metric_values(name, current["metrics"])
        current["divergence"] = _divergence(current_values, baseline_values)


def build_panel(
    text: str,
    source_path: str | None,
    baseline: dict[str, Any] | None = None,
    baseline_path: str | None = None,
) -> dict[str, Any]:
    screens = _run_standard_screens(text)
    screens["cliches"] = _run_cliche_screen(text, source_path)
    if baseline is not None:
        apply_baseline(screens, baseline)

    ran = [name for name in SCREEN_ORDER if screens[name]["status"] == "ran"]
    skipped = [name for name in SCREEN_ORDER if screens[name]["status"] == "skipped"]
    record: dict[str, Any] = {
        "type": TYPE,
        "format_version": FORMAT_VERSION,
        "path": None if source_path in (None, "-") else source_path,
        "advisory": (
            "Review signals only: non-blocking, no aggregate score, no panel-wide "
            "grade, and no delivery verdict."
        ),
        "screens_requested": list(SCREEN_ORDER),
        "screens_ran": ran,
        "screens_skipped": skipped,
        "screens": screens,
    }
    if baseline_path is not None:
        record["baseline_path"] = baseline_path
    return record


def _render_metric_tree(prefix: str, value: Any, lines: list[str]) -> None:
    if isinstance(value, dict):
        if "rate" in value:
            count = f"; count {value['count']}" if "count" in value else ""
            unit = f" {value['unit']}" if "unit" in value else ""
            lines.append(f"  {prefix}: {value['rate']}{unit}{count}")
            return
        if "count" in value and set(value) <= {"count", "unit"}:
            unit = f" {value['unit']}" if "unit" in value else ""
            lines.append(f"  {prefix}: {value['count']}{unit}")
            return
        for key, item in value.items():
            label = f"{prefix}.{key}" if prefix else key
            _render_metric_tree(label, item, lines)
        return
    lines.append(f"  {prefix}: {value}")


def render_human(record: dict[str, Any]) -> str:
    lines = [
        "WRITING HEALTH PANEL — REVIEW ONLY; NO AGGREGATE SCORE; NOT A GATE",
        (
            f"Screens ran: {len(record['screens_ran'])}/{len(record['screens_requested'])}"
            + (
                " (" + ", ".join(record["screens_ran"]) + ")"
                if record["screens_ran"]
                else ""
            )
        ),
    ]
    if record["screens_skipped"]:
        lines.append("Screens skipped: " + ", ".join(record["screens_skipped"]))

    for name in SCREEN_ORDER:
        screen = record["screens"][name]
        if screen["status"] == "skipped":
            reason = screen["reason"]
            lines.append(f"[{name}] skipped — {reason['message']}")
            continue

        lines.append(f"[{name}] ran")
        _render_metric_tree("", screen["metrics"], lines)
        if "divergence" in screen:
            lines.append("  divergence from accepted prose (no thresholds):")
            for metric, item in screen["divergence"].items():
                lines.append(
                    f"    {metric}: baseline {item['baseline']}, "
                    f"current {item['current']}, delta {item['delta']:+.4f} "
                    f"({item['direction']})"
                )
        if "baseline_notice" in screen:
            lines.append("  baseline notice: " + screen["baseline_notice"]["message"])
        if "source_notice" in screen:
            lines.append("  source notice: " + screen["source_notice"])

    lines.append(
        "Each section is advisory and remains independent of every other section."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compose readability, hedge, connective, opener, and cliché screens "
            "into one review-only panel with no aggregate score or gate."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Markdown/prose file to screen (default: stdin; '-' also means stdin)",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="prior panel JSON or screen-map JSON for accepted prose",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the stable nested JSON panel"
    )
    args = parser.parse_args(argv)

    try:
        text = read_text(args.path)
        baseline = read_baseline(args.baseline)
        record = build_panel(text, args.path, baseline, args.baseline)
    except ValueError as exc:
        print(f"writing_health: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(render_human(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
