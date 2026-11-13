"""Report generator for rule-based validation results."""
from __future__ import annotations

from ocx_rules.model import RuleResult, RuleStatus

from ocx_model_validator.reporting.model import (
    Badge,
    Cell,
    Report,
    ReportSection,
    ReportTable,
)

_STATUS_LABEL = {
    RuleStatus.PASSED: "passed",
    RuleStatus.FAILED: "FAILED",
    RuleStatus.NOT_IMPLEMENTED: "not implemented",
    RuleStatus.SKIPPED: "skipped",
    RuleStatus.CRASHED: "CRASHED",
}

_COLUMNS = ["Category / rule", "Title / message", "Severity", "Status",
            "Findings", "Unchecked", "Element", "GUID", "Line"]


def _status_counts(results: list[RuleResult]) -> list[tuple[RuleStatus, int]]:
    counts: dict[RuleStatus, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[0].value)


def _rule_rows(result: RuleResult) -> list[list[Cell]]:
    spec = result.spec
    badge = Badge(spec.severity.value, spec.severity.value)
    title = f"{spec.title} ({result.reason})" if result.reason else spec.title
    rows: list[list[Cell]] = [[
        spec.rule_id, title, badge, _STATUS_LABEL[result.status],
        len(result.findings) or None, len(result.unchecked) or None,
        None, None, None]]
    rows += [[None, f.message, badge, "finding", None, None,
              f.element_id, f.guid, f.location] for f in result.findings]
    rows += [[None, u.reason, None, "unchecked", None, None,
              u.element_id, u.guid, None] for u in result.unchecked]
    return rows


def build(results: list[RuleResult], *, source_file: str) -> Report:
    """Build a Report: status summary plus one table with an expandable row
    per rule category holding its rules, findings and unchecked elements."""
    summary = ReportTable(
        title="Summary",
        columns=["Status", "Rules"],
        rows=[[_STATUS_LABEL[s], n] for s, n in _status_counts(results)],
        footer_rows=[["total", len(results)]],
    )

    by_category: dict[str, list[RuleResult]] = {}
    for result in results:
        by_category.setdefault(result.spec.category, []).append(result)
    rows: list[list[Cell]] = []
    children: list[list[list[Cell]]] = []
    for category, members in by_category.items():
        status = ", ".join(f"{n} {_STATUS_LABEL[s]}"
                           for s, n in _status_counts(members))
        rows.append([category, f"{len(members)} rule(s)", None, status,
                     sum(len(r.findings) for r in members) or None,
                     sum(len(r.unchecked) for r in members) or None,
                     None, None, None])
        children.append([row for r in members for row in _rule_rows(r)])
    rules_table = ReportTable(title="Rules", columns=_COLUMNS, rows=rows,
                              row_children=children)

    return Report(
        title="Rule validation",
        metadata={"model": source_file, "rules run": str(len(results))},
        sections=[ReportSection(title="Rule-based validation",
                                tables=[summary, rules_table])],
    )
