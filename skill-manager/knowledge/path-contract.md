# Optional PATH commands

Declare supported entry points in `assets/cli.json`:

```json
{
  "schema_version": 1,
  "commands": {
    "example": {"runner": "python3", "path": "scripts/example.py", "args": []}
  }
}
```

This is a portfolio extension, not an upstream skills.sh hook. Runners are
`python3`, `bash`, `uv` (runs `uv run --script`), and `exec` (an executable target).
Targets stay inside the artifact's `scripts` directory. Helpers are exposed only
when explicitly declared. Dependencies and command behavior stay with their skill.

```sh
python3 <skill-root>/scripts/skill-manager cli <installed-artifact>
python3 <skill-root>/scripts/skill-manager cli <installed-artifact> --apply
python3 <skill-root>/scripts/skill-manager cli <installed-artifact> --remove --apply
```

The default destination is `~/.local/bin`; `--bin-dir` overrides it. The directory
must already be in the user's PATH to use bare names; shell configuration belongs
to the operator. Generated POSIX wrappers quote every argument, preserve the
caller's working directory, and use `exec` for signals/exit semantics. They invoke
the selected artifact directly and do not depend on Manager at runtime.

Existing unowned entries, modified generated files, missing prerequisites, and
commands shadowed earlier on PATH produce conflicts. `--adopt-existing` permits
an exact existing target symlink or the exact generated uv wrapper from the retired portfolio expose-clis script. The wrapper must match the reviewed declaration byte-for-byte and be executable; arbitrary or edited scripts remain conflicts. A
renamed declaration removes only unchanged owned obsolete launchers. Each file
write has an ownership receipt; partial filesystem failures remain diagnosable.

Use the installed artifact for normal operation. Passing a source directory is
an explicit development choice; the receipt records that path, and it may differ
from what harnesses load. There is no implicit live-source switching or watcher.
