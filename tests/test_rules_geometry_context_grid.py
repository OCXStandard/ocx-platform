"""GeometryContext: grid ref planes, GridRef planes and panel uv windows."""
from __future__ import annotations

import math

import numpy as np
import pytest
from ocx_geometry.surfaces import (
    ConeParam,
    CylinderParam,
    ExtrudedParam,
    PlaneParam,
)
from ocx_model_core.model.ir import (
    IrCoordinateSystem,
    IrLimitedByRef,
    IrPanel,
    IrPlane3D,
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

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _vessel(planes: dict[str, tuple[str, float]],
            extra: dict[str, IrRefPlane] | None = None) -> IrVessel:
    """``planes``: ref-plane id -> (axis, location in mm)."""
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    ids = {a: [pid for pid, (ax, _) in planes.items() if ax == a]
           for a in "xyz"}
    v.coordinate_systems["cs"] = IrCoordinateSystem(
        id="cs", is_global=True, x_ref_plane_ids=ids["x"],
        y_ref_plane_ids=ids["y"], z_ref_plane_ids=ids["z"])
    for pid, (_, loc) in planes.items():
        v.ref_planes[pid] = IrRefPlane(id=pid, location=Quantity(loc, "Umm"))
    v.ref_planes.update(extra or {})
    return v


def _grid(name: str, offset_mm: float | None = None) -> IrLimitedByRef:
    offset = None if offset_mm is None else Quantity(offset_mm, "Umm")
    return IrLimitedByRef(ref_type="GridRef", local_ref=name, offset=offset)


class TestRefPlaneAxis:
    def test_axis_from_coordinate_system(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1.0), "fy1": ("y", 1.0)}))
        assert geo.ref_plane_axis("fy1") == "y"
        assert geo.ref_plane_axis("fx1") == "x"
        assert geo.ref_plane_axis("nowhere") is None


class TestPanelSurfaceSynthesis:
    def test_location_only_grid_plane_is_synthesized(self):
        geo = GeometryContext(_vessel({"fz0": ("z", 250.0)}))
        panel = IrPanel(id="p",
                        unbounded_geometry=IrUnboundedGeometry(grid_ref="fz0"))
        surface = geo.panel_surface(panel)
        assert isinstance(surface, IrPlane3D)
        param = geo.surface_param(surface)
        np.testing.assert_allclose(param.o, [0.0, 0.0, 0.25])
        np.testing.assert_allclose(param.n, [0.0, 0.0, 1.0])

    def test_ref_plane_outside_any_coordinate_system_gives_none(self):
        orphan = IrRefPlane(id="orphan", location=Quantity(1.0, "Umm"))
        geo = GeometryContext(_vessel({}, {"orphan": orphan}))
        panel = IrPanel(
            id="p", unbounded_geometry=IrUnboundedGeometry(grid_ref="orphan"))
        assert geo.panel_surface(panel) is None


class TestGridRefPlane:
    def test_synthesized_plane_in_metres(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1000.0)}))
        point, normal = geo.grid_ref_plane(_grid("fx1"))
        np.testing.assert_allclose(point, [1.0, 0.0, 0.0])
        np.testing.assert_allclose(normal, [1.0, 0.0, 0.0])

    def test_offset_moves_along_the_normal(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1000.0)}))
        point, _ = geo.grid_ref_plane(_grid("fx1", offset_mm=50.0))
        np.testing.assert_allclose(point, [1.05, 0.0, 0.0])
        point, _ = geo.grid_ref_plane(_grid("fx1", offset_mm=-50.0))
        np.testing.assert_allclose(point, [0.95, 0.0, 0.0])

    def test_explicit_reference_plane_wins(self):
        explicit = IrRefPlane(
            id="rp", location=Quantity(9999.0, "Umm"),
            reference_plane=IrPlane3D(point_on_surface=_pt(0, 0, 3000),
                                      normal=IrVector3D(0.0, 0.0, 2.0)))
        geo = GeometryContext(_vessel({}, {"rp": explicit}))
        point, normal = geo.grid_ref_plane(_grid("rp"))
        np.testing.assert_allclose(point, [0.0, 0.0, 3.0])
        np.testing.assert_allclose(normal, [0.0, 0.0, 1.0])

    def test_unknown_ref_plane_gives_none(self):
        geo = GeometryContext(_vessel({}))
        assert geo.grid_ref_plane(_grid("nowhere")) is None


