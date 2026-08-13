"""Shared, static contracts implemented by ordinary command adapters."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..policy.manifest import ManifestError
from ..project.discovery import DiscoveryError
from ..runs.baseline import BaselineError
from ..runs.lifecycle import LifecycleError

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_INVALID_POLICY = 2
EXIT_UNAVAILABLE = 3
EXIT_APPROVAL_REQUIRED = 4
EXIT_BASELINE_INCOMPATIBLE = 5
INCOMPATIBLE_ERRORS = (BaselineError, LifecycleError, FileNotFoundError)
INVALID_ERRORS = (ManifestError, DiscoveryError, KeyError, ValueError)


@dataclass(frozen=True)
class Effects:
    filesystem: str
    network: str
    mutation: str
    cost: str


@dataclass(frozen=True)
class Explanation:
    id: str
    kind: str
    title: str
    purpose: str
    use_when: tuple[str, ...]
    do_not_use_when: tuple[str, ...]
    prerequisites: tuple[str, ...]
    effects: Effects
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    next_commands: tuple[str, ...]
    references: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    """Structured adapter result; the CLI alone wraps and renders its envelope."""

    status: str
    root: Path | None
    data: dict[str, Any]
    exit_code: int = EXIT_OK
    human: str | None = None


ParserConfigurator = Callable[[argparse.ArgumentParser], None]
CommandHandler = Callable[[argparse.Namespace], CommandResult]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    configure: ParserConfigurator
    handle: CommandHandler
    explanation: Explanation


READ_ONLY = Effects("reads bounded project/repository data", "none", "none", "none")
DECLARED_EXECUTION = Effects(
    "reads the project and may write declared evidence under .engineering",
    "inherited from explicitly adopted subprocesses",
    "only the named command/check or immutable evidence write",
    "none imposed by the CLI; adopted tools may have their own cost contract",
)
ACTIVE_SCAN = Effects(
    "reads bounded repository, Git, dependency, and applicable media inputs",
    "OSV may use the network unless --offline; local evidence imports and other built-ins are local",
    "no repository writes; temporary scanner reports are discarded",
    "none from the CLI; installed scanners run under their own licenses",
)
TEMPORARY_COPY = Effects(
    "reads the project and writes only inside a temporary copy",
    "inherited from the declared generator",
    "does not mutate the source checkout",
    "none imposed by the CLI",
)
DOCUMENT_AUTHORING = Effects(
    "reads the adopted role policy, existing role records, role indexes, source registers, templates, or one existing Markdown document",
    "none",
    "document new creates one non-overwriting record; document backfill atomically replaces one existing document's frontmatter while preserving its body bytes; document list/show/index/graph/trace/explain may write .engineering/document-index-v1.json",
    "none",
)


def explanation(
    name: str,
    title: str,
    purpose: str,
    use_when: tuple[str, ...],
    do_not_use_when: tuple[str, ...],
    *,
    prerequisites: tuple[str, ...] = (
        "uv is available and the skill root is resolved from the discovered SKILL.md",
    ),
    effects: Effects = READ_ONLY,
    evidence: tuple[str, ...] = ("versioned JSON status with explicit scope",),
    limitations: tuple[str, ...] = ("the explanation does not prove the capability ran",),
    next_commands: tuple[str, ...] = ("engineering explain",),
    references: tuple[str, ...] = ("docs/CONTRACT.md",),
) -> Explanation:
    return Explanation(
        f"command.{name}",
        "command",
        title,
        purpose,
        use_when,
        do_not_use_when,
        prerequisites,
        effects,
        evidence,
        limitations,
        next_commands,
        references,
    )
