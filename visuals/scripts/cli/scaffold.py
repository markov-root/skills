"""Scaffold capability domain: `visuals new` emits contract wiring only.

Task 0006. This module is the domain behind `new_cmd.py` (the command
adapter); it never imports a handler, the dispatcher, or another domain's
adapter (architecture doc, "Dependency direction"). `config` is the contract
layer; `theme` is consumed lazily inside the one function that needs it, per
the seam contract.

The binding constraint is ADR 0004, and this task is where it is most easily
violated by a helpful implementation: a scaffold that emits a DESIGNED
starting point is a defect in this skill. What is emitted, and why each
element is wiring rather than design:

- `source/index.html` — the master. Preamble: charset, `<title>` (the slug,
  the identifying string), ONE stylesheet link resolving the project theme at
  the correct relative depth for where the file actually sits (audit F2: the
  corpus hardcodes `../../`, which breaks nested visual families), and the
  readiness-signal script (the render contract, task 0005). Body: an EMPTY
  canvas element and a source-credit band carrying the slug. No colour, no
  type, no size, no layout, no composition is declared anywhere.
- `visuals/_shared/theme.css` (project-level) — derived from the project's
  own theme reference through `theme.resolve_theme` + `emit_css`, never hand
  written: a stylesheet that restates a hex the token file carries is the
  F7 defect. Written only when absent, never rewritten once present — a
  shared project asset a second `visuals new` must not silently replace.
- `source/frames.txt` — the documented manifest format, one frame.
- `BRIEF.md` — a form, not an example (criterion 4): prompted sections for
  the brief's actual content, zero sample prose that could survive into a
  real brief, plus one wiring line naming the selected canvas profile.

Kinds (`presentation`, `poster`, `figure`, `diagram`) differ ONLY by the
default canvas profile they select (criterion 5): the kind name is matched
against the profiles the project config actually declares, falling back to
the config's `default_profile` — a scaffold never invents geometry (ADR 0001).

`--force` semantics (criterion 6, conservative form): force writes only
ABSENT files. It never overwrites ANY existing file, so an edited BRIEF.md or
source master is untouchable by construction, not by a heuristic about what
"edited" means. Skipped files are reported, never silent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: The artifact kinds a scaffold knows. Each maps to a canvas profile name.
KINDS = ("presentation", "poster", "figure", "diagram")

VISUALS_DIR = "visuals"
SHARED_DIR = "_shared"
THEME_CSS_NAME = "theme.css"
SOURCE_DIR_NAME = "source"
MASTER_NAME = "index.html"
BRIEF_NAME = "BRIEF.md"
MANIFEST_NAME = "frames.txt"

#: Templates shipped under `public/assets/scaffold/`. Located from this
#: module's own location (the accepted explicit-resolver pattern; never
#: `parents[n]` guesswork against cwd).
SCAFFOLD_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "scaffold"

#: A slug segment: a safe directory name — no separators, no leading dots,
#: nothing that escapes the project root or hides.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ScaffoldRefused(Exception):
    """The scaffold is refused on contract grounds. The message names the cause."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code  # 2 = usage-shaped refusal, 3 = unavailable


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileSelection:
    """The canvas profile a kind selects, and HOW it was selected — reported,
    never silent (a name match and a fallback are different facts)."""

    name: str
    basis: str  # "name-match" | "project-default"


@dataclass(frozen=True)
class SharedTheme:
    """The project-level derived stylesheet: written once, reused after."""

    path: Path
    status: str  # "written" | "reused"
    derived_from: str  # theme name it was derived from


@dataclass(frozen=True)
class ScaffoldPlan:
    """What `apply` will do, decided entirely before anything is written."""

    visual_dir: Path
    writes: list[tuple[Path, str]]  # (absolute target path, content)
    skipped: list[tuple[Path, str]]  # (existing path, why it was not written)
    profile: ProfileSelection
    theme: SharedTheme | None  # None = shared stylesheet already present
    theme_link: str  # the href emitted into the master's preamble


def select_profile(kind: str, config_resolved) -> ProfileSelection:
    """Kind → canvas profile, from the config's DECLARED profiles only.

    A profile named for the kind wins (criterion 5's differing case); the
    config's `default_profile` is the fallback (a scaffold never invents
    geometry, ADR 0001). Which of the two happened is recorded and reported.
    """
    profiles = config_resolved.canvas_profiles
    if kind in profiles:
        return ProfileSelection(name=kind, basis="name-match")
    return ProfileSelection(
        name=config_resolved.default_profile, basis="project-default"
    )


def _check_slug(slug: str) -> list[str]:
    """Validate the slug as a project-relative path; return its segments.

    One or more safe segments (`family/demo` is the nested-visual-family
    shape audit F2 broke on). Anything that could escape the project root,
    hide, or carry a separator is a usage error, not a scaffold target.
    """
    parts = [p for p in slug.split("/") if p]
    if not parts or any(p in (".", "..") or not _SEGMENT_RE.match(p) for p in parts):
        raise ScaffoldRefused(
            f"invalid slug {slug!r}: use one or more directory names "
            "(letters, digits, dot, dash, underscore; no separators inside a name)",
            exit_code=2,
        )
    return parts


def _template(name: str) -> str:
    path = SCAFFOLD_ASSETS / name
    if not path.is_file():
        raise ScaffoldRefused(f"scaffold template missing: {path}", exit_code=1)
    return path.read_text(encoding="utf-8")


