"""Tests for OCX-PROP-001/002/003/004 property checks (checks/properties.py)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrCog,
    IrCompositeCurve3D,
    IrFlatBarSection,
    IrGenericSection,
    IrLine3D,
    IrMassProperties,
    IrMaterial,
    IrPanel,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks import renewal_thickness_on_instance
from ocx_rules.packs.best_practice.checks.properties import (
    panel_weight_cog_consistent,
    plate_weight_consistent,
    profile_closed_section,
)

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


# ---------------------------------------------------------------------------
# PROP-001/002/003 shared helpers (real IR + GeometryContext)
# ---------------------------------------------------------------------------

_UNITS = {
    "Umm": IrUnit(id="Umm", name="millimetre", symbol="mm",
                  dimension_url="D_L", to_si_factor=0.001, si_symbol="m"),
    "Ukg": IrUnit(id="Ukg", name="kilogram", symbol="kg",
                  dimension_url="D_M", to_si_factor=1.0, si_symbol="kg"),
    "Ukgoverm3": IrUnit(id="Ukgoverm3", name="kilogram per cubic metre",
                        symbol="kg/m3", dimension_url="D_MD",
                        to_si_factor=1.0, si_symbol="kg/m3"),
}


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(p0: IrPoint3D, p1: IrPoint3D) -> IrLine3D:
    return IrLine3D(curve_length=None, start=p0, end=p1)


def _square_outline() -> IrCompositeCurve3D:
    """Closed 1 m square contour in the z=0 plane (mm units)."""
    a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
    return IrCompositeCurve3D(curve_length=None, segments=[
        _line(a, b), _line(b, c), _line(c, d), _line(d, a)])


_Z_PLANE = IrPlane3D(
    id="surf1",
    point_on_surface=_pt(0, 0, 0),
    normal=IrVector3D(x=0.0, y=0.0, z=1.0),
    udirection=IrVector3D(x=1.0, y=0.0, z=0.0),
)


def _vessel() -> IrVessel:
    return IrVessel(id="v1", unit_registry=dict(_UNITS))


def _geo_ctx(vessel: IrVessel) -> SimpleNamespace:
    return SimpleNamespace(vessel=vessel, geometry=GeometryContext(vessel))


def _mass_props(weight_kg: float | None = None,
                cog_mm: tuple[float, float, float] | None = None
                ) -> IrMassProperties:
    return IrMassProperties(
        moulded_dry_weight=(Quantity(value=weight_kg, unit="Ukg")
                            if weight_kg is not None else None),
        moulded_cog=(IrCog(*cog_mm, unit="Umm")
                     if cog_mm is not None else None))


def _steel(density_kg_m3: float | None = 7850.0) -> IrMaterial:
    return IrMaterial(
        id="mat1",
        density=(Quantity(value=density_kg_m3, unit="Ukgoverm3")
                 if density_kg_m3 is not None else None))


class TestPlateWeightConsistent:
    PARAMS = {"relative_tolerance": 0.02}

    def _ctx_with_plate(self, declared_kg: float | None = 78.5,
                        thickness_mm: float | None = 10.0,
                        density: float | None = 7850.0) -> SimpleNamespace:
        """1 m2 plate on a z=0 plane panel; 10 mm x 7850 kg/m3 = 78.5 kg."""
        vessel = _vessel()
        vessel.panels["pan1"] = IrPanel(
            id="pan1", plate_ids=["pl1"],
            unbounded_geometry=IrUnboundedGeometry(surface=_Z_PLANE))
        vessel.plates["pl1"] = IrPlate(
            id="pl1", guidref="gpl1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            material_ref=Ref(local_ref="mat1"),
            thickness=(Quantity(value=thickness_mm, unit="Umm")
                       if thickness_mm is not None else None),
            mass_properties=(_mass_props(weight_kg=declared_kg)
                             if declared_kg is not None else None),
            outer_contour=_square_outline())
        vessel.materials["mat1"] = _steel(density)
        return _geo_ctx(vessel)

    def test_consistent_plate_passes(self):
        ctx = self._ctx_with_plate(declared_kg=78.5)
        assert plate_weight_consistent(ctx, self.PARAMS) == []

    def test_declared_weight_off_fails_with_both_values(self):
        ctx = self._ctx_with_plate(declared_kg=90.0)
        (finding,) = plate_weight_consistent(ctx, self.PARAMS)
        assert finding.element_id == "pl1"
        assert finding.guid == "gpl1"
        assert "90.00" in finding.message
        assert "78.50" in finding.message

    def test_missing_declared_weight_skipped(self):
        ctx = self._ctx_with_plate(declared_kg=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == []

    def test_missing_thickness_skipped(self):
        ctx = self._ctx_with_plate(declared_kg=90.0, thickness_mm=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == []

    def test_missing_density_skipped(self):
        ctx = self._ctx_with_plate(declared_kg=90.0, density=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == []

    def test_no_plates_passes(self):
        assert plate_weight_consistent(_geo_ctx(_vessel()), self.PARAMS) == []

    def test_degenerate_outline_skipped(self):
        # A collapsed (linear) outline yields surface_area 0.0, which must
        # be treated as unevaluable, not as a weight deviation.
        ctx = self._ctx_with_plate(declared_kg=78.5)
        ctx.vessel.plates["pl1"] = replace(
            ctx.vessel.plates["pl1"],
            outer_contour=_line(_pt(0, 0), _pt(1000, 0)))
        assert plate_weight_consistent(ctx, self.PARAMS) == []


class TestPanelWeightCogConsistent:
    PARAMS = {"relative_tolerance": 0.02, "cog_tolerance_mm": 50.0}

    def _ctx_with_panel(self, panel_props: IrMassProperties | None,
                        plates: list[IrMassProperties]) -> SimpleNamespace:
        vessel = _vessel()
        vessel.panels["pan1"] = IrPanel(
            id="pan1", guidref="gpan1", mass_properties=panel_props)
        for i, props in enumerate(plates):
            pid = f"pl{i}"
            vessel.plates[pid] = IrPlate(
                id=pid,
                parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
                mass_properties=props)
        return _geo_ctx(vessel)

    def test_matching_mass_sum_passes(self):
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=157.0),
            [_mass_props(weight_kg=78.5), _mass_props(weight_kg=78.5)])
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []

    def test_mass_mismatch_fails(self):
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=200.0),
            [_mass_props(weight_kg=78.5), _mass_props(weight_kg=78.5)])
        (finding,) = panel_weight_cog_consistent(ctx, self.PARAMS)
        assert finding.element_id == "pan1"
        assert finding.guid == "gpan1"
        assert "200.00" in finding.message
        assert "157.00" in finding.message

    def test_cog_within_tolerance_passes(self):
        # equal masses at x=250 and x=750 mm -> weighted CoG at x=500 mm
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=157.0, cog_mm=(500, 500, 0)),
            [_mass_props(weight_kg=78.5, cog_mm=(250, 500, 0)),
             _mass_props(weight_kg=78.5, cog_mm=(750, 500, 0))])
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []

    def test_cog_offset_fails(self):
        # weighted plate CoG at x=500 mm, panel declares x=600 -> 100 mm off
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=157.0, cog_mm=(600, 500, 0)),
            [_mass_props(weight_kg=78.5, cog_mm=(250, 500, 0)),
             _mass_props(weight_kg=78.5, cog_mm=(750, 500, 0))])
        (finding,) = panel_weight_cog_consistent(ctx, self.PARAMS)
        assert finding.element_id == "pan1"
        assert finding.guid == "gpan1"
        assert "centre of gravity" in finding.message
        assert "100.0 mm" in finding.message

    def test_panel_without_declared_mass_props_skipped(self):
        ctx = self._ctx_with_panel(None, [_mass_props(weight_kg=78.5)])
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []

    def test_panel_without_weighed_child_plates_skipped(self):
        ctx = self._ctx_with_panel(_mass_props(weight_kg=157.0),
                                   [IrMassProperties()])
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []


class TestProfileClosedSection:
    def _ctx_with_section(self, section) -> SimpleNamespace:
        vessel = _vessel()
        vessel.sections[section.id] = section
        return _geo_ctx(vessel)

    def test_closed_flat_bar_passes(self):
        ctx = self._ctx_with_section(IrFlatBarSection(
            id="s1", height=Quantity(value=100.0, unit="Umm"),
            width=Quantity(value=10.0, unit="Umm")))
        assert profile_closed_section(ctx, {}) == []

    def test_degenerate_section_fails_with_reason(self):
        ctx = self._ctx_with_section(IrFlatBarSection(
            id="s1", guidref="gs1",
            height=Quantity(value=0.0, unit="Umm"),
            width=Quantity(value=0.0, unit="Umm")))
        (finding,) = profile_closed_section(ctx, {})
        assert finding.element_id == "s1"
        assert finding.guid == "gs1"
        assert "not a closed valid polygon" in finding.message

    def test_unbuildable_section_skipped(self):
        ctx = self._ctx_with_section(IrGenericSection(id="s1"))
        assert profile_closed_section(ctx, {}) == []

    def test_no_sections_passes(self):
        assert profile_closed_section(_geo_ctx(_vessel()), {}) == []
