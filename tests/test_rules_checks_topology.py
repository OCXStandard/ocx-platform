"""Tests for OCX-TOP-001/002/003 topology checks (checks/topology.py)."""
from __future__ import annotations

from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrCompositeCurve3D,
    IrHole2D,
    IrHoleShapeCatalogue,
    IrLimitedByRef,
    IrLine3D,
    IrNurbs3D,
    IrPanel,
    IrParametricHole,
    IrPoint3D,
    IrUnit,
    IrVessel,
    Quantity,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks.topology import (
    composite_curve_continuous,
    hole_contours_closed,
    panel_limited_by_closed,
)

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(p0: IrPoint3D, p1: IrPoint3D) -> IrLine3D:
    return IrLine3D(curve_length=None, start=p0, end=p1)


def _fec(curve) -> IrLimitedByRef:
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


def _vessel(panels: dict[str, IrPanel] | None = None,
            catalogue: IrHoleShapeCatalogue | None = None) -> IrVessel:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    if panels:
        v.panels.update(panels)
    if catalogue is not None:
        v.hole_shape_catalogue = catalogue
    return v


def _ctx(vessel: IrVessel) -> SimpleNamespace:
    return SimpleNamespace(vessel=vessel, geometry=GeometryContext(vessel))


class TestPanelLimitedByClosed:
    def test_closed_square_panel_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_open_contour_fails_with_gap_in_message(self):
        panel = IrPanel(id="p1", guidref="g1", limited_by=_square_sides(gap_mm=5.0))
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})
        assert finding.element_id == "p1"
        assert finding.guid == "g1"
        assert "gap" in finding.message
        assert "mm" in finding.message

    def test_unresolvable_ref_skips_panel(self):
        sides = _square_sides(gap_mm=5.0)[:3]
        sides.append(IrLimitedByRef(ref_type="PanelRef", local_ref="nowhere"))
        panel = IrPanel(id="p1", limited_by=sides)
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_no_panels_passes(self):
        ctx = _ctx(_vessel({}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_single_closed_boundary_curve_passes(self):
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        ring = IrCompositeCurve3D(curve_length=None, segments=[
            _line(a, b), _line(b, c), _line(c, d), _line(d, a)])
        panel = IrPanel(id="p1", limited_by=[_fec(ring)])
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_single_open_boundary_curve_fails(self):
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        open_curve = IrCompositeCurve3D(curve_length=None, segments=[
            _line(a, b), _line(b, c), _line(c, d)])
        panel = IrPanel(id="p1", guidref="g1", limited_by=[_fec(open_curve)])
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})
        assert finding.element_id == "p1"
        assert "gap" in finding.message


class TestCompositeCurveContinuous:
    def _panel_with_composite(self, segments) -> IrPanel:
        comp = IrCompositeCurve3D(curve_length=None, segments=segments)
        return IrPanel(id="p1", guidref="g1", limited_by=[_fec(comp)])

    def test_continuous_composite_passes(self):
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(1000, 0), _pt(1000, 1000))]
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []

    def test_junction_gap_fails(self):
        # 2 mm gap between the end of segment 1 and the start of segment 2
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(1002, 0), _pt(1002, 1000))]
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        (finding,) = composite_curve_continuous(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "p1"
        assert finding.guid == "g1"
        assert "gap" in finding.message
        assert "mm" in finding.message

    def test_unsampleable_segment_skips_curve(self):
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                IrNurbs3D(curve_length=None)]  # no data -> cannot sample
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []

    def test_no_composite_curves_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []


class TestHoleContoursClosed:
    def test_parametric_circular_hole_passes(self):
        hole = IrHole2D(id="h1", parametric=IrParametricHole(
            variant="parametric_circle",
            diameter=Quantity(value=100.0, unit="Umm")))
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_open_curve_contour_fails(self):
        hole = IrHole2D(id="h1", guidref="gh1",
                        contour=_line(_pt(0, 0), _pt(100, 0)))
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        (finding,) = hole_contours_closed(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "h1"
        assert finding.guid == "gh1"
        assert "closed" in finding.message

    def test_empty_catalogue_passes(self):
        cat = IrHoleShapeCatalogue(id="cat")
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_missing_catalogue_passes(self):
        ctx = _ctx(_vessel())
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_hole_without_representation_skipped(self):
        hole = IrHole2D(id="h1")
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []
