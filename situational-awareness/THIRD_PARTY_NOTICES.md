# Third-party notices

This skill's original instructions, runtime code, provider logic, and bundled references are
licensed under Apache-2.0 (see [`LICENSE`](LICENSE)). Externally owned sources are linked and
synthesized rather than copied; dated cache-mechanics research is summarized in
[`references/0001-cache-optimization-findings.md`](references/0001-cache-optimization-findings.md)
with its verification report in
[`references/0001-verification.md`](references/0001-verification.md).

The bundled runtime is **stdlib-only** (no third-party Python packages), so no runtime dependencies
are shipped or keyed by name here. Build/development tooling used only by the private `dev/` factory
is tracked separately in that workspace and is never installed with the skill.
