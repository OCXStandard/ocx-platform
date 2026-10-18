"""Tests for the check-primitive library (real implementations)."""
from __future__ import annotations

import pytest
from ocx_rules.model import CheckNotImplemented
from ocx_rules.primitives import PRIMITIVE_REGISTRY, content

from tests.rules_xml import context_for

EXPECTED_PRIMITIVES = {
    "has_attribute", "unique", "cardinality", "value_in_set", "sequence",
    "ref_resolves", "closed_contour", "normals_consistent",
}


class TestPrimitiveRegistry:
    def test_all_expected_primitives_registered(self):
        assert set(PRIMITIVE_REGISTRY) == EXPECTED_PRIMITIVES

    @pytest.mark.parametrize("name", ["closed_contour", "normals_consistent"])
    def test_geometry_primitives_still_stubbed(self, name):
        with pytest.raises(CheckNotImplemented):
            PRIMITIVE_REGISTRY[name](context=None, params={})


class TestHasAttribute:
    PARAMS = {"xpath": "//ocx:Panel", "attribute": "ocx:GUIDRef"}

    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>')
        assert content.has_attribute(ctx, self.PARAMS) == []

    def test_missing_and_empty_fail(self):
        ctx = context_for('<ocx:Panel id="p1"/><ocx:Panel id="p2" ocx:GUIDRef=" "/>')
        findings = content.has_attribute(ctx, self.PARAMS)
        assert len(findings) == 2
        assert "ocx:GUIDRef" in findings[0].message
        assert findings[0].location is not None

    def test_no_matches_is_vacuous_pass(self):
        assert content.has_attribute(context_for(""), self.PARAMS) == []


class TestUnique:
    PARAMS = {
        "xpath": "//*[@ocx:GUIDRef]", "key": "@ocx:GUIDRef",
        "normalize": "guid", "exclude_tag_suffix": "Ref",
    }

    def test_pass(self):
        ctx = context_for('<ocx:Panel ocx:GUIDRef="aaa"/><ocx:Plate ocx:GUIDRef="bbb"/>')
        assert content.unique(ctx, self.PARAMS) == []

    def test_duplicate_reported_once_with_all_lines(self):
        ctx = context_for(
            '<ocx:Panel ocx:GUIDRef="{AAA}"/>'
            '<ocx:Plate ocx:GUIDRef="aaa"/>'
            '<ocx:Bracket ocx:GUIDRef="AAA"/>'
        )
        (finding,) = content.unique(ctx, self.PARAMS)
        assert "aaa" in finding.message and "3" in finding.message

    def test_ref_elements_excluded(self):
        ctx = context_for(
            '<ocx:Panel ocx:GUIDRef="aaa"/>'
            '<ocx:GridRef ocx:GUIDRef="aaa"/><ocx:GridRef ocx:GUIDRef="aaa"/>'
        )
        assert content.unique(ctx, self.PARAMS) == []

    def test_plain_id_uniqueness(self):
        params = {"xpath": "//*[@id]", "key": "@id"}
        ctx = context_for('<ocx:Panel id="x"/><ocx:Plate id="x"/>')
        assert len(content.unique(ctx, params)) == 1


class TestCardinality:
    PARAMS = {"xpath": "//ocx:Panel", "child": "ocx:ComposedOf", "min": 1}

    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p"><ocx:ComposedOf/></ocx:Panel>')
        assert content.cardinality(ctx, self.PARAMS) == []

    def test_below_min_fails(self):
        ctx = context_for('<ocx:Panel id="p"/>')
        (finding,) = content.cardinality(ctx, self.PARAMS)
        assert "at least 1" in finding.message
        assert finding.element_id == "p"

    def test_above_max_fails(self):
        params = {"xpath": "//ocx:Vessel", "child": "ocx:CoordinateSystem", "min": 1, "max": 1}
        ctx = context_for(
            '<ocx:Vessel id="v"><ocx:CoordinateSystem/><ocx:CoordinateSystem/></ocx:Vessel>')
        (finding,) = content.cardinality(ctx, params)
        assert "at most 1" in finding.message


class TestValueInSet:
    PARAMS = {"xpath": "//ocx:Panel", "key": "@tightness", "allowed": ["WaterTight", "NonTight"]}

    def test_pass_and_missing_key_ignored(self):
        ctx = context_for('<ocx:Panel tightness="WaterTight"/><ocx:Panel id="x"/>')
        assert content.value_in_set(ctx, self.PARAMS) == []

    def test_bad_value_fails(self):
        ctx = context_for('<ocx:Panel tightness="Soggy"/>')
        (finding,) = content.value_in_set(ctx, self.PARAMS)
        assert "Soggy" in finding.message


class TestSequence:
    PARAMS = {"xpath": "//ocx:KnotVector", "key": "@value"}

    def test_non_decreasing_passes(self):
        ctx = context_for('<ocx:KnotVector value="0 0 1 2 2"/>')
        assert content.sequence(ctx, self.PARAMS) == []

    def test_decreasing_fails(self):
        ctx = context_for('<ocx:KnotVector value="0 2 1"/>')
        (finding,) = content.sequence(ctx, self.PARAMS)
        assert "non-decreasing" in finding.message

    def test_max_run_enforced(self):
        params = dict(self.PARAMS, max_run=2)
        ctx = context_for('<ocx:KnotVector value="0 1 1 1 2"/>')
        (finding,) = content.sequence(ctx, params)
        assert "repeated" in finding.message

    def test_non_numeric_is_finding_not_crash(self):
        ctx = context_for('<ocx:KnotVector value="0 x 1"/>')
        (finding,) = content.sequence(ctx, self.PARAMS)
        assert "numeric" in finding.message
