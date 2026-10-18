"""Tests for identity best-practice checks (OCX-ID-001/004/005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    entitybase_has_guid_and_id,
    idbase_has_id,
    names_not_identifiers,
)

from tests.rules_xml import context_for


class TestEntityBaseHasGuidAndId:
    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>')
        assert entitybase_has_guid_and_id(ctx, {}) == []

    def test_missing_guid_and_missing_id(self):
        ctx = context_for('<ocx:Panel id="p1"/><ocx:Plate ocx:GUIDRef="bbb"/>')
        findings = entitybase_has_guid_and_id(ctx, {})
        assert len(findings) == 2
        assert "GUIDRef" in findings[0].message
        assert "id" in findings[1].message

    def test_non_entity_elements_ignored(self):
        ctx = context_for("<ocx:ComposedOf/><ocx:KnotVector/>")
        assert entitybase_has_guid_and_id(ctx, {}) == []


class TestIdBaseHasId:
    def test_pass_and_fail(self):
        ctx = context_for('<ocx:NURBS3D id="c1"/><ocx:PolyLine3D/>')
        (finding,) = idbase_has_id(ctx, {})
        assert "PolyLine3D" in finding.message


class TestNamesNotIdentifiers:
    def test_distinct_names_pass(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Panel id="b" name="Side"/>')
        assert names_not_identifiers(ctx, {}) == []

    def test_same_name_same_id_not_reported(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Panel id="a" name="Deck"/>')
        assert names_not_identifiers(ctx, {}) == []

    def test_collision_reported(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Plate id="b" name="Deck"/>')
        (finding,) = names_not_identifiers(ctx, {})
        assert "Deck" in finding.message
