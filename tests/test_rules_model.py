"""Tests for the ocx_rules core data model."""
from __future__ import annotations

import dataclasses

import pytest

from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    Finding,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
)


def _spec(**overrides) -> RuleSpec:
    base = dict(
        rule_id="OCX-TEST-001",
        title="t",
        description="d",
        category="identity",
        severity=Severity.ERROR,
        source="unittest",
        requires=frozenset({"xml"}),
        check=CheckRef(primitive="unique"),
        params={"xpath": "//*"},
    )
    base.update(overrides)
    return RuleSpec(**base)


class TestModel:
    def test_severity_values(self):
        assert {s.value for s in Severity} == {"error", "warning", "info"}

    def test_rule_status_values(self):
        assert {s.value for s in RuleStatus} == {
            "passed", "failed", "not_implemented", "skipped", "crashed"}

    def test_rule_spec_is_frozen(self):
        spec = _spec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.rule_id = "X"

    def test_check_ref_exactly_one_kind(self):
        with pytest.raises(ValueError):
            CheckRef(primitive="unique", custom="m:f")
        with pytest.raises(ValueError):
            CheckRef()

    def test_finding_defaults(self):
        f = Finding(message="boom")
        assert f.element_id is None and f.guid is None and f.location is None

    def test_rule_result_defaults(self):
        r = RuleResult(spec=_spec(), status=RuleStatus.PASSED)
        assert r.findings == () and r.reason is None and r.duration_ms == 0.0

    def test_rule_pack(self):
        pack = RulePack(name="p", version="1.0", rules=(_spec(),))
        assert pack.rules[0].rule_id == "OCX-TEST-001"

    def test_check_not_implemented_is_exception(self):
        assert issubclass(CheckNotImplemented, Exception)
