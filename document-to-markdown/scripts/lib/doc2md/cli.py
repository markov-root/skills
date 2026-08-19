"""``doc2md`` command-line surface.

Wires the owned stages together: resolve an explicit input, acquire bytes behind the untrusted-input
boundary, detect the media type, route to certified extractors, convert, persist an atomic run
bundle, and project the authoritative ``result.json`` plus a queryable-frontmatter ``document.md``.

Network fetches and any other external effect are opt-in: a URL input without ``--allow-network``
(or a network-permitting profile) is refused with exit code 3 rather than silently reaching out.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from doc2md import __version__
from doc2md.core.application import ConvertService
from doc2md.core.models import (
    ConversionPolicy,
    ConversionStatus,
    SourceDocument,
)
from doc2md.extract.registry import build_registry
from doc2md.inputs import InputRefusal, ReferenceKind, inspect_bytes, resolve_reference
from doc2md.quality.assess import DeterministicAssessor
from doc2md.route import HeuristicRouter
from doc2md.store import Acquisition, FilesystemArtifactStore, default_home
from doc2md.store.project import project_result

_MAX_LOCAL_BYTES = 200 * 1024 * 1024

_PROFILES: dict[str, dict[str, bool | None]] = {
    "fast": {"network": None},
    "balanced": {"network": None},
    "fidelity": {"network": None},
    "private": {"network": False},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_for(profile: str, *, allow_network: bool) -> ConversionPolicy:
    forced = _PROFILES.get(profile, {}).get("network")
    network = False if forced is False else allow_network
    return ConversionPolicy(allow_network=network)


class CliError(Exception):
    """A user-facing error carrying an explicit process exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@contextlib.contextmanager
def _quiet_backends() -> Iterator[None]:
    """Confine backend chatter (e.g. pymupdf's stdout banners) to stderr.

    The CLI's stdout is a machine contract (result JSON, or Markdown for ``--output -``); an
    extraction backend printing to stdout would corrupt it for a consumer piping to ``jq``.
    """

    with contextlib.redirect_stdout(sys.stderr):
        yield


def _acquire(
    reference: str,
    *,
    policy: ConversionPolicy,
) -> tuple[SourceDocument, Acquisition]:
    """Resolve and acquire bytes for one input behind the untrusted-input boundary."""

    if reference == "-":
        data = sys.stdin.buffer.read()
        inspected = inspect_bytes(data, display_name="<stdin>")
        return inspected.source, Acquisition(
            input="-", kind=inspected.detection.media_type
        )

    resolved = resolve_reference(reference)
    if resolved.kind is ReferenceKind.REMOTE_URL:
        if not policy.allow_network:
            raise CliError(
                "input is a URL but network access is not permitted; "
                "pass --allow-network or use a network-permitting profile",
                3,
            )
        from doc2md.fetch import StaticHttpFetcher

        fetched = StaticHttpFetcher().fetch_url(resolved.value)
        inspected = inspect_bytes(
            fetched.data,
            display_name=reference,
            declared_media_type=fetched.media_type,
        )
        return inspected.source, Acquisition(
            input=reference,
            source_url=resolved.value,
            kind=inspected.detection.media_type,
            retrieved_at=_now_iso(),
            fetch_layer="http",
        )

    path = Path(resolved.value)
    if path.stat().st_size > _MAX_LOCAL_BYTES:
        raise CliError(f"file exceeds the {_MAX_LOCAL_BYTES}-byte safety cap", 3)
    data = path.read_bytes()
    inspected = inspect_bytes(data, display_name=path.name)
    return inspected.source, Acquisition(
        input=reference,
        source_url=None,
        kind=inspected.detection.media_type,
        retrieved_at=_now_iso(),
        fetch_layer="local",
    )


