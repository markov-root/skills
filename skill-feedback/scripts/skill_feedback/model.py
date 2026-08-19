"""Pure values for metadata-only reads and isolated body inspection."""

from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MetadataView:
    """Body-free public projection for default list and review reads."""

    id: str
    skill: str
    date: str
    time: str
    kind: str
    status: str
    feature: str | None
    source_summary: str
    integrity: str
    author: str
    session: str | None
    invocation_id: str | None
    signal: str
    source: str | None
    impact: str | None
    outcome: str | None
    privacy_reviewed: bool
    updated: str | None
    delivery: str
    delivery_conflict: bool
    entry_sha256: str
    note_sha256: str

    def to_dict(self) -> dict:
        """Return the only supported public serialization shape."""
        return {
            "id": self.id,
            "skill": self.skill,
            "date": self.date,
            "time": self.time,
            "kind": self.kind,
            "status": self.status,
            "feature": self.feature,
            "source-summary": self.source_summary,
            "integrity": self.integrity,
            "author": self.author,
            "session": self.session,
            "invocation_id": self.invocation_id,
            "signal": self.signal,
            "source": self.source,
            "impact": self.impact,
            "outcome": self.outcome,
            "privacy_reviewed": self.privacy_reviewed,
            "updated": self.updated,
            "delivery": self.delivery,
            "delivery_conflict": self.delivery_conflict,
            "entry_sha256": self.entry_sha256,
            "note_sha256": self.note_sha256,
        }


@dataclass(frozen=True)
class BodyHandle:
    """Opaque, non-authorizing reference to one immutable body revision."""

    feedback_id: str
    entry_sha256: str


@dataclass(frozen=True)
class ScopedBodyInput:
    """One read-only body made available to an isolation provider."""

    feedback_id: str
    path: str
    body_count: int = 1
    read_only: bool = True


@dataclass(frozen=True)
class BodyInspectionRequest:
    """Fail-closed request contract for an external isolation provider."""

    body_handle: BodyHandle
    scoped_inputs: tuple[ScopedBodyInput, ...]
    read_only: bool = True
    mutation_dispatcher: None = None
    inherited_credentials: tuple[str, ...] = ()
    inherited_fds: tuple[int, ...] = ()
    writable_paths: tuple[str, ...] = ()
    network_allowed: bool = False


@dataclass(frozen=True)
class PromotionAuthorization:
    """Origin-authenticated, TOCTOU-bound promotion grant (AC-7 / R6).

    ``source_sha256`` and ``ledger_head`` pin the exact bytes and ledger the
    authorization was issued against; ``apply_delivery`` re-reads both under the
    notes lock and refuses to promote changed bytes or a moved ledger head. The
    ``block`` is the exact verified record bytes to append — never re-derived
    from whatever happens to be on disk at apply time.
    """

    feedback_id: str
    skill: str
    filename: str
    source_path: str
    destination_dir: str
    outbox_status_path: str
    destination_status_path: str
    delivery_path: str
    source_original: str
    source_sha256: str
    ledger_head: str
    ledger_path: str
    notes_lock_path: str
    block: str
    entry_sha256: str
    note_sha256: str
    origin_event_id: str
    privacy_scanner_version: int
    privacy_review_required: bool
    note_action: str
    status_action: str
    start: int
    end: int
    pending_status: dict | None


@dataclass(frozen=True)
class ObservationAuthority:
    """Immutable provenance derived from one observation ledger event."""

    feedback_id: str
    skill: str
    kind: str
    author: str | None
    actor_type: str
    signal: str
    source: str
    feature: str | None
    impact: str
    outcome: str
    invocation_id: str | None
    session: str | None
    tags: tuple[str, ...]
    note_sha256: str
    body_sha256: str | None
    entry_sha256: str | None
    canonicalization: str | None
    note_file: str
    delivery: str
    event_id: str


