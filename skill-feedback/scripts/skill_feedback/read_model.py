"""Body-free projections, isolated body handles, and legacy statistics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .inventory import (
    _declared_name,
    _path_is_writable,
    _repo_root,
    _resolve_feedback_root,
    feedback_dir,
    known_skills,
)
from .model import (
    BodyHandle,
    BodyInspectionRequest,
    BodyInspectionUnavailable,
    DELIVERY_STATES,
    ELIGIBILITY_USE_CASES,
    EVENT_SCHEMA_VERSION,
    EVIDENCE_ELIGIBILITY_POLICY_VERSION,
    EVIDENCE_RESULTS,
    FeedbackError,
    source_eligible_for,
    MetadataView,
    QUALITATIVE_PRIVACY_SCANNER_VERSION,
    ScopedBodyInput,
    _body_sha256,
    _body_v1,
    _canonical_json,
    _default_signal,
    _default_status,
    _empty_managed_note_file,
    _entry_sha256,
    _validate_event,
    _validate_skill_name,
    _without_matches,
    DeliveryBlocked,
    PromotionAuthorization,
)
from .privacy import (
    _privacy_findings_sha256,
    _stored_privacy_review_matches,
    _text_privacy_findings,
)
from .storage import (
    FEEDBACK_HOME,
    EventLedger,
    LedgerIndex,
    _event_lock_path,
    _event_path,
    _file_lock,
    _managed_note_records,
    _note_outbox_dir,
    _notes_lock_path,
    _read_delivery_sidecar,
    _read_object_sidecar,
    _write_text_atomic,
)

GROUP_DIMENSIONS = (
    "skill",
    "source",
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


def _tombstones_in_window(
    events: list[dict],
    *,
    after: datetime | None,
    before: datetime | None,
    skills: set[str],
    before_inclusive: bool = False,
) -> list[tuple[dict, datetime | None]]:
    selected = []
    for event in events:
        if event.get("event_type") != "observation.tombstoned":
            continue
        if skills and (event.get("skill") or {}).get("name") not in skills:
            continue
        payload = event.get("payload") or {}
        prior_at = payload.get("prior_occurred_at")
        if prior_at:
            try:
                prior_timestamp = _timestamp(prior_at)
            except (TypeError, ValueError):
                prior_timestamp = None
        else:
            prior_timestamp = None
        if prior_timestamp is not None and (
            (after and prior_timestamp < after)
            or (
                before
                and (
                    prior_timestamp > before
                    if before_inclusive
                    else prior_timestamp >= before
                )
            )
        ):
            continue
        if prior_timestamp is None:
            occurred = _timestamp(event["occurred_at"])
            if (after and occurred < after) or (
                before
                and (occurred > before if before_inclusive else occurred >= before)
            ):
                continue
        selected.append((event, prior_timestamp))
    return selected


def _build_censoring(
    events: list[dict],
    *,
    after: datetime | None,
    before: datetime | None,
    skills: set[str],
    before_inclusive: bool = False,
) -> dict:
    """Aggregate content-free tombstones into affected class/day buckets.

    The prior timestamp describes the deleted record's analytical bucket; the
    tombstone timestamp describes when deletion became observable. Keeping these
    separate makes post-deletion censoring distinguishable from original
    missingness without reconstructing deleted content (ADR 0022 D7).
    """
    selected = _tombstones_in_window(
        events,
        after=after,
        before=before,
        skills=skills,
        before_inclusive=before_inclusive,
    )

    by_class: dict[str, int] = {}
    by_bucket: dict[tuple[str, str], int] = {}
    corpus_versions = []
    for event, prior_timestamp in selected:
        payload = event.get("payload") or {}
        event_class = payload.get("prior_event_type") or "observation.recorded"
        day = prior_timestamp.date().isoformat() if prior_timestamp else "unknown"
        by_class[event_class] = by_class.get(event_class, 0) + 1
        key = (day, event_class)
        by_bucket[key] = by_bucket.get(key, 0) + 1
        version = payload.get("corpus_version")
        if isinstance(version, int) and not isinstance(version, bool):
            corpus_versions.append(version)

    censored = bool(selected)
    return {
        "status": "censored" if censored else "uncensored",
        "cause": "post_deletion" if censored else None,
        "post_deletion": censored,
        "original_missingness": "separate",
        "tombstone_count": len(selected),
        "corpus_version": max(corpus_versions) if corpus_versions else None,
        "affected_event_classes": dict(sorted(by_class.items())),
        "affected_time_buckets": [
            {
                "day": day,
                "event_class": event_class,
                "deleted_events": count,
            }
            for (day, event_class), count in sorted(by_bucket.items())
        ],
    }


def _one_actual(finishes: list[dict], field: str) -> str | None:
    values = {
        (event.get("payload") or {}).get("backend", {}).get(field) for event in finishes
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
        "source": start.get("source"),
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
        dimensions = dict(invocation_dimensions[invocation_id])
        dimensions["source"] = event.get("source")
        return dimensions
    return {
        "skill": (event.get("skill") or {}).get("name"),
        "source": event.get("source"),
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
            "capability_executions": 0,
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
            "linked_to_invocation": 0,
            "unlinked_to_invocation": 0,
        },
        "capture_mechanisms": {
            "automatic": 0,
            "manual-start": 0,
            "note-only": 0,
            "unknown": 0,
        },
        "preservation": {
            "praise": 0,
            "preserved": 0,
            "declared_with_test": 0,
            "verified_with_test": 0,
        },
        "rates_per_100_uses": {},
        # C4 (ADR 0021 D4): downstream-eligible counts, kept visibly distinct
        # from the raw observation/preservation counters above.
        "eligible_aggregates": {use_case: 0 for use_case in ELIGIBILITY_USE_CASES},
        # C4 (ADR 0021 D5): record-time evidence-verification result tally.
        "evidence_verification": {
            **{result: 0 for result in EVIDENCE_RESULTS},
            "observations_with_evidence": 0,
            "total_references": 0,
        },
        # Private accumulators; removed before serialization.
        "_decision_episode_ids": set(),  # C3 ADR 0020 D3
        "_source_counts": {},  # C4 ADR 0021 D3: source -> raw observation count
        "_source_eligible": {},  # C4 ADR 0021 D3: source -> eligible-for-any count
        "_privacy_strata": {},  # C4 ADR 0021 D6: task_class -> coverage accumulator
    }


def _latest_dispositions(events: list[dict]) -> dict[str, dict]:
    dispositions: dict[str, dict] = {}
    for event in sorted(events, key=lambda item: _timestamp(item["occurred_at"])):
        if event["event_type"] == "disposition.changed":
            dispositions[event["payload"]["feedback_id"]] = event
    return dispositions


def reconcile_disposition_status(events: list[dict]) -> list[str]:
    """Flag any feedback whose editable sidecar status is a closed/verified state
    (`resolved`/`preserve`) not backed by a matching latest ledger disposition
    (ADR 0019 D7).

    The append-only ledger is authoritative; `.status.json` is a rebuildable cache.
    The C2 triage commit writes the sidecar under the notes lock and appends the
    ledger event after releasing it (to avoid nesting the event lock), so a torn
    two-phase commit -- or an out-of-band sidecar edit -- can leave the sidecar
    asserting a closure the ledger does not back. Diagnostics are content-free
    (feedback id, skill, and enum statuses only)."""
    latest = _latest_dispositions(events)
    diagnostics: list[str] = []
    for skill in known_skills():
        try:
            entries = _parse_entries_unlocked(skill)
        except (FeedbackError, OSError):
            continue
        for entry in entries:
            status = entry.get("status")
            if status not in ("resolved", "preserve"):
                continue
            disposition = latest.get(entry["id"])
            ledger_status = (
                disposition["payload"].get("status") if disposition else None
            )
            if ledger_status != status:
                diagnostics.append(
                    f"feedback {entry['id']} ({skill}) sidecar status {status!r} is "
                    f"not backed by the ledger (ledger latest: {ledger_status!r})"
                )
    return diagnostics


COMPARISON_READINESS_POLICY_VERSION = 1
# C5 (ADR 0022 D2): the versioned pre-action stratum contract.
STRATUM_CONTRACT_VERSION = 1
# C5 (ADR 0022 D3): the versioned prospective-evaluation readiness policy.
READINESS_POLICY_VERSION = 2
_MIN_READY_DECISIONS = 3
_MIN_OVERLAP_RATE = 0.5
_MIN_OUTCOME_COVERAGE_RATE = 0.5
# C5 (ADR 0022 D4): the versioned immutable evaluation manifest.
EVALUATION_MANIFEST_VERSION = 1
_MIN_OBSERVATION_LINK_RATE = 0.8
_MIN_ACTIVATION_COVERAGE = 0.8
# C4 (ADR 0021 D6): a privacy stratum whose label coverage falls below this
# abstains rather than borrowing a better-observed stratum's result.
_MIN_LABEL_COVERAGE = 0.8
# C5 (ADR 0022 D5): the versioned estimator-gating policy. Every estimator is
# gated on the decision.logged population; on any unmet gate the output is a
# neutral prediction-audit/abstention that makes NO causal/OPE/regret claim.
DECISION_ESTIMATOR_POLICY_VERSION = 1
# The one predeclared target policy: uniform over the eligible candidate actions.
DEFAULT_TARGET_POLICY = "uniform_eligible"
TARGET_POLICIES = (DEFAULT_TARGET_POLICY,)
# Named-oracle reward map; "unknown" (and an absent outcome) is a MISSING reward,
# never a silent zero.
_OUTCOME_REWARDS = {
    "success": 1.0,
    "partial": 0.5,
    "failure": 0.0,
    "abandoned": 0.0,
}
# Estimator-specific assumptions, surfaced only alongside an actual estimate (never
# asserted as satisfied on abstention).
_ESTIMATOR_ASSUMPTIONS = {
    "ips": (
        "the logged chosen_action_probability is the true behaviour-policy "
        "probability of the chosen action",
        "positivity/support: the target policy places mass only where the logging "
        "policy had positive probability",
        "the pre-action covariates are complete and stable (no post-selection leak)",
        "the named oracle maps each outcome to its reward correctly",
    ),
}
ESTIMATORS = tuple(_ESTIMATOR_ASSUMPTIONS)
_MIN_ESTIMATOR_OUTCOME_COVERAGE = 0.5


def build_estimator_evaluation(
    included: list[dict],
    *,
    estimator: str,
    target_policy: str,
    censored: bool = False,
) -> dict:
    """C5 (ADR 0022 D5): gate a predeclared estimator on the decision.logged
    population and either run ONLY that estimator or emit a neutral prediction
    audit / abstention.

    Gates (all must pass to estimate): at least one logged decision; every included
    decision has a numeric logged assignment probability (propensity_known); every
    included decision is stochastic so the stochastic target has support
    (assignment_overlap); enough decisions carry a measured reward under a named
    oracle (outcome_coverage); and no attached outcome pre-dates its decision
    (no_temporal_leak). On ANY unmet gate the result is a ``prediction_audit`` with
    support diagnostics and a (typically uninformative) worst-case bound, and it
    contains NO causal / off-policy / regret claim or vocabulary. Only when every
    gate passes is an IPS estimate of the predeclared uniform-eligible target
    reported, with an effective sample size, a 95% normal-approximation interval,
    the count of missing outcomes, and the estimator's assumptions."""
    if estimator not in ESTIMATORS:
        raise FeedbackError(
            f"unknown estimator {estimator!r}; predeclared estimators: "
            f"{', '.join(ESTIMATORS)}"
        )
    if target_policy not in TARGET_POLICIES:
        raise FeedbackError(
            f"unknown target_policy {target_policy!r}; predeclared: "
            f"{', '.join(TARGET_POLICIES)}"
        )

    decisions = [
        event for event in included if event["event_type"] == "decision.logged"
    ]
    latest_outcome: dict[str, dict] = {}
    for event in included:
        if event["event_type"] != "decision.outcome":
            continue
        decision_id = event["payload"]["decision_id"]
        prior = latest_outcome.get(decision_id)
        if prior is None or _timestamp(event["occurred_at"]) >= _timestamp(
            prior["occurred_at"]
        ):
            latest_outcome[decision_id] = event

    total = len(decisions)
    known_propensity = 0
    overlapping = 0
    temporal_anomalies = 0
    reward_covered = 0
    missing_outcomes = 0
    samples: list[tuple[float, float]] = []
    for decision in decisions:
        payload = decision["payload"]
        probability = payload.get("chosen_action_probability")
        prob_known = isinstance(probability, (int, float)) and not isinstance(
            probability, bool
        )
        if prob_known:
            known_propensity += 1
        prob_overlap = prob_known and 0 < probability < 1
        if prob_overlap:
            overlapping += 1
        reward: float | None = None
        outcome_event = latest_outcome.get(payload.get("decision_id"))
        if outcome_event is None:
            missing_outcomes += 1
        elif _timestamp(outcome_event["occurred_at"]) <= _timestamp(
            decision["occurred_at"]
        ):
            temporal_anomalies += 1
        else:
            reward = _OUTCOME_REWARDS.get(outcome_event["payload"].get("outcome"))
            if reward is None:  # e.g. "unknown" -- a missing, not zero, reward
                missing_outcomes += 1
            else:
                reward_covered += 1
        if prob_overlap and reward is not None:
            mask = payload.get("eligibility_mask") or {}
            eligible = sum(1 for value in mask.values() if value) or len(
                payload.get("candidate_actions") or []
            )
            target_prob = (1.0 / eligible) if eligible else 0.0
            samples.append((target_prob / probability, reward))

    propensity_coverage = round(known_propensity / total, 3) if total else 0.0
    overlap_rate = round(overlapping / total, 3) if total else 0.0
    outcome_coverage = round(reward_covered / total, 3) if total else 0.0
    weight_sum = sum(weight for weight, _ in samples)
    weight_sq_sum = sum(weight * weight for weight, _ in samples)
    effective_sample_size = (
        round(weight_sum * weight_sum / weight_sq_sum, 3) if weight_sq_sum else 0.0
    )

    gates = [
        {
            "id": "decision_logging",
            "passed": total >= 1,
            "measured": total,
            "required": 1,
            "detail": "at least one logged decision is required",
        },
        {
            "id": "propensity_known",
            "passed": total >= 1 and known_propensity == total,
            "measured": propensity_coverage,
            "required": 1.0,
            "detail": "every included decision needs a numeric logged assignment probability",
        },
        {
            "id": "assignment_overlap",
            "passed": total >= 1 and overlapping == total,
            "measured": overlap_rate,
            "required": 1.0,
            "detail": (
                "every included decision needs a stochastic assignment "
                "(probability strictly between 0 and 1) so the target has support"
            ),
        },
        {
            "id": "outcome_coverage",
            "passed": outcome_coverage >= _MIN_ESTIMATOR_OUTCOME_COVERAGE,
            "measured": outcome_coverage,
            "required": _MIN_ESTIMATOR_OUTCOME_COVERAGE,
            "detail": "enough decisions need a measured outcome under a named oracle",
        },
        {
            "id": "no_temporal_leak",
            "passed": temporal_anomalies == 0,
            "measured": temporal_anomalies,
            "required": 0,
            "detail": "no attached outcome may pre-date its decision (pre-action covariates only)",
        },
        {
            "id": "censored_window",
            "passed": not censored,
            "measured": int(censored),
            "required": 0,
            "detail": "the evaluation window must not contain post-deletion censoring",
        },
    ]
    unmet = [gate["id"] for gate in gates if not gate["passed"]]

    support = {
        "n_decisions": total,
        "propensity_coverage": propensity_coverage,
        "overlap_rate": overlap_rate,
        "outcome_coverage": outcome_coverage,
        "temporal_anomalies": temporal_anomalies,
        "missing_outcomes": missing_outcomes,
        "effective_sample_size": effective_sample_size,
    }
    result: dict[str, Any] = {
        "policy_version": DECISION_ESTIMATOR_POLICY_VERSION,
        "estimator": estimator,
        "target_policy": target_policy,
        "mode": "estimate" if not unmet else "prediction_audit",
        "abstained": bool(unmet),
        "gates": gates,
        "support": support,
    }
    if unmet:
        # A neutral prediction audit: report the diagnostics and a worst-case reward
        # bound only. NO causal / off-policy / regret claim or vocabulary is emitted,
        # and the estimator's assumptions are NOT asserted as satisfied.
        result["unmet_gates"] = unmet
        result["summary"] = (
            "insufficient support to estimate; see unmet_gates and support diagnostics"
        )
        result["partial_identification"] = {
            "lower": 0.0,
            "upper": 1.0,
            "method": "worst-case reward bound over unsupported/unobserved outcomes",
            "informative": False,
        }
        return result

    values = [weight * reward for weight, reward in samples]
    n_samples = len(values)
    mean = sum(values) / n_samples
    if n_samples > 1:
        variance = sum((value - mean) ** 2 for value in values) / (n_samples - 1)
        std_error = (variance / n_samples) ** 0.5
    else:
        std_error = 0.0
    result["assumptions"] = list(_ESTIMATOR_ASSUMPTIONS[estimator])
    result["estimate"] = {
        "method": estimator,
        "value": round(mean, 4),
        "confidence_interval": [
            round(mean - 1.96 * std_error, 4),
            round(mean + 1.96 * std_error, 4),
        ],
        "uncertainty": {
            "std_error": round(std_error, 4),
            "interval_method": "normal-approximation 95%",
        },
        "effective_sample_size": effective_sample_size,
        "samples_used": n_samples,
        "reward_oracle": (
            "outcome->reward map (success=1.0, partial=0.5, failure=0.0, "
            "abandoned=0.0; unknown/absent is a missing reward)"
        ),
    }
    return result


