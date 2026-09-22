"""Preview and revalidate before delegating effects to Vercel skills."""

from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

from .artifacts import Refusal, artifact, digest, file_changes
from .environment import HARNESSES, atomic_json
from .inventory import observe


def target_observations(env, name):
    return [
        observe(p / name)
        for p in dict.fromkeys(p for paths in env.roots().values() for p in paths)
    ]


def placement_targets(env, name):
    """Resolved real paths of the placements this sync writes.

    A harness root outside those placements may still hold a link into one of
    them; comparing resolved paths is what distinguishes that from an override.
    """
    resolved = set()
    for path in env.placement(name).values():
        try:
            resolved.add(str(Path(path).resolve()))
        except (OSError, RuntimeError):
            continue
    return resolved


def plan(env, source, accept_installed=False):
    src = artifact(source)
    targets = target_observations(env, src["name"])
    state = env.state()
    baseline = state["skills"].get(src["name"])
    if baseline and baseline.get("binding") != env.binding():
        raise Refusal(
            "baseline belongs to a different installation scope or upstream command"
        )
    conflicts = []
    comparisons = []
    writable = {str(p) for p in env.placement(src["name"]).values()}
    placements = placement_targets(env, src["name"])
    for obs in targets:
        if obs["path"] not in writable:
            if obs["status"] == "absent":
                continue
            # A harness root can hold a link INTO a managed placement, e.g.
            # ~/.codex/skills/X -> ~/.agents/skills/X. Codex and OpenCode read
            # only their own directory, so that link is the supported way to
            # expose the shared copy rather than an override of it: it has no
            # independent content, and syncing the placement updates it by
            # construction. Record it, but do not refuse the plan over it.
            if obs["status"] == "present" and obs.get("resolved") in placements:
                comparisons.append(
                    {
                        "path": obs["path"],
                        "classification": "linked-to-placement",
                        "changes": [],
                    }
                )
                continue
            conflicts.append(
                {
                    "path": obs["path"],
                    "reason": "native override exists outside Vercel placement; reconcile it explicitly",
                }
            )
            continue
        old = baseline.get("targets", {}).get(obs["path"]) if baseline else None
        classification = (
            "identical" if obs.get("hash") == src["hash"] else "baseline-unknown"
        )
        if obs["status"] == "absent":
            classification = "not-installed"
        elif old:
            installed_changed = digest(obs) != digest(old)
            source_changed = src["hash"] != baseline["source"]["hash"]
            classification = (
                "both-changed"
                if installed_changed and source_changed
                else "installed-only"
                if installed_changed
                else "source-only"
                if source_changed
                else "identical"
            )
        hard = obs["status"] in ("broken", "unavailable") or (
            obs["status"] == "present" and obs.get("name") != src["name"]
        )
        unsafe = (
            classification in ("baseline-unknown", "installed-only", "both-changed")
            and obs.get("hash") != src["hash"]
        )
        if hard or (unsafe and not accept_installed):
            conflicts.append(
                {
                    "path": obs["path"],
                    "reason": obs["status"] if hard else classification,
                }
            )
        comparisons.append(
            {
                "path": obs["path"],
                "classification": classification,
                "changes": file_changes(src, obs),
            }
        )
    value = {
        "schema_version": 1,
        "kind": "sync-plan",
        "binding": env.binding(),
        "source": src,
        "targets": targets,
        "baseline_hash": digest(baseline),
        "accept_installed": accept_installed,
        "conflicts": conflicts,
        "comparisons": comparisons,
    }
    value["plan_id"] = digest(value)
    return value


