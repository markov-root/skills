#!/usr/bin/env python3
"""Command-line orchestration for skill-feedback.

Record outcomes and improvement observations across skills.

Selective praise, friction, bugs, wishes, and ideas land in the target skill's
own ``docs/feedback/YYYY-MM-DD.md``. Privacy-safe invocation and lifecycle events
land in a shared append-only JSONL ledger outside source repositories.

Resolution and portfolio coverage discover skills from the installed harness
skill directories and writable source artifacts under ``SKILLS_HOME/<name>/public``.
``SKI_REGISTRY`` remains an explicit test/operator override; an explicit
``SKILL_MANAGER_COMMAND`` is honoured only when set, for compatibility with an
instrumented manager. Stdlib only (Python 3.11+ for ``tomllib``); no venv
needed.

Usage:
  skill-feedback <skill> "<note>"        # record a note (see --kind)
  skill-feedback praise <skill> "..."    # noteworthy positive value
  skill-feedback friction <skill> "..."  # noteworthy negative friction
  skill-feedback start <skill> [...]      # begin an invocation; prints its id
  skill-feedback finish <skill> <id> [...]# finish an invocation
  skill-feedback run <skill> -- COMMAND    # transparent instrumented CLI boundary
  skill-feedback wrapper <skill> [...]     # plan/reconcile a source-owned adapter
  skill-feedback coverage [--check]        # audit automatic portfolio coverage
  skill-feedback onboard [<skill>]         # post-install feedback readiness plan
  skill-feedback events [filters]         # inspect the shared event ledger
  skill-feedback stats [filters]          # denominator-aware portfolio summary
  skill-feedback doctor [--json]          # inspect privacy and ledger health
  skill-feedback export [filters]          # export selected events
  skill-feedback delete [filters]          # dry-run targeted event deletion
  skill-feedback retention [--days N]      # configure/plan/apply expiry
  skill-feedback collection [MODE]         # permit/disable manifest opt-ins
  skill-feedback <skill> -               # read the note from stdin
  echo "..." | skill-feedback <skill>    # same, piped
  skill-feedback list [<skill>]          # show recorded notes
  skill-feedback review [--since DATE]   # aggregate open notes across all skills
  skill-feedback privacy-check [<skill>] # audit qualitative note content
  skill-feedback where <skill>           # print the feedback dir it would use
  skill-feedback deliver [<skill>]       # preview/apply pending-note delivery

Options for recording:
  --kind {wish,friction,bug,praise,idea}  default: wish
  --feature NAME    exact capability/command responsible
  --invocation ID   link the observation to a use
  --source SOURCE   provenance of the observation
  --impact LEVEL    low, medium, high, or unknown
  --outcome STATUS  success, partial, failure, abandoned, or unknown
  --evidence REF    repeatable evidence reference; content is not ingested
  --by NAME        author label (default: $SKILL_FEEDBACK_BY or "agent")
  --session ID     session id (default: $CLAUDE_SESSION_ID if set)
  --tag TAG        repeatable freeform tag
  --privacy-reviewed  acknowledge likely-sensitive content after review
  --dir PATH       write here instead of resolving from the registry
  --json           machine-readable result
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .inventory import (
    AGENTS_SKILLS,
    CLAUDE_SKILLS,
    CODEX_SKILLS,
    _inventory,
    _path_is_writable,
    feedback_dir,
)
from .model import (
    ACTOR_TYPES,
    DELIVERY_STATES,
    EVENT_SCHEMA_VERSION,
    EVENT_TYPES,
    IMPACTS,
    KINDS,
    OUTCOMES,
    PRIVACY_CONFIG_VERSION,
    SIGNALS,
    SKILL_NAME_PATTERN,
    SOURCES,
    STATUSES,
    WRAPPER_MARKER,
    WRAPPER_SCHEMA_VERSION,
    DeliveryBlocked,
    FeedbackError,
    IntegrityConflict,
    evaluate_transition,
    _body_sha256,
    _default_signal,
    _default_status,
    _entry_sha256,
    _new_id,
    _now,
    _parse_timestamp,
    _positive_int,
    _safe_header_value,
    _stable_event_id,
    _utc_now,
    _validate_event,
    _validate_skill_name,
)
from .privacy import (
    acknowledge_review,
    build_review_request,
    _enforce_qualitative_privacy,
    _likely_secret_fields,
    _privacy_finding_summary,
    _text_privacy_findings,
)
from .read_model import (
    GROUP_DIMENSIONS,
    _delivery_plan_for_skill,
    _inspect_event_ledger,
    _inspect_note_storage,
    _inspect_qualitative_privacy,
    _migrate_note_sessions,
    _parse_entries,
    _parse_entries_unlocked,
    authoritative_entries,
    authorize_delivery,
    body_handle_for,
    build_closeout,
    build_stats,
    metadata_views,
    reconcile_disposition_status,
)
from .storage import (
    FEEDBACK_HOME,
    _append_event,
    _append_event_once,
    _default_privacy_config,
    _event_lock_path,
    _event_path,
    _file_lock,
    _managed_note_records,
    _note_outbox_dir,
    _notes_lock_path,
    _privacy_config_path,
    _private_mode,
    _read_delivery_sidecar,
    _read_events,
    _read_events_unlocked,
    _read_object_sidecar,
    _read_privacy_config,
    _session_hash_key,
    _session_key_lock_path,
    _session_key_path,
    _write_events_unlocked,
    _write_json_atomic,
    _write_privacy_config,
    _write_text_atomic,
    apply_delivery,
)


def _session_id(explicit: str | None = None) -> str | None:
    return explicit or next(
        (
            os.environ[name]
            for name in ("CLAUDE_SESSION_ID", "CODEX_THREAD_ID", "OPENCODE_SESSION_ID")
            if os.environ.get(name)
        ),
        None,
    )


def _harness(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("SKILL_FEEDBACK_HARNESS")


def _stored_session_id(explicit: str | None = None) -> str | None:
    raw = _session_id(explicit)
    if raw is None or raw.startswith("hmac-sha256:"):
        return raw
    digest = hmac.new(_session_hash_key(), raw.encode(), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def _build_event(
    *,
    event_type: str,
    skill: str,
    invocation_id: str | None,
    payload: dict,
    skill_version: str | None = None,
    session: str | None = None,
    harness: str | None = None,
    actor_type: str = "agent",
    actor_id: str | None = None,
    source: str = "agent_judgment",
    task_class: str | None = None,
    tags: list[str] | None = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
) -> dict:
    _validate_skill_name(skill)
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event_id or _new_id("evt"),
        "event_type": event_type,
        "occurred_at": occurred_at or _utc_now(),
        "skill": {"name": skill, "version": skill_version},
        "invocation_id": invocation_id,
        "session": {"id": _stored_session_id(session), "harness": _harness(harness)},
        "actor": {"type": actor_type, "id": actor_id},
        "source": source,
        "task": {"class": task_class},
        "tags": list(dict.fromkeys(tags or [])),
        "privacy": {"content_included": False, "redacted": False},
        "payload": payload,
    }
    _validate_event(event)
    secret_fields = _likely_secret_fields(event)
    if secret_fields:
        raise FeedbackError(
            "likely secret detected in structured event field(s): "
            + ", ".join(secret_fields)
            + "; store a non-sensitive reference instead"
        )
    return event


def _event_filters(args: argparse.Namespace) -> dict:
    def values(name: str) -> list[str]:
        value = getattr(args, name, None)
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    sessions = values("session")
    return {
        "event_ids": values("event_id"),
        "skills": values("skill"),
        "invocations": values("invocation"),
        "sessions": [
            stored
            for value in sessions
            if (stored := _stored_session_id(value)) is not None
        ],
        "event_types": values("event_type"),
        "before": getattr(args, "before", None),
        "after": getattr(args, "after", None),
    }


def _select_events(events: list[dict], filters: dict) -> list[dict]:
    before = (
        _parse_timestamp(filters["before"], "--before") if filters["before"] else None
    )
    after = _parse_timestamp(filters["after"], "--after") if filters["after"] else None
    selected = []
    for event in events:
        occurred = _parse_timestamp(event["occurred_at"], "event occurred_at")
        if filters["event_ids"] and event["event_id"] not in filters["event_ids"]:
            continue
        if filters["skills"] and event["skill"]["name"] not in filters["skills"]:
            continue
        if (
            filters["invocations"]
            and event.get("invocation_id") not in filters["invocations"]
        ):
            continue
        if (
            filters["sessions"]
            and (event.get("session") or {}).get("id") not in filters["sessions"]
        ):
            continue
        if filters["event_types"] and event["event_type"] not in filters["event_types"]:
            continue
        if before and occurred >= before:
            continue
        if after and occurred < after:
            continue
        selected.append(event)
    return selected


def _has_event_selector(args: argparse.Namespace) -> bool:
    filters = _event_filters(args)
    return any(
        (
            filters["event_ids"],
            filters["skills"],
            filters["invocations"],
            filters["sessions"],
            filters["event_types"],
            filters["before"],
            filters["after"],
        )
    )


def _filter_summary(filters: dict) -> dict:
    return {key: value for key, value in filters.items() if value not in (None, [])}


def known_skills() -> list[str]:
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


def _automatic_coverage() -> dict:
    inventory = _inventory()
    entries: list[dict] = []
    for inventory_entry in inventory["entries"]:
        skill = inventory_entry["name"]
        if inventory_entry["invalid"]:
            entries.append(
                {
                    "skill": skill,
                    "status": "invalid_manifest",
                    "automatic": False,
                    "detail": inventory_entry["invalid"],
                    "commands": [],
                }
            )
            continue
        raw_source = inventory_entry["source"]
        source = Path(os.path.expanduser(raw_source)) if raw_source else None
        common = {
            "skill": skill,
            "capability": inventory_entry["capability"],
            "invoke": inventory_entry["invoke"],
            "source": str(source) if source is not None else None,
        }
        declared = inventory_entry["executables"]
        if skill == "skill-feedback":
            entries.append(
                {
                    **common,
                    "status": "self_exempt",
                    "automatic": False,
                    "detail": "self-wrapping would recurse",
                    "commands": sorted(declared),
                }
            )
            continue
        if not declared:
            status = (
                "emitter_required"
                if inventory_entry["capability"] == "mcp"
                else "no_declared_cli_boundary"
            )
            entries.append(
                {
                    **common,
                    "status": status,
                    "automatic": False,
                    "detail": (
                        "instrument the MCP/server boundary"
                        if status == "emitter_required"
                        else "declare a reliable CLI boundary or use explicit start/finish"
                    ),
                    "commands": [],
                }
            )
            continue

        commands: list[dict] = []
        for command, raw_target in sorted(declared.items()):
            target = Path(os.path.expanduser(raw_target))
            if not target.is_absolute() and source is not None:
                target = (source / target).resolve()
            elif target.is_absolute():
                target = target.resolve()
            instrumented = False
            if target.is_file():
                try:
                    with target.open(encoding="utf-8") as handle:
                        instrumented = WRAPPER_MARKER in handle.read(4096)
                except (OSError, UnicodeDecodeError):
                    pass
            commands.append(
                {
                    "command": command,
                    "target": str(target),
                    "instrumented": instrumented,
                }
            )
        automatic = bool(commands) and all(item["instrumented"] for item in commands)
        entries.append(
            {
                **common,
                "status": "instrumented" if automatic else "adapter_missing",
                "automatic": automatic,
                "detail": (
                    "every declared CLI crosses a Feedback-owned adapter"
                    if automatic
                    else "one or more declared CLIs bypass Feedback"
                ),
                "commands": commands,
            }
        )
    declared = [
        entry
        for entry in entries
        if entry["status"]
        not in {"self_exempt", "no_declared_cli_boundary", "emitter_required"}
    ]
    reliable_cli_complete = bool(declared) and all(
        entry["automatic"] for entry in declared
    )
    portfolio_complete = bool(entries) and all(
        entry["status"] in {"instrumented", "self_exempt"} for entry in entries
    )
    return {
        "version": 1,
        "command": "coverage",
        "inventory": {
            "ready": inventory["ready"],
            "source": inventory["source"],
            "contract_version": inventory["contract_version"],
            "count": len(inventory["entries"]),
            "error": inventory["error"],
        },
        "portfolio_complete": portfolio_complete,
        "reliable_cli_complete": reliable_cli_complete,
        "counts": {
            status: sum(entry["status"] == status for entry in entries)
            for status in sorted({entry["status"] for entry in entries})
        },
        "entries": entries,
    }


def _onboarding_for_entry(entry: dict, operator_ready: bool) -> dict:
    status = entry["status"]
    steps: list[dict[str, str]] = []
    if status in {"no_declared_cli_boundary", "adapter_missing"}:
        select_action = (
            "Determine where real skill use enters: a public CLI, an MCP/server "
            "dispatcher, or a harness activation. Do not substitute an optional "
            "helper or deprecated alias for primary skill activation."
            if status == "no_declared_cli_boundary"
            else (
                "Confirm every declared command is a boundary agents actually "
                "invoke and document its exit, signal, retry, credential, billing, "
                "and resume semantics."
            )
        )
        generate_action = (
            "For a stable CLI, run `skill-feedback wrapper SKILL --feature "
            "FEATURE --target REAL_EXECUTABLE --output REPOSITORY_ADAPTER --apply` "
            "and declare expected nonzero successes. For MCP or harness activation, "
            "emit the shared start/finish contract there; if no reliable callback "
            "exists, keep explicit start/finish and report the limitation."
            if status == "no_declared_cli_boundary"
            else (
                "Run `skill-feedback wrapper SKILL --feature FEATURE --target "
                "REAL_EXECUTABLE --output REPOSITORY_ADAPTER --apply`; declare every "
                "expected nonzero success with `--success-exit-code`."
            )
        )
        publish_action = (
            "Publish the selected boundary from canonical source. For a CLI, commit "
            "the generated adapter beside the skill in its `scripts/` so skills.sh "
            "installs it as an ordinary executable; feature-only telemetry must stay "
            "labeled partial rather than implying whole-skill coverage."
            if status == "no_declared_cli_boundary"
            else (
                "Commit the generated adapter beside the skill in its `scripts/` "
                "so skills.sh installs it as an ordinary executable."
            )
        )
        steps.extend(
            [
                {
                    "id": "select-boundary",
                    "action": select_action,
                    "why": "Wrapping an unused alias produces false coverage.",
                },
                {
                    "id": "generate-adapter",
                    "action": generate_action,
                    "why": "Emission must occur at the boundary that observes real use.",
                },
                {
                    "id": "publish-adapter",
                    "action": publish_action,
                    "why": "Every harness and a fresh checkout must use the same boundary.",
                },
                {
                    "id": "verify-boundary",
                    "action": (
                        "Test no-cost success, expected nonzero success, ordinary failure, "
                        "signal behavior, privacy-off fallback, and missing-Feedback "
                        "fallback; add paid/resume pilots where applicable."
                    ),
                    "why": "Process transparency and semantic outcomes are capability-specific.",
                },
            ]
        )
    elif status == "emitter_required":
        steps.append(
            {
                "id": "instrument-emitter",
                "action": (
                    "Emit the shared start/finish contract at the MCP server or tool "
                    "dispatcher boundary and test retries, cancellation, and errors."
                ),
                "why": "A CLI wrapper cannot observe an MCP call that bypasses it.",
            }
        )
    elif status == "invalid_manifest":
        steps.append(
            {
                "id": "repair-manifest",
                "action": "Repair and validate the inventory override manifest.",
                "why": "Feedback cannot derive a trustworthy boundary from invalid inventory.",
            }
        )

    adapter_ready = status == "instrumented"
    if adapter_ready and not operator_ready:
        steps.append(
            {
                "id": "enable-local-collection",
                "action": (
                    "Choose retention with `skill-feedback retention --forever` or "
                    "`--days N`, then run "
                    "`skill-feedback collection --manifest-opt-in`."
                ),
                "why": "Automatic collection is locally disabled until privacy policy is explicit.",
            }
        )
    if status not in {"self_exempt", "invalid_manifest"}:
        steps.append(
            {
                "id": "check-coverage",
                "action": (
                    "Run `skill-feedback coverage --check --declared-only`; use strict "
                    "`coverage --check` for the complete portfolio gate."
                ),
                "why": "Inventory-derived coverage detects future drift and new installations.",
            }
        )

    feedback_ready = adapter_ready and operator_ready
    if status == "self_exempt":
        feedback_ready = True
    return {
        **entry,
        "adapter_ready": adapter_ready,
        "operator_ready": operator_ready,
        "feedback_ready": feedback_ready,
        "action_required": not feedback_ready,
        "steps": steps,
    }


def cmd_onboard(args: argparse.Namespace) -> int:
    coverage = _automatic_coverage()
    inventory = coverage["inventory"]
    selected = coverage["entries"]
    if args.skill:
        selected = [entry for entry in selected if entry["skill"] == args.skill]
        if not selected:
            if not inventory["ready"]:
                raise FeedbackError(
                    f"cannot onboard {args.skill!r}: {inventory['error']}"
                )
            raise FeedbackError(f"unknown installed skill {args.skill!r}")
    try:
        config, configured = _read_privacy_config()
        operator_ready = (
            configured
            and config["automatic_collection"] == "manifest_opt_in"
            and config["retention"]["mode"] != "unset"
        )
    except FeedbackError:
        operator_ready = False
    skills = [_onboarding_for_entry(entry, operator_ready) for entry in selected]
    inventory_action_required = not inventory["ready"]
    result = {
        "version": 1,
        "command": "onboard",
        "inventory": inventory,
        "operator_ready": operator_ready,
        "action_required_count": (
            sum(item["action_required"] for item in skills)
            + int(inventory_action_required)
        ),
        "skills": skills,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if inventory_action_required:
            print(f"inventory: action required ({inventory['error']})")
        for item in skills:
            readiness = "ready" if item["feedback_ready"] else "action required"
            print(f"{item['skill']}: {readiness} ({item['status']})")
            for index, step in enumerate(item["steps"], start=1):
                print(f"  {index}. {step['action']}")
    return 1 if args.check and result["action_required_count"] else 0


def cmd_coverage(args: argparse.Namespace) -> int:
    result = _automatic_coverage()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        inventory = result["inventory"]
        print(
            f"inventory: {'ready' if inventory['ready'] else 'unavailable'} "
            f"({inventory['source']}, {inventory['count']} capabilities)"
        )
        if inventory["error"]:
            print(f"inventory detail: {inventory['error']}")
        for entry in result["entries"]:
            print(f"{entry['skill']}: {entry['status']} — {entry['detail']}")
        print(
            "declared CLI coverage: "
            + ("complete" if result["reliable_cli_complete"] else "incomplete")
        )
        print(
            "portfolio automatic coverage: "
            + ("complete" if result["portfolio_complete"] else "incomplete")
        )
    checked = (
        result["reliable_cli_complete"]
        if args.declared_only
        else result["portfolio_complete"]
    )
    checked = checked and result["inventory"]["ready"]
    return 0 if not args.check or checked else 1


def _feedback_write_target(
    name: str, override: str | None = None
) -> tuple[Path, str, Path]:
    intended = feedback_dir(name, override)
    if _path_is_writable(intended):
        return intended, "source", intended
    return _note_outbox_dir(name), "pending", intended


def _read_note(value: str | None) -> str:
    if value and value != "-":
        if value.strip():
            return value
    if value == "-" or not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return text
    raise FeedbackError("no note given: pass it as an argument, as '-', or via stdin")


def _skill_relative_note_location(
    skill: str, target: Path, path: Path, delivery: str
) -> str:
    if delivery == "pending":
        return f"note-outbox/{skill}/docs/feedback/{path.name}"
    repo_root = target.parent.parent
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise FeedbackError(
            f"note path {path} is outside its resolved skill repository {repo_root}"
        ) from exc


def cmd_record(args: argparse.Namespace) -> int:
    note = _read_note(args.note)
    privacy_findings = _enforce_qualitative_privacy(
        note,
        reviewed=args.privacy_reviewed,
        label="qualitative feedback note",
    )
    now = _now()
    target, delivery, intended = _feedback_write_target(args.skill, args.dir)

    author = _safe_header_value(
        "author", args.by or os.environ.get("SKILL_FEEDBACK_BY", "agent")
    )
    session = _safe_header_value("session", _stored_session_id(args.session))
    signal = args.signal or _default_signal(args.kind)
    status = _default_status(args.kind)
    feature = _safe_header_value("feature", args.feature)
    invocation = _safe_header_value("invocation", args.invocation)
    tags = []
    for tag in args.tag or []:
        safe_tag = _safe_header_value("tag", tag)
        if "," in safe_tag:
            raise FeedbackError("tag cannot contain a comma")
        tags.append(safe_tag)
    privacy_findings.extend(
        _enforce_qualitative_privacy(
            json.dumps(
                {
                    "author": author,
                    "feature": feature,
                    "invocation": invocation,
                    "tags": tags,
                    "evidence": args.evidence or [],
                    "skill_version": args.skill_version,
                    "task_class": args.task_class,
                },
                sort_keys=True,
            ),
            reviewed=args.privacy_reviewed,
            label="qualitative feedback metadata",
        )
    )

    path = target / f"{now:%Y-%m-%d}.md"
    meta = [f"{now:%H:%M}", args.kind, author]
    feedback_id = _new_id("fb")
    meta.append(f"id={feedback_id}")
    if session:
        meta.append(f"session={session}")
    if tags:
        meta.append("tags=" + ",".join(tags))
    for key, value in (
        ("feature", feature),
        ("invocation", invocation),
        ("signal", signal),
        ("source", args.source),
        ("impact", args.impact),
        ("outcome", args.outcome),
    ):
        if value:
            meta.append(f"{key}={_safe_header_value(key, value)}")

    header = " · ".join(meta)
    body_sha256 = _body_sha256(note)
    entry_sha256 = _entry_sha256(header, note)

    event = _build_event(
        event_type="observation.recorded",
        skill=args.skill,
        skill_version=args.skill_version,
        invocation_id=invocation,
        session=session,
        harness=args.harness,
        actor_type=args.actor,
        actor_id=author,
        source=args.source,
        task_class=args.task_class,
        tags=tags,
        payload={
            "feedback_id": feedback_id,
            "kind": args.kind,
            "signal": signal,
            "feature": feature,
            "impact": args.impact,
            "outcome": args.outcome,
            "evidence": args.evidence or [],
            "note_sha256": hashlib.sha256(note.encode()).hexdigest(),
            "note_digest": {
                "algorithm": "sha256",
                "canonicalization": "body-v1",
                "sha256": body_sha256,
            },
            "canonicalization": "body-v1",
            "entry_sha256": entry_sha256,
            "record_sha256": entry_sha256,
            "note_file": _skill_relative_note_location(
                args.skill, target, path, delivery
            ),
            "delivery": delivery,
        },
    )

    target.mkdir(parents=True, exist_ok=True)
    block = f"### {header}\n\n{note}\n\n"
    with _file_lock(_notes_lock_path(), private=True):
        new_file = not path.exists()
        with path.open("a", encoding="utf-8") as handle:
            if new_file:
                handle.write(f"# Feedback — {args.skill} — {now:%Y-%m-%d}\n\n")
                handle.write(
                    "<!-- Agent observations. Triage actionable problems and preserve "
                    "proven useful behavior. -->\n\n"
                )
            handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())

    event_path = _append_event(event)

    if args.json:
        print(
            json.dumps(
                {
                    "version": 1,
                    "ok": True,
                    "id": feedback_id,
                    "skill": args.skill,
                    "file": str(path),
                    "kind": args.kind,
                    "signal": signal,
                    "status": status,
                    "delivery": delivery,
                    "intended_directory": str(intended),
                    "event_id": event["event_id"],
                    "event_file": str(event_path),
                    "privacy": {
                        "reviewed": False,
                        "finding_kinds": sorted(
                            {item["kind"] for item in privacy_findings}
                        ),
                    },
                }
            )
        )
    else:
        suffix = f" (pending delivery to {intended})" if delivery == "pending" else ""
        print(f"recorded {args.kind} for {args.skill} -> {path}{suffix}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.body_id:
        handle = body_handle_for(skill=args.skill, feedback_id=args.body_id)
        payload = {
            "version": 1,
            "skill": args.skill,
            "body_handle": {
                "feedback_id": handle.feedback_id,
                "entry_sha256": handle.entry_sha256,
            },
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"body handle: {handle.feedback_id} · entry_sha256={handle.entry_sha256}"
            )
        return 0
    entries = authoritative_entries(_parse_entries(args.skill))
    if args.status:
        entries = [entry for entry in entries if entry["status"] in args.status]
    if args.kind:
        entries = [entry for entry in entries if entry["kind"] in args.kind]
    public_entries = metadata_views(entries)
    if args.json:
        print(
            json.dumps(
                {
                    "version": 1,
                    "skill": args.skill,
                    "count": len(public_entries),
                    "entries": public_entries,
                },
                indent=2,
            )
        )
        return 0
    if not public_entries:
        print(f"no feedback recorded for {args.skill}")
        return 0
    for entry in public_entries:
        print(
            f"\n=== {entry['skill']} · {entry['id']} · {entry['status']} · "
            f"{entry['date']} {entry['time']} · {entry['kind']} ==="
        )
        print(f"source-summary: {entry['source-summary']}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    since = args.since
    statuses = set(args.status or ("open", "planned"))
    all_entries: list[dict] = []
    discovered_entries: list[dict] = []
    errors: dict[str, str] = {}
    for name in known_skills():
        try:
            entries = authoritative_entries(_parse_entries(name))
        except (FeedbackError, OSError) as exc:
            errors[name] = str(exc)
            continue
        if since:
            entries = [entry for entry in entries if entry["date"] >= since]
        if args.kind:
            entries = [entry for entry in entries if entry["kind"] in args.kind]
        discovered_entries.extend(entries)
        all_entries.extend(
            entry for entry in entries if args.all or entry["status"] in statuses
        )
    all_entries.sort(key=lambda item: (item["date"], item["time"], item["id"]))
    delivery_counts = {state: 0 for state in DELIVERY_STATES}
    delivery_conflicts = 0
    for entry in discovered_entries:
        delivery_counts[entry["delivery"]] += 1
        delivery_conflicts += int(entry["delivery_conflict"])
    public_entries = metadata_views(all_entries)
    if args.json:
        counts: dict[str, int] = {}
        for entry in public_entries:
            counts[entry["skill"]] = counts.get(entry["skill"], 0) + 1
        print(
            json.dumps(
                {
                    "version": 1,
                    "ok": not errors,
                    "count": len(public_entries),
                    "filters": {
                        "since": since,
                        "statuses": None if args.all else sorted(statuses),
                        "kinds": sorted(args.kind) if args.kind else None,
                    },
                    "counts_by_skill": counts,
                    "delivery_counts": delivery_counts,
                    "delivery_conflicts": delivery_conflicts,
                    "errors": errors,
                    "entries": public_entries,
                },
                indent=2,
            )
        )
        return 0 if not errors else 1
    counts: dict[str, list[dict]] = {}
    for entry in public_entries:
        counts.setdefault(entry["skill"], []).append(entry)
    for name, entries in counts.items():
        latest = entries[-1]["date"]
        print(
            f"{name:<22} {len(entries):>3} note(s)   latest {latest}   "
            f"source-summary: {entries[-1]['source-summary']}"
        )
    if not public_entries:
        print(
            "no open feedback across known skills"
            + (f" since {since}" if since else "")
        )
    else:
        print(
            f"\n{len(public_entries)} note(s) across skills. "
            "Request an opaque handle with: skill-feedback list <skill> --body <id>"
        )
    print(
        "delivery: "
        + ", ".join(f"{state}={delivery_counts[state]}" for state in DELIVERY_STATES)
    )
    for name, message in errors.items():
        print(f"warning: {name}: {message}", file=sys.stderr)
    return 0 if not errors else 1


def cmd_deliver(args: argparse.Namespace) -> int:
    if args.skill:
        skills = [args.skill]
    else:
        root = FEEDBACK_HOME / "note-outbox"
        try:
            skills = (
                sorted(path.name for path in root.iterdir() if path.is_dir())
                if root.is_dir()
                else []
            )
        except OSError as exc:
            raise FeedbackError(f"cannot enumerate note outbox {root}: {exc}") from exc
    environment = dict(os.environ)
    results = []
    for name in skills:
        try:
            public, _transaction = _delivery_plan_for_skill(name)
        except (FeedbackError, OSError) as exc:
            results.append(
                {
                    "skill": name,
                    "pending": None,
                    "ready": False,
                    "applied": False,
                    "blocked_reason": str(exc),
                    "conflicts": [],
                    "diagnostics": [],
                    "entries": [],
                }
            )
            continue
        diagnostics: list[dict] = []
        for entry in public.get("entries", []):
            try:
                auth = authorize_delivery(
                    skill=name, feedback_id=entry["id"], environment=environment
                )
                entry["origin_verified"] = True
                entry["origin_event_id"] = auth.origin_event_id
                entry["privacy"] = {"scanner_version": auth.privacy_scanner_version}
                entry["_authorization"] = auth
            except DeliveryBlocked as exc:
                entry["origin_verified"] = False
                diagnostics.append(
                    {
                        "id": exc.feedback_id,
                        "type": exc.conflict_type,
                        "field": exc.field,
                    }
                )
                public.setdefault("conflicts", []).append(str(exc))
            except (FeedbackError, OSError) as exc:
                entry["origin_verified"] = False
                diagnostics.append(
                    {
                        "id": entry["id"],
                        "type": "delivery_origin_conflict",
                        "field": "",
                    }
                )
                public.setdefault("conflicts", []).append(str(exc))
        public["diagnostics"] = diagnostics
        origin_failed = any(
            not entry.get("origin_verified", True)
            for entry in public.get("entries", [])
        )
        public["ready"] = bool(public.get("ready")) and not origin_failed
        if not public.get("ready") and not public.get("blocked_reason") and diagnostics:
            public["blocked_reason"] = "origin authentication failed"

        applied: list[str] = []
        if args.apply and public.get("ready"):
            for entry in public.get("entries", []):
                if not entry.get("origin_verified"):
                    continue
                try:
                    apply_delivery(entry["_authorization"], environment)
                    applied.append(entry["id"])
                except (IntegrityConflict, FeedbackError, OSError) as exc:
                    public["ready"] = False
                    public.setdefault("conflicts", []).append(str(exc))
                    public["blocked_reason"] = str(exc)
                    applied = []
                    break
        for entry in public.get("entries", []):
            entry.pop("_authorization", None)
        public["applied"] = bool(applied)
        public["delivered"] = len(applied)
        results.append(public)
    ok = all(result.get("ready") for result in results)
    summary = {
        "version": 1,
        "ok": ok,
        "apply_requested": args.apply,
        "applied": any(result.get("applied") for result in results),
        "fully_applied": args.apply and ok,
        "skills": len(results),
        "pending": sum(
            result.get("pending")
            for result in results
            if result.get("pending") is not None
        ),
        "delivered": sum(
            result.get("delivered", 0) for result in results if result.get("applied")
        ),
        "results": results,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        mode = "applied" if args.apply else "preview"
        print(
            f"delivery {mode}: {summary['pending']} pending note(s) across "
            f"{summary['skills']} skill(s)"
        )
        for result in results:
            state = (
                f"{len(result.get('entries', []))} ready"
                if result.get("ready")
                else f"blocked: {result.get('blocked_reason') or '; '.join(result.get('conflicts', []))}"
            )
            print(f"{result['skill']}: {state}")
    return 0 if ok else 1


def cmd_where(args: argparse.Namespace) -> int:
    target, delivery, intended = _feedback_write_target(args.skill, args.dir)
    if args.json:
        outbox_records, _, _ = _managed_note_records(_note_outbox_dir(args.skill))
        delivered = len(_read_delivery_sidecar(intended / ".delivery.json"))
        print(
            json.dumps(
                {
                    "version": 1,
                    "skill": args.skill,
                    "directory": str(target),
                    "delivery": delivery,
                    "intended_directory": str(intended),
                    "canonical_writable": _path_is_writable(intended),
                    "outbox_directory": str(_note_outbox_dir(args.skill)),
                    "pending_count": len(outbox_records),
                    "delivered_count": delivered,
                },
                indent=2,
            )
        )
    else:
        print(target)
    return 0


def _triage_event_id(feedback_id: str, status: str, idempotency_key: str) -> str:
    """Deterministic disposition event_id so an idempotency key dedupes to a
    single ledger event under concurrent resolution (ADR 0018 R6)."""
    digest = hashlib.sha256(
        f"disposition:{feedback_id}:{status}:{idempotency_key}".encode()
    ).hexdigest()
    return f"evt-{digest[:32]}"


def _has_passing_receipt(
    skill: str, feedback_id: str, receipt_id: str, purpose: str | None = None
) -> bool:
    """True iff a verification.recorded event verifies this feedback id (R2/R6).

    When *purpose* is given, the verified receipt must also match it (ADR 0019 D1):
    a `resolved` transition requires a `resolution` receipt and a `preserve`
    transition a `preservation` receipt, so a receipt of the wrong purpose does not
    authorize the transition.
    """
    for event in _read_events():
        payload = event["payload"]
        if (
            event["event_type"] == "verification.recorded"
            and event["skill"]["name"] == skill
            and payload.get("receipt_id") == receipt_id
            and payload.get("feedback_id") == feedback_id
            and payload.get("verification_state") == "verified"
            and (purpose is None or payload.get("purpose") == purpose)
        ):
            return True
    return False


def _preservation_declared_event(
    skill: str, feedback_id: str, test: str, invocation_id: str | None
) -> dict:
    """A content-free record that a preservation test link was declared (ADR 0018
    R4). Recorded even when the preserve transition is rejected, so a declared but
    unverified guard is visible without ever being counted as verified."""
    return _build_event(
        event_type="preservation.declared",
        skill=skill,
        invocation_id=invocation_id,
        actor_type="agent",
        source="agent_judgment",
        payload={"feedback_id": feedback_id, "test": test},
    )


def cmd_triage(args: argparse.Namespace) -> int:
    privacy_findings = _enforce_qualitative_privacy(
        args.note,
        reviewed=args.privacy_reviewed,
        label="qualitative disposition note",
    )
    links = {
        name: value
        for name, value in (
            ("task", args.task),
            ("issue", args.issue),
            ("commit", args.commit),
            ("test", args.test),
            ("duplicate_of", args.duplicate_of),
        )
        if value
    }
    if args.status == "duplicate" and not args.duplicate_of:
        raise FeedbackError("--status duplicate requires --duplicate-of")
    receipt_id = getattr(args, "receipt_id", None)
    if receipt_id:
        links["receipt"] = receipt_id
    privacy_findings.extend(
        _enforce_qualitative_privacy(
            json.dumps(links, sort_keys=True),
            reviewed=args.privacy_reviewed,
            label="qualitative disposition links",
        )
    )
    idempotency_key = getattr(args, "idempotency_key", None)
    # The verification.recorded event is append-only and immutable, so the
    # receipt check is read before the notes lock (no nested event lock). The
    # required purpose is keyed to the target status (ADR 0019 D1): a resolution
    # receipt authorizes `resolved`, a preservation receipt authorizes `preserve`;
    # a receipt of the wrong purpose does not authorize the transition.
    required_purpose = {"resolved": "resolution", "preserve": "preservation"}.get(
        args.status
    )
    has_passing_receipt = bool(receipt_id) and _has_passing_receipt(
        args.skill, args.id, receipt_id, purpose=required_purpose
    )

    declared_test: str | None = None
    declared_error: str | None = None
    idempotent_event_id: str | None = None
    event: dict | None = None
    path: Path | None = None
    with _file_lock(_notes_lock_path(), private=True):
        entries = {entry["id"]: entry for entry in _parse_entries_unlocked(args.skill)}
        if args.id not in entries:
            raise FeedbackError(
                f"unknown feedback id {args.id!r} for {args.skill}; "
                f"run `skill-feedback list {args.skill}`"
            )
        entry_file = Path(entries[args.id]["file"])
        path = entry_file.parent / ".status.json"
        statuses = _read_object_sidecar(path, "feedback status")
        prior = statuses.get(args.id, {})
        if (
            idempotency_key
            and prior.get("idempotency_key") == idempotency_key
            and prior.get("status") == args.status
        ):
            # Idempotent replay: this exact keyed transition already applied.
            idempotent_event_id = _triage_event_id(
                args.id, args.status, idempotency_key
            )
        else:
            current_status = entries[args.id].get("status", "open")
            # ADR 0019 D3: resolved->open is the reopen lifecycle edge and must go
            # through `reopen` (which requires a discriminating recurrence and a
            # superseding receipt, and stamps the superseded_receipt link the
            # closeout classification depends on). Refuse the ungoverned triage path.
            if current_status == "resolved" and args.status == "open":
                raise FeedbackError(
                    "cannot reopen a resolved item via triage; use `reopen` "
                    "(a discriminating recurrence and superseding receipt are required)"
                )
            transition = evaluate_transition(
                current_status,
                args.status,
                has_passing_receipt=has_passing_receipt,
                has_rationale=bool(args.note),
                has_duplicate_target=bool(args.duplicate_of),
            )
            if not transition.allowed:
                if args.status == "preserve" and args.test:
                    # Record the declared (unverified) guard, then fail the
                    # transition outside the lock (ADR 0018 R4). The status
                    # transition itself is rejected; the declaration is not.
                    declared_test = args.test
                    declared_error = transition.error
                else:
                    # Atomic rejection: nothing written (ADR 0018 R6).
                    raise FeedbackError(transition.error)
            else:
                event = _build_event(
                    event_type="disposition.changed",
                    skill=args.skill,
                    skill_version=args.skill_version,
                    invocation_id=entries[args.id].get("invocation_id"),
                    session=args.session,
                    harness=args.harness,
                    actor_type=args.actor,
                    actor_id=args.by or os.environ.get("SKILL_FEEDBACK_BY", "agent"),
                    source=args.source,
                    tags=[],
                    event_id=(
                        _triage_event_id(args.id, args.status, idempotency_key)
                        if idempotency_key
                        else None
                    ),
                    payload={
                        "feedback_id": args.id,
                        "status": args.status,
                        "rationale_sha256": hashlib.sha256(
                            args.note.encode()
                        ).hexdigest(),
                        "links": links,
                    },
                )
                statuses[args.id] = {
                    "status": args.status,
                    "note": args.note,
                    "privacy_reviewed": bool(privacy_findings),
                    "links": links,
                    "updated": f"{_now():%Y-%m-%dT%H:%M:%S}",
                }
                if idempotency_key:
                    statuses[args.id]["idempotency_key"] = idempotency_key
                _write_json_atomic(path, statuses)

    if declared_test is not None:
        _append_event(
            _preservation_declared_event(
                args.skill,
                args.id,
                declared_test,
                entries[args.id].get("invocation_id"),
            )
        )
        raise FeedbackError(declared_error or "verification receipt required")

    if idempotent_event_id is not None:
        transition_event_id = idempotent_event_id
        event_file = str(_event_path())
    elif idempotency_key:
        event_path, _appended = _append_event_once(event)
        transition_event_id = event["event_id"]
        event_file = str(event_path)
    else:
        event_path = _append_event(event)
        transition_event_id = event["event_id"]
        event_file = str(event_path)

    result = {
        "version": 1,
        "ok": True,
        "skill": args.skill,
        "id": args.id,
        "status": args.status,
        "note": args.note,
        "privacy": {
            "reviewed": bool(privacy_findings),
            "finding_kinds": sorted({item["kind"] for item in privacy_findings}),
        },
        "links": links,
        "status_file": str(path),
        "event_id": transition_event_id,
        "transition_event_id": transition_event_id,
        "event_file": event_file,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.id}: {args.status} -> {path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Record a typed verification receipt (C2 / ADR 0018 R2).

    Reads the receipt JSON, validates its required fields (a missing field is a
    malformed receipt -> exit 1), classifies the outcome as verified/unverified
    WITHOUT executing the declared check (the verifier resolves check_identity as
    a filesystem path and honors the recorded observed_result; it never runs
    arbitrary code -- that keeps the verification boundary free of a code-exec
    surface), appends an append-only verification.recorded event, and returns
    {receipt_id, verification_state}. A well-formed but unverifiable receipt is a
    successful command (exit 0) reporting verification_state=unverified.
    """
    _validate_skill_name(args.skill)
    receipt_path = Path(args.receipt)
    try:
        raw = receipt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # ADR 0019 D6: a non-decodable / unreadable receipt is a malformed receipt
        # (R2), returned as a typed exit-1 error, never a raw traceback.
        raise FeedbackError(
            f"invalid verification receipt: cannot read {args.receipt}: {exc}"
        )
    try:
        receipt = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FeedbackError(f"invalid verification receipt: not valid JSON: {exc}")
    if not isinstance(receipt, dict):
        raise FeedbackError("invalid verification receipt: must be a JSON object")
    required = (
        "schema_version",
        "feedback_id",
        "purpose",
        "artifact_id",
        "change_id",
        "acceptance_criterion",
        "verifier_source",
        "check_identity",
        "oracle",
        "observed_result",
        "observed_at",
    )
    for field in required:
        if field not in receipt:
            raise FeedbackError(f"invalid verification receipt: missing field {field}")
    purpose = receipt["purpose"]
    if purpose not in ("resolution", "preservation", "recurrence"):
        raise FeedbackError(
            "invalid verification receipt: purpose must be resolution, "
            "preservation, or recurrence"
        )
    observed_result = receipt["observed_result"]
    if observed_result not in ("pass", "fail", "unavailable", "stale"):
        raise FeedbackError(
            "invalid verification receipt: observed_result must be pass, fail, "
            "unavailable, or stale"
        )
    if receipt["feedback_id"] != args.id:
        raise FeedbackError(
            "invalid verification receipt: feedback_id does not match the target"
        )
    check_identity = str(receipt["check_identity"])
    # ADR 0019 D4: the check must resolve to an existing *regular file* that is not
    # the receipt itself -- a directory or a self-reference is not evidence. `samefile`
    # compares device+inode, so it also excludes a symlink or hardlink to the receipt
    # (N1, re-verify round). The verifier still does NOT execute the check (no
    # code-exec surface); binding the check to the artifact under verification is
    # deferred to C4, so an unrelated existing file still resolves today.
    check_path = Path(check_identity) if check_identity else None
    check_resolves = False
    if check_path and check_path.is_file():
        try:
            check_resolves = not check_path.samefile(receipt_path)
        except OSError:
            check_resolves = False
    verified = observed_result == "pass" and check_resolves
    verification_state = "verified" if verified else "unverified"
    receipt_id = _new_id("rcpt")
    event = _build_event(
        event_type="verification.recorded",
        skill=args.skill,
        invocation_id=None,
        actor_type="automation",
        source="deterministic",
        payload={
            "feedback_id": args.id,
            "receipt_id": receipt_id,
            "purpose": purpose,
            "artifact_id": str(receipt["artifact_id"]),
            "change_id": str(receipt["change_id"]),
            "acceptance_criterion": str(receipt["acceptance_criterion"]),
            "verifier_source": str(receipt["verifier_source"]),
            "check_identity": check_identity,
            "oracle": str(receipt["oracle"]),
            "observed_result": observed_result,
            "observed_at": str(receipt["observed_at"]),
            "verification_state": verification_state,
        },
    )
    event_path = _append_event(event)
    result = {
        "version": 1,
        "ok": True,
        "skill": args.skill,
        "feedback_id": args.id,
        "receipt_id": receipt_id,
        "verification_state": verification_state,
        "purpose": purpose,
        "observed_result": observed_result,
        "check_resolved": check_resolves,
        "event_id": event["event_id"],
        "event_file": str(event_path),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.id}: verification {verification_state} ({receipt_id})")
    return 0


