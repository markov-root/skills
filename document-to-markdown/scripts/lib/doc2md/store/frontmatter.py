"""Deterministic, queryable YAML frontmatter projection (Task 0023).

The frontmatter is authoritative doc2md output prepended to the extracted body. It contains only
deterministic evidence in the default tier: identity, provenance, quality, shape, and a heading
outline. It is a *projection* of the authoritative ``result.json`` and is produced from the same
inputs so the two cannot drift.

Safety invariants:

* ``content_sha256`` is computed over the **body only**, so prepending or re-versioning the
  frontmatter never changes document identity.
* Untrusted harvested values (title, sitename, author) are strictly YAML-escaped; a hostile value
  cannot break out of the block or inject keys.
* The extracted body is emitted verbatim after the closing fence and a blank line, so a body that
  itself begins with ``---`` is preserved as body, never merged into the trusted header.

No third-party YAML dependency: a minimal, strict serializer quotes anything ambiguous.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from hashlib import sha256

_FRONTMATTER_SCHEMA_VERSION = 1

_LINK_RE = re.compile(r"\[[^\]]+\]\([^)\s]+\)")
_HEADING_RE = re.compile(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_TABLE_ROW_RE = re.compile(r"(?m)^[ \t]*\|.*\|[ \t]*$")
_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._/+-]*[A-Za-z0-9._/+-])?$")
# Tokens a bare scalar must never equal (YAML would type-coerce them).
_RESERVED_PLAIN = {
    "true",
    "false",
    "null",
    "yes",
    "no",
    "on",
    "off",
    "~",
}


def body_content_sha256(body: str) -> str:
    """Hash the document body only (excludes any frontmatter)."""

    return sha256(body.encode("utf-8")).hexdigest()


def yaml_scalar(value: object) -> str:
    """Serialize one scalar as a safe YAML value, quoting anything ambiguous or untrusted."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    if (
        text
        and _PLAIN_SCALAR_RE.match(text)
        and text.lower() not in _RESERVED_PLAIN
        and not text.isdigit()
    ):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'


def _emit(lines: list[str], key: str, value: object, indent: int) -> None:
    pad = "  " * indent
    if isinstance(value, Mapping):
        lines.append(f"{pad}{key}:")
        for subkey, subvalue in value.items():
            _emit(lines, str(subkey), subvalue, indent + 1)
    elif isinstance(value, (list, tuple)):
        if not value:
            lines.append(f"{pad}{key}: []")
            return
        lines.append(f"{pad}{key}:")
        for item in value:
            if isinstance(item, Mapping):
                # Render a mapping list item with the first pair on the dash line.
                pairs = list(item.items())
                first_key, first_value = pairs[0]
                lines.append(f"{pad}  - {first_key}: {yaml_scalar(first_value)}")
                for subkey, subvalue in pairs[1:]:
                    lines.append(f"{pad}    {subkey}: {yaml_scalar(subvalue)}")
            else:
                lines.append(f"{pad}  - {yaml_scalar(item)}")
    else:
        lines.append(f"{pad}{key}: {yaml_scalar(value)}")


def render_frontmatter_block(fields: Mapping[str, object]) -> str:
    """Serialize an ordered mapping to a fenced YAML frontmatter block."""

    lines: list[str] = ["---"]
    for key, value in fields.items():
        _emit(lines, key, value, 0)
    lines.append("---")
    return "\n".join(lines) + "\n"


def heading_outline(body: str) -> list[dict[str, object]]:
    """Return a deterministic heading map: level, text, and 1-based line number."""

    outline: list[dict[str, object]] = []
    for index, line in enumerate(body.splitlines(), start=1):
        match = _HEADING_RE.match(line)
        if match:
            outline.append(
                {
                    "level": len(match.group(1)),
                    "text": match.group(2).strip(),
                    "line": index,
                }
            )
    return outline


def text_metrics(body: str) -> dict[str, int]:
    """Deterministic shape metrics an agent can query without reading the body."""

    return {
        "chars": len(body),
        "words": len(body.split()),
        "links": len(_LINK_RE.findall(body)),
        "headings": len(_HEADING_RE.findall(body)),
        "table_rows": len(_TABLE_ROW_RE.findall(body)),
    }


def render_document(frontmatter: Mapping[str, object], body: str) -> str:
    """Prepend the trusted frontmatter block to the verbatim body."""

    block = render_frontmatter_block(frontmatter)
    trimmed = body.strip("\n")
    if not trimmed:
        return block
    return f"{block}\n{trimmed}\n"


def outline_is_inline(outline: Sequence[object], *, limit: int = 40) -> bool:
    """Inline a small outline; spill a large one to a companion file (caller decides)."""

    return len(outline) <= limit
