"""Report generator for rule-based validation results."""
from __future__ import annotations

from ocx_rules.model import RuleResult, RuleStatus

from ocx_model_validator.reporting.model import Report, ReportSection, ReportTable

_STATUS_LABEL = {
    RuleStatus.PASSED: "passed",
    RuleStatus.FAILED: "FAILED",
    RuleStatus.NOT_IMPLEMENTED: "not implemented",
    RuleStatus.SKIPPED: "skipped",
    RuleStatus.CRASHED: "CRASHED",
}


def build(results: list[RuleResult], *, source_file: str,
          max_findings: int = 50) -> Report:
    """Build a Report: status summary, per-rule table and a findings table."""
    counts: dict[RuleStatus, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    summary = ReportTable(
        title="Summary",
        columns=["Status", "Rules"],
        rows=[[_STATUS_LABEL[s], n] for s, n in sorted(
            counts.items(), key=lambda kv: kv[0].value)],
        footer_rows=[["total", len(results)]],
    )

    rules_table = ReportTable(
        title="Rules",
        columns=["Rule", "Title", "Category", "Severity", "Status",
                 "Findings", "Note"],
        rows=[[r.spec.rule_id, r.spec.title, r.spec.category,
               r.spec.severity.value, _STATUS_LABEL[r.status],
               len(r.findings) or None, r.reason]
              for r in results],
    )

    finding_rows = []
    for result in results:
        for finding in result.findings:
            finding_rows.append([result.spec.rule_id,
                                 result.spec.severity.value,
                                 finding.message, finding.element_id,
                                 finding.guid, finding.location])
    truncated = len(finding_rows) > max_findings
    findings_table = ReportTable(
        title="Findings",
        columns=["Rule", "Severity", "Message", "Element", "GUID", "Line"],
        rows=finding_rows[:max_findings],
    )

    notes = []
    if truncated:
        notes.append(f"Findings truncated to the first {max_findings} of "
                     f"{len(finding_rows)}.")
    tables = [summary, rules_table]
    if finding_rows:
        tables.append(findings_table)
    return Report(
        title="Rule validation",
        metadata={"model": source_file, "rules run": str(len(results))},
        sections=[ReportSection(title="Rule-based validation",
                                tables=tables, notes=notes)],
    )
