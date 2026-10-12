"""Tests for render/surfaces.py — eval/inverse round-trips per surface type."""
import math

import numpy as np
import pytest
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import make_param
from ocx_model_core.model.ir.base import IrVector3D, Quantity
from ocx_model_core.model.ir.geometry import (
    IrCone3D,
    IrCylinder3D,
    IrPlane3D,
    IrPoint3D,
    IrSphere3D,
)

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def roundtrip(param, pts3d, atol=1e-6):
    uv = param.inverse(np.asarray(pts3d, dtype=float))
    back = param.evaluate(uv)
    np.testing.assert_allclose(back, pts3d, atol=atol)
    return uv


class TestPlane:
    def test_roundtrip(self):
        s = IrPlane3D(id="p", point_on_surface=pt(1, 2, 3),
                      normal=IrVector3D(0, 0, 1))
        param = make_param(s, LR, tol_m=0.01)
        roundtrip(param, [[1, 2, 3], [5, -4, 3], [100, 100, 3]])

    def test_normals_constant(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                      normal=IrVector3D(0, 0, 2))  # non-unit input
        param = make_param(s, LR, tol_m=0.01)
        n = param.normals(np.array([[0.0, 0.0], [5.0, 5.0]]))
        np.testing.assert_allclose(n, [[0, 0, 1], [0, 0, 1]], atol=1e-12)

    def test_plane_needs_no_subdivision(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                      normal=IrVector3D(0, 0, 1))
        param = make_param(s, LR, tol_m=0.01)
        assert param.max_edge_m(0.01) is None


class TestCylinder:
    def make(self, r=2.0):
        s = IrCylinder3D(id="c", origin=pt(0, 0, 0),
                         axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um"))
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip_on_surface(self):
        param = self.make()
        pts = [[2, 0, 0], [0, 2, 5], [-2, 0, -3]]
        roundtrip(param, pts)

    def test_seam_crossing_contour_unwraps_continuously(self):
        """Points circling past the u = ±pi seam must yield monotonic u."""
        param = self.make(r=1.0)
        ang = np.linspace(0.9 * math.pi, 1.1 * math.pi, 9)  # crosses the seam
        pts = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(9)])
        uv = param.inverse(pts)
        du = np.diff(uv[:, 0])
        assert np.all(du > 0)          # no 2π jump back
        roundtrip(param, pts)

    def test_max_edge_scales_with_radius_and_tol(self):
        p1, p2 = self.make(r=1.0), self.make(r=4.0)
        assert p2.max_edge_m(0.01) == pytest.approx(2 * p1.max_edge_m(0.01))


class TestCone:
    def test_roundtrip(self):
        s = IrCone3D(id="k", origin=pt(0, 0, 0), tip=pt(0, 0, 4),
                     base_radius=Quantity(2.0, "Um"),
                     tip_radius=Quantity(1.0, "Um"))
        param = make_param(s, LR, tol_m=0.01)
        # radius at v: 2 + (1-2)*v/4
        pts = [[2, 0, 0], [0, 1.5, 2], [-1, 0, 4]]
        roundtrip(param, pts, atol=1e-6)


class TestSphere:
    def make(self, r=3.0):
        s = IrSphere3D(id="s", origin=pt(0, 0, 0), radius=Quantity(r, "Um"))
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip(self):
        param = self.make()
        pts = 3.0 * np.array([[1, 0, 0], [0, 1, 0],
                              [0.5, 0.5, np.sqrt(0.5)]])
        roundtrip(param, pts)

    def test_pole_inverse_does_not_produce_nan(self):
        param = self.make()
        pts = np.array([[1e-12, 0, 3.0], [3.0, 0, 0]])   # north pole + equator
        uv = param.inverse(pts)
        assert np.all(np.isfinite(uv))

    def test_normals_point_outward(self):
        param = self.make()
        uv = param.inverse(np.array([[3.0, 0.0, 0.0]]))
        n = param.normals(uv)
        np.testing.assert_allclose(n, [[1, 0, 0]], atol=1e-9)


class TestFactory:
    def test_unknown_surface_returns_none(self):
        class Weird:
            pass
        assert make_param(Weird(), LR, tol_m=0.01) is None

    def test_plane_missing_normal_returns_none(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0), normal=None)
        assert make_param(s, LR, tol_m=0.01) is None

    def test_sphere_zero_radius_returns_none(self):
        s = IrSphere3D(id="s", origin=pt(0, 0, 0), radius=Quantity(0.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_sphere_negative_radius_returns_none(self):
        s = IrSphere3D(id="s", origin=pt(0, 0, 0), radius=Quantity(-1.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_cylinder_zero_radius_returns_none(self):
        s = IrCylinder3D(id="c", origin=pt(0, 0, 0),
                         axis=IrVector3D(0, 0, 1),
                         radius=Quantity(0.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_cylinder_negative_radius_returns_none(self):
        s = IrCylinder3D(id="c", origin=pt(0, 0, 0),
                         axis=IrVector3D(0, 0, 1),
                         radius=Quantity(-1.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_cone_both_radii_zero_returns_none(self):
        s = IrCone3D(id="k", origin=pt(0, 0, 0), tip=pt(0, 0, 4),
                     base_radius=Quantity(0.0, "Um"),
                     tip_radius=Quantity(0.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_cone_both_radii_negative_returns_none(self):
        s = IrCone3D(id="k", origin=pt(0, 0, 0), tip=pt(0, 0, 4),
                     base_radius=Quantity(-1.0, "Um"),
                     tip_radius=Quantity(-2.0, "Um"))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_cone_valid_taper_zero_tip_radius(self):
        s = IrCone3D(id="k", origin=pt(0, 0, 0), tip=pt(0, 0, 4),
                     base_radius=Quantity(2.0, "Um"),
                     tip_radius=Quantity(0.0, "Um"))
        param = make_param(s, LR, tol_m=0.01)
        assert param is not None
