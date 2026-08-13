"""Human presentation for immutable engineering run records."""

from __future__ import annotations

from .lifecycle import FinishRecord, StartRecord


def render_start(record: StartRecord) -> str:
    selected = sum(item.selected for item in record.checks)
    failed = sum(
        item.baseline_status in {"failed", "timed_out", "unavailable"} for item in record.checks
    )
    approvals = ", ".join(record.approvals_required) or "none"
    return "\n".join(
        [
            "# Engineering run started",
            "",
            f"- Run ID: `{record.run_id}`",
            f"- Intent: {record.intent}",
            f"- Baseline checks: {selected} selected · {failed} failed/unavailable",
            f"- Approvals required: {approvals}",
            f"- Next: `{record.next_command}`",
            "",
        ]
    )


def render_finish(record: FinishRecord) -> str:
    lines = [
        "# Engineering finish evidence",
        "",
        f"- Run ID: `{record.run_id}`",
        f"- Checks executed: {sum(item.selected for item in record.check_plans)}",
        f"- Outstanding approvals: {', '.join(record.approvals_required) or 'none'}",
        f"- Unexpected paths: {', '.join(record.unexpected_paths) or 'none'}",
        f"- Validation findings: {len(record.validations)}",
        "",
        "## Supported claims",
        "",
        *(f"- {claim}" for claim in record.claims),
        "",
        "## Check evidence",
        "",
        "| Check | Comparison | Baseline | Final |",
        "| --- | --- | --- | --- |",
        *(
            f"| {item.name} | {item.classification} | "
            f"{item.baseline_status or 'not run'} | {item.final_status or 'not run'} |"
            for item in record.evidence
        ),
        "",
        "## Pre-existing failures",
        "",
        *(
            (f"- {name}" for name in record.preexisting_failures)
            if record.preexisting_failures
            else ("- none",)
        ),
        "",
        "## Checks not run",
        "",
        *(
            (f"- {item}" for item in record.checks_not_run)
            if record.checks_not_run
            else ("- none",)
        ),
        "",
        "## Validation findings",
        "",
        *(
            (
                f"- {item.source} · {item.code} · {item.path or '-'}: {item.message}"
                for item in record.validations
            )
            if record.validations
            else ("- none",)
        ),
        "",
        "## Semantic reviews",
        "",
        *(
            (
                f"- {item.reviewer}/{item.profile}: {item.status} ({item.reason})"
                for item in record.review_plans
            )
            if record.review_plans
            else ("- none adopted",)
        ),
        "",
        "## Manual recovery",
        "",
        *(
            (f"- {item}" for item in record.manual_recovery_steps)
            if record.manual_recovery_steps
            else ("- none recorded",)
        ),
        "",
        "## Assumptions",
        "",
        *(f"- {assumption}" for assumption in record.assumptions),
        "",
        "## Residual risks",
        "",
        *(f"- {risk}" for risk in record.residual_risks),
        "",
    ]
    return "\n".join(lines)