def _convert(
    source: SourceDocument,
    acquisition: Acquisition,
    *,
    policy: ConversionPolicy,
) -> tuple[dict[str, object], int, str | None]:
    """Run a full conversion. Return the public result, the exit code, and a bundle path."""

    home = default_home()
    run_id = source.sha256[:16]
    store = FilesystemArtifactStore(acquisition=acquisition, home=home, run_id=run_id)
    with _quiet_backends():
        registry = build_registry(policy)
        if not registry.extractors:
            raise CliError("no extractors are available; run 'doc2md doctor'", 3)
        service = ConvertService(
            assessor=DeterministicAssessor(),
            router=HeuristicRouter(),
            artifacts=store,
        )
        result = service.convert(source, registry.extractors, policy=policy)

    bundle = store.bundle_path(run_id)
    bundle.mkdir(parents=True, exist_ok=True)
    public = project_result(
        result=result,
        source=source,
        acquisition=acquisition,
        run_id=run_id,
        bundle_path=str(bundle),
        markdown_path="document.md" if result.artifact is not None else None,
        doc2md_version=__version__,
    )
    (bundle / "result.json").write_text(
        json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    exit_code = {
        ConversionStatus.OK: 0,
        ConversionStatus.DEGRADED: 0,
        ConversionStatus.PAUSED: 2,
        ConversionStatus.FAILED: 1,
    }[result.status]
    return public, exit_code, str(bundle)


def _cmd_convert(args: argparse.Namespace) -> int:
    policy = _policy_for(args.profile, allow_network=args.allow_network)
    source, acquisition = _acquire(args.input, policy=policy)
    public, exit_code, bundle = _convert(source, acquisition, policy=policy)

    if args.output == "-":
        if bundle is not None and (Path(bundle) / "document.md").exists():
            body = (Path(bundle) / "document.md").read_text(encoding="utf-8")
            sys.stdout.write(_strip_frontmatter(body))
        return exit_code
    if args.json or args.output is None:
        sys.stdout.write(json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    if args.output:
        document = Path(bundle) / "document.md" if bundle else None
        if document is not None and document.exists():
            Path(args.output).write_text(
                document.read_text(encoding="utf-8"), encoding="utf-8"
            )
    return exit_code


def _strip_frontmatter(document: str) -> str:
    if document.startswith("---\n"):
        end = document.find("\n---\n", 4)
        if end != -1:
            return document[end + len("\n---\n") :].lstrip("\n")
    return document


def _read_manifest(path: Path) -> list[str]:
    """Parse a newline-delimited manifest of inputs (blank lines and '#' comments ignored)."""

    inputs: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            inputs.append(stripped)
    return inputs


def run_batch(
    inputs: list[str],
    *,
    policy: ConversionPolicy,
    home: Path,
    batch_id: str,
    resume: bool,
) -> dict[str, object]:
    """Convert each input sequentially, isolating failures and checkpointing after every item.

    Sequential by design: on a 2-vCPU VM one heavy extraction (a large PDF) already saturates
    resources, so the enforced concurrency ceiling is 1. Progress is written to
    ``batches/<batch_id>/batch.json`` after each item, so an interrupted run resumes by skipping
    inputs already recorded as done.
    """

    batch_dir = home / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    record_path = batch_dir / "batch.json"

    done: dict[str, dict[str, object]] = {}
    if resume and record_path.exists():
        prior = json.loads(record_path.read_text(encoding="utf-8"))
        for item in prior.get("items", []):
            if item.get("status") in {"ok", "degraded"}:
                done[str(item["input"])] = item

    items: list[dict[str, object]] = []
    for reference in inputs:
        if reference in done:
            entry = dict(done[reference])
            entry["resumed"] = True
            items.append(entry)
        else:
            items.append(_batch_one(reference, policy=policy))
        _write_json(record_path, _batch_summary(batch_id, items))
    return _batch_summary(batch_id, items)


def _batch_one(reference: str, *, policy: ConversionPolicy) -> dict[str, object]:
    """Convert one input, converting any failure into a recorded item rather than aborting."""

    try:
        source, acquisition = _acquire(reference, policy=policy)
        public, exit_code, bundle = _convert(source, acquisition, policy=policy)
        status = str(public["status"])
        return {
            "input": reference,
            "status": status,
            "run_id": public["run_id"],
            "bundle_path": bundle,
            "exit_code": exit_code,
        }
    except (CliError, InputRefusal, OSError, ValueError) as error:
        return {
            "input": reference,
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }


def _batch_summary(batch_id: str, items: list[dict[str, object]]) -> dict[str, object]:
    counts = {"ok": 0, "degraded": 0, "failed": 0, "resumed": 0}
    for item in items:
        status = str(item.get("status"))
        if status in counts:
            counts[status] += 1
        if item.get("resumed"):
            counts["resumed"] += 1
    return {
        "batch_id": batch_id,
        "total": len(items),
        "counts": counts,
        "items": items,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _cmd_batch(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    if not manifest.exists():
        raise CliError(f"manifest not found: {args.manifest}", 3)
    inputs = _read_manifest(manifest)
    if not inputs:
        raise CliError("manifest contains no inputs", 3)
    policy = _policy_for(args.profile, allow_network=args.allow_network)
    batch_id = sha256(manifest.read_bytes()).hexdigest()[:16]
    summary = run_batch(
        inputs,
        policy=policy,
        home=default_home(),
        batch_id=batch_id,
        resume=args.resume,
    )
    sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    counts = summary["counts"]
    assert isinstance(counts, dict)
    return 1 if counts["failed"] else 0


def _cmd_plan(args: argparse.Namespace) -> int:
    policy = _policy_for(args.profile, allow_network=args.allow_network)
    resolved = resolve_reference(args.input) if args.input != "-" else None
    with _quiet_backends():
        registry = build_registry(policy)
    if resolved is not None and resolved.kind is ReferenceKind.REMOTE_URL:
        plan = {
            "input": args.input,
            "kind": "remote-url",
            "requires": "network",
            "network_permitted": policy.allow_network,
            "available_adapters": [c.adapter_id for c in registry.extractors],
        }
        sys.stdout.write(json.dumps(plan, indent=2) + "\n")
        return 0
    source, _ = _acquire(args.input, policy=policy)
    eligible = [
        c.adapter_id
        for c in registry.extractors
        if source.media_type in c.adapter.capabilities.media_types
    ]
    plan = {
        "input": args.input,
        "media_type": source.media_type,
        "eligible_adapters": eligible,
        "available_adapters": [c.adapter_id for c in registry.extractors],
    }
    sys.stdout.write(json.dumps(plan, indent=2) + "\n")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    import shutil

    with _quiet_backends():
        registry = build_registry()
    report = {
        "doc2md_version": __version__,
        "available_adapters": [c.adapter_id for c in registry.extractors],
        "unavailable_adapters": list(registry.unavailable),
        "external_tools": {"pdftotext": bool(shutil.which("pdftotext"))},
        "home": str(default_home()),
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    result_path = default_home() / "runs" / args.run_id / "result.json"
    if not result_path.exists():
        raise CliError(f"no run found for id {args.run_id}", 3)
    sys.stdout.write(result_path.read_text(encoding="utf-8"))
    return 0


def _cmd_contract(args: argparse.Namespace) -> int:
    contract = {
        "result_schema_version": 1,
        "frontmatter_schema_version": 1,
        "commands": ["convert", "plan", "show", "doctor", "contract", "version"],
        "exit_codes": {"0": "usable", "1": "failed", "2": "paused", "3": "invalid"},
    }
    sys.stdout.write(json.dumps(contract, indent=2) + "\n")
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    sys.stdout.write(f"doc2md {__version__}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc2md", description="Document to Markdown")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--profile", default="balanced", choices=sorted(_PROFILES))
        p.add_argument("--allow-network", action="store_true")

    convert = sub.add_parser("convert", help="convert an input to Markdown")
    convert.add_argument("input")
    convert.add_argument("--output", "-o", default=None)
    convert.add_argument("--json", action="store_true")
    _add_common(convert)
    convert.set_defaults(func=_cmd_convert)

    plan = sub.add_parser("plan", help="report eligible routes without extracting")
    plan.add_argument("input")
    _add_common(plan)
    plan.set_defaults(func=_cmd_plan)

    batch = sub.add_parser("batch", help="convert a manifest of inputs, resumably")
    batch.add_argument(
        "manifest", help="newline-delimited file of inputs (# comments allowed)"
    )
    batch.add_argument(
        "--resume",
        action="store_true",
        help="skip inputs already recorded as ok/degraded in this batch",
    )
    _add_common(batch)
    batch.set_defaults(func=_cmd_batch)

    show = sub.add_parser("show", help="print a run's result.json")
    show.add_argument("run_id")
    show.set_defaults(func=_cmd_show)

    doctor = sub.add_parser("doctor", help="report capability readiness")
    doctor.set_defaults(func=_cmd_doctor)

    contract = sub.add_parser("contract", help="print the stable contract summary")
    contract.set_defaults(func=_cmd_contract)

    version = sub.add_parser("version", help="print the doc2md version")
    version.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except CliError as error:
        sys.stderr.write(f"error: {error}\n")
        return error.code
    except InputRefusal as refusal:
        sys.stderr.write(f"input refused: {refusal}\n")
        return 3
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
