"""Tests for the rule-validation Report (tables rendered to rich/md/HTML)."""
from __future__ import annotations

from ocx_model_validator.reporting.generators import rules_report
from ocx_rules.model import (
    CheckRef,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
    Unchecked,
)


def _spec(rule_id: str = "R-1") -> RuleSpec:
    return RuleSpec(rule_id=rule_id, title="t", description="d",
                    category="topology", severity=Severity.ERROR,
                    source="s", requires=frozenset({"xml"}),
                    check=CheckRef(primitive="noop"))


def _tables(report):
    (section,) = report.sections
    return {t.title: t for t in section.tables}, section.notes


def test_rules_table_has_unchecked_count_column():
    results = [
        RuleResult(spec=_spec("R-1"), status=RuleStatus.PASSED,
                   unchecked=(Unchecked("x", "e1"), Unchecked("y", "e2"))),
        RuleResult(spec=_spec("R-2"), status=RuleStatus.PASSED),
    ]
    tables, _ = _tables(rules_report.build(results, source_file="m"))
    rules = tables["Rules"]
    col = rules.columns.index("Unchecked")
    assert rules.columns[col - 1] == "Findings"
    assert [row[col] for row in rules.rows] == [2, None]


def test_unchecked_elements_table_lists_entries():
    results = [RuleResult(spec=_spec("R-1"), status=RuleStatus.PASSED,
                          unchecked=(Unchecked("no surface", "e1", "g1"),))]
    tables, notes = _tables(rules_report.build(results, source_file="m"))
    table = tables["Unchecked elements"]
    assert table.columns == ["Rule", "Element", "GUID", "Reason"]
    assert table.rows == [["R-1", "e1", "g1", "no surface"]]
    assert notes == []


def test_unchecked_table_absent_when_empty():
    results = [RuleResult(spec=_spec(), status=RuleStatus.PASSED)]
    tables, _ = _tables(rules_report.build(results, source_file="m"))
    assert "Unchecked elements" not in tables


def test_unchecked_table_truncated_with_note():
    many = tuple(Unchecked("r", f"e{i}") for i in range(5))
    results = [RuleResult(spec=_spec(), status=RuleStatus.PASSED,
                          unchecked=many)]
    tables, notes = _tables(rules_report.build(results, source_file="m",
                                               max_findings=2))
    assert len(tables["Unchecked elements"].rows) == 2
    assert "Unchecked elements truncated to the first 2 of 5." in notes