def _comparison_readiness(group: dict) -> dict:
    """C3 (ADR 0020 D4): versioned gate on whether a group's per-use rates are
    comparable. Both observation-link coverage and activation coverage must meet
    the policy; otherwise the failed dimensions are named so callers know why
    per-use rates and cross-skill ordering are suppressed."""
    failed: list[str] = []
    if group["observation_link_rate"] < _MIN_OBSERVATION_LINK_RATE:
        failed.append("observation_link_rate")
    mechanisms = group["capture_mechanisms"]
    total = sum(mechanisms.values())
    captured = sum(count for name, count in mechanisms.items() if name != "unknown")
    activation_coverage = (captured / total) if total else 0.0
    if activation_coverage < _MIN_ACTIVATION_COVERAGE:
        failed.append("activation_coverage")
    return {
        "policy_version": COMPARISON_READINESS_POLICY_VERSION,
        "eligible": not failed,
        "failed_dimensions": failed,
        "activation_coverage": round(activation_coverage, 3),
        "observation_link_rate": group["observation_link_rate"],
    }


def build_activation_receipts(events: list[dict], skills: set[str]) -> dict:
    """C3 (ADR 0020 D6): activation-receipt completion vs MNAR dropout, by harness
    and closeout. A receipt with a matching activation.closeout is closed; one with
    none is preserved as dropout (never imputed as success or no-feedback), so
    outcome-correlated dropout stays visible."""
    receipts = [
        event
        for event in events
        if event["event_type"] == "activation.receipt"
        and (not skills or (event.get("skill") or {}).get("name") in skills)
    ]
    closeouts = {
        event["payload"]["receipt_id"]: event["payload"]["closeout"]
        for event in events
        if event["event_type"] == "activation.closeout"
    }
    total = len(receipts)
    closed = 0
    by_closeout: dict[str, int] = {"dropout": 0}
    by_harness: dict[str, dict[str, int]] = {}
    for receipt in receipts:
        harness = (receipt.get("session") or {}).get("harness") or "unknown"
        harness_stats = by_harness.setdefault(
            harness, {"total": 0, "closed": 0, "dropout": 0}
        )
        harness_stats["total"] += 1
        receipt_id = receipt["payload"]["receipt_id"]
        if receipt_id in closeouts:
            closed += 1
            harness_stats["closed"] += 1
            label = closeouts[receipt_id]
            by_closeout[label] = by_closeout.get(label, 0) + 1
        else:
            harness_stats["dropout"] += 1
            by_closeout["dropout"] += 1
    dropout = total - closed
    return {
        "total": total,
        "closed": closed,
        "dropout": dropout,
        "completion_rate": round(closed / total, 3) if total else 0.0,
        "dropout_rate": round(dropout / total, 3) if total else 0.0,
        "by_closeout": by_closeout,
        "by_harness": by_harness,
    }


def build_decision_strata(events: list[dict], skills: set[str]) -> dict:
    """C5 (ADR 0022 D2): report decision/outcome coverage by the pre-action
    stratum, sourcing every policy covariate ONLY from the frozen decision.logged
    event (never from a later decision.outcome). An attached outcome that does not
    strictly post-date its decision is a temporal anomaly (a potential
    covariate/label leak) -- it is flagged and not counted as coverage."""
    decisions = [
        event
        for event in events
        if event["event_type"] == "decision.logged"
        and (not skills or (event.get("skill") or {}).get("name") in skills)
    ]
    latest_outcome: dict[str, dict] = {}
    for event in events:
        if event["event_type"] != "decision.outcome":
            continue
        decision_id = event["payload"]["decision_id"]
        prior = latest_outcome.get(decision_id)
        if prior is None or _timestamp(event["occurred_at"]) >= _timestamp(
            prior["occurred_at"]
        ):
            latest_outcome[decision_id] = event

    strata: dict[str, dict] = {}
    total_anomalies = 0
    for decision in decisions:
        payload = decision["payload"]
        name = payload.get("task_stratum") or "unknown"
        stratum = strata.setdefault(
            name,
            {
                "decisions": 0,
                "outcomes": 0,
                "overlap_decisions": 0,
                "temporal_anomalies": 0,
                "difficulty_proxies": {},
                "assignment_mechanisms": {},
            },
        )
        stratum["decisions"] += 1
        proxy = payload.get("difficulty_proxy") or "unknown"
        stratum["difficulty_proxies"][proxy] = (
            stratum["difficulty_proxies"].get(proxy, 0) + 1
        )
        mechanism = payload.get("assignment_mechanism") or "unknown"
        stratum["assignment_mechanisms"][mechanism] = (
            stratum["assignment_mechanisms"].get(mechanism, 0) + 1
        )
        probability = payload.get("chosen_action_probability")
        if (
            isinstance(probability, (int, float))
            and not isinstance(probability, bool)
            and probability < 1
        ):
            stratum["overlap_decisions"] += 1
        outcome_event = latest_outcome.get(payload.get("decision_id"))
        if outcome_event is not None:
            if _timestamp(outcome_event["occurred_at"]) > _timestamp(
                decision["occurred_at"]
            ):
                stratum["outcomes"] += 1
            else:
                stratum["temporal_anomalies"] += 1
                total_anomalies += 1
    for stratum in strata.values():
        stratum["outcome_coverage_rate"] = (
            round(stratum["outcomes"] / stratum["decisions"], 3)
            if stratum["decisions"]
            else 0.0
        )
    return {
        "contract_version": STRATUM_CONTRACT_VERSION,
        # covariates are read only from the frozen decision.logged event, whose
        # occurred_at IS the decision time -- so every reported covariate was
        # available strictly before action selection.
        "covariate_source": "decision.logged",
        "total_decisions": len(decisions),
        "temporal_anomalies": total_anomalies,
        "strata": dict(sorted(strata.items())),
    }


def _learner_acquisition() -> dict[str, dict]:
    """C5 (ADR 0022 D9): actionable evidence-acquisition plans for the
    separately gated 0007/0008 learners. These artifacts authorize acquisition
    work only; emitting them never changes either learner's blocked status."""
    return {
        "0007": {
            "task_ref": "0007",
            "owner": "maintainer",
            "max_acquisition_budget": 200,
            "review_within_days": 7,
            "learner_status": "blocked",
            "unmet_gates": [
                "corpus",
                "holdout",
                "baseline",
                "uncertainty",
                "privacy",
                "workload",
            ],
            "requirements": {
                "stratified_sampling": {
                    "population": "eligible_notes",
                    "strata": ["public", "private"],
                    "method": "privacy-safe",
                },
                "duplicate_related_distinct_pairs": {
                    "labels": ["duplicate", "related", "distinct"],
                    "maintainer_reviewed": True,
                    "self_labels_accepted": False,
                },
                "prechosen_holdout": {
                    "reserved_before_model_work": True,
                    "used_for_selection": False,
                },
                "baseline": {
                    "declared": True,
                    "measures": ["precision", "recall", "abstention"],
                },
                "annotation_workload_budget": {
                    "cap": 200,
                    "unit": "maintainer-minutes",
                },
                "stopping_rule": {
                    "sequential": True,
                    "predeclared": True,
                    "criterion": "useful_uncertainty_bounds",
                },
            },
        },
        "0008": {
            "task_ref": "0008",
            "owner": "maintainer",
            "max_acquisition_budget": 100,
            "review_within_days": 14,
            "learner_status": "blocked",
            "unmet_gates": ["overlap", "full_causal_policy"],
            "requirements": {
                "prospective_decision_logging": {
                    "decision_mechanism": "decision.logged",
                    "outcome_mechanism": "decision.outcome",
                    "decision_before_selection": True,
                },
                "overlap_diagnostics": {
                    "strata": "pre_action",
                    "coverage_reported": True,
                },
                "authorized_shadow_surface": {
                    "authorization": "D8_pilot_record",
                    "low_risk": True,
                },
                "bounded_rollout_kill_rollback": {
                    "owner": "named_human",
                    "kill_switch": "deterministic_outside_policy",
                    "rollback": True,
                },
            },
        },
    }