@dataclass(frozen=True)
class DispositionAuthority:
    """Immutable latest disposition derived from the event ledger."""

    feedback_id: str
    status: str
    rationale_sha256: str
    links_json: str
    event_id: str

    @property
    def links(self) -> dict:
        import json

        return json.loads(self.links_json)


@dataclass(frozen=True)
class ReviewAuthority:
    """Immutable privacy-review authority introduced at the AC-6 seam."""

    feedback_id: str
    entry_sha256: str
    findings_sha256: str
    scanner_version: int
    event_id: str


@dataclass(frozen=True)
class PrivacyReviewRequest:
    """Content-free tuple that an operator capability must authorize."""

    skill: str
    feedback_id: str
    entry_sha256: str
    findings_sha256: str
    scanner_version: int


KINDS = ("wish", "friction", "bug", "praise", "idea")

STATUSES = (
    "open",
    "observed",
    "preserve",
    "planned",
    "fix_candidate",
    "resolved",
    "declined",
    "duplicate",
)

# --- C2 (ADR 0018 R1) evidence-bound closure state machine -------------------
# Pure, table-driven transition legality: the structural graph is checked first,
# then the receipt gates. The error strings are the exact stderr substrings the
# CLI must surface on rejection, kept distinct on purpose.
LEGAL_TRANSITIONS = {
    "open": {
        "planned",
        "fix_candidate",
        "resolved",
        "preserve",
        "declined",
        "duplicate",
    },
    "planned": {"fix_candidate"},
    "fix_candidate": {"resolved"},
    "observed": {"preserve"},
    "resolved": {"open"},  # reopen (lifecycle); driven by the reopen command
    "preserve": set(),
    "declined": set(),
    "duplicate": set(),
}

RESOLUTION_RECEIPT_REQUIRED = "resolution receipt required"
VERIFICATION_RECEIPT_REQUIRED = "verification receipt required"
ILLEGAL_TRANSITION = "illegal transition"


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    error: str | None = None


def evaluate_transition(
    current_status: str,
    target_status: str,
    *,
    has_passing_receipt: bool = False,
    has_rationale: bool = True,
    has_duplicate_target: bool = False,
) -> TransitionResult:
    """Table-driven legality for a disposition transition (ADR 0018 R1).

    Pure: no I/O and no ledger access. Returns TransitionResult(allowed, error)
    where error is the exact stderr substring the CLI surfaces on rejection.
    Structural illegality wins over a missing receipt, so planned->resolved is
    'illegal transition' while open/fix_candidate->resolved without a receipt is
    'resolution receipt required'.
    """
    if target_status not in STATUSES:
        return TransitionResult(False, ILLEGAL_TRANSITION)
    if target_status not in LEGAL_TRANSITIONS.get(current_status, set()):
        return TransitionResult(False, ILLEGAL_TRANSITION)
    if target_status == "resolved" and not has_passing_receipt:
        return TransitionResult(False, RESOLUTION_RECEIPT_REQUIRED)
    if target_status == "preserve" and not has_passing_receipt:
        return TransitionResult(False, VERIFICATION_RECEIPT_REQUIRED)
    if target_status == "declined" and not has_rationale:
        return TransitionResult(False, ILLEGAL_TRANSITION)
    if target_status == "duplicate" and not has_duplicate_target:
        return TransitionResult(False, ILLEGAL_TRANSITION)
    return TransitionResult(True, None)


SIGNALS = ("positive", "negative", "mixed")

SOURCES = (
    "explicit_user",
    "observed_user",
    "deterministic",
    "independent_evaluation",
    "agent_judgment",
    "automation",
)

IMPACTS = ("low", "medium", "high", "unknown")

OUTCOMES = ("success", "partial", "failure", "abandoned", "unknown")

DELIVERY_STATES = ("pending", "source", "delivered")

ACTOR_TYPES = ("agent", "user", "automation", "system")

