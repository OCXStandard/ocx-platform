"""GeometryContext: grid ref planes, GridRef planes and panel uv windows."""
from __future__ import annotations

import numpy as np
from ocx_model_core.model.ir import (
    IrCoordinateSystem,
    IrLimitedByRef,
    IrPanel,
    IrPlane3D,
    IrPoint3D,
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
