"""Single static registry of `visuals` CLI commands.

This is the ONLY command catalog in the artifact. Parser construction, dispatch,
`--help` text, and command listing are all derived from `COMMAND_SPECS`; adding a
command means adding one `CommandSpec` (plus its handler module) and touching
nothing else. More than one command catalog is a forbidden pattern in the
target architecture's "Dependency direction" section (dev docs, context/).

A spec's `backend` routes by dependency weight, so the bash entrypoint carries no
command knowledge:

- ``stdlib``  — the handler needs only the Python standard library. `main.py`
                imports and runs it in-process under whatever `python3` started.
- ``uv``      — the handler declares dependencies in a PEP 723 header and has an
                adjacent `uv lock` lockfile. `main.py` re-execs it under
                `uv run --script` (guard env var prevents re-exec loops).

Only commands that exist at this version are registered. Unimplemented roadmap
commands are deliberately absent rather than stubbed — the registry must not
advertise capability that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """One registered command. Everything about it lives here."""

    name: str
    usage: str  # argument synopsis shown after the program name
    summary: str  # one-line description used by help and command listing
    help_text: str  # long description used by the subcommand's --help
    backend: str  # "stdlib" or "uv"
    handler: str  # module name in this package ("doctor" -> cli/doctor.py)


BUMP_SPEC = CommandSpec(
    name="bump",
    usage="bump <slug> patch|minor|major [--check]",
    summary="Re-render a visual at an explicitly chosen version level; the version string is derived, never hand-supplied.",
    help_text=(
        "Re-render <slug> into the next version derived from the existing\n"
        "version directories, advancing the chosen component (patch, minor or\n"
        "major). The version string itself is never a hand-supplied value and\n"
        "never appears in a second place (audit F5) — the level is the only\n"
        "decision, exactly as the corpus's hand-bookkeeping should have been.\n"
        "\n"
        "Rendering is identical to `visuals render` at the same level: the\n"
        "readiness signal (or bounded-budget fallback, recorded per frame),\n"
        "the hashed receipt, automatic previews, and the `latest` repoint after\n"
        "every frame succeeded. --check adds the two-pass determinism check.\n"
        "\n"
        "Exit codes: 0 rendered, 1 blocking render failure (the message names\n"
        "the cause), 2 usage, 3 unavailable (no browser)."
    ),
    backend="uv",
    handler="bump_cmd",
)

DATA_SPEC = CommandSpec(
    name="data",
    usage="data snapshot <slug> --input PATH --source-page URL --description TEXT --limitation TEXT",
    summary="Snapshot a dataset into a visual's data directory with full provenance; limitations are required.",
    help_text=(
        "  data snapshot   copy declared inputs into <slug>'s data directory and\n"
        "                  write a provenance.json recording, per input: source\n"
        "                  identity, the upstream URL, byte size, sha256, the\n"
        "                  retrieval and ingest timestamps, what was done to the\n"
        "                  payload, what the dataset measures, and what it cannot\n"
        "                  support.\n"
        "\n"
        "This generalises the hand-written sync-data.sh scripts in the reference\n"
        "corpus into one declared step. It does NOT fetch: inputs are files the\n"
        "caller has already obtained, so network policy and credentials stay out\n"
        "of a provenance recorder. It does not run a project's derive step either.\n"
        "\n"
        "--limitation is REQUIRED and repeatable, and nothing waives it. A dataset\n"
        "whose limitations are unstated does not snapshot: the corpus records them\n"
        "in 7 of 25 visuals (audit F9), and a graphic asserting more than its data\n"
        "supports is the failure this prevents.\n"
        "\n"
        "Re-running over unchanged inputs rewrites a byte-identical provenance.json\n"
        "apart from its two timestamps, so a diff shows real change only. An input\n"
        "whose digest moved since the last snapshot is reported prominently rather\n"
        "than silently absorbed — a dataset changing underneath a published graphic\n"
        "is a finding about that graphic.\n"
        "\n"
        "Exit codes: 0 snapshotted (including with a reported digest change),\n"
        "2 usage or a contract violation that wrote nothing, 3 unavailable (not an\n"
        "adopted project)."
    ),
    backend="stdlib",
    handler="data_cmd",
)

DOCTOR_SPEC = CommandSpec(
    name="doctor",
    usage="doctor [--json]",
    summary="Report readiness of the authored-render environment, item by item.",
    help_text=(
        "Check, with a per-item verdict: Chrome/Chromium presence and version, the\n"
        "resolved python3 and uv, availability of the image-generation delegate,\n"
        "and the resolved project config when the working directory is inside an\n"
        "adopted project (a visuals.toml found by walking up).\n"
        "\n"
        "Exits 0 when the authored-render engine can run, 3 when a required\n"
        "component is absent — never 0 on an unusable environment. The delegate\n"
        "is capability-detected, not required: its absence is reported as\n"
        "unavailable, per ADR 0006.\n"
        "\n"
        "Read-only. Writes nothing."
    ),
    backend="stdlib",
    handler="doctor",
)

IMAGE_SPEC = CommandSpec(
    name="image",
    usage="image <slug> --prompt TEXT [--ref PATH]... [--profile NAME] [--label LABEL] [--into vX.Y.Z] [--execute]",
    summary="Generate an image into the shared artifact store, delegating to the image-generation skill; dry-run by default, --execute is the paid call.",
    help_text=(
        "Put a GENERATED image into the same artifact contract as an authored\n"
        "render: an immutable version directory, a receipt, a preview, and an\n"
        "atomically repointed `latest`. This command never generates anything\n"
        "itself and carries no provider knowledge (ADR 0006): it delegates to the\n"
        "installed image-generation skill, which is the authority on providers.\n"
        "\n"
        "DETECTION AND HONEST DEGRADATION, never a hard dependency: the\n"
        "delegate is capability-detected (install roots, then a PATH command);\n"
        "when it is absent the command exits 3 naming every location checked and\n"
        "how to install it — never an error, never a silent no-op, never a\n"
        "traceback.\n"
        "\n"
        "DEFAULT IS A DRY-RUN. Paid calls are behind explicit opt-in: without\n"
        "--execute the command runs the delegate's own dry-run — the exact\n"
        "command and compiled prompt, nothing billed, nothing written — and\n"
        "reports where the output would land. --execute performs the real\n"
        "(paid) generation. No test in this factory spends quota.\n"
        "\n"
        "  <slug>          the visual's directory name under visuals/ (created\n"
        "                  on first generation; a generated visual has no source\n"
        "                  master — the prompt is the lineage)\n"
        "  --prompt TEXT   what to generate (required)\n"
        "  --ref PATH      reference image, passed through (repeatable)\n"
        "  --profile NAME  delegate profile, passed through (the delegate owns\n"
        "                  the vocabulary; default auto)\n"
        "  --label LABEL   label, passed through to the delegate's lineage\n"
        "  --into vX.Y.Z   explicit version target (refused if it exists);\n"
        "                  otherwise the next version is DERIVED from the store\n"
        "  --execute       opt in to the paid generation\n"
        "\n"
        'The receipt records engine: "generative", the prompt lineage (raw and\n'
        "the delegate's compiled prompt), the provider and settings the delegate\n"
        "reports, per-frame content hashes, and the delegate's own manifest\n"
        "(copied verbatim as delegate-manifest.json). It carries NONE of the\n"
        "authored engine's measurement vocabulary — no readiness, no\n"
        "determinism, no scene graph — because a generative output is stochastic\n"
        "and verifiable only by looking (ADR 0003, Limits). A consumer can tell\n"
        "generated from authored output from the receipt alone: receipts without\n"
        "an engine field are authored.\n"
        "\n"
        "THIS SURFACE IS FIXED from its first release (ADR 0006): name,\n"
        "arguments, and output contract do not change — a later absorption of\n"
        "the delegate changes the implementation only.\n"
        "\n"
        "Exit codes: 0 ok (dry-run or generated), 1 blocking failure (the\n"
        "delegate ran and failed, or produced no output — cause named), 2 usage,\n"
        "3 unavailable (delegate absent, or not an adopted project).\n"
    ),
    backend="uv",
    handler="image_cmd",
)

IMPROVE_SPEC = CommandSpec(
    name="improve",
    usage="improve <slug> [--execute] [--new-run] [--json]",
    summary="Run one bounded unpublished render-and-probe iteration against the visual's own brief.",
    help_text=(
        "One invocation renders one unpublished version and probes its delivery\n"
        "previews against the brief's explicit Q: … | A: … criteria. The author\n"
        "revises the source between invocations. Project [improve].max_iterations\n"
        "sets a cap (default 3); reaching it is a normal advisory outcome.\n"
        "Default dry-run writes nothing and spends no quota. --execute renders,\n"
        "sends each delivery preview and minimal questions to two fresh Codex\n"
        "agents per frame, and stores sequential evidence\n"
        "in improvement.json. --new-run starts another capped sequence without\n"
        "discarding earlier evidence. The command never edits the master, ranks\n"
        "designs, or repoints latest. Use publish after human review.\n"
    ),
    backend="uv",
    handler="improve_cmd",
)

INDEX_SPEC = CommandSpec(
    name="index",
    usage="index [--json]",
    summary="Derive the portfolio status view from the store on disk — versions, staleness, findings, consumer join — replacing hand-maintained prose.",
    help_text=(
        "Walk an adopted project and derive, from the artifact store on disk,\n"
        "the per-visual status that the reference corpus maintains by hand in\n"
        "VISUALS-BRIEF.md's status column and HANDOFF.md's prose (audit 0001\n"
        "F5, F6) — and which drifts. The index is derived, never\n"
        "hand-maintained, and reads none of that prose.\n"
        "\n"
        "One row per visual (nested families are their own rows, the slug\n"
        "carrying their path): current version (from a resolving `latest`),\n"
        "frame count (counted on disk), staleness, blocking and advisory\n"
        "finding counts (from validate's own severity implementation), and\n"
        "whether a consumer manifest entry references it. The consumer join is\n"
        "reported in BOTH directions in the same output (audit F6): manifest\n"
        "entries naming visuals that do not exist, and built visuals with a\n"
        "resolving `latest` no entry references.\n"
        "\n"
        "Staleness is computed from CONTENT, never mtime — a touched file with\n"
        "identical content is never stale. Three instruments, each anchored in\n"
        "content the current receipt records: the resolved theme's tokens\n"
        "digest; every file under the visual's source*/ directories against the\n"
        "receipt's git commit (trusted only when the receipt also records a\n"
        "clean worktree — a dirty worktree means the commit does not anchor the\n"
        "rendered inputs); and the receipt's per-frame content hashes against\n"
        "the delivered bytes (an immutable version modified after render). When\n"
        "no baseline exists — the reference corpus has a zero-commit\n"
        "repository, so every receipt records commit 'uncommitted' (audit F10)\n"
        "— staleness is reported `unknown` with the reason named. `unknown` is\n"
        "a legitimate verdict, not a failure.\n"
        "\n"
        "Anomalies are rows with their cause named, never omissions and never\n"
        "exit codes: a completed run exits 0 even with anomalies. The index is\n"
        "a status view, not a gate — the four ADR 0004 blocking conditions are\n"
        "validate's, and an index exit code would be a fifth gate by the back\n"
        "door. The index ranks, scores, and grades NOTHING: a quality-score\n"
        "column would be a failure of this skill, not a feature (ADR 0004).\n"
        "\n"
        "  --json  one versioned JSON object; the human table is rendered from\n"
        "          the same data\n"
        "\n"
        "Read-only: derived from the store on disk; writes nothing, including\n"
        "no git index refresh (GIT_OPTIONAL_LOCKS=0).\n"
        "\n"
        "Exit codes: 0 ok (a completed run, regardless of anomalies), 2 usage,\n"
        "3 unavailable (not an adopted project, or an invalid project config —\n"
        "run visuals init first)."
    ),
    backend="stdlib",
    handler="index_cmd",
)

INIT_SPEC = CommandSpec(
    name="init",
    usage="init [--json]",
    summary="Adopt a project: write visuals.toml describing the tree, touching nothing else.",
    help_text=(
        "Write a visuals.toml for the working directory's project — the one file\n"
        "that adopts a tree into the visuals contract layer. Everything else in\n"
        "the tree is left untouched; the only write is the config itself.\n"
        "\n"
        "Two shapes, chosen by evidence:\n"
        "\n"
        "  An existing visuals corpus (wrapper variants encoding viewports, a\n"
        "  registry/ledger/manifest, pre-render derive or data-refresh steps)\n"
        "  produces a DISCOVERED config describing what is actually there: the\n"
        "  canvas profiles in use (e.g. 1920x1080 slide and 1920x972 title-band),\n"
        "  the three contract-layer paths, and the pre-render hooks the wrappers\n"
        "  encode. Hooks are declared, never run, by init.\n"
        "\n"
        "  An empty directory produces the neutral SCAFFOLD: one 1920x1080\n"
        "  profile with zero insets, the default theme, contract paths to fill\n"
        "  in. Geometry and contract wiring only — no compositional opinion\n"
        "  (ADR 0004).\n"
        "\n"
        "  A visuals.toml already resolvable from the working directory: refuse,\n"
        "  exit 2, name the file. init never overwrites an adopted config.\n"
        "\n"
        "The generated config is validated by loading it back through the config\n"
        "loader before it is reported as written. --json emits a structured\n"
        "report of what was (or was not) written.\n"
        "\n"
        "Exit codes: 0 written, 1 the generated config failed validation (a\n"
        "defect, reported), 2 usage or already inside an adopted project."
    ),
    backend="stdlib",
    handler="init_cmd",
)

NEW_SPEC = CommandSpec(
    name="new",
    usage="new <kind> <slug> [--style <name>] [--force] [--json]",
    summary="Scaffold a new graphic's contract wiring — and nothing else; the canvas it emits is deliberately bare.",
    help_text=(
        "Create visuals/<slug>/ with the contract wiring a graphic needs and\n"
        "NOTHING more (ADR 0004): a BRIEF.md stub that is a form to fill in,\n"
        "never an example to edit; a source master whose preamble resolves the\n"
        "project theme and shared assets at the correct relative depth for where\n"
        "the file actually sits (a nested family 'family/demo' gets the depth it\n"
        "needs — audit F2); a frame manifest in the documented format; and a\n"
        "source-credit element. The canvas is deliberately bare: no layout, no\n"
        "type scale, no colour choice, no composition. A scaffold that produces\n"
        "a designed starting point is a defect in this skill.\n"
        "\n"
        "<kind> is one of: presentation, poster, figure, diagram. Kinds differ\n"
        "ONLY by the canvas profile they select: a profile named for the kind is\n"
        "used when the project config declares one, otherwise the project's\n"
        "default profile — the scaffold never invents geometry (ADR 0001). The\n"
        "selection and how it was made are reported and recorded in BRIEF.md.\n"
        "\n"
        "The project-level shared stylesheet visuals/_shared/theme.css is\n"
        "derived from the project's own theme reference — never hand-written —\n"
        "and is written once (reported as its own action) and reused after; a\n"
        "later scaffold never rewrites it.\n"
        "\n"
        "  --style NAME   use this project's [scaffold.NAME] wiring, which must\n"
        "                 name a declared [styles.NAME]. Includes, readiness,\n"
        "                 footer and canvas come only from that declaration;\n"
        "                 no shared theme file or style default is supplied.\n"
        "                 Without --style the 0.4.0 bare output is unchanged.\n"
        "\n"
        "  --force        scaffold into an existing directory writing ONLY the\n"
        "                 files that are absent. 'Force' here does NOT mean\n"
        "                 overwrite: no existing file is ever touched, so an\n"
        "                 edited BRIEF.md or source master is untouchable by\n"
        "                 construction; every skip is reported.\n"
        "\n"
        "Refusals: an existing visual directory without --force (exit 2, the\n"
        "path is named); a theme that cannot resolve (exit 3, before anything\n"
        "is written — a scaffold whose theme link dangles must never ship\n"
        "quietly); no adopted project resolvable from the working directory\n"
        "(exit 3; run 'visuals init' first).\n"
        "\n"
        "Exit codes: 0 scaffolded, 2 usage or refusal (existing directory),\n"
        "3 unavailable (no adopted project, unresolvable theme).\n"
    ),
    backend="stdlib",
    handler="new_cmd",
)

RENDER_SPEC = CommandSpec(
    name="render",
    usage="render <slug> [--check] [--into vX.Y.Z] [--unpublished]",
    summary="Render a visual into a new immutable version; optionally keep latest unchanged for review.",
    help_text=(
        "Render every frame of <slug>'s manifest (source/frames.txt) at the\n"
        "resolved canvas profile into a NEW immutable version directory.\n"
        "Rendering into an existing version directory is refused: the previous\n"
        "output is never mutated, and a failed render leaves the previous\n"
        "`latest` intact with no partial directory behind (ADR 0004 blockers\n"
        "1-4 are all loud failures here).\n"
        "\n"
        "Pages are served from the project root over 127.0.0.1 on a\n"
        "kernel-allocated port and driven headless via Chrome's debugging\n"
        "pipe. A page implementing the readiness signal (documentElement's\n"
        "dataset.ready, or data-ready) is captured when it reports ready; a\n"
        "page that implements the signal but never fires it fails loudly\n"
        "naming the frame; a page without the signal falls back to a bounded\n"
        "virtual-time budget — the receipt records which path each frame took\n"
        "(signal / fallback-budget), so the fallback is never silent.\n"
        "\n"
        "Every render writes receipt.json (timestamp, source, manifest, canvas\n"
        "profile and viewport, renderer name and version, repository commit\n"
        "and clean/dirty state, resolved theme and resolution steps, and per\n"
        "frame a name, byte count and SHA-256 content hash), a preview per\n"
        "frame, and a contact sheet for multi-frame visuals.\n"
        "\n"
        "  --check        render twice and compare content hashes; a mismatch is\n"
        "                 reported loudly in the receipt but the exit code stays\n"
        "                 0 — determinism is reported, not blocked (ADR 0004)\n"
        "  --into vX.Y.Z  explicit migration target; refused if it exists\n"
        "  --unpublished  keep latest unchanged until an explicit publish\n"
        "\n"
        "Exit codes: 0 rendered, 1 blocking render failure (missing manifest,\n"
        "a manifest line with no URL, a Chrome error, a zero-byte output, a\n"
        "source outside the project root — each names the cause), 2 usage,\n"
        "3 unavailable (no browser found; set CHROME=/path/to/chrome)."
    ),
    backend="uv",
    handler="render_cmd",
)

PROBE_SPEC = CommandSpec(
    name="probe",
    usage="probe <slug> [--version vX.Y.Z] [--execute] [--json]",
    summary="Test delivery-size comprehension with fresh agents; dry-run by default.",
    help_text=(
        "Read delivery-size previews from latest or --version and the visual's BRIEF.md. A fresh\n"
        "agent sees only each preview and minimal questions; a separate agent\n"
        "compares its response with the brief. Failed checks persist beside the\n"
        "visual and rerun after ordinary source edits. Changed brief intent or\n"
        "missing frames make a persisted check stale. This is an advisory\n"
        "comprehension instrument, never a design verdict or blocking gate.\n"
        "\n"
        "Default dry-run: no dispatch, quota cost, or write. --execute opts in\n"
        "to two Codex calls per frame and persists failed checks. --json emits\n"
        "the report. Exit 0 includes failed probes; exit 3 means unavailable."
    ),
    backend="stdlib",
    handler="probe_cmd",
)

PUBLISH_SPEC = CommandSpec(
    name="publish",
    usage="publish <slug> <vX.Y.Z>",
    summary="Promote a reviewed immutable version to latest after checking receipt and frame hashes.",
    help_text=(
        "Check the chosen version's receipt and every recorded frame hash, then\n"
        "atomically repoint latest. Use after inspecting all frames at full and\n"
        "delivery size. Refuses an absent, malformed, or changed version and\n"
        "leaves latest unchanged on failure. Exit 0 published, 1 invalid\n"
        "artifact, 2 usage, 3 no adopted project.\n"
    ),
    backend="stdlib",
    handler="publish_cmd",
)

SOURCES_SPEC = CommandSpec(
    name="sources",
    usage="sources list|verify|add <id> [...] [--registry PATH] [--json]",
    summary="Inspect, verify and extend the attribution source registry: assets re-hashed, https provenance required, SVG assets scanned.",
    help_text=(
        "  sources list     every declared source with its verification status\n"
        "  sources verify   re-hash every declared asset and re-check the contract\n"
        "  sources add      add one entry, refusing prose provenance\n"
        "\n"
        "The registry schema is the reference corpus's own (visuals/_shared/\n"
        "sources.json), which is its strongest existing provenance practice\n"
        "(audit F9). This command enforces it rather than replacing it:\n"
        "\n"
        "  - homepage and logo_source must be https URLs. The corpus's transluce\n"
        "    row records provenance as a sentence about a sibling repository\n"
        "    (audit F2); a reader cannot re-fetch a sentence, so `add` refuses it.\n"
        "  - every declared asset is re-hashed against its recorded digest, so an\n"
        "    asset changing under a published graphic is visible.\n"
        "  - a transformed asset keeps its untransformed original, that original's\n"
        "    own digest, and a prose description of the transform.\n"
        "  - an SVG asset is scanned for five kinds of active or external content\n"
        "    (script, foreignObject, embedded image, event-handler attribute, and\n"
        "    an external or data-URI reference). A logo is a shape, not a program.\n"
        "\n"
        "`add` computes digests itself and never accepts one from the caller: a\n"
        "caller-supplied digest verifies nothing. It writes nothing when the entry\n"
        "it was asked to add does not meet the contract.\n"
        "\n"
        "Source-registry findings are ADVISORY under ADR 0004, so `verify` reports\n"
        "them and still exits 0 — a registry defect is a provenance problem worth\n"
        "seeing, not a broken artifact.\n"
        "\n"
        "Exit codes: 0 ok (including with findings), 2 usage or a refused add,\n"
        "3 unavailable (not an adopted project, or no registry declared)."
    ),
    backend="stdlib",
    handler="sources_cmd",
)

THEME_SPEC = CommandSpec(
    name="theme",
    usage="theme list | show <name> [--json|--css|--palette] | check [<name>] [--json]",
    summary="Inspect and validate theme tokens: resolution steps, derived CSS and palette, advisory palette checks.",
    help_text=(
        "Resolve a theme through the four ADR 0005 steps (project config\n"
        "reference, project themes/ directory, user registry, bundled default)\n"
        "and report it. Every token is reported WITH the resolution step that\n"
        "supplied it, so a multi-step mixture is never folklore.\n"
        "\n"
        "  list                  every theme visible to resolution, with its step\n"
        "  show <name>           every resolved token with its step; --json for the\n"
        "                        machine-readable tokens, steps, palette and derived CSS\n"
        "                        (consumed by the render receipt); --css for the derived\n"
        "                        CSS custom-property block; --palette for the derived palette\n"
        "  check [<name>]        validate the chart palette: adjacent-pair perceptual\n"
        "                        distance (CIEDE2000) and WCAG 2.2 contrast for every\n"
        "                        declared foreground/background pair. Thresholds are\n"
        "                        cited in references/SOURCES.md; findings are ADVISORY\n"
        "                        and never block (ADR 0004) — the exit code is 0 even\n"
        "                        when pairs fail. Without a name, uses the project\n"
        "                        config's theme reference.\n"
        "\n"
        "Exit codes: 0 ok (including advisory findings), 2 usage (bad arguments,\n"
        "or a theme that exists but is schema-invalid — the offending key is\n"
        "named), 3 unavailable (the named theme is found in none of the four\n"
        "resolution locations). A theme found nowhere never silently falls back\n"
        "to the bundled default; only undeclared VALUES fall back to it.\n"
        "\n"
        "Read-only: the user registry ~/.config/visuals/themes/ is read, never\n"
        "written. The bundled default is brand-neutral by ADR 0005."
    ),
    backend="stdlib",
    handler="theme_cmd",
)

MEASURE_SPEC = CommandSpec(
    name="measure",
    usage="measure <slug> [--max-bytes N]",
    summary="Report selector-keyed scene geometry, rendered fonts, bounded background paint, and stage differences.",
    help_text=(
        "Measure every manifest frame of <slug> after render readiness. Emits a\n"
        "versioned JSON report with selector-keyed element and text geometry,\n"
        "platform fonts actually used for glyphs, bounded CSS background\n"
        "composition, contrast, sibling overlap, annotations, and geometry\n"
        "differences between stages. Unsupported paint returns null rather\n"
        "than an invented colour. No findings, severities, scores, or gates.\n"
        "The report is capped at 1 MB; overflow errors without partial JSON."
    ),
    backend="stdlib",
    handler="measure_cmd",
)

CHECK_SPEC = CommandSpec(
    name="check",
    usage="check <slug> [--output DIR] [--json]",
    summary="Evaluate project-selected advisory scene checks and emit a 640px contact sheet plus flagged crops.",
    help_text=(
        "Measure every manifest frame, evaluate only project-selected advisory\n"
        "gates, and emit a delivery-size contact sheet followed by full-size\n"
        "crops for flagged regions. Numeric thresholds and crop context come\n"
        "from visuals.toml check_thresholds; unknown paint is explicitly\n"
        "not-measurable. No finding affects the exit code. This command does\n"
        "not assess hierarchy, communication, or aesthetic quality.\n"
        "Exit codes: 0 completed regardless of findings, 1 execution error,\n"
        "2 usage, 3 unavailable browser."
    ),
    backend="uv",
    handler="check_cmd",
)

VALIDATE_SPEC = CommandSpec(
    name="validate",
    usage="validate [<slug>] [--json]",
    summary="Validate the visual contract: four blocking conditions, project-selected advisory findings, and both-direction consumer-join reconciliation.",
    help_text=(
        "Walk an adopted project (or one visual's store, with <slug>) and report\n"
        "findings in the two categories ADR 0004 fixes, skill-wide:\n"
        "\n"
        "  Blocking — exactly FOUR conditions exit 1, each a correctness defect\n"
        "  that makes the artifact broken as an artifact regardless of taste:\n"
        "  content clipped outside the canvas (delivered frame dimensions vs the\n"
        "  canvas its own receipt declares), a missing or dangling `latest`, an\n"
        "  absent receipt.json in a version directory, and a malformed output\n"
        "  name (the .png.png class). Adding a fifth blocking condition requires\n"
        "  an ADR — never a decision in code.\n"
        "\n"
        "  Advisory — every other finding: a severity, a location, and what\n"
        "  would make it pass, and NEVER an effect on the exit code. Fifty\n"
        "  advisory findings and no blocking condition exit 0. Which advisory\n"
        "  checks run is the project's choice (advisory_checks in\n"
        "  visuals.toml): master-contract checks ported from the reference\n"
        "  corpus's own validator (shared includes, visual-slide geometry,\n"
        "  source-credit, renderer-title ownership), source-registry\n"
        "  validation (every declared asset re-hashed, https provenance, SVG\n"
        "  assets scanned for active or external content), consumer-join\n"
        "  reconciliation (manifest entries naming visuals that do not exist,\n"
        "  AND built visuals with a resolving latest no entry references — both\n"
        "  directions), and store-integrity (zero-byte frames, receipts naming\n"
        "  files that do not exist). The report names the checks that did NOT\n"
        "  run, so a quiet report is distinguishable from a narrow one.\n"
        "\n"
        "Coverage is deliberately wider than the corpus validator's single-level\n"
        "glob: nested visual families, alternate masters, and redesign\n"
        "generations (source-v2/) are all checked. Without a slug, every visual\n"
        "under the project root is scanned.\n"
        "\n"
        "  <slug>  validate one visual (matched by directory name; project-wide\n"
        "          checks are skipped and reported as not run)\n"
        "  --json  one versioned object, findings keyed by location\n"
        "\n"
        "Read-only: validates, never fixes. The clipped-content instrument is\n"
        "structural until tasks 0011/0012 upgrade it to measured geometry; no\n"
        "measurement-derived findings are invented here.\n"
        "\n"
        "Exit codes: 0 ok (any number of advisory findings), 1 blocking\n"
        "condition, 2 usage, 3 unavailable (not an adopted project, or an\n"
        "invalid project config — run visuals init first)."
    ),
    backend="stdlib",
    handler="validate_cmd",
)

COMMAND_SPECS: tuple[CommandSpec, ...] = (
    BUMP_SPEC,
    CHECK_SPEC,
    DATA_SPEC,
    DOCTOR_SPEC,
    IMAGE_SPEC,
    IMPROVE_SPEC,
    INDEX_SPEC,
    INIT_SPEC,
    MEASURE_SPEC,
    NEW_SPEC,
    PROBE_SPEC,
    PUBLISH_SPEC,
    RENDER_SPEC,
    SOURCES_SPEC,
    THEME_SPEC,
    VALIDATE_SPEC,
)

COMMANDS: tuple[str, ...] = tuple(spec.name for spec in COMMAND_SPECS)
COMMAND_BY_NAME: dict[str, CommandSpec] = {spec.name: spec for spec in COMMAND_SPECS}

# Dependency-weight routing for uv-backend commands. Values are module filenames
# under scripts/cli/ with a PEP 723 header; the lockfile sits beside each script.
UV_ENTRYPOINTS: dict[str, str] = {
    "check": "check_cmd.py",
    "render": "render_cmd.py",
    "bump": "bump_cmd.py",
    "image": "image_cmd.py",
    "improve": "improve_cmd.py",
}

PROG = "visuals"


def validate_registry(specs: tuple[CommandSpec, ...]) -> None:
    """Reject duplicate, unknown-backend, or handler-less registrations."""
    names = tuple(spec.name for spec in specs)
    if len(names) != len(set(names)):
        raise ValueError("command registry contains duplicate names")
    for spec in specs:
        if spec.backend not in ("stdlib", "uv"):
            raise ValueError(f"command {spec.name}: unknown backend {spec.backend!r}")
        if spec.backend == "uv" and spec.name not in UV_ENTRYPOINTS:
            raise ValueError(
                f"command {spec.name}: uv backend without a UV_ENTRYPOINTS entry"
            )
        if not spec.summary or not spec.help_text:
            raise ValueError(f"command {spec.name}: empty summary or help_text")


validate_registry(COMMAND_SPECS)