EVENT_TYPES = (
    "invocation.started",
    "invocation.finished",
    "observation.recorded",
    "observation.tombstoned",
    "disposition.changed",
    "verification.recorded",
    "preservation.declared",
    "privacy.review.acknowledged",
)

EVENT_SCHEMA_VERSION = 2

PRIVACY_CONFIG_VERSION = 3

QUALITATIVE_PRIVACY_SCANNER_VERSION = 1

AUTOMATIC_COLLECTION_MODES = ("off", "manifest_opt_in")

WRAPPER_SCHEMA_VERSION = 1

WRAPPER_MARKER = "# skill-feedback-managed-wrapper: v1"

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class FeedbackError(RuntimeError):
    pass


class IntegrityConflict(FeedbackError):
    """Raised when an append would violate ledger authority invariants."""


class DeliveryBlocked(IntegrityConflict):
    """Origin-authentication failure carrying a typed, content-free diagnostic."""

    def __init__(
        self,
        feedback_id: str,
        conflict_type: str,
        field: str = "",
        message: str | None = None,
    ) -> None:
        self.feedback_id = feedback_id
        self.conflict_type = conflict_type
        self.field = field
        super().__init__(message or f"{conflict_type}:{feedback_id}")


class BodyInspectionUnavailable(FeedbackError):
    """Raised when no external isolation capability is available."""


def _validate_skill_name(name: str) -> str:
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise FeedbackError(
            "skill name must contain only lowercase letters, digits, and hyphens "
            "(maximum 64 characters)"
        )
    return name


