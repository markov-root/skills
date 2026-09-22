# Installation contract

The command envelope has `schema_version: 1`, `command`, and command-specific
fields. Exit 0 means a clean observation, ready plan, or verified operation;
1 means differences (`diff`) or health/apply/check failures; 2 is argparse usage;
3 means conflict, stale evidence, malformed input, or unavailable prerequisite;
130 means interrupted. Read `status` as well as the exit code.

Global scope is the default. `--scope project --project-root PATH` uses the
project's discovery roots. Global observation covers `.agents/skills`, Claude's
native skill root, Codex's native skill root including `.system`, and OpenCode's
native skill root. Environment overrides for their documented configuration
locations are respected. Project observation covers `.agents/skills` and each
harness's native project directory. Supported deployment targets are explicitly
Claude Code, Codex, and OpenCode. A shared copy can also be visible to other
harnesses; updating that copy updates what those consumers read.

`present` means a readable artifact at an observed path. `absent`, `broken`,
`unavailable`, and `ambiguous` remain distinct observations. Two independent
copies exposed to one harness are ambiguous even when equal. Manager does not
guess precedence. User-installed plugins and remote/platform-hosted skills outside
these filesystem roots are outside coverage. Bundled system skills are observed
separately and never adopted for sync/removal by discovery alone.

Identity accepts a scalar top-level YAML name and a scalar metadata.version.
Unsupported name syntax is reported rather than evaluated. This is a bounded
identity reader, not a YAML or Agent Skills validator. Missing versions remain
unknown. Complete file manifests contain SHA-256 hashes, sizes and permission
bits. Nested links are observed without traversal and rejected in source artifacts.
VCS and Python bytecode caches excluded by the pinned upstream installer are
excluded consistently. Other generated files remain significant; keep runtime
state outside installable artifacts. Binary changes are metadata-only in diffs.

Manager retains only its own baselines and launcher ownership. Global state lives
under `$XDG_STATE_HOME/skill-manager/v1` or `~/.local/state/skill-manager/v1`; project
state is `.skill-manager/v1` in the project. `--state-dir` explicitly overrides it.
The versioned directory keeps retired Manager state untouched. State records local source paths and file manifests, so keep it private. Read-only
commands do not initialize state. Apply uses an exclusive POSIX advisory lock,
atomic state writes, and an operation receipt. A lock coordinates Manager processes
using that same state directory; it cannot lock editors or upstream invocations
outside Manager. Source/target fingerprints are checked before and after effects.

`sync` accepts an exact local artifact and delegates to a pinned
`npx --yes skills@1.5.23 add` with telemetry disabled and explicit targets. The
`--skills-command` JSON argv override supports an already installed CLI for
offline/cached use. It is trusted operator configuration, executed without a shell.
Changing scope or adapter invalidates existing plans/baseline bindings. Manager
does not install missing system prerequisites.

Plans contain exact content manifests and intended paths. They do not contain
file bodies. Apply re-derives the whole plan and rejects stale or altered input.
Installed modifications and missing baselines require reviewed resolution; repair
native overrides outside Vercel's placement separately. Applying identical content
skips Vercel and records verified baseline adoption. Repeating sync is a verified
no-op. No operation claims cross-tool atomicity or automatic rollback.

Removal delegates to Vercel only for unchanged installations covered by a Manager
receipt. It preserves unknown/modified paths and refuses while owned launchers
remain. Public release/export and MCP configuration never occur as a side effect.
