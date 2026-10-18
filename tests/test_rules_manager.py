"""Tests for RuleManager: discovery, filtering, execution semantics."""
from __future__ import annotations

from pathlib import Path

import pytest
from ocx_rules.config import RuleConfig
from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    Finding,
    RulePack,
    RuleSpec,
    RuleStatus,
    Severity,
)

# --- helper checks used via CheckRef(custom=...) -----------------------------

def check_passes(context, params):
    return []


def check_fails(context, params):
    return [Finding(message="violation", element_id="e1")]


def check_crashes(context, params):
    raise RuntimeError("kaboom")


def check_stub(context, params):
    raise CheckNotImplemented("later")


_HERE = "tests.test_rules_manager"


def _spec(rule_id, custom, requires=frozenset({"xml"}), category="identity",
          severity=Severity.ERROR):
    return RuleSpec(
        rule_id=rule_id, title=rule_id, description="d", category=category,
        severity=severity, source="unittest", requires=requires,
        check=CheckRef(custom=f"{_HERE}:{custom}"), params={})


def _pack(*specs):
    return RulePack(name="test", version="0", rules=tuple(specs))


@pytest.fixture()
def context(stub_dir_310: Path) -> ValidationContext:
    return ValidationContext(stub_dir_310 / "ocxxml.3docx")


class TestExecution:
    def test_statuses(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-PASS", "check_passes"),
            _spec("R-FAIL", "check_fails"),
            _spec("R-CRASH", "check_crashes"),
            _spec("R-STUB", "check_stub"),
        )])
        by_id = {r.spec.rule_id: r for r in manager.run(context)}
        assert by_id["R-PASS"].status is RuleStatus.PASSED
        assert by_id["R-FAIL"].status is RuleStatus.FAILED
        assert by_id["R-FAIL"].findings[0].message == "violation"
        assert by_id["R-CRASH"].status is RuleStatus.CRASHED
        assert "kaboom" in by_id["R-CRASH"].reason
        assert by_id["R-STUB"].status is RuleStatus.NOT_IMPLEMENTED

    def test_crash_does_not_abort_run(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-CRASH", "check_crashes"), _spec("R-PASS", "check_passes"))])
        results = manager.run(context)
        assert [r.status for r in results] == [RuleStatus.CRASHED, RuleStatus.PASSED]

    def test_unsatisfied_xml_requirement_skips(self, tmp_path):
        manager = RuleManager(packs=[_pack(_spec("R-PASS", "check_passes"))])
        results = manager.run(ValidationContext(tmp_path / "nope.3docx"))
        assert results[0].status is RuleStatus.SKIPPED
        assert results[0].reason

    def test_unsatisfied_ir_requirement_skips(self, context, monkeypatch):
        import ocx_rules.context as context_mod
        monkeypatch.setattr(
            context_mod, "_build_vessel",
            lambda p: (_ for _ in ()).throw(ValueError("no IR")))
        manager = RuleManager(packs=[_pack(
            _spec("R-IR", "check_passes", requires=frozenset({"ir"})))])
        results = manager.run(context)
        assert results[0].status is RuleStatus.SKIPPED

    def test_filter_by_category_and_rule_id(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-A", "check_passes", category="identity"),
            _spec("R-B", "check_passes", category="topology"),
        )])
        assert [r.spec.rule_id for r in manager.run(context, category="topology")] == ["R-B"]
        assert [r.spec.rule_id for r in manager.run(context, rule_id="R-A")] == ["R-A"]

    def test_config_disable_and_override(self, context):
        cfg = RuleConfig(disabled=frozenset({"R-B"}),
                         overrides={"R-A": {"severity": "info"}})
        manager = RuleManager(config=cfg, packs=[_pack(
            _spec("R-A", "check_passes"), _spec("R-B", "check_passes"))])
        results = manager.run(context)
        assert [r.spec.rule_id for r in results] == ["R-A"]
        assert results[0].spec.severity is Severity.INFO


class TestDiscovery:
    def test_entry_point_discovery_finds_best_practice_pack(self):
        packs = RuleManager().discover()
        assert "best_practice" in [p.name for p in packs]

    def test_duplicate_rule_ids_across_packs_rejected(self):
        from ocx_rules.catalogue import CatalogueError
        manager = RuleManager(packs=[
            _pack(_spec("R-DUP", "check_passes")),
            _pack(_spec("R-DUP", "check_passes")),
        ])
        with pytest.raises(CatalogueError, match="R-DUP"):
            manager.rules()
