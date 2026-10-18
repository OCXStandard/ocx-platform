"""Agent-facing JSON report for rule validation results.

Produces a plain dict (JSON-serialisable) mirroring the schema-validation
sidecar: model identity, a run summary and one entry per rule with full
source provenance (wiki source, category, severity) plus every finding's
element id, GUID and XML line number.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ocx_rules.model import RuleResult, RuleStatus, Severity

REPORT_KIND = "ocx-rule-validation"


def build(results: list[RuleResult], *, model: str) -> dict:
    """Build the JSON-serialisable report document for *results*."""
    by_status: dict[str, int] = {}
    error_findings = 0
    warning_findings = 0
    for result in results:
        by_status[result.status.value] = by_status.get(result.status.value, 0) + 1
        if result.status is RuleStatus.FAILED:
            if result.spec.severity is Severity.ERROR:
                error_findings += len(result.findings)
            elif result.spec.severity is Severity.WARNING:
                warning_findings += len(result.findings)

    return {
        "report": REPORT_KIND,
        "model": model,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "rules_run": len(results),
            "by_status": by_status,
            "error_findings": error_findings,
            "warning_findings": warning_findings,
        },
        "results": [_result_entry(r) for r in results],
    }


def _result_entry(result: RuleResult) -> dict:
    spec = result.spec
    return {
        "rule_id": spec.rule_id,
        "title": spec.title,
        "description": spec.description,
        "category": spec.category,
        "severity": spec.severity.value,
        "source": spec.source,
        "status": result.status.value,
        "reason": result.reason,
        "duration_ms": result.duration_ms,
        "findings": [
            {"message": f.message, "element_id": f.element_id,
             "guid": f.guid, "location": f.location}
            for f in result.findings
        ],
    }
