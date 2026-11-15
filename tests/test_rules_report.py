"""Tests for the rule-validation Report (tables rendered to rich/md/HTML)."""
from __future__ import annotations

from ocx_model_validator.reporting.generators import rules_report
from ocx_model_validator.reporting.model import Badge
from ocx_rules.model import (
    CheckRef,
    Finding,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
    Unchecked,
)


def _spec(rule_id: str = "R-1", category: str = "topology",
          severity: Severity = Severity.ERROR) -> RuleSpec:
    return RuleSpec(rule_id=rule_id, title=f"title {rule_id}", description="d",
                    category=category, severity=severity,
                    source="s", requires=frozenset({"xml"}),
                    check=CheckRef(primitive="noop"))


def _section(results):
    (section,) = rules_report.build(results, source_file="m").sections
    return section


def _rules_table(results):
    return {t.title: t for t in _section(results).tables}["Rules"]


def test_report_has_summary_and_one_rules_table_without_notes():
    results = [RuleResult(spec=_spec(), status=RuleStatus.FAILED,
                          findings=tuple(Finding(f"m{i}") for i in range(60)),
                          unchecked=(Unchecked("u", "e1"),))]
    section = _section(results)
    assert [t.title for t in section.tables] == ["Summary", "Rules"]
    assert section.notes == []


def test_one_row_per_category_in_first_seen_order():
    results = [
        RuleResult(spec=_spec("T-1", "topology"), status=RuleStatus.PASSED),
        RuleResult(spec=_spec("P-1", "properties"), status=RuleStatus.PASSED),
        RuleResult(spec=_spec("T-2", "topology"), status=RuleStatus.FAILED,
                   findings=(Finding("bad"),)),
    ]
    table = _rules_table(results)
    assert [row[0] for row in table.rows] == ["topology", "properties"]


def test_category_row_summarises_its_rules():
    results = [
        RuleResult(spec=_spec("T-1"), status=RuleStatus.PASSED,
                   unchecked=(Unchecked("u", "e9"),)),
        RuleResult(spec=_spec("T-2"), status=RuleStatus.FAILED,
                   findings=(Finding("a"), Finding("b"))),
    ]
    (row,) = _rules_table(results).rows
    assert row == ["topology", "2 rule(s)", None,
                   Badge("1 FAILED, 1 passed", "error"),
                   2, 1, None, None, None]


def test_category_without_failures_has_plain_status():
    results = [RuleResult(spec=_spec("T-1"), status=RuleStatus.PASSED),
               RuleResult(spec=_spec("T-2"), status=RuleStatus.SKIPPED)]
    (row,) = _rules_table(results).rows
    assert row[3] == "1 passed, 1 skipped"


def test_children_list_rules_then_their_findings_and_unchecked():
    results = [
        RuleResult(spec=_spec("T-1", severity=Severity.WARNING),
                   status=RuleStatus.FAILED,
                   findings=(Finding("gap", "e1", "g1", 42),),
                   unchecked=(Unchecked("no surface", "e2", "g2"),)),
        RuleResult(spec=_spec("T-2"), status=RuleStatus.SKIPPED,
                   reason="needs geometry"),
    ]
    (children,) = _rules_table(results).row_children
    assert children == [
        ["T-1", "title T-1", "warning", Badge("FAILED", "error"), 1, 1,
         None, None, None],
        [None, "gap", "warning", Badge("finding", "warning"), None, None,
         "e1", "g1", 42],
        [None, "no surface", None, "unchecked", None, None, "e2", "g2", None],
        ["T-2", "title T-2 (needs geometry)", "error",
         "skipped", None, None, None, None, None],
    ]


def test_all_findings_listed_without_cap():
    many = tuple(Finding(f"m{i}") for i in range(500))
    results = [RuleResult(spec=_spec(), status=RuleStatus.FAILED,
                          findings=many)]
    (children,) = _rules_table(results).row_children
    assert sum(1 for c in children
               if c[3] == Badge("finding", "warning")) == 500
