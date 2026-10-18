"""Tests for OCX-TOP-001/002/003 topology checks (checks/topology.py)."""
from __future__ import annotations

from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrLimitedByRef,
    IrLine3D,
    IrPanel,
    IrPoint3D,
    IrSeam,
    IrUnit,
    IrVessel,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks.topology import (
    boundary_continuity,
    panel_closed_contour,
    seam_continuity,
)

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(p0: IrPoint3D, p1: IrPoint3D) -> IrLine3D:
    return IrLine3D(curve_length=None, start=p0, end=p1)


def _fec(curve: IrLine3D) -> IrLimitedByRef:
    return IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="", curve=curve)


def _square_sides(gap_mm: float = 0.0) -> list[IrLimitedByRef]:
    """Four 1 m square sides in mm; last corner pulled open by gap_mm."""
    a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
    d_open = _pt(0, 1000 + gap_mm)
    return [
        _fec(_line(a, b)),
        _fec(_line(b, c)),
        _fec(_line(c, d_open)),
        _fec(_line(d, a)),
    ]


def _vessel(panels: dict[str, IrPanel], seams: dict[str, IrSeam] | None = None) -> IrVessel:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    v.panels.update(panels)
    if seams:
        v.seams.update(seams)
    return v


def _ctx(vessel: IrVessel) -> SimpleNamespace:
    return SimpleNamespace(vessel=vessel, geometry=GeometryContext(vessel))


class TestPanelClosedContour:
    def test_closed_square_panel_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_closed_contour(ctx, {"tolerance_mm": 1.0}) == []

    def test_open_contour_fails_with_gap_in_message(self):
        panel = IrPanel(id="p1", guidref="g1", limited_by=_square_sides(gap_mm=5.0))
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = panel_closed_contour(ctx, {"tolerance_mm": 1.0})
        assert finding.element_id == "p1"
        assert finding.guid == "g1"
        assert "gap" in finding.message
        assert "mm" in finding.message

    def test_unresolvable_ref_skips_panel(self):
        sides = _square_sides(gap_mm=5.0)[:3]
        sides.append(IrLimitedByRef(ref_type="PanelRef", local_ref="nowhere"))
        panel = IrPanel(id="p1", limited_by=sides)
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_closed_contour(ctx, {"tolerance_mm": 1.0}) == []

    def test_no_panels_passes(self):
        ctx = _ctx(_vessel({}))
        assert panel_closed_contour(ctx, {"tolerance_mm": 1.0}) == []


class TestBoundaryContinuity:
    def test_continuous_declared_order_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert boundary_continuity(ctx, {"tolerance_mm": 0.1}) == []

    def test_junction_gap_fails(self):
        panel = IrPanel(id="p1", limited_by=_square_sides(gap_mm=2.0))
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = boundary_continuity(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "p1"
        assert "junction" in finding.message


class TestSeamContinuity:
    def test_seam_on_panel_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides(), seam_ids=["s1"])
        seam = IrSeam(id="s1", trace_line=_line(_pt(500, 0), _pt(500, 1000)))
        ctx = _ctx(_vessel({"p1": panel}, {"s1": seam}))
        assert seam_continuity(ctx, {"tolerance_mm": 0.1}) == []

    def test_detached_seam_fails(self):
        panel = IrPanel(id="p1", limited_by=_square_sides(), seam_ids=["s1"])
        # seam lifted 10 mm above the panel plane -> off every boundary curve
        seam = IrSeam(id="s1",
                      trace_line=_line(_pt(500, 0, 10), _pt(500, 1000, 10)))
        ctx = _ctx(_vessel({"p1": panel}, {"s1": seam}))
        (finding,) = seam_continuity(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "p1"
        assert "s1" in finding.message

    def test_missing_seam_skipped(self):
        panel = IrPanel(id="p1", limited_by=_square_sides(), seam_ids=["ghost"])
        ctx = _ctx(_vessel({"p1": panel}))
        assert seam_continuity(ctx, {"tolerance_mm": 0.1}) == []
