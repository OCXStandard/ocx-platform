"""Tests for reference/connectivity best-practice checks."""
from __future__ import annotations

from dataclasses import dataclass, field

from ocx_rules.packs.best_practice.checks import (
    explicit_connectivity,
    hole_single_representation,
    panel_as_occurrence_group,
    slot_lug_plate_refs,
    stiffener_end_configurations,
)

from tests.rules_xml import context_for


class TestStiffenerEndConfigurations:
    def test_one_per_end_passes(self):
        ctx = context_for(
            '<ocx:Stiffener id="s1"><ocx:EndCutEnd1/><ocx:EndCutEnd2/></ocx:Stiffener>')
        assert stiffener_end_configurations(ctx, {}) == []

    def test_duplicate_end_fails(self):
        ctx = context_for(
            '<ocx:Stiffener id="s1"><ocx:EndCutEnd1/><ocx:EndCutEnd1/></ocx:Stiffener>')
        (finding,) = stiffener_end_configurations(ctx, {})
        assert "EndCutEnd1" in finding.message and finding.element_id == "s1"


class TestSlotLugPlateRefs:
    def test_two_lugs_pass(self):
        ctx = context_for(
            '<ocx:Slot><ocx:LugPlateRef localRef="a"/><ocx:LugPlateRef localRef="b"/></ocx:Slot>')
        assert slot_lug_plate_refs(ctx, {}) == []

    def test_three_lugs_fail(self):
        ctx = context_for(
            "<ocx:Slot>"
            '<ocx:LugPlateRef localRef="a"/><ocx:LugPlateRef localRef="b"/>'
            '<ocx:LugPlateRef localRef="c"/>'
            "</ocx:Slot>")
        (finding,) = slot_lug_plate_refs(ctx, {})
        assert "3" in finding.message


@dataclass
class _FakePanel:
    id: str
    name: str | None = None
    guidref: str | None = None
    limited_by: list = field(default_factory=list)


@dataclass
class _FakeVessel:
    panels: dict


class TestExplicitConnectivity:
    def _ctx(self, panels):
        ctx = context_for("")
        ctx.__dict__["vessel"] = _FakeVessel(panels={p.id: p for p in panels})
        return ctx

    def test_all_bounded_passes(self):
        ctx = self._ctx([_FakePanel("p1", limited_by=["x"])])
        assert explicit_connectivity(ctx, {}) == []

    def test_all_empty_passes_heuristic(self):
        ctx = self._ctx([_FakePanel("p1"), _FakePanel("p2")])
        assert explicit_connectivity(ctx, {}) == []

    def test_mixed_flags_unbounded_panel(self):
        ctx = self._ctx([_FakePanel("p1", limited_by=["x"]), _FakePanel("p2", name="Deck")])
        (finding,) = explicit_connectivity(ctx, {})
        assert finding.element_id == "p2" and "Deck" in finding.message


class TestPanelAsOccurrenceGroup:
    def test_panel_ref_on_group_passes(self):
        ctx = context_for(
            '<ocx:DesignView><ocx:OccurrenceGroup id="g1">'
            '<ocx:PanelRef localRef="p1" ocx:refType="ocx:Panel"/>'
            "</ocx:OccurrenceGroup></ocx:DesignView>")
        assert panel_as_occurrence_group(ctx, {}) == []

    def test_panel_ref_on_direct_occurrence_fails(self):
        ctx = context_for(
            '<ocx:DesignView><ocx:Occurrence id="o1">'
            '<ocx:PanelRef localRef="p1" ocx:refType="ocx:Panel"/>'
            "</ocx:Occurrence></ocx:DesignView>")
        (finding,) = panel_as_occurrence_group(ctx, {})
        assert "OccurrenceGroup" in finding.message


class TestHoleSingleRepresentation:
    def test_cutby_only_passes(self):
        ctx = context_for(
            '<ocx:Plate id="pl"><ocx:CutBy><ocx:Hole2DContour id="h">'
            '<ocx:HoleRef localRef="hc" ocx:GUIDRef="aaa"/>'
            "</ocx:Hole2DContour></ocx:CutBy></ocx:Plate>")
        assert hole_single_representation(ctx, {}) == []

    def test_both_representations_fail(self):
        ctx = context_for(
            '<ocx:Plate id="pl">'
            '<ocx:CutBy><ocx:Hole2DContour id="h">'
            '<ocx:HoleRef localRef="hc" ocx:GUIDRef="{AAA}"/>'
            "</ocx:Hole2DContour></ocx:CutBy>"
            '<ocx:OuterContour><ocx:HoleRef localRef="hc" ocx:GUIDRef="aaa"/></ocx:OuterContour>'
            "</ocx:Plate>")
        (finding,) = hole_single_representation(ctx, {})
        assert "aaa" in finding.message