def build_readiness(
    events: list[dict],
    skills: set[str],
    *,
    abandoned: dict[str, str] | None = None,
) -> dict:
    """C5 (ADR 0022 D3): a computable prospective-evaluation readiness state
    machine, separate from any learner. Each gate records its population,
    calculation, owner, review window, and acquisition budget, and returns one of
    `insufficient` / `proceed` / `abandon`. An `insufficient` gate deterministically
    LINKS a bounded acquisition task (stable id derived from the gate) with a
    scheduled review -- it is never a resting stall. `abandon` (an operator
    override) requires a rationale and preserves descriptive-only operation.
    D9 adds owned acquisition plans for the separately gated 0007/0008 learners;
    they remain blocked regardless of this evaluation-readiness verdict."""
    abandoned = abandoned or {}
    strata = build_decision_strata(events, skills)
    total = strata["total_decisions"]
    overlap = sum(s["overlap_decisions"] for s in strata["strata"].values())
    outcomes = sum(s["outcomes"] for s in strata["strata"].values())
    overlap_rate = round(overlap / total, 3) if total else 0.0
    outcome_rate = round(outcomes / total, 3) if total else 0.0

    gates: list[dict] = []

    def add_gate(
        gate_id: str,
        population: str,
        measured: float,
        required: float,
        budget: int,
        review_within_days: int,
        scope: str,
    ) -> None:
        gate = {
            "id": gate_id,
            "owner": "maintainer",
            "population": population,
            "calculation": {"measured": measured, "required": required},
            "max_acquisition_budget": budget,
            "review_within_days": review_within_days,
        }
        if gate_id in abandoned:
            gate["decision"] = "abandon"
            gate["rationale"] = abandoned[gate_id]
        elif measured >= required:
            gate["decision"] = "proceed"
        else:
            gate["decision"] = "insufficient"
            gate["acquisition_task"] = {
                "id": f"acquisition:{gate_id}",
                "scope": scope,
                "owner": "maintainer",
                "max_acquisition_budget": budget,
                "review_within_days": review_within_days,
            }
        gates.append(gate)

    add_gate(
        "decision_logging",
        f"{total} decisions logged",
        total,
        _MIN_READY_DECISIONS,
        50,
        7,
        "log prospective decisions with full policy context before evaluation",
    )
    add_gate(
        "assignment_overlap",
        f"{overlap}/{total} decisions with assignment overlap (probability < 1)",
        overlap_rate,
        _MIN_OVERLAP_RATE,
        100,
        14,
        "run an authorized randomized/interleaved pilot to create overlap",
    )
    add_gate(
        "outcome_coverage",
        f"{outcomes}/{total} decisions with a valid attached outcome",
        outcome_rate,
        _MIN_OUTCOME_COVERAGE_RATE,
        100,
        14,
        "attach measured task-level outcomes under a named oracle",
    )

    decisions_made = {gate["decision"] for gate in gates}
    if decisions_made == {"proceed"}:
        overall = "proceed"
    elif "insufficient" in decisions_made:
        overall = "insufficient"
    else:  # only proceed/abandon, at least one abandon
        overall = "abandon"
    return {
        "policy_version": READINESS_POLICY_VERSION,
        "overall": overall,
        "gates": gates,
        "learner_acquisition": _learner_acquisition(),
    }


# C5 (ADR 0022 D6): the versioned decision-profile contract. A profile is
# task-specific and lexicographic; a universal weighted scalar is inadmissible.
DECISION_PROFILE_VERSION = 1
_PROFILE_RULES = ("superiority", "non_inferiority")
_COMPARE_OPS = {
    "==": lambda value, threshold: value == threshold,
    "!=": lambda value, threshold: value != threshold,
    "<=": lambda value, threshold: value <= threshold,
    ">=": lambda value, threshold: value >= threshold,
    "<": lambda value, threshold: value < threshold,
    ">": lambda value, threshold: value > threshold,
}


def load_decision_profile(profile: dict) -> dict:
    """C5 (ADR 0022 D6): validate and freeze a versioned decision profile.

    A profile encodes lexicographic hard safety/privacy/budget constraints, ONE
    primary outcome with a superiority/non-inferiority rule + margin, secondary
    thresholds, an abstention policy, a NAMED human tie-break authority, and a
    requirement to report a Pareto frontier + sensitivity. A universal weighted
    scalar (a global leaderboard) is inadmissible, as is a profile without a named
    tie-break or a well-formed primary rule. The returned block carries a
    ``sha256`` over the canonical profile so it can be frozen into the manifest
    before any candidate is evaluated (a post-hoc weight change re-freezes a
    different manifest, never mutates the pinned one)."""
    if not isinstance(profile, dict):
        raise FeedbackError("decision profile must be a JSON object")
    if profile.get("scalar_weights") is not None or profile.get("type") == (
        "universal_scalar"
    ):
        raise FeedbackError(
            "a universal weighted-scalar leaderboard is not an admissible decision "
            "profile; declare lexicographic hard constraints + one primary rule"
        )
    primary = profile.get("primary_outcome")
    if not isinstance(primary, dict) or not primary.get("metric"):
        raise FeedbackError("decision profile requires a primary_outcome with a metric")
    if primary.get("rule") not in _PROFILE_RULES:
        raise FeedbackError(
            f"decision profile primary_outcome.rule must be one of {_PROFILE_RULES}"
        )
    if not isinstance(primary.get("margin"), (int, float)) or isinstance(
        primary.get("margin"), bool
    ):
        raise FeedbackError("decision profile primary_outcome.margin must be numeric")
    tie_break = profile.get("tie_break")
    if not isinstance(tie_break, dict) or not tie_break.get("authority"):
        raise FeedbackError(
            "decision profile requires a named human tie_break.authority"
        )
    requires = profile.get("requires") or {}
    if not (requires.get("pareto") and requires.get("sensitivity")):
        raise FeedbackError(
            "decision profile must require both a Pareto frontier and a sensitivity "
            "analysis (requires.pareto and requires.sensitivity)"
        )
    if not isinstance(profile.get("id"), str) or not isinstance(
        profile.get("version"), int
    ):
        raise FeedbackError("decision profile requires a string id and an int version")
    digest = hashlib.sha256(
        json.dumps(profile, sort_keys=True).encode("utf-8")
    ).hexdigest()
    frozen = dict(profile)
    frozen["policy_version"] = DECISION_PROFILE_VERSION
    frozen["sha256"] = digest
    return frozen


def _metric_directions(profile: dict) -> dict[str, str]:
    """Objective directions used for dominance/Pareto: the primary metric's declared
    direction (default max), and each secondary metric inferred from its comparison
    op (``<=``/``<`` minimise; ``>=``/``>`` maximise). ``==`` metrics are hard
    equality constraints, not objectives, so they are excluded."""
    directions: dict[str, str] = {}
    primary = profile["primary_outcome"]
    directions[primary["metric"]] = primary.get("direction", "max")
    for threshold in profile.get("secondary_thresholds") or []:
        op = threshold.get("op")
        if op in ("<=", "<"):
            directions.setdefault(threshold["metric"], "min")
        elif op in (">=", ">"):
            directions.setdefault(threshold["metric"], "max")
    return directions


def _dominates(a: dict, b: dict, directions: dict[str, str]) -> bool:
    """True if candidate ``a`` weakly dominates ``b`` on every objective and strictly
    beats it on at least one."""
    strictly_better = False
    for metric, direction in directions.items():
        av, bv = a["metrics"].get(metric), b["metrics"].get(metric)
        if av is None or bv is None:
            return False
        if direction == "max":
            if av < bv:
                return False
            if av > bv:
                strictly_better = True
        else:
            if av > bv:
                return False
            if av < bv:
                strictly_better = True
    return strictly_better


def _primary_passes(candidate: dict, baseline: dict, primary: dict) -> bool:
    metric, rule, margin = primary["metric"], primary["rule"], primary["margin"]
    direction = primary.get("direction", "max")
    value = candidate["metrics"].get(metric)
    base = baseline["metrics"].get(metric)
    if value is None or base is None:
        return False
    if direction == "max":
        return (
            value > base + margin if rule == "superiority" else value >= base - margin
        )
    return value < base - margin if rule == "superiority" else value <= base + margin


def evaluate_promotion(profile: dict, candidates_doc: dict) -> dict:
    """C5 (ADR 0022 D6): apply the frozen lexicographic decision profile to the
    provided candidate metric bundles and return a computable, auditable promotion
    verdict. Hard constraints eliminate first; then the primary rule/margin vs the
    baseline; then the secondary thresholds. A single eligible (or single Pareto-
    dominant) candidate is ``promote``; multiple incomparable eligibles route to the
    named human ``tie_break``; none eligible is ``abstain``. This only applies a
    frozen rule to given summaries -- it computes NO causal effect and invents no
    counterfactual."""
    if not isinstance(candidates_doc, dict):
        raise FeedbackError("candidates document must be a JSON object")
    by_name = {c["name"]: c for c in candidates_doc.get("candidates") or []}
    baseline_name = candidates_doc.get("baseline")
    if baseline_name not in by_name:
        raise FeedbackError("candidates.baseline must name one of the candidates")
    baseline = by_name[baseline_name]
    primary = profile["primary_outcome"]
    directions = _metric_directions(profile)

    def hard_violations(candidate: dict) -> list[str]:
        failed = []
        for constraint in profile.get("hard_constraints") or []:
            metric, op, threshold = (
                constraint["metric"],
                constraint["op"],
                constraint["threshold"],
            )
            value = candidate["metrics"].get(metric)
            if value is None or not _COMPARE_OPS[op](value, threshold):
                failed.append(metric)
        return failed

    contenders = [name for name in by_name if name != baseline_name]
    eliminated = [name for name in contenders if hard_violations(by_name[name])]
    survivors = [name for name in contenders if name not in eliminated]

    def secondary_ok(candidate: dict) -> bool:
        for threshold in profile.get("secondary_thresholds") or []:
            value = candidate["metrics"].get(threshold["metric"])
            if value is None or not _COMPARE_OPS[threshold["op"]](
                value, threshold["threshold"]
            ):
                return False
        return True

    def eligible_names(margin: float) -> list[str]:
        scoped = dict(primary)
        scoped["margin"] = margin
        return [
            name
            for name in survivors
            if _primary_passes(by_name[name], baseline, scoped)
            and secondary_ok(by_name[name])
        ]

    eligible = eligible_names(primary["margin"])
    if not eligible:
        decision, winner = "abstain", None
    elif len(eligible) == 1:
        decision, winner = "promote", eligible[0]
    else:
        non_dominated = [
            name
            for name in eligible
            if not any(
                other != name and _dominates(by_name[other], by_name[name], directions)
                for other in eligible
            )
        ]
        if len(non_dominated) == 1:
            decision, winner = "promote", non_dominated[0]
        else:
            decision, winner = "tie_break", None

    # Pareto frontier over all candidates (incl. baseline) on the declared objectives.
    all_names = list(by_name)
    pareto = [
        name
        for name in all_names
        if not any(
            other != name and _dominates(by_name[other], by_name[name], directions)
            for other in all_names
        )
    ]

    # Sensitivity: does the eligible set (hence the winner) survive halving/doubling
    # the primary margin? A decision that flips under a small margin change is fragile.
    margin = primary["margin"]
    perturbations = {
        "margin_x0.5": sorted(eligible_names(margin * 0.5)),
        "margin_x2": sorted(eligible_names(margin * 2)),
    }
    stable = all(set(names) == set(eligible) for names in perturbations.values())

    result = {
        "policy_version": DECISION_PROFILE_VERSION,
        "profile_sha256": profile["sha256"],
        "baseline": baseline_name,
        "decision": decision,
        "winner": winner,
        "eliminated": eliminated,
        "eligible": sorted(eligible),
        "pareto_frontier": sorted(pareto),
        "sensitivity": {"stable": stable, "eligible_at": perturbations},
    }
    if decision == "tie_break":
        result["tie_break_authority"] = profile["tie_break"]["authority"]
    return result