def _now() -> datetime:
    # Real process on the VM — wall clock is fine and wanted for dated files.
    return datetime.now()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _validate_event(event: dict) -> None:
    """Validate invariants not delegated to a heavyweight JSON Schema runtime."""
    if event.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise FeedbackError("event schema_version must be 2")
    if event.get("event_type") not in EVENT_TYPES:
        raise FeedbackError(f"unsupported event type {event.get('event_type')!r}")
    if not event.get("event_id") or not event.get("occurred_at"):
        raise FeedbackError("event_id and occurred_at are required")
    if not isinstance(event["occurred_at"], str):
        raise FeedbackError("event occurred_at must be an RFC 3339 string")
    _parse_timestamp(event["occurred_at"], "event occurred_at")
    if not (event.get("skill") or {}).get("name"):
        raise FeedbackError("event skill.name is required")
    if (event.get("actor") or {}).get("type") not in ACTOR_TYPES:
        raise FeedbackError("event actor.type is invalid")
    if event.get("source") not in SOURCES:
        raise FeedbackError("event source is invalid")
    if not isinstance(event.get("payload"), dict):
        raise FeedbackError("event payload must be an object")
    if not isinstance(event.get("tags"), list):
        raise FeedbackError("event tags must be a list")
    if not all(isinstance(tag, str) and tag for tag in event["tags"]):
        raise FeedbackError("event tags must be non-empty strings")
    privacy = event.get("privacy")
    if not isinstance(privacy, dict) or privacy.get("content_included") is not False:
        raise FeedbackError("event privacy.content_included must be false")
    if not isinstance(privacy.get("redacted"), bool):
        raise FeedbackError("event privacy.redacted must be boolean")
    event_type = event["event_type"]
    payload = event["payload"]
    if event_type.startswith("invocation.") and not event.get("invocation_id"):
        raise FeedbackError(f"{event_type} requires invocation_id")
    required_payload = {
        "invocation.started": {"feature", "backend"},
        "invocation.finished": {"outcome", "backend", "metrics", "evidence"},
        "observation.recorded": {
            "feedback_id",
            "kind",
            "signal",
            "feature",
            "impact",
            "outcome",
            "evidence",
            "note_sha256",
            "note_file",
        },
        "observation.tombstoned": {
            "feedback_id",
            "prior_event_id",
            "prior_note_sha256",
            "corpus_version",
        },
        "disposition.changed": {
            "feedback_id",
            "status",
            "rationale_sha256",
            "links",
        },
        "verification.recorded": {
            "feedback_id",
            "receipt_id",
            "purpose",
            "artifact_id",
            "change_id",
            "acceptance_criterion",
            "verifier_source",
            "check_identity",
            "oracle",
            "observed_result",
            "observed_at",
            "verification_state",
        },
        "preservation.declared": {
            "feedback_id",
            "test",
        },
        "privacy.review.acknowledged": {
            "feedback_id",
            "entry_sha256",
            "findings_sha256",
            "scanner_version",
            "capability_nonce",
            "capability_issuer",
            "capability_audience",
            "capability_expires_at",
        },
    }[event_type]
    missing = required_payload - payload.keys()
    if missing:
        raise FeedbackError(
            f"{event_type} payload missing: {', '.join(sorted(missing))}"
        )
    if event_type == "invocation.started":
        _validate_backend(payload["backend"])
    elif event_type == "invocation.finished":
        if payload["outcome"] not in OUTCOMES:
            raise FeedbackError("invocation.finished outcome is invalid")
        _validate_backend(payload["backend"])
        if not isinstance(payload["metrics"], dict):
            raise FeedbackError("invocation.finished metrics must be an object")
        for name, value in payload["metrics"].items():
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                raise FeedbackError(
                    f"invocation.finished metric {name} must be non-negative"
                )
        _validate_evidence(payload["evidence"])
    elif event_type == "observation.recorded":
        if payload["kind"] not in KINDS:
            raise FeedbackError("observation.recorded kind is invalid")
        if payload["signal"] not in SIGNALS:
            raise FeedbackError("observation.recorded signal is invalid")
        if payload["impact"] not in IMPACTS:
            raise FeedbackError("observation.recorded impact is invalid")
        if payload["outcome"] not in OUTCOMES:
            raise FeedbackError("observation.recorded outcome is invalid")
        _validate_evidence(payload["evidence"])
        if not re.fullmatch(r"[0-9a-f]{64}", payload["note_sha256"]):
            raise FeedbackError("observation.recorded note_sha256 is invalid")
        if payload.get("delivery", "source") not in ("source", "pending"):
            raise FeedbackError("observation.recorded delivery is invalid")
        if "entry_sha256" in payload and not re.fullmatch(
            r"[0-9a-f]{64}", str(payload["entry_sha256"])
        ):
            raise FeedbackError("observation.recorded entry_sha256 is invalid")
        if "record_sha256" in payload and payload.get("record_sha256") != payload.get(
            "entry_sha256"
        ):
            raise FeedbackError("observation.recorded record_sha256 is inconsistent")
        if "canonicalization" in payload and payload["canonicalization"] != "body-v1":
            raise FeedbackError("observation.recorded canonicalization is invalid")
        if "note_digest" in payload:
            digest = payload["note_digest"]
            if (
                not isinstance(digest, dict)
                or digest.get("algorithm") != "sha256"
                or digest.get("canonicalization") != "body-v1"
                or not re.fullmatch(r"[0-9a-f]{64}", str(digest.get("sha256", "")))
            ):
                raise FeedbackError("observation.recorded note_digest is invalid")
    elif event_type == "disposition.changed":
        if payload["status"] not in STATUSES:
            raise FeedbackError("disposition.changed status is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", payload["rationale_sha256"]):
            raise FeedbackError("disposition.changed rationale_sha256 is invalid")
        if not isinstance(payload["links"], dict):
            raise FeedbackError("disposition.changed links must be an object")
    elif event_type == "verification.recorded":
        if payload["purpose"] not in ("resolution", "preservation", "recurrence"):
            raise FeedbackError("verification.recorded purpose is invalid")
        if payload["observed_result"] not in ("pass", "fail", "unavailable", "stale"):
            raise FeedbackError("verification.recorded observed_result is invalid")
        if payload["verification_state"] not in ("verified", "unverified"):
            raise FeedbackError("verification.recorded verification_state is invalid")
    elif event_type == "privacy.review.acknowledged":
        if set(payload) != required_payload:
            raise FeedbackError(
                "privacy.review.acknowledged payload must be content-free and exact"
            )
        if (event.get("actor") or {}).get("type") != "user":
            raise FeedbackError(
                "privacy.review.acknowledged requires a user capability actor"
            )
        for field in ("entry_sha256", "findings_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(payload[field])):
                raise FeedbackError(f"privacy.review.acknowledged {field} is invalid")
        if payload["scanner_version"] != QUALITATIVE_PRIVACY_SCANNER_VERSION:
            raise FeedbackError(
                "privacy.review.acknowledged scanner_version is invalid"
            )
        if payload["capability_audience"] != "privacy-review":
            raise FeedbackError(
                "privacy.review.acknowledged capability audience is invalid"
            )
        for field in ("capability_nonce", "capability_issuer"):
            if not isinstance(payload[field], str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}", payload[field]
            ):
                raise FeedbackError(f"privacy.review.acknowledged {field} is required")
        if event.get("source") != "explicit_user" or event.get("tags") != []:
            raise FeedbackError(
                "privacy.review.acknowledged provenance must be capability sealed"
            )
        actor_id = (event.get("actor") or {}).get("id")
        if not isinstance(actor_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}", actor_id
        ):
            raise FeedbackError("privacy.review.acknowledged actor id is invalid")
        expires_at = _parse_timestamp(
            payload["capability_expires_at"],
            "privacy.review.acknowledged capability_expires_at",
        )
        occurred_at = _parse_timestamp(
            event["occurred_at"], "privacy.review.acknowledged occurred_at"
        )
        if expires_at <= occurred_at:
            raise FeedbackError(
                "privacy.review.acknowledged capability was expired at acknowledgement"
            )


