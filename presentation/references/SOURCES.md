# Sources

External guidance this skill's knowledge relies on. The decision record behind the standard is
the dev factory's research 0001 (not shipped).

| Topic | Source | Used in |
| --- | --- | --- |
| Stand-off annotation anchored by quoted text | W3C, *Web Annotation Data Model*, §4.2.4 TextQuoteSelector (Recommendation, 23 Feb 2017), https://www.w3.org/TR/annotation-model/#text-quote-selector | `script-format.md` |
| Version numbers | *Semantic Versioning 2.0.0*, https://semver.org/ | `artifact-contract.md` (adapted: the levels describe audience-visible change, not API change) |
| Intent vs. resolved fact (lockfiles) | the manifest/lockfile split used by package managers, e.g. Cargo, *Cargo.toml vs Cargo.lock*, https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html | `artifact-contract.md` (pins) |
| Design tokens | W3C Design Tokens Community Group, *Design Tokens Format Module* (draft), https://tr.designtokens.org/format/ | `components.md` |
| JSON Schema | *JSON Schema 2020-12*, https://json-schema.org/draft/2020-12 | the schemas in `assets/schemas/` |
| Dual encoding; never colour alone | W3C, *WCAG 2.2*, Success Criterion 1.4.1 Use of Color, https://www.w3.org/TR/WCAG22/#use-of-color | `deck-standard.md` |