def build_evaluation_manifest(
    events: list[dict],
    *,
    as_of: str,
    skills: set[str],
    estimator: str | None = None,
    target_policy: str = DEFAULT_TARGET_POLICY,
    decision_profile: dict | None = None,
    candidates: dict | None = None,
    note_entries: list[dict] | None = None,
) -> dict:
    """C5 (ADR 0022 D4): a byte-stable immutable evaluation manifest.

    A true ``as_of`` cutoff is applied CONSISTENTLY to every event class: only
    events whose ``occurred_at`` is at or before the cutoff enter the evaluand, so
    a later finish/label/disposition (which necessarily has a later timestamp) is
    excluded and re-running the same ``as_of`` is byte-stable as the ledger grows.
    A different ``as_of`` yields a distinct version_key -- a new version is produced
    only by an explicit later cutoff, never by rewriting an old one. The ledger
    digest is over the canonical, deterministically ordered included events.

    When ``estimator`` is given (D5), a gated ``estimator_evaluation`` section is
    added over the same cutoff population; when it is ``None`` the manifest is
    byte-identical to the CP-4 manifest (the estimator layers on, never mutates)."""
    cutoff = _timestamp(as_of)
    normalized_as_of = cutoff.isoformat().replace("+00:00", "Z")
    included = [
        event
        for event in events
        if _timestamp(event["occurred_at"]) <= cutoff
        and (not skills or (event.get("skill") or {}).get("name") in skills)
    ]
    # Tombstones live outside the evaluand, but a later deletion of an event whose
    # prior timestamp falls inside this historical cutoff must still invalidate the
    # manifest. Include that content-free evidence in the digest/version key even
    # when the deletion itself happened after ``as_of``.
    affecting_tombstones = [
        event
        for event, _ in _tombstones_in_window(
            events,
            after=None,
            before=cutoff,
            skills=skills,
            before_inclusive=True,
        )
    ]
    manifest_events = {event["event_id"]: event for event in included}
    manifest_events.update({event["event_id"]: event for event in affecting_tombstones})
    ordered = sorted(
        manifest_events.values(),
        key=lambda event: (event["occurred_at"], event["event_id"]),
    )
    canonical = "\n".join(json.dumps(event, sort_keys=True) for event in ordered)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    censoring = _build_censoring(
        events,
        after=None,
        before=cutoff,
        skills=skills,
        before_inclusive=True,
    )
    ineligible_ids: set[str] = set()
    if note_entries is not None:
        effective, conflicts, orphans, _ = _reconcile_entries(
            note_entries,
            index=LedgerIndex.from_events(included),
            include_event_orphans=True,
        )
        ineligible_ids.update(item["id"] for item in conflicts)
        ineligible_ids.update(item["id"] for item in orphans)
        ineligible_ids.update(
            item["id"]
            for item in effective
            if item.get("_integrity", "unverified") != "verified"
        )
    ineligible_observation_ids = {
        (event.get("payload") or {}).get("feedback_id")
        for event in included
        if event.get("event_type") == "observation.recorded"
        and (event.get("payload") or {}).get("feedback_id") in ineligible_ids
    }
    evaluand = [
        event
        for event in included
        if event.get("event_type") != "observation.tombstoned"
        and not (
            event.get("event_type") == "observation.recorded"
            and (event.get("payload") or {}).get("feedback_id")
            in ineligible_observation_ids
        )
    ]
    event_counts: dict[str, int] = {}
    for event in evaluand:
        event_counts[event["event_type"]] = event_counts.get(event["event_type"], 0) + 1
    manifest: dict[str, Any] = {
        "manifest_version": EVALUATION_MANIFEST_VERSION,
        "as_of": normalized_as_of,
        "version_key": f"{normalized_as_of}:{digest[:12]}",
        "maturation_rule": (
            "events with occurred_at <= as_of enter the evaluand; later tombstones "
            "whose deleted record falls inside the cutoff remain outside the "
            "evaluand but invalidate its history. Origin-ineligible observations and "
            "tombstones are excluded from population counts."
        ),
        "population": {
            "skills": sorted(skills) if skills else None,
            "total_events": len(evaluand),
            "event_counts": dict(sorted(event_counts.items())),
            "origin_ineligible": len(ineligible_observation_ids),
        },
        "ledger_digest": {
            "algorithm": "sha256",
            "canonicalization": "event-sorted-v1",
            "sha256": digest,
        },
        "schema_versions": {
            "event": EVENT_SCHEMA_VERSION,
            "stratum": STRATUM_CONTRACT_VERSION,
            "readiness": READINESS_POLICY_VERSION,
        },
        "censoring": censoring,
        "origin_integrity": {
            "status": "conflict"
            if ineligible_observation_ids
            else ("verified" if note_entries is not None else "unverified"),
            "checked": note_entries is not None,
            "ineligible_records": len(ineligible_observation_ids),
        },
        "decision_strata": build_decision_strata(evaluand, skills),
    }
    if estimator is not None:
        manifest["estimator_evaluation"] = build_estimator_evaluation(
            evaluand,
            estimator=estimator,
            target_policy=target_policy,
            censored=censoring["post_deletion"],
        )
    if decision_profile is not None:
        frozen = load_decision_profile(decision_profile)
        manifest["decision_profile"] = frozen
        manifest["schema_versions"]["decision_profile"] = DECISION_PROFILE_VERSION
        if candidates is not None:
            manifest["promotion_decision"] = evaluate_promotion(frozen, candidates)
    return manifest


