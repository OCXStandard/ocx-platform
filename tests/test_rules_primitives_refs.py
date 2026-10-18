"""Tests for the ref_resolves primitive."""
from __future__ import annotations

from ocx_rules.primitives.references import ref_resolves

from tests.rules_xml import context_for


class TestRefResolves:
    def test_guid_reference_resolves(self):
        ctx = context_for(
            '<ocx:Plate id="pl1" ocx:GUIDRef="{AAA}"/>'
            '<ocx:PlateRef localRef="pl1" ocx:GUIDRef="aaa" ocx:refType="ocx:Plate"/>'
        )
        assert ref_resolves(ctx, {}) == []

    def test_dangling_guid_falls_back_to_local_ref(self):
        ctx = context_for(
            '<ocx:Plate id="pl1" ocx:GUIDRef="aaa"/>'
            '<ocx:PlateRef localRef="pl1" ocx:GUIDRef="zzz"/>'
        )
        assert ref_resolves(ctx, {}) == []

    def test_dangling_reference_fails(self):
        ctx = context_for('<ocx:GridRef localRef="nope" ocx:GUIDRef="zzz"/>')
        (finding,) = ref_resolves(ctx, {})
        assert "GridRef" in finding.message and "zzz" in finding.message
        assert finding.location is not None

    def test_local_only_reference(self):
        ctx = context_for(
            '<ocx:Section id="s1"/>'
            '<ocx:SectionRef localRef="s1"/><ocx:SectionRef localRef="s2"/>'
        )
        (finding,) = ref_resolves(ctx, {})
        assert "s2" in finding.message

    def test_reftype_element_without_ref_suffix_resolves(self):
        ctx = context_for(
            '<ocx:Material id="m1" ocx:GUIDRef="bbb"/>'
            '<ocx:PlateMaterial localRef="m1" ocx:GUIDRef="{BBB}" ocx:refType="ocx:Material"/>'
        )
        assert ref_resolves(ctx, {}) == []

    def test_dangling_reftype_element_fails(self):
        ctx = context_for(
            '<ocx:PlateMaterial localRef="nope" ocx:GUIDRef="zzz" ocx:refType="ocx:Material"/>'
        )
        (finding,) = ref_resolves(ctx, {})
        assert "PlateMaterial" in finding.message

    def test_no_references_is_vacuous_pass(self):
        assert ref_resolves(context_for('<ocx:Panel id="p"/>'), {}) == []
