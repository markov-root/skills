"""Privacy-safe value objects shared by repository-inspection layers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .dependencies import DependencyEvidence

HIGH_RISK_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "service-account.json",
}
HIGH_RISK_SUFFIXES = {
    ".bak",
    ".backup",
    ".db",
    ".dump",
    ".kdbx",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}
MEDIA_SUFFIXES = {".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
METADATA_FIELDS = {
    "Author",
    "Creator",
    "GPSLatitude",
    "GPSLongitude",
    "OwnerName",
    "SerialNumber",
}
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9.-])"
)
PRIVATE_IPV4_RE = re.compile(
    r"(?<!\d)(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?!\d)"
)
INTERNAL_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)+(?:home\.lab|internal|lan|local)(?![A-Za-z0-9.-])",
    re.IGNORECASE,
)
HOME_PATH_RE = re.compile(
    r"(?:/home/[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+)"
)


@dataclass(frozen=True)
class ActiveFinding:
    id: str
    domain: str
    severity: str
    message: str
    fingerprint: str
    source: str
    path: str | None = None
    line: int | None = None
    advisory: str | None = None
    package: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class ToolEvidence:
    name: str
    state: str
    executable: str | None
    executable_sha256: str | None
    version: str | None
    network: str


@dataclass(frozen=True)
class InspectionLayer:
    name: str
    domain: str
    status: str
    required: bool
    scope: tuple[str, ...]
    findings: tuple[ActiveFinding, ...]
    tool: ToolEvidence | None
    duration_ms: int
    truncated: bool = False
    reason: str = ""
    limitations: tuple[str, ...] = ()
    dependency_evidence: tuple[DependencyEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["scope"] = list(self.scope)
        value["findings"] = [asdict(item) for item in self.findings]
        value["limitations"] = list(self.limitations)
        value.pop("dependency_evidence")
        return value


def fingerprint(category: str, path: str | None, value: str) -> str:
    material = "\0".join((category, path or "", value)).encode("utf-8", "surrogatepass")
    return hashlib.sha256(material).hexdigest()


def bounded_text(value: bytes | str, limit: int = 500) -> str:
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    return text.strip().replace("\x00", "")[:limit]


def safe_path(root: Path, value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            return None
    pure = PurePosixPath(value.removeprefix("./"))
    if pure.is_absolute() or ".." in pure.parts:
        return None
    return pure.as_posix()


def reportable_path(value: str | None) -> str | None:
    if value is None:
        return None
    if (
        EMAIL_RE.search(value)
        or PRIVATE_IPV4_RE.search(value)
        or INTERNAL_HOST_RE.search(value)
        or HOME_PATH_RE.search(value)
    ):
        return None
    return value


def finding_status(findings: Sequence[ActiveFinding]) -> str:
    return "failed" if findings else "passed"


def dependency_identifier(value: Any) -> str:
    bounded = bounded_text(str(value or "unknown"), limit=200)
    if any(ord(character) < 32 or ord(character) == 127 for character in bounded):
        return "redacted"
    return bounded if reportable_path(bounded) is not None else "redacted"


def privacy_finding(
    finding_id: str,
    message: str,
    _value: str,
    *,
    source: str,
    path: str | None = None,
    line: int | None = None,
) -> ActiveFinding:
    location_identity = f"{source}:{line or 0}:{message}"
    return ActiveFinding(
        finding_id,
        "privacy",
        "warning",
        f"{message}; matched value redacted and requires publication review",
        fingerprint(finding_id, path, location_identity),
        source,
        path,
        line,
    )