def build_stats(
    events: list[dict],
    *,
    after: datetime | None,
    before: datetime | None,
    skills: set[str],
    group_by: tuple[str, ...],
    allow_partial: bool = False,
) -> dict:
    """Aggregate an invocation-start cohort and time-windowed observations.

    When a group fails the comparison-readiness policy (ADR 0020 D4) its per-use
    rates are suppressed and cross-skill ordering is withheld, unless
    ``allow_partial`` opts into an explicitly non-comparable descriptive view.
    """
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
        # C3 (ADR 0020 D3/D5): count this selected invocation as one
        # capability.execution, stratify by harness capture mechanism, and record
        # its decision episode (if any) for the executions-per-episode ratio.
        population["capability_executions"] += 1
        mechanism = start["payload"].get("capture_mechanism") or "unknown"
        if mechanism not in group["capture_mechanisms"]:
            mechanism = "unknown"
        group["capture_mechanisms"][mechanism] += 1
        episode_id = start["payload"].get("decision_episode_id")
        if episode_id:
            group["_decision_episode_ids"].add(episode_id)
        population["duplicate_start_events"] += len(ordered_starts) - 1
        population["conflicting_start_events"] += sum(
            _start_signature(event) != _start_signature(start)
            for event in ordered_starts[1:]
        )
        population["duplicate_finish_events"] += max(0, len(invocation_finishes) - 1)
        population["mismatched_finish_events"] += len(all_invocation_finishes) - len(
            invocation_finishes
        )
        population["conflicting_actual_backend_fields"] += _actual_backend_conflicts(
            invocation_finishes
        )
        if not invocation_finishes:
            population["incomplete"] += 1
            population["unknown_outcomes"] += 1
            continue
        outcomes = {event["payload"]["outcome"] for event in invocation_finishes}
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
                "actual-router": (finish["payload"].get("backend") or {}).get("router"),
                "actual-provider": (finish["payload"].get("backend") or {}).get(
                    "provider"
                ),
                "actual-model": (finish["payload"].get("backend") or {}).get("model"),
                "actual-effort": (finish["payload"].get("backend") or {}).get("effort"),
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
    declared_test_ids = {
        event["payload"]["feedback_id"]
        for event in events
        if event["event_type"] == "preservation.declared"
    }
    verified_preservation_ids = {
        event["payload"]["feedback_id"]
        for event in events
        if event["event_type"] == "verification.recorded"
        and event["payload"].get("purpose") == "preservation"
        and event["payload"].get("verification_state") == "verified"
    }
    for event in observations:
        dimensions = _observation_dimensions(event, selected_invocations)
        group = group_for(dimensions)
        payload = event["payload"]
        group["observations"][payload["kind"]] += 1
        group["observations"][payload["signal"]] += 1
        if event.get("invocation_id"):
            group["observations"]["linked_to_invocation"] += 1
        else:
            group["observations"]["unlinked_to_invocation"] += 1
        feedback_id = payload["feedback_id"]
        disposition = dispositions.get(feedback_id)
        is_preserved = bool(
            disposition and disposition["payload"].get("status") == "preserve"
        )
        preservation = group["preservation"]
        if payload["kind"] == "praise":
            preservation["praise"] += 1
            if is_preserved:
                preservation["preserved"] += 1
        # C2 (ADR 0018 R4): a declared test link counts as declared_with_test for
        # any kind; only a passing preservation receipt counts as verified.
        if feedback_id in verified_preservation_ids:
            preservation["verified_with_test"] += 1
        elif feedback_id in declared_test_ids:
            preservation["declared_with_test"] += 1
        # C4 (ADR 0021 D1/D3/D4): stratify by source tier and decide per-use-case
        # downstream eligibility. A source tier alone never scores -- the
        # observation must ALSO carry >=1 verified evidence receipt (D2) and meet
        # the use-case condition. agent_judgment/automation are raw-only.
        source = event.get("source")
        group["_source_counts"][source] = group["_source_counts"].get(source, 0) + 1
        receipts = payload.get("evidence_verification") or []
        has_verified_evidence = any(
            receipt.get("result") == "verified" for receipt in receipts
        )
        # C4 (ADR 0021 D5): tally record-time verification results for the group.
        evidence_tally = group["evidence_verification"]
        if receipts:
            evidence_tally["observations_with_evidence"] += 1
        for receipt in receipts:
            evidence_tally["total_references"] += 1
            result = receipt.get("result")
            if result in EVIDENCE_RESULTS:
                evidence_tally[result] += 1
        # C4 (ADR 0021 D6): accumulate non-ignorable, privacy-correlated label
        # missingness by the privacy-safe task-class stratum. Only content-free
        # fields (screening outcome, label availability) are read.
        stratum = (event.get("task") or {}).get("class") or "unknown"
        privacy_stratum = group["_privacy_strata"].setdefault(
            stratum, {"total": 0, "labeled": 0, "screening_outcomes": {}}
        )
        privacy_stratum["total"] += 1
        if payload.get("label_available"):
            privacy_stratum["labeled"] += 1
        screening_outcome = (event.get("privacy") or {}).get("screening_outcome")
        if screening_outcome:
            privacy_stratum["screening_outcomes"][screening_outcome] = (
                privacy_stratum["screening_outcomes"].get(screening_outcome, 0) + 1
            )
        outcome = payload.get("outcome")
        use_case_condition = {
            "preservation": is_preserved,
            "recommendation": payload.get("signal") == "positive",
            "user_preference": True,
            "outcome": outcome not in (None, "unknown"),
            "failure_prediction": outcome == "failure",
        }
        eligible_for_any = False
        for use_case in ELIGIBILITY_USE_CASES:
            if (
                source_eligible_for(source, use_case)
                and has_verified_evidence
                and use_case_condition[use_case]
            ):
                group["eligible_aggregates"][use_case] += 1
                eligible_for_any = True
        if eligible_for_any:
            group["_source_eligible"][source] = (
                group["_source_eligible"].get(source, 0) + 1
            )

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
            and _timestamp(event["occurred_at"]) > _timestamp(praise["occurred_at"])
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
        # C3 (ADR 0020 D3/D5): observation link rate and the decision-episode ratio.
        obs = group["observations"]
        linked = obs["linked_to_invocation"]
        total_obs = linked + obs["unlinked_to_invocation"]
        group["observation_link_rate"] = (
            round(linked / total_obs, 3) if total_obs else 0.0
        )
        episodes = group.pop("_decision_episode_ids")
        executions = group["population"]["capability_executions"]
        group["population"]["decision_episodes"] = len(episodes)
        group["population"]["executions_per_episode"] = (
            round(executions / len(episodes), 3) if episodes else 0.0
        )
        # C4 (ADR 0021 D3): source-stratified population, raw counts always
        # visible and per-source eligible counts distinct from them.
        source_counts = group.pop("_source_counts")
        source_eligible = group.pop("_source_eligible")
        raw_total = sum(source_counts.values())
        group["source_distribution"] = {
            "policy_version": EVIDENCE_ELIGIBILITY_POLICY_VERSION,
            "raw_total": raw_total,
            "by_source": {
                source: {
                    "count": count,
                    "rate_pct": round(100 * count / raw_total, 3) if raw_total else 0.0,
                    "eligible": source_eligible.get(source, 0),
                    "classified_as": source,
                }
                for source, count in sorted(source_counts.items())
            },
            "eligible_total": sum(source_eligible.values()),
        }
        # C4 (ADR 0021 D6): per-stratum label coverage; a censored stratum
        # abstains and never borrows a better-observed stratum's result.
        privacy_strata = group.pop("_privacy_strata")
        group["privacy_missingness"] = {
            "policy_version": EVIDENCE_ELIGIBILITY_POLICY_VERSION,
            "min_label_coverage": _MIN_LABEL_COVERAGE,
            "strata": {
                name: {
                    "total": accumulator["total"],
                    "labeled": accumulator["labeled"],
                    "label_coverage_rate": (
                        round(accumulator["labeled"] / accumulator["total"], 3)
                        if accumulator["total"]
                        else 0.0
                    ),
                    "abstain": (
                        (accumulator["labeled"] / accumulator["total"])
                        if accumulator["total"]
                        else 0.0
                    )
                    < _MIN_LABEL_COVERAGE,
                    "screening_outcomes": accumulator["screening_outcomes"],
                    "borrowed_result": None,
                }
                for name, accumulator in sorted(privacy_strata.items())
            },
        }
        # C3 (ADR 0020 D4): suppress non-comparable per-use rates unless the caller
        # explicitly opts into a partial-descriptive view.
        readiness = _comparison_readiness(group)
        group["comparison_readiness"] = readiness
        if not readiness["eligible"] and not allow_partial:
            group.pop("rates_per_100_uses", None)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: tuple(
            "" if value is None else str(value)
            for value in group["dimensions"].values()
        ),
    )
    # C3 (ADR 0020 D4): cross-skill ordering is withheld unless every group is
    # comparison-ready; --allow-partial-descriptive emits a labelled non-comparable
    # view instead. No `ranking` key is emitted while ordering is not ready.
    all_eligible = all(
        group["comparison_readiness"]["eligible"] for group in ordered_groups
    )
    if allow_partial:
        cross_skill_ordering = {"status": "partial_descriptive"}
        non_comparable = True
    elif all_eligible and ordered_groups:
        cross_skill_ordering = {"status": "ready"}
        non_comparable = False
    else:
        cross_skill_ordering = {"status": "suppressed"}
        non_comparable = True
    return {
        "version": 1,
        "cross_skill_ordering": cross_skill_ordering,
        "non_comparable": non_comparable,
        "activation_receipts": build_activation_receipts(events, skills),
        "censoring": _build_censoring(
            events, after=after, before=before, skills=skills
        ),
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


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def build_closeout(events: list[dict], skill: str) -> dict:
    """Project a per-skill verified-closure and reopen closeout report (ADR 0018
    R5) from the append-only event ledger.

    Pure projection: consumes raw events, returns the report dict. All metrics are
    derived from observation.recorded and disposition.changed events scoped to the
    given skill, and are HISTORICAL (an item verified then reopened still counts as
    a verified closeout for the outflow and reopen denominators).
    """
    observations = [
        event
        for event in events
        if event["event_type"] == "observation.recorded"
        and (event.get("skill") or {}).get("name") == skill
    ]
    dispositions = [
        event
        for event in events
        if event["event_type"] == "disposition.changed"
        and (event.get("skill") or {}).get("name") == skill
    ]
    ordered_dispositions = sorted(
        dispositions, key=lambda event: _timestamp(event["occurred_at"])
    )
    ordered_observations = sorted(
        observations, key=lambda event: _timestamp(event["occurred_at"])
    )

    # Earliest observation per feedback id (for inflow-age and time-to-verification).
    earliest_observation: dict[str, dict] = {}
    for event in ordered_observations:
        earliest_observation.setdefault(event["payload"]["feedback_id"], event)
    observation_time = {
        feedback_id: _timestamp(event["occurred_at"])
        for feedback_id, event in earliest_observation.items()
    }

    # Latest disposition per feedback id.
    latest_disposition: dict[str, dict] = {}
    for event in ordered_dispositions:
        latest_disposition[event["payload"]["feedback_id"]] = event

    inflow = len(observations)

    # Verified receipts for this skill, keyed by (feedback_id, receipt_id) -> purpose
    # (ADR 0019 D2): a closing disposition counts as verified outflow only if its
    # links.receipt references a verified receipt of the matching purpose. Legacy
    # pre-C2 prose-only resolves (no receipt link, or a link with no backing verified
    # receipt) are excluded and reported separately rather than silently dropped.
    verified_receipts = {
        (event["payload"]["feedback_id"], event["payload"]["receipt_id"]): event[
            "payload"
        ].get("purpose")
        for event in events
        if event["event_type"] == "verification.recorded"
        and (event.get("skill") or {}).get("name") == skill
        and event["payload"].get("verification_state") == "verified"
    }

    # C4 (ADR 0021 D7): receipts whose verified check is artifact-bound (digest
    # match). Only this subset is artifact-attested; the remainder is advisory.
    bound_receipt_keys = {
        (event["payload"]["feedback_id"], event["payload"]["receipt_id"])
        for event in events
        if event["event_type"] == "verification.recorded"
        and (event.get("skill") or {}).get("name") == skill
        and event["payload"].get("verification_state") == "verified"
        and event["payload"].get("artifact_binding") == "bound"
    }

    def _receipt_backed(disposition: dict, purpose: str) -> bool:
        payload = disposition["payload"]
        receipt_id = (payload.get("links") or {}).get("receipt")
        if not receipt_id:
            return False
        return verified_receipts.get((payload["feedback_id"], receipt_id)) == purpose

    def _receipt_bound(disposition: dict) -> bool:
        payload = disposition["payload"]
        receipt_id = (payload.get("links") or {}).get("receipt")
        return bool(
            receipt_id and (payload["feedback_id"], receipt_id) in bound_receipt_keys
        )

    # Historic verified closes (ADR 0019 D2/D5): a resolved disposition backed by a
    # verified resolution receipt, OR a preserve disposition backed by a verified
    # preservation receipt (`observed -> preserve` is itself a verified closure).
    verified_resolved_ids = {
        event["payload"]["feedback_id"]
        for event in dispositions
        if event["payload"].get("status") == "resolved"
        and _receipt_backed(event, "resolution")
    }
    verified_preserved_ids = {
        event["payload"]["feedback_id"]
        for event in dispositions
        if event["payload"].get("status") == "preserve"
        and _receipt_backed(event, "preservation")
    }
    verified_ids = verified_resolved_ids | verified_preserved_ids
    verified_outflow = len(verified_ids)
    # C4 (ADR 0021 D7): the artifact-bound subset of verified closes. verified_outflow
    # still counts every verified close (legacy-compatible), but a consumer that
    # requires artifact attestation reads verified_and_bound_outflow -- the unbound
    # remainder trusts a check not bound to the artifact (the R3-1 residual).
    verified_and_bound_ids = {
        event["payload"]["feedback_id"]
        for event in dispositions
        if (
            (
                event["payload"].get("status") == "resolved"
                and _receipt_backed(event, "resolution")
            )
            or (
                event["payload"].get("status") == "preserve"
                and _receipt_backed(event, "preservation")
            )
        )
        and _receipt_bound(event)
    }
    verified_and_bound_outflow = len(verified_and_bound_ids)
    # A closing disposition (resolved or preserve) not backed by a verified receipt
    # of the matching purpose is a legacy/unverified close -- surfaced symmetrically
    # for both statuses rather than silently dropped (re-verify R3-2).
    legacy_unverified_ids = {
        event["payload"]["feedback_id"]
        for event in dispositions
        if (
            event["payload"].get("status") == "resolved"
            and not _receipt_backed(event, "resolution")
        )
        or (
            event["payload"].get("status") == "preserve"
            and not _receipt_backed(event, "preservation")
        )
    } - verified_ids
    legacy_unverified_outflow = len(legacy_unverified_ids)

    # Reopened: LATEST disposition is open AND carries a superseded_receipt link.
    reopened_ids = {
        feedback_id
        for feedback_id, event in latest_disposition.items()
        if event["payload"].get("status") == "open"
        and "superseded_receipt" in (event["payload"].get("links") or {})
    }
    reopened_feedback_ids = sorted(reopened_ids)

    # Actionably-open: latest disposition is open WITHOUT superseded_receipt, or no
    # disposition at all (a freshly recorded note defaults to open for non-praise;
    # praise defaults to "observed").
    open_ids = set()
    for feedback_id, event in earliest_observation.items():
        kind = event["payload"].get("kind")
        disposition = latest_disposition.get(feedback_id)
        if disposition is None:
            if _default_status(kind) == "open":
                open_ids.add(feedback_id)
        elif disposition["payload"].get(
            "status"
        ) == "open" and "superseded_receipt" not in (
            disposition["payload"].get("links") or {}
        ):
            open_ids.add(feedback_id)
    open_ids -= reopened_ids
    open_feedback_ids = sorted(open_ids)

    verified_close_rate = verified_outflow / inflow if inflow else 0.0
    reopen_rate = len(reopened_ids) / verified_outflow if verified_outflow else 0.0

    if open_ids:
        earliest_open = min(observation_time[feedback_id] for feedback_id in open_ids)
        oldest_open_age_seconds = max(
            0.0, (datetime.now(timezone.utc) - earliest_open).total_seconds()
        )
    else:
        oldest_open_age_seconds = 0.0

    # Time from a feedback item's first observation to its first verified closure
    # (a resolved or preserve disposition; ADR 0019 D5).
    durations: list[float] = []
    for feedback_id in sorted(verified_ids):
        if feedback_id not in observation_time:
            continue
        first_resolved = next(
            (
                _timestamp(event["occurred_at"])
                for event in ordered_dispositions
                if event["payload"]["feedback_id"] == feedback_id
                and event["payload"].get("status") in ("resolved", "preserve")
            ),
            None,
        )
        if first_resolved is not None:
            durations.append(
                max(
                    0.0,
                    (first_resolved - observation_time[feedback_id]).total_seconds(),
                )
            )

    return {
        "skill": skill,
        "population": {
            "inflow": inflow,
            "verified_outflow": verified_outflow,
            "verified_and_bound_outflow": verified_and_bound_outflow,
            "verified_resolved": len(verified_resolved_ids),
            "verified_preserved": len(verified_preserved_ids),
            "legacy_unverified_outflow": legacy_unverified_outflow,
        },
        "rates": {
            "verified_close_rate": verified_close_rate,
            "reopen_rate": reopen_rate,
        },
        "oldest_open_age_seconds": oldest_open_age_seconds,
        "time_to_verification_seconds": {
            "count": len(durations),
            "median": _median(durations),
        },
        "open_feedback_ids": open_feedback_ids,
        "reopened_feedback_ids": reopened_feedback_ids,
    }


def _actor_type_for_source(source: str | None) -> str:
    if source in {"explicit_user", "observed_user"}:
        return "user"
    if source == "automation":
        return "automation"
    return "agent"


def _diagnostic(feedback_id: str, conflict_type: str, field: str) -> dict:
    return {"id": feedback_id, "type": conflict_type, "field": field}


def _add_diagnostic(target: list[dict], diagnostic: dict) -> None:
    if diagnostic not in target:
        target.append(diagnostic)


def _reconcile_entries(
    entries: list[dict],
    *,
    index: LedgerIndex | None = None,
    include_event_orphans: bool = False,
) -> tuple[list[dict], list[dict], list[dict], dict[str, dict]]:
    """Join editable projections to immutable ledger authority without prose output."""
    index = index or LedgerIndex.read()
    effective: list[dict] = []
    conflicts: list[dict] = []
    orphans: list[dict] = []
    reconciled: dict[str, dict] = {}
    note_ids: set[str] = set()

    for entry in entries:
        feedback_id = entry["id"]
        note_ids.add(feedback_id)
        origins = index.origins_for(feedback_id)
        if not origins:
            # Explicit fb-* IDs are created by the ledger-backed writer. Older
            # curated/manual notes remain readable but intentionally unverified.
            if feedback_id.startswith("fb-"):
                _add_diagnostic(
                    orphans,
                    _diagnostic(feedback_id, "note_event_orphan", "origin"),
                )
            item = dict(entry)
            item["_authority_reconciled"] = True
            item["_integrity"] = "unverified"
            effective.append(item)
            continue
        if len(origins) != 1:
            _add_diagnostic(
                conflicts,
                _diagnostic(feedback_id, "origin_event_ambiguous", "origin"),
            )
            # No arbitrary ledger event may win an ambiguous authority join.
            continue

        origin = origins[0]
        item_conflicts: list[dict] = []
        claims = {
            "kind": entry.get("kind"),
            "author": entry.get("author"),
            "signal": entry.get("signal"),
            "source": entry.get("source"),
            "feature": entry.get("feature"),
            "impact": entry.get("impact"),
            "outcome": entry.get("outcome"),
            "invocation_id": entry.get("invocation_id"),
            "session": entry.get("session"),
            "tags": tuple(entry.get("tags") or ()),
        }
        authoritative_claims = {
            "kind": origin.kind,
            "author": origin.author,
            "signal": origin.signal,
            "source": origin.source,
            "feature": origin.feature,
            "impact": origin.impact,
            "outcome": origin.outcome,
            "invocation_id": origin.invocation_id,
            "session": origin.session,
            "tags": origin.tags,
        }
        legacy_session_pending = bool(
            origin.session and not origin.session.startswith("hmac-sha256:")
        )
        for field, expected in authoritative_claims.items():
            if field == "session" and legacy_session_pending:
                continue
            if claims[field] != expected:
                _add_diagnostic(
                    item_conflicts,
                    _diagnostic(feedback_id, "note_metadata_integrity_conflict", field),
                )

        body_sha256 = entry.get("note_sha256") or _body_sha256(entry.get("text", ""))
        if origin.body_sha256 is not None:
            body_matches = body_sha256 == origin.body_sha256
        else:
            body_matches = origin.note_sha256 in {
                body_sha256,
                entry.get("_legacy_note_sha256"),
            }
        if not body_matches:
            _add_diagnostic(
                item_conflicts,
                _diagnostic(feedback_id, "note_body_integrity_conflict", "body"),
            )

        if (
            origin.entry_sha256 is not None
            and entry.get("entry_sha256") != origin.entry_sha256
            and not item_conflicts
            and not legacy_session_pending
        ):
            _add_diagnostic(
                item_conflicts,
                _diagnostic(feedback_id, "note_metadata_integrity_conflict", "record"),
            )

        disposition = index.dispositions.get(feedback_id)
        projection = entry.get("_status_projection") or {}
        if disposition is not None:
            if projection.get("status") != disposition.status:
                _add_diagnostic(
                    item_conflicts,
                    _diagnostic(feedback_id, "status_integrity_conflict", "status"),
                )
            rationale = projection.get("note")
            rationale_sha256 = (
                hashlib.sha256(rationale.encode()).hexdigest()
                if isinstance(rationale, str)
                else None
            )
            if rationale_sha256 != disposition.rationale_sha256:
                _add_diagnostic(
                    item_conflicts,
                    _diagnostic(feedback_id, "status_integrity_conflict", "rationale"),
                )
            if _canonical_json(projection.get("links") or {}) != disposition.links_json:
                _add_diagnostic(
                    item_conflicts,
                    _diagnostic(feedback_id, "status_integrity_conflict", "links"),
                )
        elif any(key in projection for key in ("status", "note", "links")):
            field = next(
                key for key in ("status", "note", "links") if key in projection
            )
            _add_diagnostic(
                item_conflicts,
                _diagnostic(
                    feedback_id,
                    "status_integrity_conflict",
                    "rationale" if field == "note" else field,
                ),
            )

        review = index.reviews.get(feedback_id)
        current_findings = _text_privacy_findings(entry.get("text", ""))
        review_valid = bool(
            review is not None
            and origin.entry_sha256 is not None
            and review.entry_sha256 == origin.entry_sha256
            and review.findings_sha256 == _privacy_findings_sha256(current_findings)
            and review.scanner_version == QUALITATIVE_PRIVACY_SCANNER_VERSION
        )
        if entry.get("_privacy_header_claim") and not review_valid:
            _add_diagnostic(
                item_conflicts,
                _diagnostic(feedback_id, "unbacked_review_claim", "privacy_reviewed"),
            )
        if (
            projection.get("privacy_review") is not None
            or projection.get("privacy_reviewed") is True
        ) and not review_valid:
            _add_diagnostic(
                item_conflicts,
                _diagnostic(feedback_id, "unbacked_review_claim", "privacy_review"),
            )

        for diagnostic in item_conflicts:
            _add_diagnostic(conflicts, diagnostic)

        item = dict(entry)
        item.update(
            {
                "kind": origin.kind,
                "author": origin.author or "unknown",
                "signal": origin.signal,
                "source": origin.source,
                "feature": origin.feature,
                "impact": origin.impact,
                "outcome": origin.outcome,
                "invocation_id": origin.invocation_id,
                "session": origin.session,
                "tags": list(origin.tags),
                "status": disposition.status
                if disposition is not None
                else _default_status(origin.kind),
                "resolution": None,
                "links": {},
                "updated": None,
                "privacy_reviewed": review_valid,
                "privacy_review": None,
                "entry_sha256": origin.entry_sha256 or entry.get("entry_sha256"),
                "note_sha256": origin.note_sha256,
                "_actor_type": origin.actor_type,
                "_authority_reconciled": True,
                "_integrity": "conflict" if item_conflicts else "verified",
            }
        )
        effective.append(item)
        reconciled[feedback_id] = {
            "note_sha256": origin.note_sha256,
            "body_sha256": body_sha256,
            "entry_sha256": origin.entry_sha256,
            "canonicalization": "body-v1",
        }

    if include_event_orphans:
        for feedback_id in index.observations:
            if feedback_id not in note_ids:
                _add_diagnostic(
                    orphans,
                    _diagnostic(feedback_id, "event_note_orphan", "note"),
                )

    return effective, conflicts, orphans, reconciled


def authoritative_entries(entries: list[dict]) -> list[dict]:
    reconciled, _, _, _ = _reconcile_entries(entries)
    return reconciled


def metadata_view(entry: dict, authority: dict | None = None) -> MetadataView:
    """Project an internal parsed entry onto the body-free public contract."""
    authority = authority or {}
    source = authority.get("source", entry.get("source"))
    payload = authority.get("payload") or {}
    signal = payload.get("signal") or entry.get("signal") or "mixed"
    actor_type = entry.get("_actor_type") or (authority.get("actor") or {}).get("type")
    actor_type = actor_type or _actor_type_for_source(source)
    review_state = "reviewed" if entry.get("privacy_reviewed") else "unreviewed"
    source_summary = " · ".join(
        (
            f"source-class={source or 'unknown'}",
            f"signal={signal}",
            f"actor-type={actor_type}",
            f"review-state={review_state}",
        )
    )
    return MetadataView(
        id=entry["id"],
        skill=entry["skill"],
        date=entry["date"],
        time=entry["time"],
        kind=entry["kind"],
        status=entry["status"],
        feature=entry.get("feature"),
        source_summary=source_summary,
        integrity=entry.get("_integrity", "unverified"),
        author=entry.get("author", "unknown"),
        session=entry.get("session"),
        invocation_id=entry.get("invocation_id"),
        signal=signal,
        source=source,
        impact=entry.get("impact"),
        outcome=entry.get("outcome"),
        privacy_reviewed=bool(entry.get("privacy_reviewed")),
        updated=entry.get("updated"),
        delivery=entry["delivery"],
        delivery_conflict=bool(entry.get("delivery_conflict")),
        entry_sha256=entry["entry_sha256"],
        note_sha256=entry["note_sha256"],
    )


def metadata_views(entries: list[dict]) -> list[dict]:
    """Serialize entries without retaining a path to body-bearing values."""
    if not all(entry.get("_authority_reconciled") for entry in entries):
        entries, _, _, _ = _reconcile_entries(entries)
    return [metadata_view(entry).to_dict() for entry in entries]


_BODY_HANDLE_LOCATORS: dict[BodyHandle, tuple[str, dict[str, str]]] = {}
_PATH_ENV_KEYS = (
    "HOME",
    "SKI_REGISTRY",
    "SKILLS_HOME",
    "SKI_CLAUDE_SKILLS",
    "SKI_AGENTS_SKILLS",
    "SKI_CODEX_SKILLS",
    "CODEX_HOME",
    "SKILL_FEEDBACK_HOME",
    "XDG_STATE_HOME",
    "LOCALAPPDATA",
)


def _environment_path(value: str, environment: dict[str, str]) -> Path:
    if value == "~":
        return Path(environment.get("HOME", str(Path.home())))
    if value.startswith("~/"):
        return Path(environment.get("HOME", str(Path.home()))) / value[2:]
    return Path(value)


def _feedback_home_for_environment(environment: dict[str, str]) -> Path:
    explicit = environment.get("SKILL_FEEDBACK_HOME")
    if explicit:
        return _environment_path(explicit, environment)
    home = Path(environment.get("HOME", str(Path.home())))
    legacy = home / "Skills" / "exported-data" / "skill-feedback"
    if legacy.exists():
        return legacy
    state = Path(environment.get("XDG_STATE_HOME", home / ".local" / "state"))
    return state / "skill-feedback"


def _body_directories(skill: str, environment: dict[str, str]) -> list[Path]:
    """Resolve candidate stores using only path-related environment values."""
    directories: list[Path] = []

    def add(path: Path) -> None:
        if path not in directories:
            directories.append(path)

    skills_home = _environment_path(
        environment.get("SKILLS_HOME", "~/Skills"), environment
    )
    if skills_home.is_dir():
        try:
            repositories = sorted(
                path for path in skills_home.iterdir() if path.is_dir()
            )
        except OSError:
            repositories = []
        for repo in repositories:
            if _declared_name(repo) == skill:
                add(_resolve_feedback_root(repo))

    registry_value = environment.get("SKI_REGISTRY")
    if registry_value:
        registry = _environment_path(registry_value, environment)
        try:
            manifests = sorted(registry.glob("*.toml")) if registry.is_dir() else []
        except OSError:
            manifests = []
        for manifest_path in manifests:
            try:
                manifest = tomllib.loads(manifest_path.read_text())
            except (OSError, tomllib.TOMLDecodeError):
                continue
            if manifest.get("name", manifest_path.stem) != skill:
                continue
            raw = manifest.get("skill_dir") or manifest.get("claude_skill_dir")
            if raw:
                source = _environment_path(str(raw), environment)
                if not source.is_absolute():
                    source = (manifest_path.parent / source).resolve()
                add(_resolve_feedback_root(_repo_root(source)))

    home = Path(environment.get("HOME", str(Path.home())))
    installed_roots = (
        environment.get("SKI_CLAUDE_SKILLS", str(home / ".claude" / "skills")),
        environment.get("SKI_AGENTS_SKILLS", str(home / ".agents" / "skills")),
        environment.get(
            "SKI_CODEX_SKILLS",
            str(Path(environment.get("CODEX_HOME", home / ".codex")) / "skills"),
        ),
    )
    for raw_root in installed_roots:
        candidate = _environment_path(str(raw_root), environment) / skill
        if candidate.exists():
            add(_resolve_feedback_root(candidate.resolve()))

    add(
        _feedback_home_for_environment(environment)
        / "note-outbox"
        / skill
        / "docs"
        / "feedback"
    )
    return directories


def _body_record(
    skill: str, feedback_id: str, environment: dict[str, str]
) -> tuple[str, str]:
    matches: list[tuple[str, str]] = []
    for directory in _body_directories(skill, environment):
        if not directory.is_dir():
            continue
        try:
            paths = sorted(directory.glob("*.md"))
        except OSError:
            continue
        for path in paths:
            try:
                text = path.read_text()
            except OSError as exc:
                raise FeedbackError(
                    f"cannot read feedback note for {feedback_id}"
                ) from exc
            for match in re.finditer(
                r"(?ms)^### (?P<header>[^\n]+)\n\n(?P<body>.*?)(?=^### |\Z)",
                text,
            ):
                header = match.group("header")
                body = match.group("body").strip()
                metadata = {
                    key: value
                    for part in (piece.strip() for piece in header.split("·")[3:])
                    if "=" in part
                    for key, value in [part.split("=", 1)]
                }
                if metadata.get("id") == feedback_id:
                    matches.append((body, _entry_sha256(header, body)))
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        raise FeedbackError(
            f"body handle requires exactly one immutable entry for {feedback_id!r}"
        )
    return unique[0]


def body_handle_for(
    *,
    skill: str,
    feedback_id: str,
    environment: dict[str, str] | None = None,
) -> BodyHandle:
    """Create an opaque handle without retaining body bytes in the handle."""
    _validate_skill_name(skill)
    environment = dict(os.environ if environment is None else environment)
    _, entry_sha256 = _body_record(skill, feedback_id, environment)
    handle = BodyHandle(feedback_id=feedback_id, entry_sha256=entry_sha256)
    safe_environment = {
        key: environment[key] for key in _PATH_ENV_KEYS if key in environment
    }
    _BODY_HANDLE_LOCATORS[handle] = (skill, safe_environment)
    return handle


def inspect_body(handle: BodyHandle, *, provider=None):
    """Redeem a handle exactly once through an injected isolation provider."""
    if provider is None or not callable(getattr(provider, "inspect", None)):
        raise BodyInspectionUnavailable(
            "body inspection is unavailable without an isolation provider"
        )
    locator = _BODY_HANDLE_LOCATORS.pop(handle, None)
    if locator is None:
        raise BodyInspectionUnavailable("body handle is unknown or already redeemed")
    skill, environment = locator
    body, entry_sha256 = _body_record(skill, handle.feedback_id, environment)
    if entry_sha256 != handle.entry_sha256:
        raise FeedbackError("body changed after the handle was issued")

    fd, raw_path = tempfile.mkstemp(prefix="skill-feedback-body-", suffix=".txt")
    scoped_path = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        scoped_path.chmod(0o400)
        request = BodyInspectionRequest(
            body_handle=handle,
            scoped_inputs=(
                ScopedBodyInput(feedback_id=handle.feedback_id, path=str(scoped_path)),
            ),
        )
        inspection = provider.inspect(request)
    finally:
        scoped_path.unlink(missing_ok=True)

    if getattr(inspection, "untrusted", None) is not True:
        raise FeedbackError("isolation provider did not mark body output untrusted")
    for field in ("authorization", "capability", "receipt", "token"):
        if getattr(inspection, field, None) is not None:
            raise FeedbackError("isolation provider returned mutation authority")
    return inspection


def _iter_feedback_files(name: str) -> list[Path]:
    files: list[Path] = []
    try:
        d = feedback_dir(name)
    except FeedbackError:
        d = None
    if d is not None and d.is_dir():
        files.extend(d.glob("*.md"))
    outbox = _note_outbox_dir(name)
    if outbox.is_dir():
        files.extend(outbox.glob("*.md"))
    return sorted(set(files))


def _delivery_states(name: str) -> dict[str, dict]:
    try:
        path = feedback_dir(name) / ".delivery.json"
    except FeedbackError:
        return {}
    return _read_delivery_sidecar(path)


def _curated_entry(
    name: str,
    path: Path,
    text: str,
    statuses: dict[str, dict],
    pending: bool,
) -> dict:
    explicit_ids = re.findall(
        r"(?mi)^\s*<!--\s*feedback-id\s*:\s*(.*?)\s*-->\s*$",
        text,
    )
    if len(explicit_ids) > 1:
        raise FeedbackError(
            f"curated feedback {path} has multiple explicit feedback IDs"
        )
    if explicit_ids and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", explicit_ids[0]
    ):
        raise FeedbackError(
            f"curated feedback {path} has an invalid explicit feedback ID"
        )
    body = re.sub(r"(?m)^# [^\n]+\n+", "", text, count=1)
    body = re.sub(r"(?ms)<!--.*?-->", "", body).strip()
    digest = hashlib.sha256(f"{path.name}:{body}".encode()).hexdigest()[:8]
    feedback_id = (
        explicit_ids[0]
        if explicit_ids
        else f"{path.stem.replace('-', '')}-curated-{digest}"
    )
    disposition = statuses.get(feedback_id, {})
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    privacy_review = disposition.get("privacy_review")
    privacy_reviewed = _stored_privacy_review_matches(
        disposition,
        entry_sha256=body_hash,
        findings=_text_privacy_findings(body),
    )
    return {
        "id": feedback_id,
        "skill": name,
        "date": path.stem,
        "time": "",
        "kind": "curated",
        "author": "unknown",
        "session": None,
        "tags": [],
        "feature": None,
        "invocation_id": None,
        "signal": "mixed",
        "source": None,
        "impact": "unknown",
        "outcome": "unknown",
        "status": disposition.get("status", "open"),
        "resolution": disposition.get("note"),
        "privacy_reviewed": privacy_reviewed,
        "privacy_review": privacy_review,
        "resolution_privacy_reviewed": disposition.get("privacy_reviewed", False),
        "links": disposition.get("links", {}),
        "updated": disposition.get("updated"),
        "text": body,
        "file": str(path),
        "entry_sha256": body_hash,
        "note_sha256": body_hash,
        "delivery": "pending" if pending else "source",
        "delivery_conflict": False,
        "_status_projection": disposition,
        "_privacy_header_claim": False,
        "_legacy_note_sha256": body_hash,
    }


