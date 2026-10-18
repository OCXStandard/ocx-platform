"""Tests for OCX-PROP-004 renewal_thickness_on_instance."""
from __future__ import annotations

from dataclasses import dataclass, field

from ocx_rules.packs.best_practice.checks import renewal_thickness_on_instance

from tests.rules_xml import context_for


@dataclass
class _Part:
    id: str
    renewal_thickness: object = None
    web_renewal_thickness: object = None
    flange_renewal_thickness: object = None


@dataclass
class _Vessel:
    plates: dict = field(default_factory=dict)
    brackets: dict = field(default_factory=dict)
    stiffeners: dict = field(default_factory=dict)
    pillars: dict = field(default_factory=dict)
    edge_reinforcements: dict = field(default_factory=dict)


def _ctx(body: str, vessel: _Vessel) -> object:
    ctx = context_for(body)
    ctx.__dict__["vessel"] = vessel
    return ctx


class TestRenewalThicknessOnInstance:
    def test_no_renewal_anywhere_passes(self):
        ctx = _ctx('<ocx:Plate id="p"/>', _Vessel(plates={"p": _Part("p")}))
        assert renewal_thickness_on_instance(ctx, {}) == []

    def test_instance_level_renewal_passes(self):
        body = ('<ocx:XSectionCatalogue><ocx:BarSection id="b">'
                '<ocx:WebRenewalThickness numericvalue="2" unit="u1"/>'
                "</ocx:BarSection></ocx:XSectionCatalogue>")
        vessel = _Vessel(stiffeners={"s": _Part("s", web_renewal_thickness=object())})
        assert renewal_thickness_on_instance(_ctx(body, vessel), {}) == []

    def test_shared_definition_only_fails(self):
        body = ('<ocx:XSectionCatalogue><ocx:BarSection id="b">'
                '<ocx:WebRenewalThickness numericvalue="2" unit="u1"/>'
                "</ocx:BarSection></ocx:XSectionCatalogue>")
        vessel = _Vessel(stiffeners={"s": _Part("s")})
        (finding,) = renewal_thickness_on_instance(_ctx(body, vessel), {})
        assert "instance" in finding.message
