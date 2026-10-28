# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=10",
# ]
# ///
"""`visuals image` — capability-detecting delegate onto the image-generation skill.

ADR 0006: this command is a delegating shim, shipped on day one so the public
surface never breaks. It NEVER generates anything itself and carries no
provider knowledge — the delegate is the authority on providers. It exists to
put a generated image into the SAME contract layer as an authored render: an
immutable version directory, a receipt, a preview, and an atomically repointed
`latest`.

Detection and honest degradation, never a hard dependency: when the delegate is
absent the command reports it as unavailable (exit 3) naming every location
checked and how to install it — not an error, not a silent no-op, never a
traceback.

The receipt is a GENERATIVE receipt: `engine: "generative"`, the prompt
lineage, the provider and settings the delegate reports, and per-frame content
hashes. It carries none of the authored engine's measurement vocabulary — no
readiness, no determinism, no scene graph — because a generative output is
stochastic and verifiable only by looking (ADR 0003, Limits). A consumer can
tell generated from authored output from the receipt alone.

Paid calls are behind explicit opt-in: without `--execute` the command runs the
delegate's own dry-run (exact command and compiled prompt, nothing billed,
nothing written). No test in this factory spends quota.

Exit codes: 0 ok (dry-run or executed), 1 blocking failure (the delegate ran
and failed, or produced no output — cause named), 2 usage, 3 unavailable
(delegate absent, or no adopted project).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


class ImageCommandError(Exception):
    """A blocking failure of the delegate run. Message names the cause."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visuals image", add_help=False,
        description=(
            "Generate an image into the shared artifact store by delegating to\n"
            "the installed image-generation skill. Without --execute this is a\n"
            "dry-run: the delegate is capability-detected, the exact command and\n"
            "compiled prompt are shown, and nothing is written. The paid call is\n"
            "always an explicit opt-in."
        ),
    )
    parser.add_argument("slug", help="the visual's directory name under visuals/ (created on first generation)")
    parser.add_argument("--prompt", required=True, help="what to generate (passed to the delegate; required)")
    parser.add_argument(
        "--ref", action="append", default=[], metavar="PATH", dest="refs",
        help="reference image passed through to the delegate (repeatable)",
    )
    parser.add_argument(
        "--profile", default="auto", metavar="NAME",
        help="delegate profile passed through (the delegate owns the vocabulary; default auto)",
    )
    parser.add_argument("--label", help="label passed through to the delegate's lineage")
    parser.add_argument(
        "--into", metavar="vX.Y.Z",
        help="explicit version directory target (refused if it exists); "
             "otherwise the next version is derived from the store",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="perform the real (paid) generation; without this flag the command "
             "is a dry-run that costs nothing and writes nothing",
    )
    return parser


# --------------------------------------------------------------------------
# delegate invocation
# --------------------------------------------------------------------------


def delegate_generate_command(
    delegate, *, prompt: str, out: Path, refs: list[str], profile: str,
    label: str | None, dry_run: bool,
) -> list[str]:
    """The delegate's own CLI, invoked through whatever route detected it.

    No provider knowledge lives here: flags, profiles and backends are the
    delegate's surface, passed through verbatim.
    """
    command = [*delegate.invocation, "generate", "--prompt", prompt, "--out", str(out)]
    for ref in refs:
        command += ["--ref", ref]
    command += ["--profile", profile]
    if label:
        command += ["--label", label]
    if dry_run:
        command.append("--dry-run")
    if delegate.is_entrypoint:
        command.insert(0, "python3")  # a script entry point needs its interpreter
    return command