def _parse_entries_unlocked(name: str) -> list[dict]:
    files = _iter_feedback_files(name)
    if not files:
        return []
    statuses_by_directory = {
        path.parent: _read_object_sidecar(
            path.parent / ".status.json", "feedback status"
        )
        for path in files
    }
    delivery_states = _delivery_states(name)
    entries: list[dict] = []
    for path in files:
        try:
            text = path.read_text()
        except OSError as exc:
            raise FeedbackError(f"cannot read feedback note {path}: {exc}") from exc
        statuses = statuses_by_directory[path.parent]
        pending = path.parent == _note_outbox_dir(name)
        matches = list(
            re.finditer(
                r"(?ms)^### (?P<header>[^\n]+)\n\n(?P<body>.*?)(?=^### |\Z)",
                text,
            )
        )
        if not matches:
            if _empty_managed_note_file(text):
                continue
            entries.append(_curated_entry(name, path, text, statuses, pending))
            continue
        unmanaged = _without_matches(text, matches)
        if not _empty_managed_note_file(unmanaged):
            entries.append(_curated_entry(name, path, unmanaged, statuses, pending))
        for index, match in enumerate(matches, start=1):
            header = match.group("header")
            raw_body = match.group("body")
            raw_note = raw_body[:-2] if raw_body.endswith("\n\n") else raw_body
            body = raw_body.strip()
            parts = [part.strip() for part in header.split("·")]
            metadata = {
                key: value
                for part in parts[3:]
                if "=" in part
                for key, value in [part.split("=", 1)]
            }
            feedback_id = metadata.get("id")
            if not feedback_id:
                digest = hashlib.sha256(
                    f"{path.name}:{index}:{header}:{body}".encode()
                ).hexdigest()[:8]
                feedback_id = f"{path.stem.replace('-', '')}-{index:03d}-{digest}"
            disposition = statuses.get(feedback_id, {})
            kind = parts[1] if len(parts) > 1 else "unknown"
            status = disposition.get("status", "open")
            if not disposition and kind == "praise":
                status = "observed"
            entry_hash = _entry_sha256(header, body)
            privacy_review = disposition.get("privacy_review")
            privacy_reviewed = metadata.get(
                "privacy-reviewed"
            ) == "true" or _stored_privacy_review_matches(
                disposition,
                entry_sha256=entry_hash,
                findings=_text_privacy_findings(body),
            )
            delivery = "pending" if pending else "source"
            delivery_conflict = False
            if not pending and feedback_id in delivery_states:
                state = delivery_states[feedback_id]
                if state.get("entry_sha256") == entry_hash:
                    delivery = "delivered"
                else:
                    delivery_conflict = True
            entries.append(
                {
                    "id": feedback_id,
                    "skill": name,
                    "date": path.stem,
                    "time": parts[0] if parts else "",
                    "kind": kind,
                    "author": parts[2] if len(parts) > 2 else "unknown",
                    "session": metadata.get("session"),
                    "tags": [tag for tag in metadata.get("tags", "").split(",") if tag],
                    "feature": metadata.get("feature"),
                    "invocation_id": metadata.get("invocation"),
                    "signal": metadata.get("signal") or _default_signal(kind),
                    "source": metadata.get("source"),
                    "impact": metadata.get("impact"),
                    "outcome": metadata.get("outcome"),
                    "status": status,
                    "resolution": disposition.get("note"),
                    "privacy_reviewed": privacy_reviewed,
                    "privacy_review": privacy_review,
                    "resolution_privacy_reviewed": disposition.get(
                        "privacy_reviewed", False
                    ),
                    "links": disposition.get("links", {}),
                    "updated": disposition.get("updated"),
                    "text": body,
                    "file": str(path),
                    "entry_sha256": entry_hash,
                    "note_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "delivery": delivery,
                    "delivery_conflict": delivery_conflict,
                    "_status_projection": disposition,
                    "_privacy_header_claim": metadata.get("privacy-reviewed") == "true",
                    "_legacy_note_sha256": hashlib.sha256(
                        raw_note.encode()
                    ).hexdigest(),
                }
            )
    by_id: dict[str, list[dict]] = {}
    for entry in entries:
        by_id.setdefault(entry["id"], []).append(entry)

    result: list[dict] = []
    for duplicates in by_id.values():
        if len(duplicates) == 1:
            result.extend(duplicates)
            continue
        fingerprints = {
            (
                entry["entry_sha256"],
                entry["status"],
                entry["resolution"],
                entry["resolution_privacy_reviewed"],
                json.dumps(entry["privacy_review"], sort_keys=True),
                json.dumps(entry["links"], sort_keys=True),
                entry["updated"],
            )
            for entry in duplicates
        }
        if len(fingerprints) == 1:
            # A retry can persist the destination before pruning the outbox.
            # Prefer the canonical copy, but only when the immutable record and
            # disposition are exact matches.
            chosen = max(
                duplicates,
                key=lambda entry: DELIVERY_STATES.index(entry["delivery"]),
            )
            if chosen["delivery"] != "delivered" and any(
                entry["delivery"] == "pending" for entry in duplicates
            ):
                chosen["delivery"] = "pending"
            result.append(chosen)
            continue
        for entry in duplicates:
            entry["delivery_conflict"] = True
        result.extend(duplicates)
    return result


