"""Tests for the exporter plausibility checks (checks/plausibility.py)."""
from __future__ import annotations

import math
from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrCog,
    IrCompositeCurve3D,
    IrInclination,
    IrLine3D,
    IrMassProperties,
    IrPanel,
    IrPillar,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrStiffener,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
    part_cog_within_geometry,
    shared_positions_and_cogs,
    web_near_normal,
    web_not_in_plate,
)

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")

# z = 0 plane (normal +z) and a far plane y = 5 m (normal +y).
_Z_PLANE = IrPlane3D(id="zp", point_on_surface=IrPoint3D(x=0, y=0, z=0, unit="Umm"),
                     normal=IrVector3D(x=0.0, y=0.0, z=1.0))
_FAR_PLANE = IrPlane3D(id="fp", point_on_surface=IrPoint3D(x=0, y=5000, z=0, unit="Umm"),
                       normal=IrVector3D(x=0.0, y=1.0, z=0.0))


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(a, b) -> IrLine3D:
    return IrLine3D(curve_length=None, start=_pt(*a), end=_pt(*b))


def _mass(cog_mm) -> IrMassProperties | None:
    return None if cog_mm is None else IrMassProperties(
        moulded_cog=IrCog(*cog_mm, unit="Umm"))


def _incl(pos=(500, 0, 0), web=(0.0, 0.0, 1.0)) -> IrInclination:
    return IrInclination(
        position=None if pos is None else _pt(*pos),
        web_direction=None if web is None else IrVector3D(x=web[0], y=web[1], z=web[2]))


def _stiffener(sid: str, *, panel: str | None = "p1", incls=None,
               trace=((0, 0, 0), (1000, 0, 0)), cog=None) -> IrStiffener:
    parent = (ParentRef(kind=ParentKind.PANEL, id=panel) if panel
              else ParentRef(kind=ParentKind.VESSEL, id="v1"))
    return IrStiffener(id=sid, guidref=f"g-{sid}", parent_ref=parent,
                       trace=_line(*trace),
                       inclinations=[_incl()] if incls is None else incls,
                       mass_properties=_mass(cog))


def _pillar(pid: str, *, incls=None, cog=None) -> IrPillar:
    return IrPillar(id=pid, guidref=f"g-{pid}",
                    parent_ref=ParentRef(kind=ParentKind.VESSEL, id="v1"),
                    trace=_line((0, 0, 0), (0, 0, 3000)),
                    inclinations=[] if incls is None else incls,
                    mass_properties=_mass(cog))


def _plate(pid: str, *, cog=None) -> IrPlate:
    a, b, c, d = (0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (0, 1000, 0)
    contour = IrCompositeCurve3D(curve_length=None, segments=[
        _line(a, b), _line(b, c), _line(c, d), _line(d, a)])
    return IrPlate(id=pid, guidref=f"g-{pid}",
                   parent_ref=ParentRef(kind=ParentKind.PANEL, id="p1"),
                   outer_contour=contour, mass_properties=_mass(cog))


def _panel(pid: str = "p1", surfaces=(_Z_PLANE,)) -> IrPanel:
    ug = (IrUnboundedGeometry(surface=surfaces[0], surfaces=tuple(surfaces))
          if surfaces else None)
    return IrPanel(id=pid, unbounded_geometry=ug)


def _ctx(*, panels=(), stiffeners=(), pillars=(), plates=()) -> SimpleNamespace:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    v.panels.update({p.id: p for p in panels})
    v.stiffeners.update({s.id: s for s in stiffeners})
    v.pillars.update({p.id: p for p in pillars})
    v.plates.update({p.id: p for p in plates})
    return SimpleNamespace(vessel=v, geometry=GeometryContext(v))


class TestInclinationPositionOnTrace:
    PARAMS = {"position_tolerance_mm": 50.0}

    def test_position_on_trace_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1")])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []

    def test_position_within_tolerance_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=(500, 40, 0))])])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []

    def test_stiffener_position_off_trace_fails(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=(500, 1000, 0))])])
        (finding,) = inclination_position_on_trace(ctx, self.PARAMS)
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "Inclination 0" in finding.message
        assert "1.000 m" in finding.message

    def test_pillar_position_off_trace_fails(self):
        ctx = _ctx(pillars=[_pillar("c1", incls=[_incl(pos=(2000, 0, 1000))])])
        (finding,) = inclination_position_on_trace(ctx, self.PARAMS)
        assert finding.element_id == "c1"
        assert "2.000 m" in finding.message

    def test_missing_position_is_skipped(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=None)])])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []


_S45 = math.sqrt(0.5)