def _validate_backend(backend: object) -> None:
    if not isinstance(backend, dict):
        raise FeedbackError("event backend must be an object")
    expected = {"router", "provider", "model", "effort"}
    if set(backend) != expected:
        raise FeedbackError("event backend fields do not match the v2 contract")
    if not all(value is None or isinstance(value, str) for value in backend.values()):
        raise FeedbackError("event backend values must be strings or null")


def _validate_evidence(evidence: object) -> None:
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) and item for item in evidence
    ):
        raise FeedbackError("event evidence must be a list of non-empty strings")


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeedbackError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise FeedbackError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _default_signal(kind: str) -> str:
    if kind == "praise":
        return "positive"
    if kind in ("friction", "bug"):
        return "negative"
    return "mixed"


def _default_status(kind: str) -> str:
    return "observed" if kind == "praise" else "open"


def _safe_header_value(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    if "\n" in value or "·" in value:
        raise FeedbackError(f"{name} cannot contain a newline or '·'")
    return value


def _entry_sha256(header: str, body: str) -> str:
    canonical = f"entry-v1\n### {header}\n\n{_body_v1(body)}\n"
    return hashlib.sha256(canonical.encode()).hexdigest()


def _body_v1(body: str) -> str:
    """Canonical observation body: Unicode text with edge whitespace removed."""
    return body.strip()


def _body_sha256(body: str) -> str:
    return hashlib.sha256(_body_v1(body).encode()).hexdigest()


def _canonical_json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _empty_managed_note_file(text: str) -> bool:
    remainder = re.sub(r"(?m)^# Feedback[^\n]*\n+", "", text, count=1)
    remainder = re.sub(r"(?ms)<!--.*?-->", "", remainder)
    return not remainder.strip()


def _without_matches(text: str, matches: list[re.Match]) -> str:
    remainder = text
    for match in reversed(matches):
        remainder = remainder[: match.start()] + remainder[match.end() :]
    return remainder


def _stable_event_id(invocation_id: str, phase: str) -> str:
    digest = hashlib.sha256(f"{invocation_id}\0{phase}".encode()).hexdigest()
    return f"evt-{phase}-{digest}"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed
