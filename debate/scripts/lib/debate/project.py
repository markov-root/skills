"""Debate PROJECT layout (ADR-0008): fixed inputs at the top of `<slug>/`, per-run traces under
`runs/<run-name>/`. This module owns the layout so the CLI and engine stay ignorant of it.

    <slug>/
      item.md          the debated item (paper/draft/claim) — human-authored
      debate.yaml      the ask: protocol, question, criteria + pointers to item/materials
      materials/       research corpus the panel may cite (manifest.yaml + source files)
      cast.yaml        modular panel: proposers / redteam / arbitrator + per-voice reasoning_effort
      prompts/         exact round prompts (editable snapshot, ADR-0006/0007)
      runs/<name>/     one execution's traces (RunStore writes here)

`load_project()` composes the flat `spec` dict the DelphiTask already understands (id, protocol,
question, context, criteria) by folding `item.md` + rendered `materials/` into `context`, so the
task stays domain-free (ADR-0002). `scaffold_project()` writes the skeleton from a named panel.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from debate._resources import copy_private_tree, resource_path
from debate.input_contracts import (
    InputContractError,
    MaterialsManifestInput,
    ProjectInput,
    load_cast_input,
    load_project_input,
    resolve_owned_path,
    validate_identifier,
)

_PROTOCOLS = ("delphi", "idea")


# How the panel accesses evidence (ADR-0010). A property of the DEBATE, set in debate.yaml:
#   context — inject the materials MAP (abstracts) into every voice's prompt. Any backend.
#   disk    — voices OPEN the full files in materials/ on demand. Agentic CLI backends ONLY.
#   search  — voices SEARCH the internet for NEW sources (max-entropy). Web-capable backends only;
#             the deterministic verbatim-quote gate is OFF (sources aren't pinned).
MATERIALS_MODES = ("context", "disk", "search")
_DISK_BACKENDS = {"claude_code", "codex_cli"}  # can read files off disk
_WEB_BACKENDS = {
    "openrouter",
    "claude_code",
}  # can search the web (codex exec has no net by default)


def _cast_backends(cast: dict) -> list[tuple[str, str]]:
    """(voice-id, backend) for every voice in the cast — proposers + redteam + arbitrator."""
    voices = list(cast.get("debaters") or [])
    if cast.get("redteam"):
        voices.append(cast["redteam"])
    if cast.get("arbitrator"):
        voices.append(cast["arbitrator"])
    return [(v.get("id", "?"), v.get("backend", "openrouter")) for v in voices]


def validate_materials_mode(mode: str, cast: dict) -> None:
    """Fail fast (ADR-0010) when a materials mode is incompatible with the cast's backends — e.g.
    `disk` with an OpenRouter voice that cannot read files. Raises SystemExit with the offenders."""
    if mode not in MATERIALS_MODES:
        raise SystemExit(f"materials_mode must be one of {MATERIALS_MODES}, got {mode!r}")
    if mode == "disk":
        bad = [f"{i} ({b})" for i, b in _cast_backends(cast) if b not in _DISK_BACKENDS]
        if bad:
            raise SystemExit(
                f"materials_mode 'disk' needs every voice to read files off disk "
                f"({'/'.join(sorted(_DISK_BACKENDS))}); these cannot: {', '.join(bad)}. "
                f"Use a claude_code/codex_cli-only panel, or mode 'context'."
            )
    if mode == "search":
        bad = [f"{i} ({b})" for i, b in _cast_backends(cast) if b not in _WEB_BACKENDS]
        if bad:
            raise SystemExit(
                f"materials_mode 'search' needs web-capable voices "
                f"({'/'.join(sorted(_WEB_BACKENDS))}); these cannot: {', '.join(bad)}. "
                f"(codex exec has no network by default.) Use a web panel or mode 'context'."
            )


def is_project(path: Path | str) -> bool:
    """True if `path` is a debate project directory (has a debate.yaml)."""
    p = Path(path)
    return p.is_dir() and (p / "debate.yaml").exists()


def _render_materials(materials_dir: Path) -> str:
    """Inject the research corpus as a MAP of per-source abstracts (ADR-0009), not full text — the
    map is cheap and tells each voice what is in the corpus and where. When the manifest has fetched
    sources, use `materials.render_map` (summaries); otherwise fall back to full text of any loose
    .md/.txt files dropped in the folder (small manual corpora)."""
    if not materials_dir.is_dir():
        return ""
    manifest = materials_dir / "manifest.yaml"
    if manifest.exists():
        from debate.materials import render_map

        try:
            if rendered := render_map(materials_dir):
                return rendered
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    parts: list[str] = []
    for f in sorted(materials_dir.iterdir()):
        if f.suffix.lower() in {".md", ".txt"} and f.name != "manifest.yaml":
            parts.append(f"\n===== SOURCE: {f.name} =====\n{f.read_text().strip()}")
    if not parts:
        return ""
    return "MATERIALS (research corpus — cite verbatim from these sources):\n" + "\n".join(parts)


def load_project(folder: Path | str, *, item_override: Path | str | None = None) -> dict:
    """Load a project directory into the flat `spec` dict the tasks understand (ADR-0008).

    `context` is composed from the debated item + the rendered `materials/` corpus, so the panel
    argues about the item and may cite the materials. `id`, `protocol`, `question`, `criteria` come
    from `debate.yaml`. The project's own files are canonical (ADR-0006): editing them changes the
    next run.

    `item_override` swaps in a DIFFERENT item file for this run only (e.g. an edited draft with
    inline comments) while reusing the same materials/cast/prompts — the run snapshots the item it
    used, so provenance stays honest. `spec['item_path']` records which file was read.
    """
    folder = Path(folder).resolve()
    dfile = folder / "debate.yaml"
    if not dfile.exists():
        raise SystemExit(f"not a debate project (no debate.yaml): {folder}")
    try:
        document = load_project_input(
            yaml.safe_load(dfile.read_text()) or {},
            source=dfile,
            default_id=folder.name,
        )
    except InputContractError as exc:
        raise SystemExit(str(exc)) from exc
    ask = document.to_runtime()
    protocol = ask["protocol"]

    context_parts: list[str] = []
    try:
        item = (
            resolve_owned_path(
                folder,
                item_override,
                kind="--item override",
                allow_external=True,
            )
            if item_override
            else resolve_owned_path(folder, ask["item"], kind="debate.yaml item")
        )
        materials_dir = resolve_owned_path(
            folder, ask.get("materials", "materials"), kind="debate.yaml materials"
        )
    except InputContractError as exc:
        raise SystemExit(str(exc)) from exc
    if not item.exists():
        raise SystemExit(f"item file not found: {item}")
    if item.read_text().strip():
        context_parts.append(f"THE ITEM UNDER DEBATE:\n{item.read_text().strip()}")
    materials = _render_materials(materials_dir)
    if materials:
        context_parts.append(materials)
    # An inline context in debate.yaml is appended after the files (rare; files are primary).
    if ask.get("context"):
        context_parts.append(str(ask["context"]).strip())

    # Record the frozen evidence-universe id (task-0027) so a run states WHICH corpus it used.
    from debate.materials_contract import corpus_version, load_manifest

    spec = {
        "id": ask.get("id", folder.name),
        "protocol": protocol,
        "question": str(ask["question"]).strip(),
        "criteria": str(ask.get("criteria", "")).strip(),
        "context": "\n\n".join(context_parts),
        "materials_mode": ask.get("materials_mode", "context"),
        "corpus_version": corpus_version(load_manifest(folder)),
        "item_path": str(item),
    }
    # Protocol overrides ride through to the engine ONLY when present, so absent keys keep the task
    # default (engine.plan.load_plan → default_plan; the task's own aggregator). Passing these
    # through is what makes a `rounds:` / `aggregator:` block in debate.yaml actually take effect on
    # the PROJECT path — it previously did nothing here, because these keys were silently dropped.
    if "rounds" in ask:
        spec["rounds"] = ask["rounds"]
    if "aggregator" in ask:
        spec["aggregator"] = ask["aggregator"]
    return spec


def load_cast(folder: Path | str) -> dict:
    """Read the project's canonical `cast.yaml` into the engine's cast shape
    ({debaters, redteam, arbitrator, panel}). Per-voice `reasoning_effort` rides along on each spec
    (backends read it where supported). The folder's cast.yaml wins over the named registry."""
    folder = Path(folder)
    cfile = folder / "cast.yaml"
    if not cfile.exists():
        raise SystemExit(f"{folder}: no cast.yaml (scaffold with `debate new` or add one)")
    try:
        return load_cast_input(yaml.safe_load(cfile.read_text()) or {}, source=cfile).to_runtime()
    except InputContractError as exc:
        raise SystemExit(str(exc)) from exc


