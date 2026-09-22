# Skill manager

Inspect installed skills, compare source changes, and sync reviewed artifacts
across Claude Code, Codex, and OpenCode. Optional PATH commands are a local
convenience; each public skill remains usable independently.

Install this repository with Vercel skills, selecting `skill-manager` and your
target agents. From the installed folder, run:

```sh
python3 scripts/skill-manager list
python3 scripts/skill-manager sync /path/to/skill-artifact
```

Sync previews by default; `--apply` performs the operation. Python 3.11+ on POSIX
is required. Placement also requires Node 20+ and npx. See [SKILL.md](SKILL.md)
for the full workflow and contracts. No public remote URL is assumed by this README.
