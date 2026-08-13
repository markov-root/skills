"""Static source of truth for commands and non-command capability explanations."""

from __future__ import annotations

from ..commands import (
    check,
    classify,
    docs,
    doctor,
    document,
    explain,
    finish,
    fitness,
    generated,
    init,
    inspect,
    install_hooks,
    instructions,
    knowledge,
    start,
    suggest_manifest,
)
from ..commands.contracts import (
    ACTIVE_SCAN,
    DECLARED_EXECUTION,
    READ_ONLY,
    CommandSpec,
    Explanation,
)

ACTIVE_INSPECTION_PROFILES = inspect.ACTIVE_PROFILES
ADAPTER_KINDS = ("semantic-reviewer",)
MAX_EXPLANATIONS = 100

COMMAND_SPECS: tuple[CommandSpec, ...] = (
    inspect.SPEC,
    init.SPEC,
    start.SPEC,
    finish.SPEC,
    suggest_manifest.SPEC,
    doctor.SPEC,
    instructions.SPEC,
    install_hooks.SPEC,
    classify.SPEC,
    check.SPEC,
    fitness.SPEC,
    generated.SPEC,
    docs.SPEC,
    document.SPEC,
    knowledge.SPEC,
    explain.SPEC,
)
COMMANDS = tuple(spec.name for spec in COMMAND_SPECS)
COMMAND_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}


def _mode(
    identifier: str,
    kind: str,
    title: str,
    purpose: str,
    use_when: tuple[str, ...],
    do_not_use_when: tuple[str, ...],
    *,
    prerequisites: tuple[str, ...],
    effects=READ_ONLY,
    evidence: tuple[str, ...] = ("versioned JSON status with explicit scope",),
    limitations: tuple[str, ...] = ("the explanation does not prove the capability ran",),
    next_commands: tuple[str, ...] = ("engineering explain",),
    references: tuple[str, ...] = ("docs/CONTRACT.md",),
) -> Explanation:
    return Explanation(
        identifier,
        kind,
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


PROFILE_EXPLANATIONS = (
    _mode(
        "profile.inspect.passive",
        "profile",
        "Passive repository mapping",
        "Observe a checkout without executing inferred commands or requiring adoption.",
        ("entering an unfamiliar repository",),
        ("requesting vulnerability or privacy scans",),
        prerequisites=("a readable target directory",),
        next_commands=(
            "engineering inspect --json",
            "engineering suggest-manifest --json",
        ),
    ),
    *(
        _mode(
            f"profile.inspect.{name}",
            "profile",
            f"Active {name} inspection",
            (
                "Run bounded built-in security layers."
                if name == "security"
                else (
                    "Run bounded Git/current-tree privacy layers."
                    if name == "privacy"
                    else "Require bounded security, privacy, and Agent Skill publication-repository hygiene layers before publication review."
                )
            ),
            (f"explicit {name} preflight is required",),
            ("granting publication approval", "silently adopting scanner policy"),
            prerequisites=("required external scanners are installed when applicable",),
            effects=ACTIVE_SCAN,
            evidence=(
                "independent layer scope, identity, status, findings, truncation, and limits",
                "separate local-production, local-full, and provider dependency populations",
                "reconciled advisory identities, disagreements, freshness, and release risks",
                "portable private-path ignore coverage and current Git index hygiene for Agent Skill repositories",
            ),
            limitations=("a pass is scoped evidence, not proof of absence or permission",),
            next_commands=(
                f"engineering inspect {name} --target TARGET --json",
                "engineering inspect publication --target TARGET --dependency-evidence PATH --json",
            ),
            references=(
                "docs/context/security.md",
                "docs/context/dependency-evidence.md",
            ),
        )
        for name in ACTIVE_INSPECTION_PROFILES
    ),
)

ADAPTER_EXPLANATIONS = (
    _mode(
        "adapter.semantic-reviewer",
        "adapter",
        "Optional semantic-reviewer adapter",
        "Provide advisory model review inside the isolated finish lifecycle.",
        ("a measured project need justifies adopting semantic-reviewer",),
        (
            "automatic installation or adoption",
            "treating tool output as project authority",
        ),
        prerequisites=(
            "the reviewer is declared in engineering.yaml",
            "the reviewer command is reviewed",
        ),
        effects=DECLARED_EXECUTION,
        evidence=("execution identity, version, network expectation, and cited findings",),
        limitations=("semantic review is model opinion and a no-finding result is not proof",),
        next_commands=("engineering finish RUN_ID",),
    ),
)

CATALOG = (
    *(spec.explanation for spec in COMMAND_SPECS),
    *PROFILE_EXPLANATIONS,
    *ADAPTER_EXPLANATIONS,
)
CATALOG_BY_ID = {item.id: item for item in CATALOG}


def validate_registry(
    command_specs: tuple[CommandSpec, ...],
    catalog: tuple[Explanation, ...],
) -> None:
    """Reject duplicate, missing, or mismatched command registrations."""

    command_names = tuple(spec.name for spec in command_specs)
    explanation_ids = tuple(item.id for item in catalog)
    if len(command_names) != len(set(command_names)):
        raise ValueError("command registry contains duplicate names")
    if len(explanation_ids) != len(set(explanation_ids)) or len(catalog) > MAX_EXPLANATIONS:
        raise ValueError("capability explanation registry is duplicate or unbounded")
    registered = {f"command.{name}" for name in command_names}
    explained = {item.id for item in catalog if item.kind == "command"}
    if registered != explained:
        raise ValueError("command explanations drifted from the command registry")
    for spec in command_specs:
        if spec.explanation.id != f"command.{spec.name}" or spec.explanation.kind != "command":
            raise ValueError(f"command specification metadata drifted: {spec.name}")
    for item in catalog:
        for field in (
            "use_when",
            "do_not_use_when",
            "prerequisites",
            "evidence",
            "limitations",
            "next_commands",
            "references",
        ):
            value = getattr(item, field)
            if (
                not isinstance(value, tuple)
                or not value
                or not all(isinstance(entry, str) and entry for entry in value)
            ):
                raise ValueError(f"explanation {item.id} has an invalid {field} contract")


validate_registry(COMMAND_SPECS, CATALOG)


def select_explanations(
    identifiers: tuple[str, ...] = (), *, kind: str | None = None
) -> tuple[Explanation, ...]:
    unknown = tuple(identifier for identifier in identifiers if identifier not in CATALOG_BY_ID)
    if unknown:
        raise KeyError(f"unknown explanation identifiers: {list(unknown)}")
    selected = (
        tuple(CATALOG_BY_ID[identifier] for identifier in dict.fromkeys(identifiers))
        if identifiers
        else CATALOG
    )
    return tuple(item for item in selected if kind is None or item.kind == kind)
