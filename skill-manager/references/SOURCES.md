# Sources

- **Vercel skills** — https://github.com/vercel-labs/skills — installer, CLI and
  agent directory definitions. Checked 2026-09-06 using the locally cached 1.5.23
  package and upstream Context7 documentation. In this version universal agents
  use `.agents/skills`; Claude gets a native link/copy. Source files are copied
  to the canonical installation before harness links are created.
- **Agent Skills specification** — https://agentskills.io/specification —
  portable skill-folder contract. `assets/cli.json` is a local optional extension.
- **MCPM** — https://mcpm.sh/ — MCP management and client integration remain
  upstream responsibilities. Manager does not write MCP client configurations.

Re-verify placement, exclusions, flags, and harness roots when changing the pinned
Vercel adapter. Record actual versions and isolated installation evidence; current
documentation alone does not prove installed behavior.
