"""Tests for the agent-facing JSON report of rule validation results."""
from __future__ import annotations

from ocx_model_validator.reporting.generators import rules_json
from ocx_rules.model import (
    CheckRef,
    Finding,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
)


def _spec(rule_id: str = "OCX-ID-001", severity: Severity = Severity.ERROR,
          source: str = "https://ocxwiki.example/best-practice#guids") -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id,
        title="Unique GUIDs",
        description="All entities shall carry a unique GUIDRef.",
        category="identity",
        severity=severity,
        source=source,
        requires=frozenset({"xml"}),
        check=CheckRef(primitive="noop"),
    )


class TestRulesJsonBuild:
    def test_top_level_shape(self):
        doc = rules_json.build([], model="m.3docx")
        assert doc["report"] == "ocx-rule-validation"
        assert doc["model"] == "m.3docx"
        assert "validated_at" in doc
        assert doc["results"] == []
        assert doc["summary"]["rules_run"] == 0

    def test_result_carries_provenance_and_findings(self):
        finding = Finding(message="duplicate GUID", element_id="PL1",
                          guid="abc-123", location=42)
        result = RuleResult(spec=_spec(), status=RuleStatus.FAILED,
                            findings=(finding,), duration_ms=1.5)
        doc = rules_json.build([result], model="m.3docx")
        (entry,) = doc["results"]
        assert entry["rule_id"] == "OCX-ID-001"
        assert entry["severity"] == "error"
        assert entry["source"] == "https://ocxwiki.example/best-practice#guids"
        assert entry["status"] == "failed"
        assert entry["category"] == "identity"
        assert entry["description"].startswith("All entities")
        (f,) = entry["findings"]
        assert f == {"message": "duplicate GUID", "element_id": "PL1",
                     "guid": "abc-123", "location": 42}

    def test_summary_counts_statuses_and_finding_severities(self):
        failed_err = RuleResult(
            spec=_spec("R-1", Severity.ERROR), status=RuleStatus.FAILED,
            findings=(Finding(message="a"), Finding(message="b")))
        failed_warn = RuleResult(
            spec=_spec("R-2", Severity.WARNING), status=RuleStatus.FAILED,
            findings=(Finding(message="c"),))
        passed = RuleResult(spec=_spec("R-3"), status=RuleStatus.PASSED)
        skipped = RuleResult(spec=_spec("R-4"), status=RuleStatus.SKIPPED,
                             reason="no geometry")
        doc = rules_json.build([failed_err, failed_warn, passed, skipped],
                               model="m.3docx")
        summary = doc["summary"]
        assert summary["rules_run"] == 4
        assert summary["by_status"] == {"failed": 2, "passed": 1, "skipped": 1}
        assert summary["error_findings"] == 2
        assert summary["warning_findings"] == 1

    def test_skipped_reason_preserved(self):
        result = RuleResult(spec=_spec(), status=RuleStatus.SKIPPED,
                            reason="requires geometry")
        doc = rules_json.build([result], model="m.3docx")
        assert doc["results"][0]["reason"] == "requires geometry"
        assert doc["results"][0]["findings"] == []

    def test_json_serialisable(self):
        import json

        result = RuleResult(spec=_spec(), status=RuleStatus.FAILED,
                            findings=(Finding(message="x"),))
        text = json.dumps(rules_json.build([result], model="m.3docx"))
        assert "ocx-rule-validation" in text
