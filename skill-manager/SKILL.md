---
name: skill-manager
description: >-
  Inspect installed skills across Claude Code, Codex, and OpenCode; compare source
  artifacts with installed copies; sync reviewed development changes through Vercel
  skills; and manage optional owned PATH launchers. Use for skill installation
  state, stale copies, post-development sync, command exposure, and installation
  health. MCP server provisioning belongs to MCPM and install-mcp.
license: Apache-2.0
compatibility: >-
  Python 3.11+ on POSIX. Inventory and diff use only the standard library.
  Placement requires Node 20+ and npx; the default adapter pins Vercel skills 1.5.23.
  An uncached upstream invocation needs network access. PATH exposure is optional.
metadata:
  version: "0.1.2"
---

# Skill manager

Make installed skill state visible and bring reviewed source changes into the
installed copies. Each skill retains its own runtime implementation and portable
invocation. Vercel skills owns placement; MCPM owns MCP servers.

## Invocation

Resolve `<skill-root>` from the directory containing this loaded `SKILL.md`, following
symlinks to the artifact when needed. It is a placeholder for the actual location supplied
by the harness, not a fixed install directory or the shell's working directory. If that
location is unavailable, use the harness's skill location metadata or ask for it rather
than guessing a home-directory path.

Prefer the named PATH command after checking once per session that it targets this
artifact: use `command -v`, then inspect the resolved symlink or launcher target and
runner against `assets/cli.json`. A matching command name or version alone is insufficient.
If the command is absent, points elsewhere, or cannot be verified, use the bundled
invocation below. Quote the resolved root so installation paths containing spaces work.
Keep the caller's working directory. PATH installation and skill-manager are optional;
these instructions work with an ordinary skills.sh installation too.

Preferred command: `skill-manager`. Bundled fallback examples:

```sh
python3 "<skill-root>/scripts/skill-manager" list
python3 "<skill-root>/scripts/skill-manager" diff <artifact-directory>
python3 "<skill-root>/scripts/skill-manager" sync <artifact-directory> --plan <plan.json>
python3 "<skill-root>/scripts/skill-manager" sync --plan <plan.json> --apply
```

Every command accepts `--json`; use `--help` for scope and adapter options.

## Workflow

1. Use `list` or `doctor` to inspect observed discovery paths. Read the
   [installation contract](knowledge/installation-contract.md) for scope,
   provenance, statuses, and upstream boundaries. A path observation does not
   prove a running harness has refreshed its context.
2. Select the exact artifact containing `SKILL.md`. Run its own validation before
   deploying development changes. `diff` compares contents and permissions,
   including edits with an unchanged version number.
3. Inspect added, changed, and removed paths and any conflicts. A missing baseline
   cannot establish which copy was edited. `--accept-installed` explicitly chooses
   the selected source over differing installed contents; use it only after that
   resolution is authorized. Broken or ambiguous paths need separate repair.
4. `sync` previews by default. Save a plan for review, then apply it within the
   user's authorization. Apply refuses changed preconditions and verifies the
   resulting copies. A failed upstream operation can leave partial changes; inspect
   the receipt and `doctor` before retrying.
5. Use `finish` to compose the skill's own validation, sync, and installed smoke
   command. Read [development workflow](knowledge/development-workflow.md) for an
   example and the distinction between source checks, installed checks, and reload.
6. If requested, expose declared commands with `cli`. Read the
   [PATH contract](knowledge/path-contract.md) before applying launchers or
   adopting an existing symlink. Optional exposure never changes public skill
   requirements. `remove` previews removal of unchanged managed installations;
   remove their owned launchers first.

For a remote source, use Vercel skills to obtain a reviewed local artifact before
syncing it. This release coordinates local artifact deployment; it does not
resolve remote releases or infer source URLs. Upstream update and public Git
publication remain distinct operations.

Report the selected source, affected harness paths, content differences, apply
result, and checks actually performed. Keep unavailable provenance and runtime
checks explicit. Feedback onboarding is optional: if `skill-feedback` is available,
use its existing `onboard` command and privacy policy.

## Resources

- [CLI declarations](assets/cli.json) describe this skill's optional command.
- [Upstream evidence](references/SOURCES.md) records the adapter baseline and
  re-verification triggers.
