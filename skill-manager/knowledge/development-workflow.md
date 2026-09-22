# Finish development and update installed copies

Each skill owns validation and smoke behavior. Manager accepts explicit JSON argv
arrays to compose them without a shell. The placeholders `{source}` and
`{installed}` expand to the chosen artifact paths.

```sh
python3 <manager-root>/scripts/skill-manager finish <artifact> \
  --validate-command '["python3", "/path/to/validate.py", "{source}"]' \
  --smoke-command '["python3", "{installed}/scripts/example.py", "--help"]'
```

This runs validation and previews sync. Add `--apply` under the user's deployment
authorization to perform it and then run the installed smoke. Prefer a side-effect
free functional check over `--help` when the skill provides one. `INSTALL_DIR` and
`SKILL_NAME` are also set for existing per-skill smoke scripts.

Validation failure prevents sync. Installed smoke failure reports failure even
if copying succeeded. PATH health is separate from runtime smoke and is reported
separately; invoking `cli` remains an explicit optional operation. `doctor` checks
observed installations, saved source drift, owned launchers, and the last operation.
Neither command proves a currently running agent reloaded skill instructions.

This release uses an explicit completion command. An editor watcher or development
hook is not enabled. Public consumers can install the skill folder through
skills.sh and run bundled scripts without Manager or PATH convenience. Local
source deployment and exporting/pushing public repositories have separate owners.