def _contour(*pts: IrPoint3D) -> IrPolyLine3D:
    return IrPolyLine3D(curve_length=None, vertices=list(pts), is_closed=True)


_XY_SQUARE = _contour(_pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000))
_Z = np.array([0.0, 0.0, 1.0])
_XY = PlaneParam(np.zeros(3), _Z, np.array([1.0, 0.0, 0.0]))  # u = x, v = y


class _BoxedPlane(PlaneParam):
    def uv_domain(self):
        return (0.0, 1.0, 0.0, 2.0)


class TestPanelUvWindow:
    def _geo(self) -> GeometryContext:
        return GeometryContext(_vessel({}))

    def test_contour_box_grown_by_extent_plus_one_metre(self):
        panel = IrPanel(id="p", outer_contours=[_XY_SQUARE])
        assert self._geo().panel_uv_window(panel, _XY) == pytest.approx(
            (-2.0, 3.0, -2.0, 3.0))

    def test_extra_points_extend_the_box(self):
        panel = IrPanel(id="p", outer_contours=[_XY_SQUARE])
        extra = [np.array([[2.0, 0.0, 0.0], [2.0, 1.0, 0.0]])]
        assert self._geo().panel_uv_window(panel, _XY, extra) == \
            pytest.approx((-3.0, 5.0, -2.0, 3.0))

    def test_point_on_surface_alone(self):
        panel = IrPanel(id="p", point_on_surface=_pt(500, 500))
        assert self._geo().panel_uv_window(panel, _XY) == pytest.approx(
            (-0.5, 1.5, -0.5, 1.5))

    def test_clamped_to_uv_domain(self):
        extruded = ExtrudedParam(np.array([[0.0, 0, 0], [4.0, 0, 0]]), _Z)
        panel = IrPanel(id="p", outer_contours=[_contour(
            _pt(0, 0, 0), _pt(1000, 0, 0), _pt(1000, 0, 1000),
            _pt(0, 0, 1000))])
        assert self._geo().panel_uv_window(panel, extruded) == pytest.approx(
            (0.0, 3.0, -2.0, 3.0))

    def test_no_data_falls_back_to_finite_domain(self):
        panel = IrPanel(id="p")
        boxed = _BoxedPlane(np.zeros(3), _Z)
        assert self._geo().panel_uv_window(panel, boxed) == (0.0, 1.0, 0.0, 2.0)
        assert self._geo().panel_uv_window(panel, _XY) is None

    def test_periodic_span_capped_at_two_pi(self):
        c = 1000.0 / math.sqrt(2.0)
        quarter = _contour(_pt(1000, 0, 0), _pt(c, c, 0), _pt(0, 1000, 0),
                           _pt(0, 1000, 1000), _pt(c, c, 1000),
                           _pt(1000, 0, 1000))
        panel = IrPanel(id="p", outer_contours=[quarter])
        u0, u1, v0, v1 = self._geo().panel_uv_window(
            panel, CylinderParam(np.zeros(3), _Z, 1.0))
        assert u1 - u0 == pytest.approx(2.0 * math.pi)
        assert (v0, v1) == pytest.approx((-2.0, 3.0))

    def test_cone_clamps_only_the_finite_apex_side(self):
        # Apex at v = 4 m; domain (-inf, inf, -inf, 4).
        cone = ConeParam(np.zeros(3), np.array([0.0, 0.0, 2.0]), 1.0, 0.5)
        panel = IrPanel(id="p", outer_contours=[_contour(
            _pt(500, 0, 2000), _pt(0, 500, 2000), _pt(0, 250, 3000),
            _pt(250, 0, 3000))])
        u0, u1, v0, v1 = self._geo().panel_uv_window(panel, cone)
        assert np.isfinite([u0, u1]).all() and u1 > u0
        assert (v0, v1) == pytest.approx((0.0, 4.0))
        assert self._geo().panel_uv_window(IrPanel(id="q"), cone) is None