def cmd_reopen(args: argparse.Namespace) -> int:
    """Reopen a verified item on a discriminating recurrence (ADR 0018 R1/R6).

    Returns it to `open` with lifecycle_state=reopened, preserving the superseded
    resolution receipt and recording the triggering recurrence. Requires the item
    to be currently resolved/preserve, the receipt to be its passing verification,
    and the recurrence to be a real linked observation (never inferred from text).
    """
    _validate_skill_name(args.skill)
    if not _has_passing_receipt(
        args.skill, args.id, args.receipt_id, purpose="resolution"
    ):
        raise FeedbackError(
            f"cannot reopen {args.id!r}: {args.receipt_id!r} is not a passing "
            f"resolution verification receipt for it"
        )
    with _file_lock(_notes_lock_path(), private=True):
        entries = {entry["id"]: entry for entry in _parse_entries_unlocked(args.skill)}
        if args.id not in entries:
            raise FeedbackError(
                f"unknown feedback id {args.id!r} for {args.skill}; "
                f"run `skill-feedback list {args.skill}`"
            )
        if args.recurrence not in entries:
            raise FeedbackError(
                f"unknown recurrence feedback id {args.recurrence!r} for {args.skill}"
            )
        current_status = entries[args.id].get("status", "open")
        transition = evaluate_transition(current_status, "open")
        if not transition.allowed:
            raise FeedbackError(
                f"cannot reopen from {current_status!r}: {transition.error}"
            )
        rationale = (
            f"reopened via recurrence {args.recurrence} superseding receipt "
            f"{args.receipt_id}"
        )
        links = {"recurrence": args.recurrence, "superseded_receipt": args.receipt_id}
        event = _build_event(
            event_type="disposition.changed",
            skill=args.skill,
            skill_version=args.skill_version,
            invocation_id=entries[args.id].get("invocation_id"),
            session=args.session,
            harness=args.harness,
            actor_type=args.actor,
            actor_id=args.by or os.environ.get("SKILL_FEEDBACK_BY", "agent"),
            source=args.source,
            tags=[],
            payload={
                "feedback_id": args.id,
                "status": "open",
                "rationale_sha256": hashlib.sha256(rationale.encode()).hexdigest(),
                "links": links,
            },
        )
        entry_file = Path(entries[args.id]["file"])
        path = entry_file.parent / ".status.json"
        statuses = _read_object_sidecar(path, "feedback status")
        statuses[args.id] = {
            "status": "open",
            "note": rationale,
            "lifecycle_state": "reopened",
            "superseded_receipt_id": args.receipt_id,
            "recurrence": args.recurrence,
            "links": links,
            "updated": f"{_now():%Y-%m-%dT%H:%M:%S}",
        }
        _write_json_atomic(path, statuses)
    event_path = _append_event(event)
    result = {
        "version": 1,
        "ok": True,
        "skill": args.skill,
        "id": args.id,
        "status": "open",
        "lifecycle_state": "reopened",
        "superseded_receipt_id": args.receipt_id,
        "recurrence": args.recurrence,
        "event_id": event["event_id"],
        "event_file": str(event_path),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.id}: reopened (superseded {args.receipt_id})")
    return 0


