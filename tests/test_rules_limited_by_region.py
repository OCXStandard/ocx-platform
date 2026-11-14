"""OCX-TOP-001 for panels bounded by GridRefs (checks/limited_by_region.py)."""
from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

from ocx_model_core.model.ir import (
    IrCoordinateSystem,
    IrCylinder3D,
    IrLimitedByRef,
    IrLine3D,
    IrPanel,
    IrPoint3D,
    IrPolyLine3D,
    IrRefPlane,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    Quantity,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.model import CheckOutcome, Unchecked
from ocx_rules.packs.best_practice.checks.topology import panel_limited_by_closed

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")
_PLANES = {"fx0": ("x", 0.0), "fx1": ("x", 1000.0), "fx2": ("x", 5000.0),
           "fy0": ("y", 0.0), "fy1": ("y", 1000.0), "fy2": ("y", 5000.0),
           "fz0": ("z", 0.0), "fz1": ("z", 1000.0)}
_NOT_CLOSED = ("Panel boundary is not closed: LimitedBy does not enclose "
               "the panel")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _grid(name: str, offset_mm: float | None = None) -> IrLimitedByRef:
    offset = None if offset_mm is None else Quantity(offset_mm, "Umm")
    return IrLimitedByRef(ref_type="GridRef", local_ref=name, offset=offset)


def _fec(p0: IrPoint3D, p1: IrPoint3D) -> IrLimitedByRef:
    return IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="",
                          curve=IrLine3D(curve_length=None, start=p0, end=p1))


def _square() -> IrPolyLine3D:
    return IrPolyLine3D(curve_length=None, is_closed=True, vertices=[
        _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)])


def _flat_panel(refs: list[IrLimitedByRef], *, contour: bool = True,
                surface: bool = True) -> IrPanel:
    """Panel on grid plane fz0 (z = 0), OuterContour 0..1000 mm square."""
    return IrPanel(
        id="p1", guidref="g1", limited_by=refs,
        unbounded_geometry=(IrUnboundedGeometry(grid_ref="fz0")
                            if surface else None),
        outer_contours=[_square()] if contour else [])


def _run(panel: IrPanel) -> CheckOutcome:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    ids = {a: [p for p, (ax, _) in _PLANES.items() if ax == a] for a in "xyz"}
    v.coordinate_systems["cs"] = IrCoordinateSystem(
        id="cs", is_global=True, x_ref_plane_ids=ids["x"],
        y_ref_plane_ids=ids["y"], z_ref_plane_ids=ids["z"])
    for pid, (_, loc) in _PLANES.items():
        v.ref_planes[pid] = IrRefPlane(id=pid, location=Quantity(loc, "Umm"))
    v.panels["p1"] = panel
    ctx = SimpleNamespace(vessel=v, geometry=GeometryContext(v))
    return panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})


def _unchecked(reason: str) -> CheckOutcome:
    return CheckOutcome(unchecked=(Unchecked(reason, "p1", "g1"),))


_XXYY = ["fx0", "fx1", "fy0", "fy1"]


class TestGridRefPanels:
    def test_four_grid_planes_close(self):
        assert _run(_flat_panel([_grid(n) for n in _XXYY])) == CheckOutcome()

    def test_three_grid_planes_are_not_closed(self):
        outcome = _run(_flat_panel([_grid(n) for n in _XXYY[:3]]))
        (finding,) = outcome.findings
        assert finding.message == _NOT_CLOSED
        assert (finding.element_id, finding.guid) == ("p1", "g1")
        assert outcome.unchecked == ()

    def test_distant_parallel_plane_is_stray(self):
        outcome = _run(_flat_panel([_grid(n) for n in [*_XXYY, "fx2"]]))
        assert [f.message for f in outcome.findings] == [
            "LimitedBy boundary GridRef fx2 does not bound the panel"]

    def test_grid_and_free_edge_mix_closes(self):
        refs = [_grid("fx0"), _grid("fy0"), _grid("fy1"),
                _fec(_pt(1000, 0), _pt(1000, 1000))]
        assert _run(_flat_panel(refs)) == CheckOutcome()

    def test_offset_grid_ref_opens_the_boundary(self):
        refs = [_grid("fx0"), _grid("fy0"), _grid("fy1", offset_mm=50.0),
                _fec(_pt(1000, 0), _pt(1000, 1000))]
        (finding,) = _run(_flat_panel(refs)).findings
        assert finding.message == _NOT_CLOSED

    def test_curved_panel_closes(self):
        c = 1000.0 / math.sqrt(2.0)
        quarter = IrPolyLine3D(curve_length=None, is_closed=True, vertices=[
            _pt(1000, 0, 0), _pt(c, c, 0), _pt(0, 1000, 0),
            _pt(0, 1000, 1000), _pt(c, c, 1000), _pt(1000, 0, 1000)])
        cylinder = IrCylinder3D(origin=_pt(0, 0, 0),
                                axis=IrVector3D(0.0, 0.0, 1.0),
                                radius=Quantity(1000.0, "Umm"))
        panel = IrPanel(
            id="p1", guidref="g1",
            limited_by=[_grid(n) for n in ("fz0", "fz1", "fx0", "fy0")],
            unbounded_geometry=IrUnboundedGeometry(surface=cylinder),
            outer_contours=[quarter], point_on_surface=_pt(c, c, 500))
        assert _run(panel) == CheckOutcome()

    def test_unresolvable_grid_ref_is_dangling(self):
        refs = [_grid(n) for n in _XXYY[:3]] + [_grid("nowhere")]
        assert _run(_flat_panel(refs)) == _unchecked(
            "1 dangling boundary ref(s) (GridRef×1)")

    def test_curveless_ref_beside_grid_refs_unchecked(self):
        refs = [_grid(n) for n in _XXYY[:3]]
        refs.append(IrLimitedByRef(ref_type="PanelRef", local_ref="p9"))
        assert _run(_flat_panel(refs)) == _unchecked(
            "1 boundary ref(s) without explicit curve (PanelRef×1)")

    def test_no_panel_surface_unchecked(self):
        panel = _flat_panel([_grid(n) for n in _XXYY], surface=False)
        assert _run(panel) == _unchecked("no buildable panel surface")

    def test_no_panel_extent_unchecked(self):
        panel = _flat_panel([_grid(n) for n in _XXYY], contour=False)
        assert _run(panel) == _unchecked("cannot determine panel extent")

    def test_no_contour_with_point_on_surface_unchecked(self):
        panel = _flat_panel([_grid(n) for n in ("fx0", "fx2", "fy0", "fy2")],
                            contour=False)
        panel.point_on_surface = _pt(2500, 2500)
        assert _run(panel) == _unchecked("cannot determine panel extent")

    def test_no_seed_point_unchecked(self):
        panel = _flat_panel([_grid(n) for n in _XXYY])
        panel.outer_contours = [IrPolyLine3D(
            curve_length=None, is_closed=True,
            vertices=[_pt(0, 0), _pt(500, 500), _pt(1000, 1000)])]
        assert _run(panel) == _unchecked("no seed point")

    def test_evaluation_error_unchecked(self):
        target = ("ocx_rules.packs.best_practice.checks.limited_by_region."
                  "intersect_surface_plane")
        with patch(target, side_effect=RuntimeError("boom")):
            outcome = _run(_flat_panel([_grid(n) for n in _XXYY]))
        assert outcome == _unchecked("boundary evaluation failed: boom")