class TestWebDirection:
    NOT_IN_PLATE = {"max_angle_deg": 80.0}
    NEAR_NORMAL = {"warn_angle_deg": 30.0, "max_angle_deg": 80.0}

    def _run(self, ctx):
        return (web_not_in_plate(ctx, self.NOT_IN_PLATE),
                web_near_normal(ctx, self.NEAR_NORMAL))

    def test_web_along_normal_passes_both(self):
        ctx = _ctx(panels=[_panel()], stiffeners=[_stiffener("s1")])
        assert self._run(ctx) == ([], [])

    def test_flipped_normal_is_equivalent(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 0.0, -1.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_web_at_45_degrees_warns_only(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, _S45, _S45))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, warnings = self._run(ctx)
        assert errors == []
        (finding,) = warnings
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "45.0" in finding.message

    def test_web_in_plate_plane_is_error_only(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, warnings = self._run(ctx)
        assert warnings == []
        (finding,) = errors
        assert finding.element_id == "s1"
        assert "90.0" in finding.message

    def test_off_trace_position_is_evaluated_on_trace(self):
        s = _stiffener("s1", incls=[_incl(pos=(500, 0, 3000), web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_missing_position_uses_trace_start(self):
        s = _stiffener("s1", incls=[_incl(pos=None, web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_uses_nearest_of_several_panel_surfaces(self):
        # ug.surface is the far plane; only ug.surfaces holds the z-plane.
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel(surfaces=(_FAR_PLANE, _Z_PLANE))], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_stiffener_without_panel_is_skipped(self):
        s = _stiffener("s1", panel=None, incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_panel_without_surface_is_skipped(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel(surfaces=())], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_trace_far_from_surface_is_skipped(self):
        s = _stiffener("s1", trace=((0, 0, 1000), (1000, 0, 1000)),
                       incls=[_incl(pos=(500, 0, 1000), web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_missing_or_zero_web_is_skipped(self):
        s = _stiffener("s1", incls=[_incl(web=None), _incl(web=(0.0, 0.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])


class TestPartCogWithinGeometry:
    PARAMS = {"margin_mm": 500.0}

    def test_stiffener_cog_on_trace_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 0, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_cog_within_margin_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 400, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_stiffener_cog_far_outside_fails(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 5000, 0))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "4.500 m" in finding.message

    def test_plate_cog_inside_contour_box_passes(self):
        ctx = _ctx(plates=[_plate("pl1", cog=(500, 500, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_plate_cog_outside_fails(self):
        ctx = _ctx(plates=[_plate("pl1", cog=(500, 500, 6000))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "pl1"
        assert "5.500 m" in finding.message

    def test_pillar_cog_outside_fails(self):
        ctx = _ctx(pillars=[_pillar("c1", cog=(3000, 0, 1000))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "c1"

    def test_part_without_mass_properties_is_skipped(self):
        ctx = _ctx(stiffeners=[_stiffener("s1")], plates=[_plate("pl1")])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []


class TestSharedPositionsAndCogs:
    PARAMS = {"tolerance_mm": 1.0, "min_parts": 3}

    def test_three_parts_sharing_a_position_fail(self):
        ctx = _ctx(stiffeners=[_stiffener(f"s{i}") for i in range(3)])
        findings = shared_positions_and_cogs(ctx, self.PARAMS)
        assert sorted(f.element_id for f in findings) == ["s0", "s1", "s2"]
        assert all("Inclination position (0.500, 0.000, 0.000)" in f.message
                   for f in findings)
        assert all("shared by 3 parts" in f.message for f in findings)

    def test_two_parts_sharing_a_position_pass(self):
        ctx = _ctx(stiffeners=[_stiffener(f"s{i}") for i in range(2)])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_part_repeating_its_own_position_counts_once(self):
        twice = _stiffener("s0", incls=[_incl(), _incl()])
        ctx = _ctx(stiffeners=[twice, _stiffener("s1")])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_values_within_tolerance_are_grouped(self):
        ctx = _ctx(stiffeners=[
            _stiffener("s0", incls=[_incl(pos=(500.0, 0, 0))]),
            _stiffener("s1", incls=[_incl(pos=(500.2, 0, 0))]),
            _stiffener("s2", incls=[_incl(pos=(499.9, 0, 0))])])
        assert len(shared_positions_and_cogs(ctx, self.PARAMS)) == 3

    def test_distinct_positions_pass(self):
        ctx = _ctx(stiffeners=[
            _stiffener(f"s{i}", incls=[_incl(pos=(100 * i, 0, 0))]) for i in range(3)])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_cog_shared_across_part_kinds_fails(self):
        cog = (195404, 24082, 2964)
        ctx = _ctx(plates=[_plate("pl1", cog=cog)],
                   stiffeners=[_stiffener("s1", incls=[], cog=cog)],
                   pillars=[_pillar("c1", cog=cog)])
        findings = shared_positions_and_cogs(ctx, self.PARAMS)
        assert sorted(f.element_id for f in findings) == ["c1", "pl1", "s1"]
        assert all(f.message.startswith("Moulded COG (195.404, 24.082, 2.964)")
                   for f in findings)
