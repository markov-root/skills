"""Bounded, atomic allocation for explicitly adopted typed documents."""

from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..policy.manifest import DocsCurrencyPolicy, DocumentRolePolicy
from ..policy.path_matching import matches_any
from ..resources import template_path
from .contracts import DOCUMENT_ROLES, RECORD_ROLES
from .projection import allocation_summary

MAX_ROLE_DOCUMENTS = 2_000
MAX_ALLOCATION_ATTEMPTS = 100
_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_ROLE_LABELS = {
    "adr": "ADR",
    "task": "Task",
    "lesson": "Lesson",
    "audit": "Audit",
    "research": "Research",
    "handoff": "Handoff",
    "specification": "Specification",
    "knowledge": "Knowledge",
    "reference": "Reference",
    "standard": "Standard",
    "guide": "Guide",
    "roadmap": "Roadmap",
    "changelog": "Changelog",
    "runbook": "Runbook",
    "index": "Index",
    "template": "Template",
}


@dataclass(frozen=True)
class DocumentAllocation:
    role: str
    id: str
    uid: str
    title: str
    path: str
    created: str
    updated: str
    transition_history: str | None


def allocate_document(
    root: Path,
    policy: DocsCurrencyPolicy | None,
    role: str,
    *,
    title: str | None = None,
    now: datetime | None = None,
    random_hex: str | None = None,
) -> DocumentAllocation:
    """Create exactly one fully rendered role template without overwriting a path."""
    root = root.resolve()
    declaration = _declaration(policy, role)
    _allocation_directory(root, declaration)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    selected_title = (title or f"New {_ROLE_LABELS[role]}").strip()
    if not selected_title:
        raise ValueError("document title must not be empty")
    if any(character in selected_title for character in "\r\n"):
        raise ValueError("document title must be a single line")
    slug = _slug(selected_title)
    suffix = random_hex or uuid.uuid4().hex[:8]
    if not _HEX8.fullmatch(suffix):
        raise ValueError(
            "document UID random suffix must be eight lowercase hexadecimal characters"
        )
    template = _template(role)

    next_number = _next_number(root, declaration)
    limit = (10**declaration.id_prefix_digits) - 1
    for offset in range(MAX_ALLOCATION_ATTEMPTS):
        number = next_number + offset
        if number > limit:
            raise ValueError(
                f"role {role!r} exhausted its {declaration.id_prefix_digits}-digit number space"
            )
        identifier = f"{number:0{declaration.id_prefix_digits}d}"
        document_id = identifier if role in RECORD_ROLES else f"{role}-{identifier}"
        relative = (Path(declaration.index).parent / f"{identifier}-{slug}.md").as_posix()
        if not matches_any(relative, declaration.include):
            raise ValueError(
                f"allocator path {relative!r} is not selected by role {role!r} include patterns"
            )
        target = root / relative
        uid = f"{role}-{moment:%Y%m%dT%H%M%S%fZ}-{suffix}"
        rendered = _render(template, role, document_id, uid, selected_title, moment)
        try:
            _write_exclusive(target, rendered)
        except FileExistsError:
            continue
        return DocumentAllocation(
            role,
            document_id,
            uid,
            selected_title,
            relative,
            moment.date().isoformat(),
            moment.date().isoformat(),
            "unverified" if role in RECORD_ROLES else None,
        )
    raise ValueError(f"role {role!r} allocation collided {MAX_ALLOCATION_ATTEMPTS} times")


def _declaration(
    policy: DocsCurrencyPolicy | None,
    role: str,
) -> DocumentRolePolicy:
    if role not in DOCUMENT_ROLES:
        raise ValueError(f"unknown document role {role!r}")
    declarations = () if policy is None else policy.roles
    matching = [item for item in declarations if item.name == role and item.contract is not None]
    if len(matching) != 1:
        raise ValueError(
            f"document role {role!r} is not adopted exactly once with a typed contract"
        )
    return matching[0]


def _allocation_directory(root: Path, declaration: DocumentRolePolicy) -> Path:
    directory = (root / declaration.index).parent
    try:
        resolved = directory.resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"role {declaration.name!r} allocation directory escapes the project"
        ) from exc
    if not resolved.is_dir():
        raise ValueError(f"role {declaration.name!r} allocation directory does not exist")
    return resolved


def _next_number(root: Path, declaration: DocumentRolePolicy) -> int:
    numbers: list[int] = []
    selected: set[Path] = set()
    for pattern in declaration.include:
        if pattern.startswith("!"):
            continue
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if matches_any(relative, declaration.include):
                selected.add(path)
            if len(selected) > MAX_ROLE_DOCUMENTS:
                raise ValueError(f"role {declaration.name!r} exceeds the allocator scan bound")
    for path in selected:
        prefix = path.name[: declaration.id_prefix_digits]
        if len(prefix) == declaration.id_prefix_digits and prefix.isdigit():
            numbers.append(int(prefix))
    return max(numbers, default=0) + 1


def _template(role: str) -> str:
    path = template_path(f"{role}.md")
    if not path.is_file():
        raise ValueError(f"bundled document template for role {role!r} is unavailable")
    return path.read_text(encoding="utf-8")


def _render(
    template: str,
    role: str,
    identifier: str,
    uid: str,
    title: str,
    moment: datetime,
) -> str:
    rendered = template
    rendered = re.sub(
        r"^summary: .+$",
        f"summary: {json.dumps(allocation_summary(_ROLE_LABELS[role], title), ensure_ascii=False)}",
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        rf'^id: "(?:{re.escape(role)}-)?NNNN"$',
        f'id: "{identifier}"',
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        rf'^uid: "?{re.escape(role)}-YYYYMMDDTHHMMSSffffffZ-RANDOM8"?$',
        f'uid: "{uid}"',
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    rendered = re.sub(
        r"^title: .+$",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        rendered,
        count=1,
        flags=re.MULTILINE,
    )
    if role in RECORD_ROLES:
        numeric_id = identifier.removeprefix(f"{role}-")
        rendered = rendered.replace('  id: "NNNN"', f'  id: "{numeric_id}"', 1)
        rendered = rendered.replace(
            f"  uid: {role}-YYYYMMDDTHHMMSSffffffZ-RANDOM8",
            f"  uid: {uid}",
            1,
        )
        rendered = re.sub(
            r"^  title: .+$",
            f"  title: {json.dumps(title, ensure_ascii=False)}",
            rendered,
            count=1,
            flags=re.MULTILINE,
        )
    day = moment.date().isoformat()
    rendered = rendered.replace('"YYYY-MM-DD"', f'"{day}"')
    rendered = rendered.replace(
        '"YYYY-MM-DDTHH:MM:SSZ"',
        f'"{moment:%Y-%m-%dT%H:%M:%SZ}"',
    )
    if role in RECORD_ROLES:
        rendered = re.sub(
            rf"^# {_ROLE_LABELS[role]} NNNN: .+$",
            f"# {_ROLE_LABELS[role]} {identifier}: {title}",
            rendered,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        rendered = re.sub(
            rf"^# {_ROLE_LABELS[role]}: TITLE$",
            f"# {_ROLE_LABELS[role]}: {title}",
            rendered,
            count=1,
            flags=re.MULTILINE,
        )
    return rendered


def _slug(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:80].rstrip("-")
    return slug or "record"


def _write_exclusive(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
