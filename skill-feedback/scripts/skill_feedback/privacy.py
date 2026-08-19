"""Privacy-scanning seam for skill-feedback."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .model import (
    FeedbackError,
    PrivacyReviewRequest,
    QUALITATIVE_PRIVACY_SCANNER_VERSION,
    _new_id,
    _validate_event,
    _validate_skill_name,
)

__all__: tuple[str, ...] = ()

SECRET_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|pwd|secret)"
            r"\s*[:=]\s*[\"']?[^\s,\"']{8,}"
        ),
    ),
)

SENSITIVE_CONTENT_PATTERNS = (
    (
        "email-address",
        re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@(?:[a-z0-9-]+\.)+[a-z]{2,}(?![\w.-])"),
    ),
    (
        "unix-user-home",
        re.compile(r"(?<![\w/])/(?:home|Users)/[^/\s`\"']+"),
    ),
    (
        "tilde-home-path",
        re.compile(r"(?<![\w])~/(?:[^/\s`\"']+/?)"),
    ),
    (
        "windows-user-home",
        re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s`\"']+"),
    ),
    (
        "ip-address",
        re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"),
    ),
    (
        "private-hostname",
        re.compile(
            r"(?i)\b(?:[a-z0-9-]+\.)+(?:home\.lab|internal|local)(?::\d{1,5})?\b"
        ),
    ),
    (
        "ssh-user-host",
        re.compile(r"(?i)(?<![\w.-])[\w.-]+@[\w.-]+:[^\s`\"']+"),
    ),
    (
        "labeled-contact-or-person",
        re.compile(
            r"(?i)\b(?:full\s+name|person|patient|client|customer|employee|"
            r"phone|mobile|telephone|street\s+address|postal\s+address|passport|"
            r"national\s+id|social\s+security)\s*[:=]\s*\S+"
        ),
    ),
    (
        "url-query",
        re.compile(r"(?i)\bhttps?://[^\s`\"'?]+\?[^\s`\"']+"),
    ),
)


def _iter_string_fields(value: object, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_string_fields(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_string_fields(item, f"{path}[{index}]")


def _likely_secret_fields(value: object) -> list[str]:
    findings = []
    for path, text in _iter_string_fields(value):
        if any(pattern.search(text) for _, pattern in SECRET_PATTERNS):
            findings.append(path)
    return sorted(set(findings))


def _text_privacy_findings(text: str) -> list[dict]:
    """Return content-free privacy findings for a qualitative text value."""
    findings = []
    seen = set()
    for severity, patterns in (
        ("block", SECRET_PATTERNS),
        ("review", SENSITIVE_CONTENT_PATTERNS),
    ):
        for kind, pattern in patterns:
            for match in pattern.finditer(text):
                key = (severity, kind, match.start())
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "severity": severity,
                        "kind": kind,
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
    return sorted(
        findings,
        key=lambda item: (item["line"], item["severity"], item["kind"]),
    )


def _privacy_finding_summary(findings: list[dict]) -> str:
    grouped: dict[str, set[int]] = {}
    for finding in findings:
        grouped.setdefault(finding["kind"], set()).add(finding["line"])
    return ", ".join(
        f"{kind} at line(s) {','.join(str(line) for line in sorted(lines))}"
        for kind, lines in sorted(grouped.items())
    )


def _privacy_findings_sha256(findings: list[dict]) -> str:
    canonical = {
        "scanner_version": QUALITATIVE_PRIVACY_SCANNER_VERSION,
        "findings": findings,
    }
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def build_review_request(
    *, skill: str, feedback_id: str, entry_sha256: str, text: str
) -> PrivacyReviewRequest:
    """Build the indivisible content-free tuple requiring operator authority."""
    _validate_skill_name(skill)
    if not isinstance(feedback_id, str) or not feedback_id:
        raise FeedbackError("privacy review feedback_id is required")
    if not re.fullmatch(r"[0-9a-f]{64}", entry_sha256):
        raise FeedbackError("privacy review entry_sha256 is invalid")
    findings = _text_privacy_findings(text)
    if any(item["severity"] == "block" for item in findings):
        raise FeedbackError(
            "cannot acknowledge likely secrets; remove or redact the note"
        )
    if not any(item["severity"] == "review" for item in findings):
        raise FeedbackError("feedback entry has no review-required privacy findings")
    return PrivacyReviewRequest(
        skill=skill,
        feedback_id=feedback_id,
        entry_sha256=entry_sha256,
        findings_sha256=_privacy_findings_sha256(findings),
        scanner_version=QUALITATIVE_PRIVACY_SCANNER_VERSION,
    )


def _capability_token(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}", value
    ):
        raise PermissionError(f"operator capability {label} is invalid")
    return value


def _capability_expiry(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PermissionError("operator capability expiry is invalid")
    return value.astimezone(timezone.utc)


def acknowledge_review(
    request: PrivacyReviewRequest,
    *,
    capability_provider=None,
    now: datetime | None = None,
) -> dict:
    """Exchange a trusted one-use operator grant for a sealed review event."""
    authorize = getattr(capability_provider, "authorize", None)
    if not callable(authorize):
        raise PermissionError("operator capability unavailable")
    grant = authorize(request)
    if getattr(grant, "actor_type", None) != "user":
        raise PermissionError("operator capability actor must be user")
    if getattr(grant, "audience", None) != "privacy-review":
        raise PermissionError("operator capability audience is invalid")
    for field in (
        "feedback_id",
        "entry_sha256",
        "findings_sha256",
        "scanner_version",
    ):
        if getattr(grant, field, None) != getattr(request, field):
            raise PermissionError(f"operator capability {field} is not bound")

    issued_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expires_at = _capability_expiry(getattr(grant, "expires_at", None))
    if expires_at <= issued_at:
        raise PermissionError("operator capability has expired")
    subject = _capability_token(getattr(grant, "subject", None), "subject")
    issuer = _capability_token(getattr(grant, "issuer", None), "issuer")
    nonce = _capability_token(getattr(grant, "nonce", None), "nonce")
    occurred_at = issued_at.isoformat().replace("+00:00", "Z")
    expires = expires_at.isoformat().replace("+00:00", "Z")
    event = {
        "schema_version": 2,
        "event_id": _new_id("evt"),
        "event_type": "privacy.review.acknowledged",
        "occurred_at": occurred_at,
        "skill": {"name": request.skill, "version": None},
        "invocation_id": None,
        "session": {"id": None, "harness": None},
        "actor": {"type": "user", "id": subject},
        "source": "explicit_user",
        "task": {"class": None},
        "tags": [],
        "privacy": {"content_included": False, "redacted": False},
        "payload": {
            "feedback_id": request.feedback_id,
            "entry_sha256": request.entry_sha256,
            "findings_sha256": request.findings_sha256,
            "scanner_version": request.scanner_version,
            "capability_nonce": nonce,
            "capability_issuer": issuer,
            "capability_audience": "privacy-review",
            "capability_expires_at": expires,
        },
    }
    _validate_event(event)
    return event


def _stored_privacy_review_matches(
    disposition: dict,
    *,
    entry_sha256: str,
    findings: list[dict],
) -> bool:
    review = disposition.get("privacy_review")
    return (
        isinstance(review, dict)
        and review.get("scanner_version") == QUALITATIVE_PRIVACY_SCANNER_VERSION
        and review.get("entry_sha256") == entry_sha256
        and review.get("findings_sha256") == _privacy_findings_sha256(findings)
    )


def _enforce_qualitative_privacy(
    text: str,
    *,
    reviewed: bool,
    label: str,
) -> list[dict]:
    """Screen qualitative content before persistence without echoing matches."""
    findings = _text_privacy_findings(text)
    blocked = [item for item in findings if item["severity"] == "block"]
    if blocked:
        raise FeedbackError(
            f"likely secret detected in {label}: {_privacy_finding_summary(blocked)}; "
            "remove or redact it before recording"
        )
    review = [item for item in findings if item["severity"] == "review"]
    if review and not reviewed:
        raise FeedbackError(
            f"privacy review required for {label}: "
            f"{_privacy_finding_summary(review)}; remove/generalize it or rerun with "
            "--privacy-reviewed after confirming the content is appropriate to store"
        )
    return findings