def _parse_entries(name: str) -> list[dict]:
    lock = _notes_lock_path()
    if not lock.exists():
        return _parse_entries_unlocked(name)
    with _file_lock(lock, shared=True, private=True):
        return _parse_entries_unlocked(name)


def _delivery_plan_for_skill(name: str) -> tuple[dict, dict]:
    outbox = _note_outbox_dir(name)
    destination = feedback_dir(name)
    outbox_records, outbox_contents, unmanaged_outbox = _managed_note_records(outbox)
    source_records, source_contents, unmanaged_source = _managed_note_records(
        destination
    )
    outbox_status_path = outbox / ".status.json"
    source_status_path = destination / ".status.json"
    delivery_path = destination / ".delivery.json"
    outbox_statuses = _read_object_sidecar(outbox_status_path, "feedback status")
    source_statuses = _read_object_sidecar(source_status_path, "feedback status")
    delivery_states = _read_delivery_sidecar(delivery_path)

    conflicts: list[str] = []
    conflicts.extend(f"unmanaged outbox record: {item}" for item in unmanaged_outbox)
    duplicate_outbox = {
        feedback_id: items
        for feedback_id, items in outbox_records.items()
        if len(items) != 1
    }
    for feedback_id in duplicate_outbox:
        conflicts.append(f"{feedback_id}: duplicate id in outbox")
    duplicate_source = {
        feedback_id: items
        for feedback_id, items in source_records.items()
        if len(items) != 1
    }
    for feedback_id in duplicate_source:
        conflicts.append(f"{feedback_id}: duplicate id in canonical source")

    entries = []
    for feedback_id, outbox_items in sorted(outbox_records.items()):
        if len(outbox_items) != 1:
            continue
        record = outbox_items[0]
        existing_items = source_records.get(feedback_id, [])
        note_action = "copy"
        if existing_items:
            if len(existing_items) != 1:
                continue
            existing = existing_items[0]
            if (
                existing["entry_sha256"] != record["entry_sha256"]
                or existing["filename"] != record["filename"]
            ):
                conflicts.append(
                    f"{feedback_id}: canonical source contains a different record"
                )
                continue
            note_action = "already_present"
        target_path = destination / record["filename"]
        if note_action == "copy" and target_path.exists():
            target_text = source_contents.get(target_path, "")
            if not _empty_managed_note_file(target_text) and not source_records:
                conflicts.append(
                    f"{feedback_id}: destination file is not managed feedback format"
                )
                continue
            if str(target_path) in unmanaged_source:
                conflicts.append(
                    f"{feedback_id}: destination file contains unmanaged feedback"
                )
                continue

        pending_status = outbox_statuses.get(feedback_id)
        canonical_status = source_statuses.get(feedback_id)
        if (
            pending_status is not None
            and canonical_status is not None
            and pending_status != canonical_status
        ):
            conflicts.append(f"{feedback_id}: disposition differs at destination")
            continue
        status_action = (
            "copy"
            if pending_status is not None and canonical_status is None
            else "unchanged"
        )

        expected_state = {
            "from": f"note-outbox/{name}/docs/feedback/{record['filename']}",
            "to": f"docs/feedback/{record['filename']}",
            "entry_sha256": record["entry_sha256"],
            "note_sha256": record["note_sha256"],
        }
        existing_state = delivery_states.get(feedback_id)
        if existing_state is not None and any(
            existing_state.get(key) != value for key, value in expected_state.items()
        ):
            conflicts.append(f"{feedback_id}: delivery state differs from record")
            continue
        entries.append(
            {
                "id": feedback_id,
                "filename": record["filename"],
                "entry_sha256": record["entry_sha256"],
                "note_sha256": record["note_sha256"],
                "note_action": note_action,
                "status_action": status_action,
                "delivery_action": (
                    "unchanged" if existing_state is not None else "record"
                ),
            }
        )

    ready = not conflicts and (not entries or _path_is_writable(destination))
    blocked_reason = None
    if entries and not _path_is_writable(destination):
        blocked_reason = f"canonical feedback directory is not writable: {destination}"
    public = {
        "skill": name,
        "source": str(destination),
        "outbox": str(outbox),
        "pending": len(outbox_records),
        "ready": ready,
        "blocked_reason": blocked_reason,
        "conflicts": conflicts,
        "entries": entries,
    }
    transaction = {
        "destination": destination,
        "outbox": outbox,
        "outbox_records": outbox_records,
        "source_records": source_records,
        "outbox_contents": outbox_contents,
        "source_contents": source_contents,
        "outbox_status_path": outbox_status_path,
        "source_status_path": source_status_path,
        "delivery_path": delivery_path,
        "outbox_statuses": outbox_statuses,
        "source_statuses": source_statuses,
        "delivery_states": delivery_states,
    }
    return public, transaction


def _env_feedback_home(environment: dict[str, str]) -> Path:
    return _feedback_home_for_environment(environment)


def _env_records(directory: Path, feedback_id: str) -> list[dict]:
    records, _, _ = _managed_note_records(directory)
    return records.get(feedback_id, [])


def _locate_record(
    skill: str, feedback_id: str, environment: dict[str, str]
) -> dict | None:
    """Locate the pending note by scanning the actual write-target directories
    (mirrors the AC-3-green `_body_record` locator), preferring the outbox. The
    delivery source MUST resolve to the outbox record, never to an already-promoted
    destination copy (else recovery would prune the wrong file)."""
    outbox = (
        _feedback_home_for_environment(environment)
        / "note-outbox"
        / skill
        / "docs"
        / "feedback"
    )
    ordered = [outbox] + [
        directory
        for directory in _body_directories(skill, environment)
        if directory != outbox
    ]
    for directory in ordered:
        if not directory.is_dir():
            continue
        try:
            paths = sorted(directory.glob("*.md"))
        except OSError:
            continue
        for path in paths:
            try:
                text = path.read_text()
            except OSError:
                continue
            for match in re.finditer(
                r"(?ms)^### (?P<header>[^\n]+)\n\n(?P<body>.*?)(?=^### |\Z)",
                text,
            ):
                header = match.group("header")
                body = match.group("body").strip()
                parts = [piece.strip() for piece in header.split("·")]
                metadata = {
                    key: value
                    for part in parts[3:]
                    if "=" in part
                    for key, value in [part.split("=", 1)]
                }
                if metadata.get("id") == feedback_id:
                    return {
                        "path": path,
                        "filename": path.name,
                        "header": header,
                        "body": body,
                        "block": f"### {header}\n\n{body}\n\n",
                        "start": match.start(),
                        "end": match.end(),
                        "text": text,
                        "entry_sha256": _entry_sha256(header, body),
                    }
    return None