def _cast_doc(cast: dict, protocol: str, lean: bool) -> dict:
    """The sectioned cast.yaml document written by a scaffold, from a resolved named panel."""
    legacy = {
        "panel": cast.get("panel"),
        "protocol": protocol,
        "proposers": cast["debaters"],
        "redteam": (None if lean else cast.get("redteam")),
        # single arbitrator today; a list here later promotes it to a judge panel (ADR-0008).
        "arbitrator": cast["arbitrator"],
    }
    return load_cast_input(legacy, source="<scaffold cast>").model_dump(
        by_alias=True, exclude_none=True, exclude_defaults=True
    )


def scaffold_project(
    folder: Path,
    *,
    slug: str,
    protocol: str,
    cast: dict,
    lean: bool,
    question: str | None = None,
    item_src: Path | None = None,
) -> None:
    """Create the project skeleton (ADR-0008). Only writes what is ABSENT, so re-scaffolding never
    clobbers authored inputs — the same non-destructive contract as ADR-0006's snapshot."""
    try:
        validate_identifier(slug, kind="project slug")
        if protocol not in _PROTOCOLS:
            raise InputContractError(
                "validation_failed",
                f"protocol must be one of {_PROTOCOLS}, got {protocol!r}",
            )
        # Validate the supplied cast and all new authored data before the first mkdir.
        canonical_cast = _cast_doc(cast, protocol, lean)
        project_input = ProjectInput(
            schema_id=ProjectInput.CONTRACT_ID,
            schema_version=ProjectInput.CONTRACT_VERSION,
            id=slug,
            protocol=protocol,
            question=question
            or "Produce the strongest steelman AGAINST the thesis of the item under debate.",
            criteria="Each option is one distinct, independently defensible line of argument, "
            "grounded in the item and materials. Options must be mutually distinct.",
            item="items/v0.1.0.md",
            materials="materials",
            materials_mode="context",
        )
    except (InputContractError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "materials").mkdir(exist_ok=True)
    (folder / "items").mkdir(exist_ok=True)

    # Versioned item drafts live in items/ (ADR-0008); the first is v0.1.0. Iterate by adding
    # items/v0.2.0.md etc. and pointing debate.yaml `item:` (or `--item`) at the one to debate.
    item = folder / "items" / "v0.1.0.md"
    if not item.exists():
        if item_src and item_src.exists():
            item.write_text(item_src.read_text())
        else:
            item.write_text(
                f"# {slug}\n\n<!-- Paste the paper/draft/claim to be debated here. -->\n"
            )

    dfile = folder / "debate.yaml"
    if not dfile.exists():
        ask = project_input.model_dump(by_alias=True, exclude_none=True)
        # Commented, ready-to-uncomment protocol template (ADR-0011; docs/round-types.md §3). The
        # named panel + the default plan cover almost every debate, so this stays OFF by default —
        # but showing the exact keys teaches the shape without an agent having to read source.
        rounds_hint = (
            "\n"
            "# --- Protocol (advanced; OPTIONAL) -------------------------------------------\n"
            "# Omit this block for the default plan: floor (propose·critique·revise) + one\n"
            "# adversarial pass (redteam·respond) + a dynamic escalation pass that fires only\n"
            "# when `max` > 5. Uncomment to change the SHAPE. Ref: docs/round-types.md §1-§5.\n"
            "# rounds:\n"
            "#   min: 3                 # floor is always 3; min may not go below it\n"
            "#   max: 9                 # CAP = floor(3) + 2 per adversarial/escalation pass;\n"
            "#                          # must be >= the non-dynamic phase count in `plan`\n"
            "#   plan:                  # `aggregate` is auto-appended; propose must be first\n"
            "#     - propose\n"
            "#     - critique\n"
            "#     - revise\n"
            "#     - { pass: adversarial }               # redteam·respond; list N for N passes\n"
            "#     - { pass: escalation, dynamic: true } # escalate·respond; may propose; repeats\n"
            "#   referees:              # only before_revise / before_respond are read\n"
            "#     before_revise:  [near_duplicate, non_atomic, thin_rationale]\n"
            "#     before_respond: [unaddressed, overreach]\n"
            "# Two clean red-team passes, NO escalation:  (set max >= 7)\n"
            "#   plan: [propose, critique, revise, { pass: adversarial }, { pass: adversarial }]\n"
        )
        dfile.write_text(yaml.safe_dump(ask, sort_keys=False) + rounds_hint)

    cfile = folder / "cast.yaml"
    if not cfile.exists():
        cfile.write_text(yaml.safe_dump(canonical_cast, sort_keys=False))

    prompts = folder / "prompts"
    if not prompts.exists():
        copy_private_tree(resource_path("prompts", protocol), prompts)

    mman = folder / "materials" / "manifest.yaml"
    if not mman.exists():
        manifest = MaterialsManifestInput(
            schema_id=MaterialsManifestInput.CONTRACT_ID,
            schema_version=MaterialsManifestInput.CONTRACT_VERSION,
        )
        mman.write_text(
            "# Research corpus for the panel (fetch-then-pin, ADR-0008).\n"
            + yaml.safe_dump(
                manifest.model_dump(exclude_none=True, exclude_defaults=True), sort_keys=False
            )
            + "# Add sources using schemas/inputs/materials-manifest.schema.json.\n"
        )


def sha256_file(path: Path) -> str:
    """SHA-256 of a file — the pin for a materials source (fetch-then-pin, ADR-0008)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