def run_delegate(command: list[str], *, capture: bool = True) -> str:
    """Run the delegate; return its stdout when captured."""
    try:
        proc = subprocess.run(
            command, capture_output=capture, text=True, timeout=1800,
        )
    except OSError as exc:
        raise ImageCommandError(f"cannot run the delegate: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ImageCommandError(f"delegate timed out after {exc.timeout}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ImageCommandError(
            f"delegate failed (exit {proc.returncode}): {detail or 'no output'}"
        )
    return proc.stdout or ""


def load_delegate_manifest(manifest_path: Path) -> dict | None:
    """Read the delegate's own manifest, or None when it did not write one.

    The manifest is copied into the version directory as provenance; its
    absence is a warning, never a failure — the delegate is the authority on
    what it records.
    """
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------
# receipt — the generative engine's own vocabulary
# --------------------------------------------------------------------------

#: Words that belong to the authored engine's measurement loop and must NEVER
#: appear in a generative receipt or its reporting (ADR 0003, Limits). The test
#: suite asserts this list stays absent.
FORBIDDEN_VOCABULARY = ("measured", "measurement", "readiness", "determinism", "scene graph")


def build_receipt(
    *,
    slug: str,
    version: str,
    delegate_route,
    prompt: str,
    profile: str,
    label: str | None,
    refs: list[dict],
    provider: str | None,
    manifest: dict | None,
    delegate_manifest_name: str | None,
    frames: list[dict],
    previews: list[str],
    warnings: list[str],
) -> dict:
    """Assemble the generative receipt.

    Everything here is provenance the generative engine can actually supply:
    prompt lineage (raw + the delegate's compiled prompt), the provider and
    settings the delegate reports, per-frame content hashes, and engine
    attribution. Receipts WITHOUT an `engine` field are authored receipts
    (documented reading); `engine: "generative"` makes this one distinguishable
    from the receipt alone (task 0014 criterion 3).
    """
    skill = (manifest or {}).get("skill", {})
    compiled_prompt = (manifest or {}).get("prompt")
    receipt: dict = {
        "schema_version": 1,
        "engine": "generative",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "visual": slug,
        "version": version,
        "delegate": {
            "skill": skill.get("name", "image-generation"),
            "version": skill.get("version"),
            "entrypoint": delegate_route.location,
            "route": delegate_route.kind,
            "manifest": delegate_manifest_name,
        },
        "generation": {
            "prompt": prompt,
            "compiled_prompt": compiled_prompt,
            "profile": profile,
            "label": label,
            "refs": refs,
            "provider": provider,
        },
        "frames": [dict(f) for f in frames],
        "previews": list(previews),
    }
    if warnings:
        receipt["warnings"] = list(warnings)
    return receipt


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------


def _resolve_visual_dir(root: Path, slug: str, store) -> Path:
    """Where this visual's store lives: candidates match render's convention
    (`<root>/visuals/<slug>`, then `<root>/<slug>`); created on first
    generation — a generated visual has no source master, the prompt is the
    lineage."""
    for cand in (root / "visuals" / slug, root / slug):
        if cand.is_dir() and store.existing_versions(cand):
            return cand
    return root / "visuals" / slug


def _refs_for_receipt(args_refs: list[str], manifest: dict | None, store) -> list[dict]:
    """Reference lineage: the delegate's own records when it wrote a manifest,
    otherwise hashes computed here — never invented."""
    manifest_refs = (manifest or {}).get("references")
    if isinstance(manifest_refs, list) and manifest_refs:
        return manifest_refs
    return [
        {"path": ref, "sha256": store.sha256_file(Path(ref))} for ref in args_refs
    ]


def main(argv: list[str]) -> int:
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse usage error -> the usage exit code
        return exc.code or 2

    import config  # noqa: PLC0415  (capability domain, lazy per seam contract)
    import delegate as delegate_mod
    import store  # noqa: PLC0415

    try:
        config_resolved = config.resolve_config(Path.cwd())
    except config.ConfigError as exc:
        print(f"visuals image: project config is invalid: {exc}", file=sys.stderr)
        return 3
    if config_resolved is None:
        print(
            "visuals image: not an adopted project — no visuals.toml found walking up "
            f"from {Path.cwd()}; run 'visuals init' first",
            file=sys.stderr,
        )
        return 3

    # Capability detection, before anything else: absence degrades honestly
    # (exit 3 naming the install path), never a crash and never a silent no-op.
    route = delegate_mod.resolve_delegate()
    if route is None:
        print(
            "visuals image: the image-generation delegate is not installed — "
            + delegate_mod.missing_detail(),
            file=sys.stderr,
        )
        return 3

    visual_dir = _resolve_visual_dir(config_resolved.root, args.slug, store)
    if args.into is not None:
        if not store.VERSION_RE.match(args.into):
            print(
                f"visuals image: --into {args.into!r} is not a version directory "
                "name (expected vX.Y.Z)",
                file=sys.stderr,
            )
            return 2
        version = args.into
    else:
        version = store.derive_next_version(visual_dir)

    if not args.execute:
        # Dry-run by default (task 0014 criterion 7): the delegate's own
        # --dry-run shows the exact command and compiled prompt, billing
        # nothing. Nothing is written here — no staging, no store writes.
        print(f"dry-run: delegate detected ({route.location})")
        run_delegate(
            delegate_generate_command(
                route, prompt=args.prompt, out=Path("frame-01.png"), refs=args.refs,
                profile=args.profile, label=args.label, dry_run=True,
            ),
            capture=False,
        )
        print(f"would write: {visual_dir / version} (frame-01.png + receipt.json + preview)")
        print("dry-run only: nothing was written and nothing was billed — "
              "re-run with --execute to generate")
        return 0

    warnings: list[str] = []

    def builder(staging: Path) -> None:
        out = staging / "frame-01.png"
        command = delegate_generate_command(
            route, prompt=args.prompt, out=out, refs=args.refs,
            profile=args.profile, label=args.label, dry_run=False,
        )
        run_delegate(command)
        if not out.is_file():
            raise ImageCommandError(f"delegate reported success without producing {out}")
        manifest_path = out.with_suffix(".manifest.json")
        manifest = load_delegate_manifest(manifest_path)
        if manifest is None:
            warnings.append(
                f"delegate wrote no manifest beside {out.name}; receipt records the "
                "invocation only"
            )
            manifest_name = None
        else:
            # The delegate's own manifest stays verbatim beside the frame (it
            # is already inside the staging directory); the receipt records it
            # by name — never copied into a second file (audit F7).
            manifest_name = manifest_path.name
            fmt = (manifest.get("output") or {}).get("format")
            if fmt and str(fmt).upper() not in ("PNG",):
                warnings.append(
                    f"delegate produced {fmt}, stored as frame-01.png; the mime the "
                    "delegate recorded is in the frame's manifest"
                )
        previews = store.emit_previews(staging, ["frame-01"], 640)
        frame = {
            "name": "frame-01",
            "bytes": out.stat().st_size,
            "sha256": store.sha256_file(out),
            "verification": "visual-only",
        }
        receipt = build_receipt(
            slug=args.slug, version=version, delegate_route=route,
            prompt=args.prompt, profile=args.profile, label=args.label,
            refs=_refs_for_receipt(args.refs, manifest, store),
            provider=(manifest or {}).get("backend"),
            manifest=manifest, delegate_manifest_name=manifest_name,
            frames=[frame],
            previews=[p.name for p in previews], warnings=warnings,
        )
        store.write_receipt(staging, receipt)

    try:
        target = store.stage_and_commit(visual_dir, version, builder)
    except store.StoreError as exc:
        print(f"visuals image: error: {exc}", file=sys.stderr)
        return 1
    except ImageCommandError as exc:
        print(f"visuals image: error: {exc}", file=sys.stderr)
        return 1
    store.repoint_latest(visual_dir, version)

    print(f"generated {args.slug} -> {target}")
    print(f"delegate: {route.location}")
    print(f"receipt: {target / 'receipt.json'}")
    print(f"latest -> {version}")
    for warning in warnings:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))