def _backend(args: argparse.Namespace) -> dict:
    return {
        "router": args.router,
        "provider": args.provider,
        "model": args.model,
        "effort": args.effort,
    }


def _automatic_collection_enabled(skill: str) -> bool:
    disabled = os.environ.get("SKILL_FEEDBACK_DISABLE", "").lower()
    if disabled in {"1", "true", "yes", "on"}:
        return False
    disabled_skills = {
        item.strip()
        for item in os.environ.get("SKILL_FEEDBACK_DISABLE_SKILLS", "").split(",")
        if item.strip()
    }
    if skill in disabled_skills:
        return False
    try:
        config, configured = _read_privacy_config()
    except FeedbackError:
        return False
    return (
        configured
        and config["automatic_collection"] == "manifest_opt_in"
        and config["retention"]["mode"] != "unset"
    )


def _exec_uninstrumented(command: list[str]) -> int:
    os.execv(command[0], command)
    return 127


def _wrapper_content(
    *,
    skill: str,
    feature: str,
    target: Path,
    output: Path,
    success_exit_codes: tuple[int, ...] = (),
) -> str:
    relative_target = os.path.relpath(target, output.parent)
    metadata = json.dumps(
        {
            "schema": WRAPPER_SCHEMA_VERSION,
            "skill": skill,
            "feature": feature,
            "success_exit_codes": list(success_exit_codes),
            "target": relative_target,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "#!/usr/bin/env python3\n"
        f"{WRAPPER_MARKER}\n"
        f"# metadata: {metadata}\n"
        '"""Generated adapter. Reconcile with `skill-feedback wrapper --apply`."""\n'
        "from __future__ import annotations\n\n"
        "import os\n"
        "import shutil\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        f"_SKILL = {skill!r}\n"
        f"_FEATURE = {feature!r}\n"
        f"_SUCCESS_EXIT_CODES = {success_exit_codes!r}\n"
        f"_TARGET = (Path(__file__).resolve().parent / {relative_target!r}).resolve()\n"
        "_COMMAND = [str(_TARGET), *sys.argv[1:]]\n"
        "_RUN_OPTIONS = [\n"
        "    item\n"
        "    for code in _SUCCESS_EXIT_CODES\n"
        '    for item in ("--success-exit-code", str(code))\n'
        "]\n"
        '_FEEDBACK = shutil.which("skill-feedback")\n'
        "if _FEEDBACK is None or Path(_FEEDBACK).resolve() == Path(__file__).resolve():\n"
        "    os.execv(str(_TARGET), _COMMAND)\n"
        "os.execv(\n"
        "    _FEEDBACK,\n"
        "    [\n"
        "        _FEEDBACK,\n"
        '        "run",\n'
        "        _SKILL,\n"
        '        "--feature",\n'
        "        _FEATURE,\n"
        "        *_RUN_OPTIONS,\n"
        '        "--",\n'
        "        *_COMMAND,\n"
        "    ],\n"
        ")\n"
    )


def cmd_wrapper(args: argparse.Namespace) -> int:
    """Plan or reconcile a repository-owned CLI telemetry adapter."""
    skill = _validate_skill_name(args.skill)
    if skill == "skill-feedback":
        raise FeedbackError("skill-feedback cannot wrap itself recursively")
    feature = args.feature.strip()
    if not feature or "\n" in feature or "\x00" in feature:
        raise FeedbackError("wrapper feature must be a non-empty single-line value")
    success_exit_codes = tuple(sorted(set(args.success_exit_code or [])))
    if any(code < 1 or code > 255 for code in success_exit_codes):
        raise FeedbackError("success exit codes must be between 1 and 255")

    target = Path(args.target).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if target == output:
        raise FeedbackError("wrapper target and output must be different paths")
    if not target.is_file():
        raise FeedbackError(f"wrapper target is not a file: {target}")
    if not os.access(target, os.X_OK):
        raise FeedbackError(f"wrapper target is not executable: {target}")

    expected = _wrapper_content(
        skill=skill,
        feature=feature,
        target=target,
        output=output,
        success_exit_codes=success_exit_codes,
    )
    exists = output.exists() or output.is_symlink()
    if exists and (output.is_symlink() or not output.is_file()):
        raise FeedbackError(f"refusing to overwrite non-file wrapper: {output}")
    current = output.read_text() if output.is_file() else None
    if current is not None and current != expected and WRAPPER_MARKER not in current:
        raise FeedbackError(f"refusing to overwrite unmanaged wrapper: {output}")

    executable = output.is_file() and os.access(output, os.X_OK)
    if current == expected and executable:
        status = "current"
    elif current == expected:
        status = "mode-drift"
    elif current is None:
        status = "missing"
    else:
        status = "content-drift"

    applied = False
    if args.apply and status != "current":
        if current != expected:
            _write_text_atomic(output, expected, mode=0o755)
        else:
            output.chmod(0o755)
        applied = True
        status = "current"

    result = {
        "version": WRAPPER_SCHEMA_VERSION,
        "command": "wrapper",
        "ok": True,
        "skill": skill,
        "feature": feature,
        "success_exit_codes": list(success_exit_codes),
        "target": str(target),
        "output": str(output),
        "status": status,
        "change_needed": status != "current",
        "applied": applied,
        "sha256": hashlib.sha256(expected.encode()).hexdigest(),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    elif applied:
        print(f"reconciled wrapper: {output}")
    elif status == "current":
        print(f"wrapper current: {output}")
    else:
        print(f"wrapper needs {status}: {output} (re-run with --apply)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a CLI target with content-free, fail-open lifecycle instrumentation."""
    _validate_skill_name(args.skill)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise FeedbackError("run requires an executable after --")
    target = Path(command[0])
    if not target.is_absolute():
        raise FeedbackError("run target must be an absolute path")
    if args.skill not in known_skills() or not _automatic_collection_enabled(
        args.skill
    ):
        return _exec_uninstrumented(command)

    feature = args.feature or target.name
    supplied_idempotency_key = args.idempotency_key or os.environ.get(
        "SKILL_FEEDBACK_IDEMPOTENCY_KEY"
    )
    idempotency_key = supplied_idempotency_key or _new_id("run")
    invocation_digest = hashlib.sha256(
        f"{args.skill}\0{feature}\0{idempotency_key}".encode()
    ).hexdigest()
    invocation_id = f"use-{invocation_digest}"
    try:
        started = _build_event(
            event_type="invocation.started",
            event_id=_stable_event_id(invocation_id, "start"),
            skill=args.skill,
            invocation_id=invocation_id,
            harness=args.harness,
            actor_type="automation",
            actor_id="skill-feedback-wrapper",
            source="automation",
            tags=["automatic", "cli"],
            payload={
                "feature": feature,
                "backend": {
                    "router": None,
                    "provider": None,
                    "model": None,
                    "effort": None,
                },
            },
        )
        if supplied_idempotency_key:
            _append_event_once(started)
        else:
            _append_event(started)
    except (FeedbackError, OSError):
        return _exec_uninstrumented(command)

    started_ns = time.monotonic_ns()
    child = subprocess.Popen(command)
    forwarded_signal: int | None = None
    previous_handlers: dict[int, object] = {}

    def forward(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        if child.poll() is None:
            try:
                os.kill(child.pid, signum)
            except ProcessLookupError:
                pass

    handled = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
    for signum in handled:
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward)
    try:
        returncode = child.wait()
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)

    duration_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
    outcome = (
        "success"
        if returncode == 0 or returncode in (args.success_exit_code or [])
        else ("abandoned" if returncode < 0 else "failure")
    )
    try:
        finished = _build_event(
            event_type="invocation.finished",
            event_id=_stable_event_id(invocation_id, "finish"),
            skill=args.skill,
            invocation_id=invocation_id,
            harness=args.harness,
            actor_type="automation",
            actor_id="skill-feedback-wrapper",
            source="automation",
            tags=["automatic", "cli"],
            payload={
                "outcome": outcome,
                "backend": {
                    "router": None,
                    "provider": None,
                    "model": None,
                    "effort": None,
                },
                "metrics": {
                    "duration_ms": duration_ms,
                    "cost_usd": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "retries": None,
                },
                "evidence": [],
            },
        )
        if supplied_idempotency_key:
            _append_event_once(finished)
        else:
            _append_event(finished)
    except (FeedbackError, OSError):
        pass

    terminating_signal = -returncode if returncode < 0 else forwarded_signal
    if returncode < 0 and terminating_signal is not None:
        signal.signal(terminating_signal, signal.SIG_DFL)
        os.kill(os.getpid(), terminating_signal)
        return 128 + terminating_signal
    return returncode


def cmd_start(args: argparse.Namespace) -> int:
    _validate_skill_name(args.skill)
    if args.skill not in known_skills():
        raise FeedbackError(f"unknown skill {args.skill!r}")
    invocation_id = args.invocation_id or _new_id("use")
    event = _build_event(
        event_type="invocation.started",
        skill=args.skill,
        skill_version=args.skill_version,
        invocation_id=invocation_id,
        session=args.session,
        harness=args.harness,
        actor_type=args.actor,
        actor_id=args.by or os.environ.get("SKILL_FEEDBACK_BY", "agent"),
        source=args.source,
        task_class=args.task_class,
        tags=args.tag,
        payload={"feature": args.feature, "backend": _backend(args)},
    )
    path = _append_event(event)
    result = {
        "version": EVENT_SCHEMA_VERSION,
        "ok": True,
        "invocation_id": invocation_id,
        "event_id": event["event_id"],
        "event_file": str(path),
    }
    print(json.dumps(result, indent=2) if args.json else invocation_id)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    _validate_skill_name(args.skill)
    if args.skill not in known_skills():
        raise FeedbackError(f"unknown skill {args.skill!r}")
    metrics = {
        "duration_ms": args.duration_ms,
        "cost_usd": args.cost_usd,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "retries": args.retries,
    }
    event = _build_event(
        event_type="invocation.finished",
        skill=args.skill,
        skill_version=args.skill_version,
        invocation_id=args.invocation_id,
        session=args.session,
        harness=args.harness,
        actor_type=args.actor,
        actor_id=args.by or os.environ.get("SKILL_FEEDBACK_BY", "agent"),
        source=args.source,
        task_class=args.task_class,
        tags=args.tag,
        payload={
            "outcome": args.outcome,
            "backend": _backend(args),
            "metrics": metrics,
            "evidence": args.evidence or [],
        },
    )
    path = _append_event(event)
    result = {
        "version": EVENT_SCHEMA_VERSION,
        "ok": True,
        "invocation_id": args.invocation_id,
        "event_id": event["event_id"],
        "event_file": str(path),
    }
    print(
        json.dumps(result, indent=2)
        if args.json
        else f"{args.invocation_id}: {args.outcome}"
    )
    return 0


def cmd_collection(args: argparse.Namespace) -> int:
    config, configured = _read_privacy_config()
    if args.manifest_opt_in:
        if config["retention"]["mode"] == "unset":
            raise FeedbackError(
                "choose a retention policy before enabling automatic collection"
            )
        config["automatic_collection"] = "manifest_opt_in"
        _write_privacy_config(config)
        configured = True
    elif args.off:
        config["automatic_collection"] = "off"
        _write_privacy_config(config)
        configured = True
    result = {
        "version": PRIVACY_CONFIG_VERSION,
        "configured": configured,
        "automatic_collection": config["automatic_collection"],
        "retention": config["retention"],
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"automatic collection: {config['automatic_collection']}")
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    events = _read_events()
    events = _select_events(events, _event_filters(args))
    if args.limit is not None:
        events = events[-args.limit :]
    if args.json:
        print(
            json.dumps(
                {
                    "version": EVENT_SCHEMA_VERSION,
                    "count": len(events),
                    "event_file": str(_event_path()),
                    "events": events,
                },
                indent=2,
            )
        )
        return 0
    if not events:
        print("no matching skill feedback events")
        return 0
    for event in events:
        print(
            f"{event['occurred_at']}  {event['event_type']:<22} "
            f"{event['skill']['name']:<22} {event.get('invocation_id') or '-'}"
        )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    after = _parse_timestamp(args.after, "--after") if args.after else None
    before = _parse_timestamp(args.before, "--before") if args.before else None
    if after and before and after >= before:
        raise FeedbackError("--after must be earlier than --before")
    group_by = tuple(args.group_by or ("skill",))
    if len(group_by) != len(set(group_by)):
        raise FeedbackError("--group-by dimensions cannot be repeated")
    result = build_stats(
        _read_events(),
        after=after,
        before=before,
        skills=set(args.skill or []),
        group_by=group_by,
    )
    coverage = _automatic_coverage()
    coverage_by_skill = {
        entry["skill"]: {
            "status": entry["status"],
            "automatic": entry["automatic"],
        }
        for entry in coverage["entries"]
    }
    result["coverage"] = {
        "inventory": coverage["inventory"],
        "portfolio_complete": coverage["portfolio_complete"],
        "reliable_cli_complete": coverage["reliable_cli_complete"],
        "counts": coverage["counts"],
        "by_skill": coverage_by_skill,
    }
    for group in result["groups"]:
        skill = group["dimensions"].get("skill")
        group["coverage"] = (
            coverage_by_skill.get(
                skill,
                {"status": "not_in_inventory", "automatic": False},
            )
            if skill is not None
            else {
                "status": "portfolio",
                "automatic": coverage["portfolio_complete"],
            }
        )
    if not coverage["inventory"]["ready"] or not coverage["portfolio_complete"]:
        result["limitations"].append(
            "usage denominators are incomplete where automatic coverage is absent"
        )
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    inventory = coverage["inventory"]
    print(
        "coverage: "
        f"inventory={'ready' if inventory['ready'] else 'unavailable'} "
        f"portfolio={'complete' if coverage['portfolio_complete'] else 'incomplete'} "
        f"declared-cli={'complete' if coverage['reliable_cli_complete'] else 'incomplete'}"
    )
    print(
        "population: invocation starts in window; matching finishes joined "
        "across the full ledger"
    )
    for group in result["groups"]:
        label = ", ".join(
            f"{name}={value if value is not None else 'unknown'}"
            for name, value in group["dimensions"].items()
        )
        population = group["population"]
        observations = group["observations"]
        preservation = group["preservation"]
        print(
            f"{label}: uses={population['uses']} finished={population['finished']} "
            f"incomplete={population['incomplete']} success={group['outcomes']['success']} "
            f"failure={group['outcomes']['failure']} praise={observations['praise']} "
            f"friction={observations['friction']} bugs={observations['bug']} "
            f"preserved={preservation['preserved']} "
            f"declared_with_test={preservation['declared_with_test']} "
            f"verified_with_test={preservation['verified_with_test']} "
            f"coverage={group['coverage']['status']}"
        )
    if result["negative_after_praise"]:
        print(
            "warning: "
            f"{len(result['negative_after_praise'])} praised behavior(s) have later "
            "negative evidence"
        )
    print("interpretation: descriptive evidence, not a scalar or causal ranking")
    return 0


def cmd_closeout(args: argparse.Namespace) -> int:
    """Project a per-skill verified-closure and reopen closeout report (ADR 0018
    R5) from the append-only event ledger."""
    _validate_skill_name(args.skill)
    report = build_closeout(_read_events(), args.skill)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"skill: {report['skill']}")
    print(
        "population: "
        f"inflow={report['population']['inflow']} "
        f"verified_outflow={report['population']['verified_outflow']}"
    )
    print(
        "rates: "
        f"verified_close_rate={report['rates']['verified_close_rate']:.3f} "
        f"reopen_rate={report['rates']['reopen_rate']:.3f}"
    )
    print(f"oldest_open_age_seconds: {report['oldest_open_age_seconds']:.0f}")
    print(
        "time_to_verification_seconds: "
        f"count={report['time_to_verification_seconds']['count']} "
        f"median={report['time_to_verification_seconds']['median']:.3f}"
    )
    print(f"open_feedback_ids: {', '.join(report['open_feedback_ids']) or '(none)'}")
    print(
        "reopened_feedback_ids: "
        f"{', '.join(report['reopened_feedback_ids']) or '(none)'}"
    )
    return 0


def _write_export(path: Path, content: str, *, force: bool) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not force:
        raise FeedbackError(f"export target exists: {path}; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
        path.chmod(0o600)
    finally:
        if temp.exists():
            temp.unlink()


def cmd_export(args: argparse.Namespace) -> int:
    filters = _event_filters(args)
    events = _select_events(_read_events(), filters)
    if args.format == "json":
        content = json.dumps(
            {
                "version": EVENT_SCHEMA_VERSION,
                "count": len(events),
                "filters": _filter_summary(filters),
                "events": events,
            },
            indent=2,
        )
        content += "\n"
    else:
        content = "".join(
            json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
            for event in events
        )
    if args.out:
        target = Path(args.out)
        _write_export(target, content, force=args.force)
        result = {
            "version": EVENT_SCHEMA_VERSION,
            "count": len(events),
            "file": str(target.expanduser().resolve()),
            "format": args.format,
            "filters": _filter_summary(filters),
        }
        print(
            json.dumps(result, indent=2)
            if args.json
            else f"exported {len(events)} event(s) -> {result['file']}"
        )
    else:
        sys.stdout.write(content)
    return 0


def _deletion_plan(events: list[dict], filters: dict) -> dict:
    selected = _select_events(events, filters)
    return {
        "version": EVENT_SCHEMA_VERSION,
        "matched": len(selected),
        "retained": len(events) - len(selected),
        "filters": _filter_summary(filters),
        "sample_event_ids": [event["event_id"] for event in selected[:20]],
    }


def _apply_event_deletion(filters: dict) -> tuple[dict, Path]:
    with _file_lock(_event_lock_path(), private=True):
        events = _read_events_unlocked()
        selected_ids = {event["event_id"] for event in _select_events(events, filters)}
        retained = [event for event in events if event["event_id"] not in selected_ids]
        plan = {
            "version": EVENT_SCHEMA_VERSION,
            "matched": len(selected_ids),
            "retained": len(retained),
            "filters": _filter_summary(filters),
            "sample_event_ids": sorted(selected_ids)[:20],
            "applied": True,
        }
        path = _write_events_unlocked(retained) if selected_ids else _event_path()
    return plan, path


def cmd_delete(args: argparse.Namespace) -> int:
    if not _has_event_selector(args):
        raise FeedbackError("delete requires at least one selector")
    filters = _event_filters(args)
    if args.apply:
        plan, path = _apply_event_deletion(filters)
    else:
        plan = _deletion_plan(_read_events(), filters)
        plan["applied"] = False
        path = _event_path()
    plan["event_file"] = str(path)
    if args.json:
        print(json.dumps(plan, indent=2))
    elif args.apply:
        print(f"deleted {plan['matched']} event(s); retained {plan['retained']}")
    else:
        print(
            f"would delete {plan['matched']} event(s); retained {plan['retained']}. "
            "Pass --apply to execute."
        )
    return 0


def _tombstone_event(origin: dict, corpus_version: int) -> dict:
    """A content-free successor event recording that a record was retention-expired
    (R5/AC-8): retention must be observable in the append-only ledger, never a
    silent truncation. Carries no body/text — only the prior event id and note
    digest plus a monotonic corpus version."""
    payload = origin.get("payload") or {}
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": "observation.tombstoned",
        "event_id": _new_id("evt"),
        "occurred_at": _utc_now(),
        "skill": origin.get("skill"),
        "actor": origin.get("actor"),
        "source": origin.get("source"),
        "invocation_id": None,
        "tags": [],
        "privacy": {"content_included": False, "redacted": False},
        "payload": {
            "feedback_id": payload.get("feedback_id"),
            "prior_event_id": origin.get("event_id"),
            "prior_note_sha256": payload.get("note_sha256"),
            "corpus_version": corpus_version,
        },
    }


def _retention_filters(days: int) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return {
        "event_ids": [],
        "skills": [],
        "invocations": [],
        "sessions": [],
        "event_types": [],
        "before": cutoff.isoformat().replace("+00:00", "Z"),
        "after": None,
    }


def cmd_retention(args: argparse.Namespace) -> int:
    if args.clear and args.apply:
        raise FeedbackError("retention --clear cannot be combined with --apply")
    config, configured = _read_privacy_config()
    if args.days is not None:
        config["retention"] = {"mode": "days", "days": args.days}
        _write_privacy_config(config)
        configured = True
    elif args.forever:
        config["retention"] = {"mode": "forever", "days": None}
        _write_privacy_config(config)
        configured = True
    elif args.clear:
        config["retention"] = {"mode": "unset", "days": None}
        _write_privacy_config(config)
        configured = True

    retention = config["retention"]
    mode = retention["mode"]
    days = retention["days"]
    if args.apply and mode == "unset":
        raise FeedbackError(
            "retention is not configured; set --days or --forever before --apply"
        )
    if mode in ("unset", "forever"):
        plan = {
            "version": EVENT_SCHEMA_VERSION,
            "configured": configured,
            "retention": retention,
            "automatic_collection": config["automatic_collection"],
            "content_capture": False,
            "matched": 0,
            "retained": len(_read_events()),
            "applied": False,
            "event_file": str(_event_path()),
        }
    else:
        filters = _retention_filters(days)
        if args.apply:
            # Capture the record-bearing events being expired BEFORE deletion so
            # retention can leave a content-free tombstone for each (R5/AC-8), then
            # delete the originals.
            expiring = [
                event
                for event in _select_events(_read_events(), filters)
                if event.get("event_type") == "observation.recorded"
            ]
            plan, path = _apply_event_deletion(filters)
            existing_tombstones = sum(
                1
                for event in _read_events()
                if event.get("event_type") == "observation.tombstoned"
            )
            for offset, origin in enumerate(expiring):
                _append_event(
                    _tombstone_event(origin, existing_tombstones + 2 + offset)
                )
        else:
            plan = _deletion_plan(_read_events(), filters)
            plan["applied"] = False
            path = _event_path()
        plan.update(
            {
                "configured": configured,
                "retention": retention,
                "automatic_collection": config["automatic_collection"],
                "content_capture": False,
                "event_file": str(path),
            }
        )
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        retention_label = (
            f"{days} day(s)"
            if mode == "days"
            else ("forever" if mode == "forever" else "not configured")
        )
        action = "deleted" if plan["applied"] else "would delete"
        print(
            f"retention: {retention_label}; {action} {plan['matched']} event(s); "
            f"retain {plan['retained']}"
        )
    return 0


def _portable_existing_note_location(skill: str, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        root = feedback_dir(skill).parent.parent.resolve()
        return path.resolve().relative_to(root).as_posix()
    except (FeedbackError, ValueError):
        parts = path.parts
        for index in range(len(parts) - 1):
            if parts[index : index + 2] == ("docs", "feedback"):
                return Path(*parts[index:]).as_posix()
    return value


def _migrate_privacy_storage() -> dict:
    changed_fields = 0
    hashed_sessions = 0
    relative_locations = 0
    authoritative_sessions: dict[str, str] = {}
    with _file_lock(_event_lock_path(), private=True):
        events = _read_events_unlocked()
        for event in events:
            session = (event.get("session") or {}).get("id")
            if session and not session.startswith("hmac-sha256:"):
                event["session"]["id"] = _stored_session_id(session)
                if event.get("event_type") == "observation.recorded":
                    event["payload"].pop("entry_sha256", None)
                    event["payload"].pop("record_sha256", None)
                hashed_sessions += 1
                changed_fields += 1
            if event.get("event_type") == "observation.recorded":
                feedback_id = (event.get("payload") or {}).get("feedback_id")
                stored_session = (event.get("session") or {}).get("id")
                if feedback_id and stored_session:
                    authoritative_sessions[feedback_id] = stored_session
                note_file = (event.get("payload") or {}).get("note_file")
                if isinstance(note_file, str) and Path(note_file).is_absolute():
                    portable = _portable_existing_note_location(
                        event["skill"]["name"], note_file
                    )
                    if portable != note_file:
                        event["payload"]["note_file"] = portable
                        relative_locations += 1
                        changed_fields += 1
        if changed_fields:
            _write_events_unlocked(events)
    changed_note_files = _migrate_note_sessions(
        _stored_session_id, authoritative_sessions
    )
    return {
        "fields_changed": changed_fields,
        "sessions_hashed": hashed_sessions,
        "note_locations_relativized": relative_locations,
        "markdown_files_changed": changed_note_files,
    }


def cmd_privacy_check(args: argparse.Namespace) -> int:
    if args.acknowledge:
        if not args.skill:
            raise FeedbackError("privacy-check --acknowledge requires a skill")
        if not args.note:
            raise FeedbackError("privacy-check --acknowledge requires --note")
        _enforce_qualitative_privacy(
            args.note,
            reviewed=False,
            label="privacy acknowledgement note",
        )

        def plan() -> tuple[dict, object]:
            entries = [
                entry
                for entry in _parse_entries_unlocked(args.skill)
                if entry["id"] == args.acknowledge
            ]
            if len(entries) != 1:
                raise FeedbackError(
                    f"privacy acknowledgement requires exactly one feedback entry "
                    f"{args.acknowledge!r} for {args.skill}"
                )
            entry = entries[0]
            findings = _text_privacy_findings(entry["text"])
            review_findings = [
                item for item in findings if item["severity"] == "review"
            ]
            request = build_review_request(
                skill=args.skill,
                feedback_id=entry["id"],
                entry_sha256=entry["entry_sha256"],
                text=entry["text"],
            )
            already_acknowledged = any(
                event.get("event_type") == "privacy.review.acknowledged"
                and (event.get("payload") or {}).get("feedback_id")
                == request.feedback_id
                and (event.get("payload") or {}).get("entry_sha256")
                == request.entry_sha256
                and (event.get("payload") or {}).get("findings_sha256")
                == request.findings_sha256
                and (event.get("payload") or {}).get("scanner_version")
                == request.scanner_version
                for event in _read_events()
            )
            result = {
                "version": 1,
                "ok": True,
                "skill": args.skill,
                "feedback_id": entry["id"],
                "finding_kinds": sorted({item["kind"] for item in review_findings}),
                "entry_sha256": request.entry_sha256,
                "findings_sha256": request.findings_sha256,
                "scanner_version": request.scanner_version,
                "already_acknowledged": already_acknowledged,
                "apply_requested": args.apply,
                "applied": False,
                "operator_capability_required": True,
            }
            return result, request

        lock = _notes_lock_path()
        if lock.exists():
            with _file_lock(lock, shared=True, private=True):
                result, request = plan()
        else:
            result, request = plan()
        if args.apply:
            try:
                acknowledge_review(request, capability_provider=None)
            except PermissionError as exc:
                raise FeedbackError(str(exc)) from exc
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            action = (
                "already acknowledged"
                if result["already_acknowledged"]
                else ("acknowledged" if result["applied"] else "would acknowledge")
            )
            print(
                f"{result['skill']}:{result['feedback_id']}: {action} "
                f"({', '.join(result['finding_kinds'])})"
            )
        return 0

    if args.apply or args.note or args.by:
        raise FeedbackError(
            "--apply, --note, and --by require privacy-check --acknowledge"
        )
    result = {"version": 1, **_inspect_qualitative_privacy(args.skill)}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = "ok" if result["ok"] else "review required"
        print(f"skill-feedback privacy-check: {state}")
        print(
            f"skills: {result['skills_scanned']} · entries: {result['entries_scanned']} "
            f"· blocked: {result['block_findings']} · "
            f"review: {result['review_findings']}"
        )
        for item in result["findings"]:
            labels = _privacy_finding_summary(item["findings"])
            acknowledgement = "reviewed" if item["reviewed"] else "unreviewed"
            print(
                f"{item['skill']}:{item['feedback_id']}:{item['part']}: "
                f"{acknowledgement}: {labels}"
            )
        for name, error in result["errors"].items():
            print(f"error: {name}: {error}")
    return 0 if result["ok"] else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    repaired = []
    if args.fix_permissions and FEEDBACK_HOME.exists():
        FEEDBACK_HOME.chmod(0o700)
        repaired.append(str(FEEDBACK_HOME))
        for path in (
            _event_path(),
            _event_lock_path(),
            _notes_lock_path(),
            _privacy_config_path(),
            _session_key_path(),
            _session_key_lock_path(),
        ):
            if path.exists():
                path.chmod(0o600)
                repaired.append(str(path))
    migrated = (
        _migrate_privacy_storage()
        if args.migrate_privacy
        else {
            "fields_changed": 0,
            "sessions_hashed": 0,
            "note_locations_relativized": 0,
            "markdown_files_changed": 0,
        }
    )

    errors = []
    warnings = []
    try:
        config, configured = _read_privacy_config()
    except FeedbackError as exc:
        config, configured = _default_privacy_config(), False
        errors.append(str(exc))

    home_private, home_mode = _private_mode(FEEDBACK_HOME, 0o700)
    event_private, event_mode = _private_mode(_event_path(), 0o600)
    event_lock_private, event_lock_mode = _private_mode(_event_lock_path(), 0o600)
    notes_lock_private, notes_lock_mode = _private_mode(_notes_lock_path(), 0o600)
    config_private, config_mode = _private_mode(_privacy_config_path(), 0o600)
    key_private, key_mode = _private_mode(_session_key_path(), 0o600)
    key_lock_private, key_lock_mode = _private_mode(_session_key_lock_path(), 0o600)
    for label, private, mode in (
        ("feedback home", home_private, home_mode),
        ("event ledger", event_private, event_mode),
        ("event lock", event_lock_private, event_lock_mode),
        ("notes lock", notes_lock_private, notes_lock_mode),
        ("privacy configuration", config_private, config_mode),
        ("session hash key", key_private, key_mode),
        ("session key lock", key_lock_private, key_lock_mode),
    ):
        if not private:
            errors.append(f"{label} permissions differ from required mode ({mode})")

    events, ledger_errors = _inspect_event_ledger()
    errors.extend(ledger_errors)
    content_events = [
        event["event_id"]
        for event in events
        if (event.get("privacy") or {}).get("content_included") is not False
    ]
    if content_events:
        errors.append(f"{len(content_events)} event(s) include content")
    secret_events = {
        event["event_id"]: _likely_secret_fields(event)
        for event in events
        if _likely_secret_fields(event)
    }
    if secret_events:
        errors.append(f"{len(secret_events)} event(s) contain likely secrets")
    raw_session_events = [
        event["event_id"]
        for event in events
        if (event.get("session") or {}).get("id")
        and not event["session"]["id"].startswith("hmac-sha256:")
    ]
    absolute_note_events = [
        event["event_id"]
        for event in events
        if event["event_type"] == "observation.recorded"
        and Path(event["payload"]["note_file"]).is_absolute()
    ]
    if raw_session_events:
        warnings.append(
            f"{len(raw_session_events)} legacy event(s) have unhashed session identifiers"
        )
    if absolute_note_events:
        warnings.append(
            f"{len(absolute_note_events)} legacy event(s) have absolute note locations"
        )
    note_storage = _inspect_note_storage()
    integrity_diagnostics = [
        *note_storage.get("integrity_conflicts", []),
        *note_storage.get("orphans", []),
    ]
    errors.extend(integrity_diagnostics)
    # ADR 0019 D7: the ledger is authoritative; flag any sidecar closure the ledger
    # does not back (a torn two-phase triage commit or an out-of-band edit).
    errors.extend(reconcile_disposition_status(events))
    if not note_storage["ok"] and not integrity_diagnostics:
        warnings.append(
            "qualitative note storage has conflicts, orphan delivery states, or "
            "unreadable skill stores; inspect doctor --json"
        )
    qualitative_privacy = _inspect_qualitative_privacy()
    if qualitative_privacy["block_findings"]:
        errors.append(
            f"{qualitative_privacy['block_findings']} likely secret finding(s) "
            "exist in qualitative feedback"
        )
    if qualitative_privacy["unreviewed_groups"]:
        warnings.append(
            f"{qualitative_privacy['unreviewed_groups']} qualitative feedback "
            "item(s) need privacy review; inspect doctor --json"
        )
    if qualitative_privacy["errors"]:
        warnings.append(
            "some qualitative feedback could not be privacy-audited; inspect doctor --json"
        )
    if not configured:
        warnings.append("privacy configuration has not been written")
    if config["retention"]["mode"] == "unset":
        warnings.append(
            "retention is not configured; automatic collection remains blocked"
        )

    result = {
        "version": EVENT_SCHEMA_VERSION,
        "ok": not errors,
        "safe_for_automatic_collection": (
            not errors
            and configured
            and config["retention"]["mode"] != "unset"
            and not raw_session_events
            and not absolute_note_events
        ),
        "automatic_collection_active": (
            not errors
            and configured
            and config["automatic_collection"] == "manifest_opt_in"
            and config["retention"]["mode"] != "unset"
            and not raw_session_events
            and not absolute_note_events
        ),
        "home": str(FEEDBACK_HOME),
        "event_file": str(_event_path()),
        "event_count": len(events),
        "note_storage": note_storage,
        "read_model": {
            "ledger_authoritative": note_storage.get("ledger_authoritative", True),
            "reconciled": note_storage.get("reconciled", {}),
        },
        "qualitative_privacy": qualitative_privacy,
        "privacy": config,
        "permissions": {
            "home": home_mode,
            "events": event_mode,
            "lock": event_lock_mode,
            "event_lock": event_lock_mode,
            "notes_lock": notes_lock_mode,
            "config": config_mode,
            "session_hash_key": key_mode,
            "session_key_lock": key_lock_mode,
        },
        "likely_secret_events": secret_events,
        "errors": errors,
        "warnings": warnings,
        "repaired": repaired,
        "migrated": migrated,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"skill-feedback doctor: {'ok' if result['ok'] else 'problems found'}")
        print(f"events: {len(events)} at {_event_path()}")
        retention = config["retention"]
        retention_label = (
            str(retention["days"]) if retention["mode"] == "days" else retention["mode"]
        )
        print(f"retention: {retention_label}")
        for warning in warnings:
            print(f"warning: {warning}")
        for error in errors:
            print(f"error: {error}")
    return 0 if result["ok"] else 1


RESERVED = (
    "record",
    "praise",
    "friction",
    "list",
    "review",
    "privacy-check",
    "where",
    "deliver",
    "triage",
    "start",
    "finish",
    "run",
    "wrapper",
    "coverage",
    "onboard",
    "events",
    "stats",
    "doctor",
    "export",
    "delete",
    "retention",
    "collection",
)


def _identity_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--by", help="actor identifier")
    parser.add_argument("--session", help="harness session id")
    parser.add_argument("--harness", help="harness name")
    parser.add_argument("--actor", choices=ACTOR_TYPES, default="agent")
    parser.add_argument("--source", choices=SOURCES, default="agent_judgment")
    parser.add_argument("--skill-version", help="skill commit or release")
    parser.add_argument("--task-class", help="privacy-safe workload class")
    parser.add_argument("--tag", action="append", help="freeform tag (repeatable)")


def _backend_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--router")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--effort")


def _event_selector_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-id", action="append")
    parser.add_argument("--skill", action="append")
    parser.add_argument("--invocation", action="append")
    parser.add_argument("--session", action="append")
    parser.add_argument("--event-type", action="append", choices=EVENT_TYPES)
    parser.add_argument("--before", help="exclusive RFC 3339 upper bound")
    parser.add_argument("--after", help="inclusive RFC 3339 lower bound")


def record_parser(
    *, prog: str = "skill-feedback", include_kind: bool = True
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Record a per-skill improvement note.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("skill", help="skill name (as in the installer registry)")
    p.add_argument("note", nargs="?", help="the note text, or '-' for stdin")
    if include_kind:
        p.add_argument("--kind", choices=KINDS, default="wish")
    p.add_argument("--feature", help="exact capability or command responsible")
    p.add_argument("--invocation", help="invocation id to join")
    p.add_argument("--signal", choices=SIGNALS)
    p.add_argument("--impact", choices=IMPACTS, default="unknown")
    p.add_argument("--outcome", choices=OUTCOMES, default="unknown")
    p.add_argument(
        "--evidence", action="append", help="evidence reference (repeatable)"
    )
    p.add_argument(
        "--privacy-reviewed",
        action="store_true",
        help="acknowledge likely-sensitive note content after review",
    )
    _identity_options(p)
    p.add_argument("--dir", help="write under PATH/docs/feedback instead of resolving")
    p.add_argument("--json", action="store_true")
    return p


def print_help() -> None:
    record_parser().print_help()


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print_help()
        return 0

    head, rest = argv[0], argv[1:]
    try:
        if head == "list":
            p = argparse.ArgumentParser(prog="skill-feedback list")
            p.add_argument("skill")
            p.add_argument("--dir")
            p.add_argument("--status", action="append", choices=STATUSES)
            p.add_argument("--kind", action="append", choices=KINDS)
            body_group = p.add_mutually_exclusive_group()
            body_group.add_argument("--body", dest="body_id", metavar="ID")
            body_group.add_argument("--text", dest="body_id", metavar="ID")
            p.add_argument("--json", action="store_true")
            return cmd_list(p.parse_args(rest))
        if head == "review":
            p = argparse.ArgumentParser(prog="skill-feedback review")
            p.add_argument("--since", help="only files on/after YYYY-MM-DD")
            p.add_argument("--status", action="append", choices=STATUSES)
            p.add_argument("--kind", action="append", choices=KINDS)
            p.add_argument("--all", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_review(p.parse_args(rest))
        if head == "privacy-check":
            p = argparse.ArgumentParser(prog="skill-feedback privacy-check")
            p.add_argument("skill", nargs="?")
            p.add_argument("--acknowledge", metavar="ID")
            p.add_argument("--note")
            p.add_argument("--by")
            p.add_argument("--actor", choices=ACTOR_TYPES, default="agent")
            p.add_argument("--apply", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_privacy_check(p.parse_args(rest))
        if head == "where":
            p = argparse.ArgumentParser(prog="skill-feedback where")
            p.add_argument("skill")
            p.add_argument("--dir")
            p.add_argument("--json", action="store_true")
            return cmd_where(p.parse_args(rest))
        if head == "deliver":
            p = argparse.ArgumentParser(prog="skill-feedback deliver")
            p.add_argument("skill", nargs="?")
            p.add_argument("--apply", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_deliver(p.parse_args(rest))
        if head == "triage":
            p = argparse.ArgumentParser(prog="skill-feedback triage")
            p.add_argument("skill")
            p.add_argument("id")
            p.add_argument("--status", required=True, choices=STATUSES)
            p.add_argument("--note", required=True)
            p.add_argument("--task")
            p.add_argument("--issue")
            p.add_argument("--commit")
            p.add_argument("--test")
            p.add_argument("--duplicate-of")
            p.add_argument(
                "--receipt-id",
                help="passing verification receipt id required to reach resolved/preserve",
            )
            p.add_argument(
                "--idempotency-key",
                help="dedupe a keyed transition to a single ledger event",
            )
            p.add_argument(
                "--privacy-reviewed",
                action="store_true",
                help="acknowledge likely-sensitive disposition content after review",
            )
            _identity_options(p)
            p.add_argument("--json", action="store_true")
            return cmd_triage(p.parse_args(rest))
        if head == "verify":
            p = argparse.ArgumentParser(prog="skill-feedback verify")
            p.add_argument("skill")
            p.add_argument("id")
            p.add_argument("--receipt", required=True)
            p.add_argument("--json", action="store_true")
            return cmd_verify(p.parse_args(rest))
        if head == "reopen":
            p = argparse.ArgumentParser(prog="skill-feedback reopen")
            p.add_argument("skill")
            p.add_argument("id")
            p.add_argument("--recurrence", required=True)
            p.add_argument("--receipt-id", required=True)
            _identity_options(p)
            p.add_argument("--json", action="store_true")
            return cmd_reopen(p.parse_args(rest))
        if head == "start":
            p = argparse.ArgumentParser(prog="skill-feedback start")
            p.add_argument("skill")
            p.add_argument("--invocation-id")
            p.add_argument("--feature")
            _identity_options(p)
            _backend_options(p)
            p.add_argument("--json", action="store_true")
            return cmd_start(p.parse_args(rest))
        if head == "finish":
            p = argparse.ArgumentParser(prog="skill-feedback finish")
            p.add_argument("skill")
            p.add_argument("invocation_id")
            p.add_argument("--outcome", required=True, choices=OUTCOMES)
            p.add_argument("--evidence", action="append")
            p.add_argument("--duration-ms", type=int)
            p.add_argument("--cost-usd", type=float)
            p.add_argument("--input-tokens", type=int)
            p.add_argument("--output-tokens", type=int)
            p.add_argument("--retries", type=int)
            _identity_options(p)
            _backend_options(p)
            p.add_argument("--json", action="store_true")
            return cmd_finish(p.parse_args(rest))
        if head == "run":
            p = argparse.ArgumentParser(prog="skill-feedback run")
            p.add_argument("skill")
            p.add_argument("--feature")
            p.add_argument("--harness")
            p.add_argument("--idempotency-key")
            p.add_argument("--success-exit-code", action="append", type=int)
            if "--" not in rest:
                raise FeedbackError("run requires -- before the target command")
            boundary = rest.index("--")
            args = p.parse_args(rest[:boundary])
            args.command = rest[boundary + 1 :]
            return cmd_run(args)
        if head == "wrapper":
            p = argparse.ArgumentParser(prog="skill-feedback wrapper")
            p.add_argument("skill")
            p.add_argument("--feature", required=True)
            p.add_argument("--target", required=True)
            p.add_argument("--output", required=True)
            p.add_argument(
                "--success-exit-code",
                action="append",
                type=int,
                help="nonzero target exit code that means successful behavior",
            )
            p.add_argument("--apply", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_wrapper(p.parse_args(rest))
        if head == "coverage":
            p = argparse.ArgumentParser(prog="skill-feedback coverage")
            p.add_argument("--check", action="store_true")
            p.add_argument(
                "--declared-only",
                action="store_true",
                help="check only already-declared CLI boundaries",
            )
            p.add_argument("--json", action="store_true")
            return cmd_coverage(p.parse_args(rest))
        if head == "onboard":
            p = argparse.ArgumentParser(prog="skill-feedback onboard")
            p.add_argument("skill", nargs="?")
            p.add_argument("--check", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_onboard(p.parse_args(rest))
        if head == "events":
            p = argparse.ArgumentParser(prog="skill-feedback events")
            _event_selector_options(p)
            p.add_argument("--limit", type=int)
            p.add_argument("--json", action="store_true")
            args = p.parse_args(rest)
            if args.limit is not None and args.limit < 0:
                raise FeedbackError("--limit must be zero or greater")
            return cmd_events(args)
        if head == "stats":
            p = argparse.ArgumentParser(prog="skill-feedback stats")
            p.add_argument("--skill", action="append")
            p.add_argument("--after", help="inclusive RFC 3339 start-cohort bound")
            p.add_argument("--before", help="exclusive RFC 3339 start-cohort bound")
            p.add_argument(
                "--group-by",
                action="append",
                choices=GROUP_DIMENSIONS,
                help="dimension to group by (repeatable; default: skill)",
            )
            p.add_argument("--json", action="store_true")
            return cmd_stats(p.parse_args(rest))
        if head == "closeout":
            p = argparse.ArgumentParser(prog="skill-feedback closeout")
            p.add_argument("--skill", required=True)
            p.add_argument("--json", action="store_true")
            return cmd_closeout(p.parse_args(rest))
        if head == "doctor":
            p = argparse.ArgumentParser(prog="skill-feedback doctor")
            p.add_argument("--fix-permissions", action="store_true")
            p.add_argument("--migrate-privacy", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_doctor(p.parse_args(rest))
        if head == "export":
            p = argparse.ArgumentParser(prog="skill-feedback export")
            _event_selector_options(p)
            p.add_argument("--format", choices=("jsonl", "json"), default="jsonl")
            p.add_argument("--out")
            p.add_argument("--force", action="store_true")
            p.add_argument(
                "--json",
                action="store_true",
                help="machine-readable summary when --out is used",
            )
            args = p.parse_args(rest)
            if args.json and not args.out:
                raise FeedbackError(
                    "export --json requires --out; use --format json for data"
                )
            if args.force and not args.out:
                raise FeedbackError("export --force requires --out")
            return cmd_export(args)
        if head == "delete":
            p = argparse.ArgumentParser(prog="skill-feedback delete")
            _event_selector_options(p)
            p.add_argument("--apply", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_delete(p.parse_args(rest))
        if head == "retention":
            p = argparse.ArgumentParser(prog="skill-feedback retention")
            group = p.add_mutually_exclusive_group()
            group.add_argument("--days", type=_positive_int)
            group.add_argument("--forever", action="store_true")
            group.add_argument("--clear", action="store_true")
            p.add_argument("--apply", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_retention(p.parse_args(rest))
        if head == "collection":
            p = argparse.ArgumentParser(prog="skill-feedback collection")
            group = p.add_mutually_exclusive_group()
            group.add_argument("--manifest-opt-in", action="store_true")
            group.add_argument("--off", action="store_true")
            p.add_argument("--json", action="store_true")
            return cmd_collection(p.parse_args(rest))
        if head in ("praise", "friction"):
            p = record_parser(
                prog=f"skill-feedback {head}",
                include_kind=False,
            )
            args = p.parse_args(rest)
            args.kind = head
            return cmd_record(args)

        # Bare form: `skill-feedback <skill> "<note>"`. `record` is an explicit alias.
        args = record_parser().parse_args(rest if head == "record" else argv)
        return cmd_record(args)
    except FeedbackError as exc:
        print(f"skill-feedback: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
