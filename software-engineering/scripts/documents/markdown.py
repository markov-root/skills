"""Repository-local GFM parsing and structural validation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

MARKDOWN = MarkdownIt("commonmark").enable("table")


@dataclass(frozen=True)
class DocFinding:
    path: str
    line: int
    code: str
    message: str


class GithubSlugger:
    """Small deterministic implementation of GitHub-style heading IDs."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def slug(self, text: str) -> str:
        base = _github_slug(text)
        count = self._seen.get(base, 0)
        self._seen[base] = count + 1
        return base if count == 0 else f"{base}-{count}"


def _github_slug(text: str) -> str:
    cleaned: list[str] = []
    for character in text.strip().lower():
        category = unicodedata.category(character)
        if character in {"-", "_"}:
            cleaned.append(character)
        elif character.isspace():
            # github-slugger replaces each whitespace character rather than collapsing runs.
            cleaned.append("-")
        elif category.startswith("P") or character in {"$", "+", "<", "=", ">", "^", "`", "|", "~"}:
            continue
        else:
            cleaned.append(character)
    return "".join(cleaned)


def slugify(text: str) -> str:
    """Return the first GitHub-compatible slug for compatibility with callers."""
    return GithubSlugger().slug(text)


def _inline_text(token: Token) -> str:
    if not token.children:
        return token.content
    pieces: list[str] = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            pieces.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            pieces.append(" ")
        elif child.type == "image":
            pieces.append(child.content)
    return "".join(pieces)


def _document_facts(text: str) -> tuple[set[str], list[tuple[int, str]], list[tuple[int, int]]]:
    tokens = MARKDOWN.parse(text)
    slugs: set[str] = set()
    links: list[tuple[int, str]] = []
    tables: list[tuple[int, int]] = []
    slugger = GithubSlugger()
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            slugs.add(slugger.slug(_inline_text(tokens[index + 1])))
        if token.type == "inline":
            line = (token.map[0] + 1) if token.map else 1
            for child in token.children or ():
                if child.type == "link_open":
                    destination = child.attrGet("href")
                    if destination is not None:
                        links.append((line, destination))
        if token.type == "table_open" and token.map:
            tables.append((token.map[0], token.map[1]))
    return slugs, links, tables


def validate_markdown(
    root: Path,
    paths: Sequence[str],
    *,
    required_headings: Sequence[str] = (),
    forbidden_patterns: Sequence[str] = (),
) -> tuple[DocFinding, ...]:
    root = root.resolve()
    findings: list[DocFinding] = []
    facts: dict[Path, tuple[set[str], list[tuple[int, str]], list[tuple[int, int]]]] = {}

    def read_facts(file: Path):
        if file not in facts:
            facts[file] = _document_facts(file.read_text(encoding="utf-8"))
        return facts[file]

    for relative in sorted(paths):
        file = root / relative
        lines = file.read_text(encoding="utf-8").splitlines()
        headings, links, tables = read_facts(file)
        required_slugger = GithubSlugger()
        for required in required_headings:
            if required_slugger.slug(required) not in headings:
                findings.append(DocFinding(relative, 1, "missing-heading", required))
        for line_no, line in enumerate(lines, 1):
            for forbidden in forbidden_patterns:
                if re.search(forbidden, line):
                    findings.append(DocFinding(relative, line_no, "forbidden-syntax", forbidden))
        for line_no, destination in links:
            destination_parts = destination.split(maxsplit=1)
            if not destination_parts:
                findings.append(
                    DocFinding(relative, line_no, "empty-link", "link destination is empty")
                )
                continue
            target_text = destination_parts[0].strip("<>")
            if target_text.startswith(("http://", "https://", "mailto:")):
                continue
            target_name, _, anchor = unquote(target_text).partition("#")
            target = file if not target_name else file.parent / target_name
            try:
                target.resolve().relative_to(root)
            except ValueError:
                findings.append(DocFinding(relative, line_no, "unsafe-link", target_text))
                continue
            if not target.exists():
                findings.append(DocFinding(relative, line_no, "broken-link", target_text))
            elif anchor and target.suffix.lower() in {".md", ".markdown"}:
                target_headings, _, _ = read_facts(target)
                if anchor not in target_headings:
                    findings.append(DocFinding(relative, line_no, "broken-anchor", target_text))
        findings.extend(_table_findings(relative, lines, tables))
    return tuple(findings)


def table_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip().removeprefix("|")
    if stripped.endswith("|") and not _escaped(stripped, len(stripped) - 1):
        stripped = stripped[:-1]
    cells: list[str] = []
    start = 0
    for index, character in enumerate(stripped):
        if character == "|" and not _escaped(stripped, index):
            cells.append(stripped[start:index])
            start = index + 1
    cells.append(stripped[start:])
    return tuple(cells)


def _escaped(value: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _table_findings(
    path: str, lines: Sequence[str], tables: Sequence[tuple[int, int]]
) -> list[DocFinding]:
    findings: list[DocFinding] = []
    for start, end in tables:
        expected = len(table_cells(lines[start]))
        # The delimiter is row two. Validate body rows against the authored header width;
        # markdown-it normalizes short rows in its token stream.
        for index in range(start + 2, end):
            if len(table_cells(lines[index])) != expected:
                findings.append(
                    DocFinding(path, index + 1, "malformed-table", "inconsistent column count")
                )
    return findings


def findings_json(findings: Sequence[DocFinding]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "findings": [asdict(item) for item in findings],
    }


def findings_markdown(findings: Sequence[DocFinding]) -> str:
    rows = [
        ("Path", "Line", "Code", "Message"),
        *[(item.path, str(item.line), item.code, item.message) for item in findings],
    ]
    widths = [max(len(row[index]) for row in rows) for index in range(4)]

    def render(row: tuple[str, ...]) -> str:
        return (
            "| " + " | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) + " |"
        )

    return "\n".join(
        [
            "# Documentation findings",
            "",
            render(rows[0]),
            render(tuple("-" * width for width in widths)),
            *(render(row) for row in rows[1:]),
            "",
            f"Findings represented: {len(findings)}.",
            "",
        ]
    )
