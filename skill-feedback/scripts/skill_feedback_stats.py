"""Explainable aggregates for the Skill Feedback event ledger."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

GROUP_DIMENSIONS = (
    "skill",
    "feature",
    "version",
    "task-class",
    "requested-router",
    "requested-provider",
    "requested-model",
    "requested-effort",
    "actual-router",
    "actual-provider",
    "actual-model",
    "actual-effort",
    "day",
)
OUTCOMES = ("success", "partial", "failure", "abandoned", "unknown")
OBSERVATION_KINDS = ("praise", "friction", "bug", "wish", "idea")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _in_window(event: dict, after: datetime | None, before: datetime | None) -> bool:
    occurred = _timestamp(event["occurred_at"])
    return not ((after and occurred < after) or (before and occurred >= before))


def _one_actual(finishes: list[dict], field: str) -> str | None:
    values = {
        (event.get("payload") or {}).get("backend", {}).get(field)
        for event in finishes
    }
    values.discard(None)
    return next(iter(values)) if len(values) == 1 else None


def _actual_backend_conflicts(finishes: list[dict]) -> int:
    return sum(
        len(
            {
                event["payload"]["backend"].get(field)
                for event in finishes
                if event["payload"]["backend"].get(field) is not None
            }
        )
        > 1
        for field in ("router", "provider", "model", "effort")
    )


def _start_signature(event: dict) -> tuple[Any, ...]:
    backend = event["payload"]["backend"]
    return (
        event["skill"]["name"],
        event["skill"].get("version"),
        event["payload"].get("feature"),
        (event.get("task") or {}).get("class"),
        backend.get("router"),
        backend.get("provider"),
        backend.get("model"),
        backend.get("effort"),
    )


def _dimensions(start: dict, finishes: list[dict]) -> dict[str, str | None]:
    backend = (start.get("payload") or {}).get("backend") or {}
    return {
        "skill": (start.get("skill") or {}).get("name"),
        "feature": (start.get("payload") or {}).get("feature"),
        "version": (start.get("skill") or {}).get("version"),
        "task-class": (start.get("task") or {}).get("class"),
        "requested-router": backend.get("router"),
        "requested-provider": backend.get("provider"),
        "requested-model": backend.get("model"),
        "requested-effort": backend.get("effort"),
        "actual-router": _one_actual(finishes, "router"),
        "actual-provider": _one_actual(finishes, "provider"),
        "actual-model": _one_actual(finishes, "model"),
        "actual-effort": _one_actual(finishes, "effort"),
        "day": _timestamp(start["occurred_at"]).date().isoformat(),
    }


def _observation_dimensions(
    event: dict,
    invocation_dimensions: dict[str, dict[str, str | None]],
) -> dict[str, str | None]:
    invocation_id = event.get("invocation_id")
    if invocation_id in invocation_dimensions:
        return invocation_dimensions[invocation_id]
    return {
        "skill": (event.get("skill") or {}).get("name"),
        "feature": (event.get("payload") or {}).get("feature"),
        "version": (event.get("skill") or {}).get("version"),
        "task-class": (event.get("task") or {}).get("class"),
        "requested-router": None,
        "requested-provider": None,
        "requested-model": None,
        "requested-effort": None,
        "actual-router": None,
        "actual-provider": None,
        "actual-model": None,
        "actual-effort": None,
        "day": _timestamp(event["occurred_at"]).date().isoformat(),
    }


def _key(
    dimensions: dict[str, str | None], group_by: tuple[str, ...]
) -> tuple[str | None, ...]:
    return tuple(dimensions[name] for name in group_by)


def _new_group(
    key: tuple[str | None, ...], group_by: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "dimensions": dict(zip(group_by, key, strict=True)),
        "population": {
            "uses": 0,
            "finished": 0,
            "incomplete": 0,
            "conflicting_finishes": 0,
            "unknown_outcomes": 0,
            "duplicate_start_events": 0,
            "conflicting_start_events": 0,
            "duplicate_finish_events": 0,
            "mismatched_finish_events": 0,
            "conflicting_actual_backend_fields": 0,
            "orphan_finish_events": 0,
        },
        "outcomes": {outcome: 0 for outcome in OUTCOMES},
        "observations": {
            **{kind: 0 for kind in OBSERVATION_KINDS},
            "positive": 0,
            "negative": 0,
            "mixed": 0,
            "unlinked_to_invocation": 0,
        },
        "preservation": {
            "praise": 0,
            "preserved": 0,
            "preserved_with_test": 0,
            "preserved_without_test": 0,
        },
        "rates_per_100_uses": {},
    }


def _latest_dispositions(events: list[dict]) -> dict[str, dict]:
    dispositions: dict[str, dict] = {}
    for event in sorted(events, key=lambda item: _timestamp(item["occurred_at"])):
        if event["event_type"] == "disposition.changed":
            dispositions[event["payload"]["feedback_id"]] = event
    return dispositions


def build_stats(
    events: list[dict],
    *,
    after: datetime | None,
    before: datetime | None,
    skills: set[str],
    group_by: tuple[str, ...],
) -> dict:
    """Aggregate an invocation-start cohort and time-windowed observations."""
    starts: dict[str, list[dict]] = defaultdict(list)
    finishes: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        invocation_id = event.get("invocation_id")
        if event["event_type"] == "invocation.started" and invocation_id:
            starts[invocation_id].append(event)
        elif event["event_type"] == "invocation.finished" and invocation_id:
            finishes[invocation_id].append(event)

    groups: dict[tuple[str | None, ...], dict[str, Any]] = {}

    def group_for(dimensions: dict[str, str | None]) -> dict[str, Any]:
        key = _key(dimensions, group_by)
        if key not in groups:
            groups[key] = _new_group(key, group_by)
        return groups[key]

    selected_invocations: dict[str, dict[str, str | None]] = {}
    selected_start_ids = set()
    for invocation_id, invocation_starts in starts.items():
        ordered_starts = sorted(
            invocation_starts, key=lambda item: _timestamp(item["occurred_at"])
        )
        start = ordered_starts[0]
        if skills and start["skill"]["name"] not in skills:
            continue
        if not _in_window(start, after, before):
            continue
        selected_start_ids.add(invocation_id)
        all_invocation_finishes = sorted(
            finishes.get(invocation_id, []),
            key=lambda item: _timestamp(item["occurred_at"]),
        )
        invocation_finishes = [
            event
            for event in all_invocation_finishes
            if event["skill"]["name"] == start["skill"]["name"]
        ]
        dimensions = _dimensions(start, invocation_finishes)
        selected_invocations[invocation_id] = dimensions
        group = group_for(dimensions)
        population = group["population"]
        population["uses"] += 1
        population["duplicate_start_events"] += len(ordered_starts) - 1
        population["conflicting_start_events"] += sum(
            _start_signature(event) != _start_signature(start)
            for event in ordered_starts[1:]
        )
        population["duplicate_finish_events"] += max(
            0, len(invocation_finishes) - 1
        )
        population["mismatched_finish_events"] += (
            len(all_invocation_finishes) - len(invocation_finishes)
        )
        population["conflicting_actual_backend_fields"] += (
            _actual_backend_conflicts(invocation_finishes)
        )
        if not invocation_finishes:
            population["incomplete"] += 1
            population["unknown_outcomes"] += 1
            continue
        outcomes = {
            event["payload"]["outcome"] for event in invocation_finishes
        }
        if len(outcomes) != 1:
            population["conflicting_finishes"] += 1
            population["unknown_outcomes"] += 1
            continue
        outcome = next(iter(outcomes))
        population["finished"] += 1
        group["outcomes"][outcome] += 1
        if outcome == "unknown":
            population["unknown_outcomes"] += 1

    for invocation_id, invocation_finishes in finishes.items():
        if invocation_id in starts or invocation_id in selected_start_ids:
            continue
        for finish in invocation_finishes:
            if skills and finish["skill"]["name"] not in skills:
                continue
            if not _in_window(finish, after, before):
                continue
            dimensions = {
                "skill": finish["skill"]["name"],
                "feature": None,
                "version": finish["skill"].get("version"),
                "task-class": (finish.get("task") or {}).get("class"),
                "requested-router": None,
                "requested-provider": None,
                "requested-model": None,
                "requested-effort": None,
                "actual-router": (finish["payload"].get("backend") or {}).get(
                    "router"
                ),
                "actual-provider": (finish["payload"].get("backend") or {}).get(
                    "provider"
                ),
                "actual-model": (finish["payload"].get("backend") or {}).get(
                    "model"
                ),
                "actual-effort": (finish["payload"].get("backend") or {}).get(
                    "effort"
                ),
                "day": _timestamp(finish["occurred_at"]).date().isoformat(),
            }
            group_for(dimensions)["population"]["orphan_finish_events"] += 1

    dispositions = _latest_dispositions(events)
    observations = [
        event
        for event in events
        if event["event_type"] == "observation.recorded"
        and (not skills or event["skill"]["name"] in skills)
        and _in_window(event, after, before)
    ]
    for event in observations:
        dimensions = _observation_dimensions(event, selected_invocations)
        group = group_for(dimensions)
        payload = event["payload"]
        group["observations"][payload["kind"]] += 1
        group["observations"][payload["signal"]] += 1
        if not event.get("invocation_id"):
            group["observations"]["unlinked_to_invocation"] += 1
        if payload["kind"] == "praise":
            preservation = group["preservation"]
            preservation["praise"] += 1
            disposition = dispositions.get(payload["feedback_id"])
            if disposition and disposition["payload"]["status"] == "preserve":
                preservation["preserved"] += 1
                if disposition["payload"]["links"].get("test"):
                    preservation["preserved_with_test"] += 1
                else:
                    preservation["preserved_without_test"] += 1

    negative_after_praise = []
    praise_events = [
        event
        for event in observations
        if event["payload"]["kind"] == "praise" and event["payload"]["feature"]
    ]
    negative_events = [
        event
        for event in observations
        if event["payload"]["signal"] == "negative" and event["payload"]["feature"]
    ]
    for praise in praise_events:
        later = [
            event
            for event in negative_events
            if event["skill"]["name"] == praise["skill"]["name"]
            and event["payload"]["feature"] == praise["payload"]["feature"]
            and _timestamp(event["occurred_at"])
            > _timestamp(praise["occurred_at"])
        ]
        if later:
            negative_after_praise.append(
                {
                    "skill": praise["skill"]["name"],
                    "feature": praise["payload"]["feature"],
                    "praise_feedback_id": praise["payload"]["feedback_id"],
                    "negative_feedback_ids": [
                        event["payload"]["feedback_id"] for event in later
                    ],
                }
            )

    for group in groups.values():
        uses = group["population"]["uses"]
        for name in (*OUTCOMES, *OBSERVATION_KINDS):
            numerator = (
                group["outcomes"].get(name)
                if name in OUTCOMES
                else group["observations"].get(name)
            )
            group["rates_per_100_uses"][name] = (
                round(100 * numerator / uses, 3) if uses else None
            )

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: tuple(
            "" if value is None else str(value)
            for value in group["dimensions"].values()
        ),
    )
    return {
        "version": 1,
        "population": {
            "invocation_cohort": "earliest invocation.started in the selected window",
            "observation_cohort": "observation.recorded in the selected window",
            "finish_join": "all matching finishes, including outside the selected window",
            "disposition_scope": "latest disposition in the full ledger",
            "after_inclusive": after.isoformat().replace("+00:00", "Z")
            if after
            else None,
            "before_exclusive": before.isoformat().replace("+00:00", "Z")
            if before
            else None,
            "skills": sorted(skills) if skills else None,
        },
        "group_by": list(group_by),
        "group_count": len(ordered_groups),
        "groups": ordered_groups,
        "negative_after_praise": negative_after_praise,
        "limitations": [
            "rates are descriptive associations, not causal skill rankings",
            "unlinked observations cannot inherit backend dimensions",
            "missing finishes remain unknown rather than failures",
            "agent and automation judgments are not user preference labels",
        ],
    }