def _theme_link_href(depth: int) -> str:
    """Relative href from the master to the shared stylesheet.

    The master sits at `<root>/visuals/<segments...>/source/index.html`; the
    shared stylesheet at `<root>/visuals/_shared/theme.css`. Reaching it
    needs one `../` per segment plus one for `source/` — computed from where
    the file actually is, never hardcoded (audit F2/F6: the corpus's
    hardcoded `../../` breaks nested visual families).
    """
    return "../" * (depth + 1) + f"{SHARED_DIR}/{THEME_CSS_NAME}"


def _derived_theme_css(config_resolved) -> tuple[str, str]:
    """Derive the shared stylesheet from the project's own theme reference.

    Consumes task 0004's theme module lazily (seam contract). The result is
    DERIVED from the token source — emit_css emits custom properties and
    nothing else — so no hex value gains a second hand-written home (F7).
    A theme that cannot resolve fails loudly here: a scaffold whose theme
    link dangles is exactly the silent-unwired-contract failure audit F2
    records, so it must never ship quietly.
    """
    try:
        import theme  # noqa: PLC0415  (contract layer, lazy per the seam contract)
    except ImportError:
        raise ScaffoldRefused(
            "theme resolution module not present in this build; cannot derive "
            "the shared stylesheet",
            exit_code=3,
        ) from None
    try:
        resolved = theme.resolve_theme(config_resolved.theme, config_resolved)
    except theme.ThemeUnavailable as exc:
        raise ScaffoldRefused(
            f"the project theme could not be resolved: {exc}", exit_code=3
        ) from exc
    steps = ", ".join(resolved.steps_consulted) or "no steps consulted"
    header = (
        f"/* visuals shared stylesheet — derived, not authored.\n"
        f"   Derived from theme '{resolved.name}' "
        f"(resolution: {steps}) by 'visuals new'.\n"
        f"   Edit the theme tokens, not this file; regenerate if the project\n"
        f"   theme changes. Written once when the first visual is scaffolded;\n"
        f"   never rewritten by a later scaffold. */\n"
    )
    return header + theme.emit_css(resolved.tokens), resolved.name


def plan_scaffold(config_resolved, kind: str, slug: str, force: bool) -> ScaffoldPlan:
    """Decide the entire scaffold before writing anything.

    Refusals happen here, before any write: existing visual directory without
    `--force`, invalid slug, theme that cannot resolve. Under `force`, files
    that already exist are recorded as skips and never written.
    """
    if kind not in KINDS:
        raise ScaffoldRefused(
            f"unknown kind {kind!r}; one of: {', '.join(KINDS)}", exit_code=2
        )
    parts = _check_slug(slug)

    root = Path(config_resolved.root)
    visual_dir = root.joinpath(VISUALS_DIR, *parts)
    source_dir = visual_dir / SOURCE_DIR_NAME
    shared_css = root / VISUALS_DIR / SHARED_DIR / THEME_CSS_NAME

    if visual_dir.exists() and not force:
        raise ScaffoldRefused(
            f"refusing to scaffold: {visual_dir} already exists "
            "(pass --force to fill only the files that are absent; "
            "existing files are never overwritten)",
            exit_code=2,
        )
    if visual_dir.exists() and not visual_dir.is_dir():
        raise ScaffoldRefused(
            f"refusing to scaffold: {visual_dir} exists and is not a directory",
            exit_code=2,
        )

    profile = select_profile(kind, config_resolved)
    depth = len(parts)  # segments under visuals/ ; source/ adds one more
    href = _theme_link_href(depth)

    brief = (
        _template("BRIEF.md.tmpl")
        .replace("{{SLUG}}", slug)
        .replace("{{PROFILE}}", profile.name)
        .replace("{{BASIS}}", profile.basis)
        .replace("{{KIND}}", kind)
    )
    master = _template("index.html.tmpl").replace("{{SLUG}}", slug).replace(
        "{{THEME_REL}}", href
    )
    manifest = _template("frames.txt.tmpl")

    writes: list[tuple[Path, str]] = []
    skipped: list[tuple[Path, str]] = []
    for target, content in (
        (visual_dir / BRIEF_NAME, brief),
        (source_dir / MASTER_NAME, master),
        (source_dir / MANIFEST_NAME, manifest),
    ):
        if target.exists():
            skipped.append((target, "exists; force never overwrites"))
        else:
            writes.append((target, content))

    theme_entry: SharedTheme | None = None
    if shared_css.exists():
        skipped.append(
            (
                shared_css,
                "existing project shared stylesheet; a shared asset is never rewritten",
            )
        )
    else:
        css, theme_name = _derived_theme_css(config_resolved)
        theme_entry = SharedTheme(
            path=shared_css, status="written", derived_from=theme_name
        )
        writes.append((shared_css, css))

    return ScaffoldPlan(
        visual_dir=visual_dir,
        writes=writes,
        skipped=skipped,
        profile=profile,
        theme=theme_entry,
        theme_link=href,
    )


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppliedScaffold:
    visual_dir: Path
    written: list[Path]
    skipped: list[Path]
    profile: ProfileSelection
    theme: SharedTheme | None


def apply_plan(plan: ScaffoldPlan) -> AppliedScaffold:
    """Execute the plan. Parents are created as needed; writes are complete
    files (nothing partial is left behind — a scaffold is not a transaction
    the author should have to clean up)."""
    written: list[Path] = []
    for target, content in plan.writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return AppliedScaffold(
        visual_dir=plan.visual_dir,
        written=written,
        skipped=[path for path, _ in plan.skipped],
        profile=plan.profile,
        theme=plan.theme,
    )