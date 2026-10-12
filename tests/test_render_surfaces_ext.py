"""Tests for extruded + NURBS surface parametrizations."""
import numpy as np
import pytest
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import make_param
from ocx_model_core.model.ir.base import IrVector3D
from ocx_model_core.model.ir.geometry import (
    IrExtrudedSurface,
    IrLine3D,
    IrNurbsSurface,
    IrPoint3D,
)

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


class TestExtruded:
    def make(self):
        s = IrExtrudedSurface(
            id="e",
            base_curve=IrLine3D(None, start=pt(0, 0, 0), end=pt(4, 0, 0)),
            sweep=IrVector3D(0, 0, 1),
        )
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip(self):
        param = self.make()
        pts = np.array([[0.0, 0, 0], [2.0, 0, 3.0], [4.0, 0, -1.0]])
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-6)
        # u is arclength along the base line, v metres along the sweep
        np.testing.assert_allclose(uv[1], [2.0, 3.0], atol=1e-6)

    def test_missing_base_curve_returns_none(self):
        s = IrExtrudedSurface(id="e", base_curve=None, sweep=IrVector3D(0, 0, 1))
        assert make_param(s, LR, tol_m=0.01) is None

    def test_straight_base_needs_no_subdivision(self):
        assert self.make().max_edge_m(0.01) is None

    def test_curved_base_requests_subdivision(self):
        """A circular-arc base curve must bound mesh edges by the chord formula."""
        from ocx_geometry.surfaces import ExtrudedParam, _chord_edge
        r = 5.0
        theta = np.linspace(0.0, np.pi / 2, 200)
        base = np.column_stack(
            [np.zeros_like(theta), r * np.cos(theta), r * np.sin(theta)])
        param = ExtrudedParam(base, np.array([1.0, 0.0, 0.0]))
        edge = param.max_edge_m(0.01)
        assert edge is not None
        assert edge == pytest.approx(_chord_edge(r, 0.01), rel=0.1)


def flat_nurbs_surface():
    """Degree-1 x degree-1 B-spline patch spanning [0,4]x[0,2] in the XY plane."""
    return IrNurbsSurface(
        id="n", u_degree=1, v_degree=1,
        u_knot_vector=[0, 0, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(0, 0, 0), pt(0, 2, 0)],
                        [pt(4, 0, 0), pt(4, 2, 0)]],
    )


def curved_nurbs_surface():
    """Degree-2 x degree-1 patch bulging in z."""
    return IrNurbsSurface(
        id="n2", u_degree=2, v_degree=1,
        u_knot_vector=[0, 0, 0, 1, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(0, 0, 0), pt(0, 2, 0)],
                        [pt(2, 0, 2), pt(2, 2, 2)],   # raised middle row
                        [pt(4, 0, 0), pt(4, 2, 0)]],
    )


class TestNurbs:
    def test_flat_patch_roundtrip(self):
        param = make_param(flat_nurbs_surface(), LR, tol_m=0.01)
        assert param is not None
        pts = np.array([[1.0, 1.0, 0.0], [3.0, 0.5, 0.0]])
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-5)

    def test_curved_patch_newton_inversion(self):
        param = make_param(curved_nurbs_surface(), LR, tol_m=0.01)
        # take exact surface points, invert, re-evaluate
        probe_uv = np.array([[0.25, 0.5], [0.5, 0.25], [0.75, 0.75]])
        pts = param.evaluate(probe_uv)
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-5)

    def test_curved_patch_requests_subdivision(self):
        param = make_param(curved_nurbs_surface(), LR, tol_m=0.001)
        edge = param.max_edge_m(0.001)
        assert edge is not None and edge > 0

    def test_missing_knots_returns_none(self):
        s = IrNurbsSurface(id="n", u_degree=1, v_degree=1,
                           control_points=[[pt(0, 0, 0)]])
        assert make_param(s, LR, tol_m=0.01) is None

    def test_ragged_control_points_returns_none(self):
        """Ragged control-point rows trigger IndexError in geomdl."""
        s = IrNurbsSurface(
            id="n", u_degree=1, v_degree=1,
            u_knot_vector=[0, 0, 1, 1], v_knot_vector=[0, 0, 1, 1],
            control_points=[[pt(0, 0, 0), pt(0, 2, 0)], [pt(4, 0, 0)]],
        )
        assert make_param(s, LR, tol_m=0.01) is None

    def test_degree_too_high_for_control_points_returns_none(self):
        """Degree too high for control points triggers GeomdlException."""
        s = IrNurbsSurface(
            id="n", u_degree=3, v_degree=1,
            u_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
            v_knot_vector=[0, 0, 1, 1],
            control_points=[[pt(0, 0, 0), pt(0, 2, 0)],
                            [pt(4, 0, 0), pt(4, 2, 0)]],
        )
        assert make_param(s, LR, tol_m=0.01) is None
