# Target agent contract

This file describes the stable target surface. It is not evidence that the CLI is implemented.

## Commands

```text
doc2md plan INPUT [SELECTION] [--profile NAME] [--json]
doc2md convert INPUT [SELECTION] [--output PATH|-] [--profile NAME] [--json]
doc2md batch MANIFEST [--resume RUN_ID] [--json]
doc2md show RUN_ID [--json]
doc2md status [--json]
doc2md doctor [--json]
doc2md cleanup [FILTERS] [--plan PLAN_ID] [--apply] [--json]
doc2md contract [--json]
doc2md benchmark ...
```

`INPUT` is a local path, an HTTP(S) URL, or `-` for stdin. `--profile` constrains policy; it does not
name an extractor. `SELECTION` is a bounded page, slide, sheet, or archive-entry request. The default
profile is local, extractive, and benchmark-routed.

`plan` may resolve, safely acquire the minimum evidence needed for detection, and report eligible
routes, but it performs no extraction, paid processing, or external processor upload. `doctor`
reports capability readiness and missing requirements without treating ambient credentials as
permission. `cleanup` is a dry run unless `--apply` references the exact unchanged plan.

`--output -` writes only Markdown to stdout and is incompatible with `--json`; the provenance result
remains discoverable through the emitted run ID. Encrypted-document secrets are accepted only
through a protected file/file-descriptor channel or trusted library callback, never as an argv value.

## Conversion result

Every conversion returns one versioned result object:

```json
{
  "schema_version": 1,
  "run_id": "opaque-id",
  "status": "ok|degraded|failed|paused",
  "request": {
    "profile": "balanced",
    "selection": null,
    "retention": "derived"
  },
  "source": {
    "input": "path-or-url",
    "canonical_url": null,
    "media_type": "application/pdf",
    "raw_sha256": "hex",
    "bytes": 12345,
    "retrieved_at": null
  },
  "output": {
    "markdown_path": "document.md",
    "markdown_sha256": "hex",
    "markdown_source_map_path": "document.source-map.json",
    "provenance_tier": "deterministic-extraction",
    "ir_path": "document-ir.json",
    "ir_sha256": "hex",
    "assets_dir": null,
    "coverage": {
      "scope": "whole|requested-subset",
      "fulfilled": [],
      "missing": []
    }
  },
  "route": {
    "profile": "balanced",
    "winner": "adapter-id",
    "attempts": []
  },
  "quality": {
    "usable": true,
    "score": null,
    "metrics": {},
    "flags": []
  },
  "provenance": {
    "doc2md_version": "version",
    "adapter_versions": {},
    "config_digest": "hex"
  },
  "warnings": []
}
```

## Artifact bundle

Runs live under `${DOC2MD_HOME:-~/.local/share/doc2md}/runs/<run-id>/`:

```text
result.json       machine-readable source of truth
document.md       selected Markdown output
raw/              source bytes when retention policy permits
attempts/         candidate outputs and diagnostics
assets/           referenced images or attachments, when requested
```

`result.json` is authoritative. Paths are relative to the run directory. A caller may request an
explicit output file, but the provenance record remains discoverable through `show`.

## Exit codes

```text
0  usable result (`ok` or caller-accepted `degraded`)
1  terminal failure
2  paused/recoverable; use the emitted resume command
3  invalid invocation or unavailable required capability
```

The schema is stable, not frozen. Breaking changes require a schema-version increment and migration
notes for every known consumer.