def upstream(env, args):
    invocation = env.command + args
    environment = dict(os.environ, DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
    # stdout/stderr are inherited on stderr to keep --json stdout machine-readable.
    import sys

    try:
        run = subprocess.run(
            invocation,
            cwd=env.project,
            env=environment,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
        )
    except FileNotFoundError as exc:
        raise Refusal(
            f"upstream executable unavailable: {env.command[0]}; install it first"
        ) from exc
    return {"argv": invocation, "exit_code": run.returncode}


def apply(env, supplied):
    if supplied.get("kind") != "sync-plan" or supplied.get("schema_version") != 1:
        raise Refusal("expected a version 1 sync plan")
    with env.lock():
        current = plan(
            env, supplied["source"]["path"], supplied.get("accept_installed", False)
        )
        if current != supplied:
            raise Refusal(
                "stale or modified plan; source, installed paths, or baseline changed"
            )
        if current["conflicts"]:
            raise Refusal(
                "plan has unresolved conflicts; inspect the diff before choosing a resolution"
            )
        src = current["source"]
        state = env.state()
        placements = env.placement(src["name"])
        unchanged = all(
            observe(p).get("hash") == src["hash"] for p in placements.values()
        )
        receipt = {
            "schema_version": 1,
            "kind": "sync-receipt",
            "plan_id": current["plan_id"],
            "time": datetime.now(timezone.utc).isoformat(),
            "source": {k: v for k, v in src.items() if k != "files"},
            "binding": env.binding(),
            "status": "in-progress",
            "upstream": None,
        }
        atomic_json(env.state_dir / "last-operation.json", receipt)
        if not unchanged:
            flags = ["--global"] if env.scope == "global" else []
            receipt["upstream"] = upstream(
                env,
                [
                    "add",
                    src["path"],
                    *flags,
                    "--skill",
                    src["name"],
                    "--agent",
                    *HARNESSES,
                    "-y",
                ],
            )
        verified = {h: observe(p) for h, p in placements.items()}
        receipt["targets"] = {
            h: {
                "path": o["path"],
                "status": "verified" if o.get("hash") == src["hash"] else "failed",
                "hash": o.get("hash"),
            }
            for h, o in verified.items()
        }
        source_stable = artifact(src["path"])["hash"] == src["hash"]
        success = (
            source_stable
            and all(v["status"] == "verified" for v in receipt["targets"].values())
            and (receipt["upstream"] is None or receipt["upstream"]["exit_code"] == 0)
        )
        receipt["status"] = (
            ("unchanged" if unchanged else "applied") if success else "partial"
        )
        receipt["source_stable"] = source_stable
        if success:
            state["skills"][src["name"]] = {
                "source": src,
                "binding": env.binding(),
                "targets": {o["path"]: o for o in verified.values()},
                "receipt": current["plan_id"],
            }
            env.save(state)
        atomic_json(env.state_dir / "last-operation.json", receipt)
        return receipt


def remove(env, name, do_apply=False):
    state = env.state()
    previous = state["skills"].get(name)
    if not previous or previous.get("binding") != env.binding():
        raise Refusal("removal requires a Manager receipt for this scope")
    current = target_observations(env, name)
    owned = previous["targets"]
    if any(o["status"] != "absent" and o != owned.get(o["path"]) for o in current):
        raise Refusal(
            "installed paths changed or are not owned; preserve them and inspect"
        )
    if any(x.get("skill") == name for x in state["launchers"].values()):
        raise Refusal("remove this skill's owned PATH launchers first")
    result = {
        "kind": "remove-plan",
        "name": name,
        "targets": current,
        "status": "planned",
    }
    if not do_apply:
        return result
    with env.lock():
        if target_observations(env, name) != current or env.state() != state:
            raise Refusal("removal state changed; retry the preview")
        flags = ["--global"] if env.scope == "global" else []
        run = upstream(env, ["remove", name, *flags, "--agent", *HARNESSES, "-y"])
        after = target_observations(env, name)
        result.update(
            kind="remove-receipt",
            upstream=run,
            targets=after,
            status="removed"
            if run["exit_code"] == 0 and all(o["status"] == "absent" for o in after)
            else "partial",
        )
        if result["status"] == "removed":
            del state["skills"][name]
            env.save(state)
        atomic_json(env.state_dir / "last-operation.json", result)
        return result
