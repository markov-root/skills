"""Explicit scope, observed roots, and Manager-owned state."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from .artifacts import Refusal

HARNESSES = ("claude-code", "codex", "opencode")


class Environment:
    def __init__(self, scope="global", project=None, state_dir=None, command=None):
        self.scope = scope
        self.project = Path(project or Path.cwd()).resolve()
        self.home = Path.home()
        self.command = command or ["npx", "--yes", "skills@1.5.23"]
        if (
            not isinstance(self.command, list)
            or not self.command
            or not all(isinstance(x, str) and x for x in self.command)
        ):
            raise Refusal("skills command must be a nonempty JSON argv array")
        if scope == "project":
            self.shared = self.project / ".agents/skills"
            self.native = {
                "claude-code": self.project / ".claude/skills",
                "codex": self.project / ".codex/skills",
                "opencode": self.project / ".opencode/skills",
            }
            default = self.project / ".skill-manager/v1"
        else:
            self.shared = self.home / ".agents/skills"
            self.native = {
                "claude-code": Path(
                    os.environ.get("CLAUDE_CONFIG_DIR") or self.home / ".claude"
                )
                / "skills",
                "codex": Path(os.environ.get("CODEX_HOME") or self.home / ".codex")
                / "skills",
                "opencode": Path(
                    os.environ.get("XDG_CONFIG_HOME") or self.home / ".config"
                )
                / "opencode/skills",
            }
            default = (
                Path(os.environ.get("XDG_STATE_HOME") or self.home / ".local/state")
                / "skill-manager/v1"
            )
        self.state_dir = (
            Path(state_dir).expanduser().resolve() if state_dir else default
        )

    def roots(self):
        return {
            h: list(dict.fromkeys([self.shared, self.native[h]])) for h in HARNESSES
        }

    def placement(self, name):
        # Vercel universal agents write shared; Claude writes a harness symlink.
        return {
            "claude-code": self.native["claude-code"] / name,
            "codex": self.shared / name,
            "opencode": self.shared / name,
        }

    def binding(self):
        return {
            "scope": self.scope,
            "shared": str(self.shared),
            "native": {k: str(v) for k, v in self.native.items()},
            "state_dir": str(self.state_dir),
            "command": self.command,
        }

    def state(self):
        path = self.state_dir / "state.json"
        if not path.exists():
            return {"schema_version": 1, "skills": {}, "launchers": {}}
        data = json.loads(path.read_text())
        if (
            data.get("schema_version") != 1
            or not isinstance(data.get("skills"), dict)
            or not isinstance(data.get("launchers"), dict)
        ):
            raise Refusal(
                "unsupported Manager state; preserve it and inspect before migration"
            )
        return data

    def save(self, state):
        atomic_json(self.state_dir / "state.json", state)

    @contextmanager
    def lock(self):
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state_dir / "operation.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Refusal(
                    "another Manager operation holds this state lock"
                ) from exc
            yield


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".manager-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
