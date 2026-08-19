"""Skill and path discovery seam for skill-feedback."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from .model import FeedbackError, SKILL_NAME_PATTERN, _validate_skill_name

HOME = Path(os.environ.get("HOME", str(Path.home())))


def _feedback_home() -> Path:
    legacy = HOME / "Skills" / "exported-data" / "skill-feedback"
    if legacy.exists():
        return legacy
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
        return local / "Skill Feedback"
    if sys.platform == "darwin":
        return HOME / "Library" / "Application Support" / "Skill Feedback"
    state = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local" / "state"))
    return state / "skill-feedback"


FEEDBACK_HOME = Path(
    os.environ.get("SKILL_FEEDBACK_HOME", _feedback_home())
).expanduser()


def known_skills() -> list[str]:
    """Return inventory, installed, system, and pending-outbox skill names."""
    names = {entry["name"] for entry in _inventory()["entries"]}
    for root in (CLAUDE_SKILLS, AGENTS_SKILLS, CODEX_SKILLS):
        if root.is_dir():
            try:
                names.update(
                    path.name
                    for path in root.iterdir()
                    if path.is_dir() and SKILL_NAME_PATTERN.fullmatch(path.name)
                )
            except OSError:
                pass
    codex_system = CODEX_SKILLS / ".system"
    if codex_system.is_dir():
        try:
            names.update(path.name for path in codex_system.iterdir() if path.is_dir())
        except OSError:
            pass
    outbox = FEEDBACK_HOME / "note-outbox"
    try:
        if outbox.is_dir():
            names.update(path.name for path in outbox.iterdir() if path.is_dir())
    except OSError:
        pass
    return sorted(names)


__all__: tuple[str, ...] = ()

REGISTRY_OVERRIDE = (
    Path(os.environ["SKI_REGISTRY"]).expanduser()
    if os.environ.get("SKI_REGISTRY")
    else None
)

MANAGER_COMMAND = os.environ.get("SKILL_MANAGER_COMMAND", "skill")

MANAGER_EXPLICIT = "SKILL_MANAGER_COMMAND" in os.environ

CLAUDE_SKILLS = Path(
    os.environ.get("SKI_CLAUDE_SKILLS", HOME / ".claude" / "skills")
).expanduser()

AGENTS_SKILLS = Path(
    os.environ.get("SKI_AGENTS_SKILLS", HOME / ".agents" / "skills")
).expanduser()

CODEX_SKILLS = Path(
    os.environ.get(
        "SKI_CODEX_SKILLS",
        Path(os.environ.get("CODEX_HOME", HOME / ".codex")) / "skills",
    )
).expanduser()

SKILLS_HOME = Path(os.environ.get("SKILLS_HOME", HOME / "Skills")).expanduser()

_INVENTORY_CACHE: dict | None = None


def _inventory_from_registry_override() -> dict:
    assert REGISTRY_OVERRIDE is not None
    entries = []
    errors = []
    if not REGISTRY_OVERRIDE.is_dir():
        return {
            "ready": False,
            "source": "registry_override",
            "contract_version": 1,
            "entries": [],
            "error": f"registry override is not a directory: {REGISTRY_OVERRIDE}",
        }
    try:
        manifests = sorted(REGISTRY_OVERRIDE.glob("*.toml"))
    except OSError as exc:
        return {
            "ready": False,
            "source": "registry_override",
            "contract_version": 1,
            "entries": [],
            "error": f"cannot enumerate registry override: {exc}",
        }
    for path in manifests:
        try:
            manifest = tomllib.loads(path.read_text())
        except (tomllib.TOMLDecodeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
            entries.append(
                {
                    "name": path.stem,
                    "capability": None,
                    "invoke": None,
                    "source": None,
                    "executables": {},
                    "invalid": str(exc),
                }
            )
            continue
        raw_source = manifest.get("skill_dir") or manifest.get("claude_skill_dir")
        source = Path(os.path.expanduser(raw_source)) if raw_source else None
        if source is not None and not source.is_absolute():
            source = (path.parent / source).resolve()
        cli = manifest.get("cli")
        declared = cli.get("executables", {}) if isinstance(cli, dict) else {}
        entries.append(
            {
                "name": manifest.get("name", path.stem),
                "capability": manifest.get("type"),
                "invoke": manifest.get("invoke"),
                "source": str(source) if source is not None else None,
                "executables": declared if isinstance(declared, dict) else {},
                "invalid": None,
            }
        )
    return {
        "ready": bool(entries) and not errors,
        "source": "registry_override",
        "contract_version": 1,
        "entries": entries,
        "error": "; ".join(errors)
        if errors
        else (None if entries else "inventory is empty"),
    }


def _inventory_from_manager() -> dict:
    try:
        result = subprocess.run(
            [MANAGER_COMMAND, "list", "--json"],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ready": False,
            "source": "skill-manager",
            "contract_version": None,
            "entries": [],
            "error": f"cannot execute Skill Manager inventory: {exc}",
        }
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")
        return {
            "ready": False,
            "source": "skill-manager",
            "contract_version": None,
            "entries": [],
            "error": (
                f"Skill Manager inventory exited {result.returncode}"
                + (f": {detail[:500]}" if detail else "")
            ),
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ready": False,
            "source": "skill-manager",
            "contract_version": None,
            "entries": [],
            "error": f"Skill Manager inventory returned invalid JSON: {exc}",
        }
    version = payload.get("contract_version") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else None
    raw_entries = data.get("entries") if isinstance(data, dict) else None
    if (
        version != 2
        or payload.get("operation") != "list"
        or payload.get("outcome") != "current"
        or not isinstance(raw_entries, list)
    ):
        return {
            "ready": False,
            "source": "skill-manager",
            "contract_version": version,
            "entries": [],
            "error": "unsupported or unsuccessful Skill Manager inventory contract",
        }
    entries = []
    errors = []
    seen_names = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            errors.append(f"entry {index} is not an object")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not SKILL_NAME_PATTERN.fullmatch(name):
            errors.append(f"entry {index} has invalid capability name")
            continue
        if name in seen_names:
            errors.append(f"{name}: duplicate capability name")
            continue
        seen_names.add(name)
        capability = raw.get("capability")
        source = raw.get("source")
        executables = raw.get("executables")
        if not isinstance(capability, str):
            errors.append(f"{name}: capability is not a string")
            continue
        if source is not None and not isinstance(source, str):
            errors.append(f"{name}: source is not a string or null")
            continue
        if not isinstance(executables, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in executables.items()
        ):
            errors.append(f"{name}: executables is not a string map")
            continue
        entries.append(
            {
                "name": name,
                "capability": capability,
                "invoke": None,
                "source": source,
                "executables": executables,
                "invalid": None,
            }
        )
    return {
        "ready": bool(entries) and not errors,
        "source": "skill-manager",
        "contract_version": version,
        "entries": entries,
        "error": "; ".join(errors)
        if errors
        else (None if entries else "inventory is empty"),
    }


def _read_frontmatter_name(md_path: Path) -> str | None:
    """Return the SKILL.md frontmatter ``name``, or None if it cannot be parsed."""
    if not md_path.is_file():
        return None
    try:
        lines = md_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^name:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip("\"'")
    return None


def _artifact_root(repo: Path) -> Path:
    """The shippable artifact dir for a skill root (public/ under B-workspace)."""
    cand = repo / "public"
    return cand if cand.is_dir() else repo


def _scripts_executables(skill_artifact: Path) -> dict:
    """Executable scripts under ``scripts/``, keyed by command name."""
    scripts = skill_artifact / "scripts"
    if not scripts.is_dir():
        return {}
    out: dict[str, str] = {}
    try:
        for path in sorted(scripts.iterdir()):
            if path.is_file() and os.access(path, os.X_OK):
                out[path.stem] = f"scripts/{path.name}"
    except OSError:
        return {}
    return out


def _inventory_from_filesystem() -> dict:
    """Synthesize the skill inventory from installed + source skill artifacts.

    Skills.sh installs skills under the harness skill directories; the monorepo
    keeps writable source artifacts under ``SKILLS_HOME/<name>/public``. When
    neither ``SKI_REGISTRY`` nor an explicit ``SKILL_MANAGER_COMMAND`` is set we
    discover from these, so the retired Skill Manager is never invoked.
    """
    seen: dict[str, Path] = {}

    def add(name: str, root: Path) -> None:
        if name and name not in seen:
            seen[name] = root

    if SKILLS_HOME.is_dir():
        try:
            for repo in SKILLS_HOME.iterdir():
                if not repo.is_dir():
                    continue
                for md in (
                    repo / "public" / "SKILL.md",
                    repo / "SKILL.md",
                    repo / "skill" / "SKILL.md",
                ):
                    name = _read_frontmatter_name(md)
                    if name:
                        add(name, repo)
                        break
        except OSError:
            pass

    for root in (CLAUDE_SKILLS, AGENTS_SKILLS, CODEX_SKILLS, CODEX_SKILLS / ".system"):
        if not root.is_dir():
            continue
        try:
            for sub in root.iterdir():
                if not sub.is_dir():
                    continue
                name = (
                    sub.name
                    if SKILL_NAME_PATTERN.fullmatch(sub.name)
                    else _read_frontmatter_name(sub / "SKILL.md")
                )
                if name:
                    add(name, sub)
        except OSError:
            pass

    entries: list[dict] = []
    for name in sorted(seen):
        root = seen[name]
        artifact = _artifact_root(root)
        entries.append(
            {
                "name": name,
                "capability": "cli" if (artifact / "scripts").is_dir() else None,
                "invoke": None,
                "source": str(artifact),
                "executables": _scripts_executables(artifact),
                "invalid": None,
            }
        )
    return {
        "ready": bool(entries),
        "source": "skills-sh-filesystem",
        "contract_version": 1,
        "entries": entries,
        "error": None if entries else "no installed or source skill artifacts found",
    }


def _inventory() -> dict:
    global _INVENTORY_CACHE
    if _INVENTORY_CACHE is not None:
        return _INVENTORY_CACHE
    if REGISTRY_OVERRIDE is not None:
        _INVENTORY_CACHE = _inventory_from_registry_override()
    elif MANAGER_EXPLICIT:
        _INVENTORY_CACHE = _inventory_from_manager()
    else:
        _INVENTORY_CACHE = _inventory_from_filesystem()
    return _INVENTORY_CACHE


def registry_skill_dir(name: str) -> Path | None:
    """Return the source directory reported by the authoritative inventory."""
    _validate_skill_name(name)
    entry = next(
        (item for item in _inventory()["entries"] if item["name"] == name),
        None,
    )
    raw = entry.get("source") if entry else None
    return Path(os.path.expanduser(raw)) if raw else None


def installed_skill_dir(name: str) -> Path | None:
    _validate_skill_name(name)
    candidates = (
        CLAUDE_SKILLS / name,
        AGENTS_SKILLS / name,
        CODEX_SKILLS / name,
        CODEX_SKILLS / ".system" / name,
    )
    return next((path for path in candidates if path.exists()), None)


def _repo_root(start: Path) -> Path:
    """Nearest ancestor that owns the skill: has .git or a skill.toml.

    Falls back to the parent of a ``skill/`` dir, else *start* itself. This keeps
    feedback at the repo root (matching the existing docs/feedback convention)
    even when the registry points at a symlinked or nested skill dir.
    """
    for ancestor in (start, *start.parents):
        if (ancestor / ".git").exists() or (ancestor / "skill.toml").is_file():
            return ancestor
    if start.name == "skill":
        return start.parent
    return start


def source_repo_by_name(name: str) -> Path | None:
    """Repo under SKILLS_HOME whose skill.toml declares this ``name``.

    A repo that *declares* it owns the skill is authoritative for its feedback —
    this beats the registry when a skill was installed as a copy (registry points
    at the copy) rather than symlinked to source.
    """
    if not SKILLS_HOME.is_dir():
        return None
    try:
        repositories = sorted(p for p in SKILLS_HOME.iterdir() if p.is_dir())
    except OSError as exc:
        raise FeedbackError(
            f"cannot enumerate skill source home {SKILLS_HOME}: {exc}"
        ) from exc
    for repo in repositories:
        if _declared_name(repo) == name:
            return repo
    return None


def _declared_name(repo: Path) -> str | None:
    """The skill name a repo declares, from SKILL.md or legacy skill.toml.

    Prefers the B-workspace ``public/SKILL.md``, then a repo-root or legacy
    ``skill/SKILL.md``, then ``skill.toml`` for surviving legacy repos.
    """
    for md in (
        repo / "public" / "SKILL.md",
        repo / "SKILL.md",
        repo / "skill" / "SKILL.md",
    ):
        name = _read_frontmatter_name(md)
        if name:
            return name
    manifest = repo / "skill.toml"
    if manifest.is_file():
        try:
            declared = tomllib.loads(manifest.read_text()).get("name")
            if declared:
                return declared
        except (tomllib.TOMLDecodeError, OSError):
            pass
    return None


def feedback_dir(name: str, override: str | None = None) -> Path:
    """Resolve where feedback for *name* should be written.

    Preference order:
      1. explicit --dir override
      2. a source repo under SKILLS_HOME that declares ``name`` in its skill.toml
      3. the source repo behind the registry ``skill_dir`` (follow symlinks, walk
         up to the nearest .git / skill.toml)
      4. the installed skill dir itself (vendored skills with no source repo)
      5. an installed Claude, Agent Skills, or Codex system skill directory
    """
    _validate_skill_name(name)
    if override:
        return Path(override).expanduser().resolve() / "docs" / "feedback"

    repo = source_repo_by_name(name)
    if repo is not None:
        return _resolve_feedback_root(repo)

    skill_dir = registry_skill_dir(name)
    if skill_dir is not None:
        real = skill_dir.resolve() if skill_dir.exists() else skill_dir
        return _resolve_feedback_root(real)

    installed = installed_skill_dir(name)
    if installed is not None:
        return _resolve_feedback_root(installed.resolve())

    raise FeedbackError(
        f"unknown skill {name!r}: no registry entry or installed skill directory.\n"
        f"known skills: {', '.join(known_skills()) or '(registry empty)'}\n"
        f"pass --dir PATH to write feedback somewhere explicit."
    )


def _resolve_feedback_root(target: Path) -> Path:
    """Docs-feedback home for a skill root, honouring the <name>/{public,dev} layout.

    Under the B-workspace shape the writable factory owns ``dev/docs/feedback``;
    legacy and installed (non-B-workspace) skills keep ``docs/feedback``.
    """
    if target.name == "public" and (target.parent / "dev").is_dir():
        return target.parent / "dev" / "docs" / "feedback"
    if (target / "dev").is_dir():
        return target / "dev" / "docs" / "feedback"
    return target / "docs" / "feedback"


def _path_is_writable(path: Path) -> bool:
    """Check whether *path* can be created/written without mutating it."""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.is_dir() and os.access(candidate, os.W_OK | os.X_OK)