def authorize_delivery(
    *,
    skill: str,
    feedback_id: str,
    environment: dict[str, str] | None = None,
) -> PromotionAuthorization:
    """Authenticate one outbox record against its immutable origin event (R6).

    Fails closed (raises ``DeliveryBlocked`` with a typed, content-free
    diagnostic) unless: exactly one origin event names the record; the body-v1
    digest and every header provenance field equal the event authority (new
    records also the canonical ``entry_sha256``); status/review projections
    reconcile; and the *current* privacy scanner approves the exact candidate
    bytes (review findings require a capability-backed acknowledgement). The
    returned authorization pins the exact source bytes and the ledger head so
    ``storage.apply_delivery`` can re-close the TOCTOU window at promotion.
    """
    _validate_skill_name(skill)
    environment = dict(os.environ if environment is None else environment)
    feedback_home = _env_feedback_home(environment)
    ledger_path = feedback_home / "events.jsonl"
    event_lock = feedback_home / ".events.lock"
    notes_lock = feedback_home / ".notes.lock"
    outbox_dir = feedback_home / "note-outbox" / skill / "docs" / "feedback"
    outbox_status_path = outbox_dir / ".status.json"
    directories = _body_directories(skill, environment)
    destination = directories[0] if directories else outbox_dir
    destination_status_path = destination / ".status.json"
    delivery_path = destination / ".delivery.json"

    with _file_lock(event_lock, shared=True, private=True):
        events = EventLedger(ledger_path)._read_unlocked()
    index = LedgerIndex.from_events(events)
    origins = index.origins_for(feedback_id)
    if not origins:
        raise DeliveryBlocked(feedback_id, "note_event_orphan", "event")
    if len(origins) > 1:
        raise DeliveryBlocked(feedback_id, "origin_event_ambiguous", "event")
    origin = origins[0]

    record = _locate_record(skill, feedback_id, environment)
    if record is None:
        raise DeliveryBlocked(feedback_id, "note_event_orphan", "source")
    body = record["body"]
    header = record["header"]
    entry_sha256 = _entry_sha256(header, body)

    # Body digest vs origin authority (never trust on-disk hashes as proof).
    if origin.body_sha256 is not None:
        if hashlib.sha256(_body_v1(body).encode()).hexdigest() != origin.body_sha256:
            raise DeliveryBlocked(feedback_id, "delivery_origin_conflict", "body")
    else:
        # Legacy origin attributes the whole-note hash; accept only when the
        # parsed body is byte-identical to that note.
        if hashlib.sha256(body.encode()).hexdigest() != origin.note_sha256:
            raise DeliveryBlocked(feedback_id, "delivery_origin_conflict", "body")
    if origin.entry_sha256 and entry_sha256 != origin.entry_sha256:
        raise DeliveryBlocked(feedback_id, "delivery_origin_conflict", "metadata")

    # Header provenance fields must equal the event authority.
    parts = [piece.strip() for piece in header.split("·")]
    metadata = {
        key: value
        for part in parts[3:]
        if "=" in part
        for key, value in [part.split("=", 1)]
    }
    kind = parts[1] if len(parts) > 1 else "unknown"
    author = parts[2] if len(parts) > 2 else "unknown"
    claims = (
        ("kind", kind, origin.kind),
        ("author", author, origin.author),
        ("source", metadata.get("source"), origin.source),
        ("signal", metadata.get("signal") or _default_signal(kind), origin.signal),
        ("impact", metadata.get("impact"), origin.impact),
        ("outcome", metadata.get("outcome"), origin.outcome),
        ("feature", metadata.get("feature"), origin.feature),
    )
    for field, claimed, expected in claims:
        if claimed != expected:
            raise DeliveryBlocked(feedback_id, "delivery_origin_conflict", field)

    # Status/review sidecars reconcile to authority (display-only caches).
    outbox_statuses = _read_object_sidecar(outbox_status_path, "feedback status")
    pending_status = outbox_statuses.get(feedback_id)
    if pending_status is not None:
        disposition = index.dispositions.get(feedback_id)
        if disposition is not None:
            if pending_status.get("status") != disposition.status:
                raise DeliveryBlocked(feedback_id, "delivery_origin_conflict", "status")
            rationale_sha = hashlib.sha256(
                str(pending_status.get("note") or "").encode()
            ).hexdigest()
            if (
                pending_status.get("note")
                and disposition.rationale_sha256
                and rationale_sha != disposition.rationale_sha256
            ):
                raise DeliveryBlocked(
                    feedback_id, "delivery_origin_conflict", "rationale"
                )

    # Current privacy scanner on the exact candidate bytes (R6: re-screen).
    findings = _text_privacy_findings(body)
    findings_sha = _privacy_findings_sha256(findings)
    blocked = any(item["severity"] == "block" for item in findings)
    review = [item for item in findings if item["severity"] == "review"]
    review_required = bool(review)
    if blocked:
        raise DeliveryBlocked(feedback_id, "privacy_block", "privacy")
    if review_required:
        authority = index.reviews.get(feedback_id)
        if not (
            authority is not None
            and authority.entry_sha256 == entry_sha256
            and authority.findings_sha256 == findings_sha
            and authority.scanner_version == QUALITATIVE_PRIVACY_SCANNER_VERSION
        ):
            raise DeliveryBlocked(feedback_id, "privacy_review_required", "privacy")

    # Destination presence decides copy vs already-present; a differing record
    # is a conflict (fails closed, never overwrites).
    note_action = "copy"
    existing = _env_records(destination, feedback_id)
    if existing:
        if len(existing) != 1 or existing[0]["entry_sha256"] != entry_sha256:
            raise DeliveryBlocked(
                feedback_id, "delivery_origin_conflict", "destination"
            )
        note_action = "already_present"

    destination_statuses = _read_object_sidecar(
        destination_status_path, "feedback status"
    )
    status_action = (
        "copy"
        if pending_status is not None
        and destination_statuses.get(feedback_id) != pending_status
        else "unchanged"
    )

    source_path = record["path"]
    source_original = record["text"]
    source_sha256 = hashlib.sha256(source_original.encode()).hexdigest()
    ledger_head = (
        ""
        if not ledger_path.is_file()
        else hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    )
    return PromotionAuthorization(
        feedback_id=feedback_id,
        skill=skill,
        filename=record["filename"],
        source_path=str(source_path),
        destination_dir=str(destination),
        outbox_status_path=str(outbox_status_path),
        destination_status_path=str(destination_status_path),
        delivery_path=str(delivery_path),
        source_original=source_original,
        source_sha256=source_sha256,
        ledger_head=ledger_head,
        ledger_path=str(ledger_path),
        notes_lock_path=str(notes_lock),
        block=record["block"],
        entry_sha256=entry_sha256,
        note_sha256=hashlib.sha256(body.encode()).hexdigest(),
        origin_event_id=origin.event_id,
        privacy_scanner_version=QUALITATIVE_PRIVACY_SCANNER_VERSION,
        privacy_review_required=review_required,
        note_action=note_action,
        status_action=status_action,
        start=record["start"],
        end=record["end"],
        pending_status=pending_status,
    )


def _inspect_event_ledger() -> tuple[list[dict], list[str]]:
    path = _event_path()
    if not path.exists():
        return [], []
    with _file_lock(_event_lock_path(), shared=True, private=True):
        try:
            lines = path.read_text().splitlines()
        except OSError as exc:
            return [], [f"cannot read event ledger: {exc}"]
    events = []
    errors = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            _validate_event(event)
        except (json.JSONDecodeError, FeedbackError) as exc:
            errors.append(f"line {line_number}: {exc}")
            continue
        events.append(event)
    return events, errors


def _inspect_note_storage() -> dict:
    try:
        index = LedgerIndex.read()
        index_error = None
    except (FeedbackError, OSError) as exc:
        index = LedgerIndex.from_events([])
        index_error = str(exc)

    def inspect() -> dict:
        counts = {state: 0 for state in DELIVERY_STATES}
        conflicts = 0
        errors: dict[str, str] = {}
        if index_error is not None:
            errors["ledger"] = index_error
        orphan_delivery_states: dict[str, list[str]] = {}
        delivery_state_conflicts: dict[str, list[str]] = {}
        all_entries: list[dict] = []
        for skill in known_skills():
            try:
                entries = _parse_entries_unlocked(skill)
                all_entries.extend(entries)
                for entry in entries:
                    counts[entry["delivery"]] += 1
                    conflicts += int(entry["delivery_conflict"])
                source_entries: dict[str, list[dict]] = {}
                for entry in entries:
                    if entry["delivery"] in {"source", "delivered"}:
                        source_entries.setdefault(entry["id"], []).append(entry)
                states = _delivery_states(skill)
                orphaned = sorted(set(states) - set(source_entries))
                if orphaned:
                    orphan_delivery_states[skill] = orphaned
                invalid = []
                for feedback_id, state in states.items():
                    candidates = source_entries.get(feedback_id, [])
                    if len(candidates) != 1:
                        continue
                    entry = candidates[0]
                    if (
                        state["entry_sha256"] != entry["entry_sha256"]
                        or state["note_sha256"] != entry["note_sha256"]
                        or state["to"] != f"docs/feedback/{Path(entry['file']).name}"
                    ):
                        invalid.append(feedback_id)
                if invalid:
                    delivery_state_conflicts[skill] = sorted(invalid)
            except (FeedbackError, OSError) as exc:
                errors[skill] = str(exc)
        _, integrity_conflicts, orphans, reconciled = _reconcile_entries(
            all_entries,
            index=index,
            include_event_orphans=not errors,
        )
        return {
            "ok": (
                not errors
                and not conflicts
                and not orphan_delivery_states
                and not delivery_state_conflicts
                and not integrity_conflicts
                and not orphans
            ),
            "counts": counts,
            "delivery_conflicts": conflicts,
            "orphan_delivery_states": orphan_delivery_states,
            "delivery_state_conflicts": delivery_state_conflicts,
            "integrity_conflicts": integrity_conflicts,
            "orphans": orphans,
            "reconciled": reconciled,
            "ledger_authoritative": True,
            "errors": errors,
            "outbox_root": str(FEEDBACK_HOME / "note-outbox"),
        }

    lock = _notes_lock_path()
    if not lock.exists():
        return inspect()
    with _file_lock(lock, shared=True, private=True):
        return inspect()


def _inspect_qualitative_privacy(skill: str | None = None) -> dict:
    """Audit parsed observation and disposition prose without returning content."""
    skills = [_validate_skill_name(skill)] if skill else known_skills()
    findings = []
    errors = {}
    entries_scanned = 0
    for name in skills:
        try:
            entries = authoritative_entries(_parse_entries(name))
        except (FeedbackError, OSError) as exc:
            errors[name] = str(exc)
            continue
        entries_scanned += len(entries)
        for entry in entries:
            parts = (
                (
                    "observation",
                    entry.get("text"),
                    bool(entry.get("privacy_reviewed")),
                ),
                (
                    "disposition",
                    entry.get("resolution"),
                    bool(entry.get("resolution_privacy_reviewed")),
                ),
            )
            for part, text, reviewed in parts:
                if not text:
                    continue
                item_findings = _text_privacy_findings(text)
                if not item_findings:
                    continue
                findings.append(
                    {
                        "skill": name,
                        "feedback_id": entry["id"],
                        "note_file": Path(entry["file"]).name,
                        "part": part,
                        "reviewed": reviewed,
                        "findings": item_findings,
                    }
                )
    block_count = sum(
        1
        for item in findings
        for finding in item["findings"]
        if finding["severity"] == "block"
    )
    review_count = sum(
        1
        for item in findings
        for finding in item["findings"]
        if finding["severity"] == "review"
    )
    unreviewed_count = sum(
        1
        for item in findings
        if not item["reviewed"]
        and any(finding["severity"] == "review" for finding in item["findings"])
    )
    return {
        "ok": not errors and block_count == 0 and unreviewed_count == 0,
        "skills_scanned": len(skills),
        "entries_scanned": entries_scanned,
        "finding_groups": len(findings),
        "block_findings": block_count,
        "review_findings": review_count,
        "unreviewed_groups": unreviewed_count,
        "findings": findings,
        "errors": errors,
    }


def _migrate_note_sessions(
    stored_session_id, authoritative_sessions: dict[str, str] | None = None
) -> int:
    changed_files = 0
    seen = set()
    pattern = re.compile(r"(?P<prefix>\s·\ssession=)(?P<value>[^·\n]+)")
    with _file_lock(_notes_lock_path(), private=True):
        for skill in known_skills():
            try:
                target = feedback_dir(skill)
            except FeedbackError:
                continue
            resolved = target.resolve()
            if resolved in seen or not target.is_dir():
                continue
            seen.add(resolved)
            for path in sorted(target.glob("*.md")):
                original = path.read_text()

                def replace(match: re.Match) -> str:
                    captured = match.group("value")
                    value = captured.strip()
                    trailing = captured[len(captured.rstrip()) :]
                    header_start = original.rfind("### ", 0, match.start())
                    header_end = original.find("\n", match.end())
                    header = original[header_start:header_end]
                    id_match = re.search(r"(?:^|\s·\s)id=([^·\n]+)", header)
                    feedback_id = id_match.group(1).strip() if id_match else None
                    stored = (authoritative_sessions or {}).get(feedback_id)
                    stored = stored or stored_session_id(value)
                    return f"{match.group('prefix')}{stored}{trailing}"

                updated = pattern.sub(replace, original)
                if updated != original:
                    _write_text_atomic(path, updated)
                    changed_files += 1
    return changed_files
