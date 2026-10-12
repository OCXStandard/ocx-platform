"""Parametric hole profiles and 3D placement."""
import numpy as np
import pytest
from ocx_geometry.holes import parametric_profile, place_hole
from ocx_geometry.measure import LengthResolver
from ocx_model_core.model.ir.base import Quantity
from ocx_model_core.model.ir.catalogues import IrParametricHole
from ocx_model_core.model.ir.geometry import IrPoint3D, IrTransformation, IrVector3D
from shapely.geometry import Polygon

L = LengthResolver(None)
TOL = 0.005


def q(v):
    return Quantity(v, "Um")


def _bbox(p):
    return (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())


def _poly(p):
    poly = Polygon(p)
    assert poly.is_valid and poly.is_simple
    return poly


class TestParametricProfiles:
    def test_circle(self):
        p = parametric_profile(
            IrParametricHole("parametric_circle", diameter=q(0.5)), L, TOL)
        assert np.allclose(_bbox(p), (-0.25, -0.25, 0.25, 0.25), atol=0.01)
        assert len(p) >= 12
        assert _poly(p).area == pytest.approx(np.pi * 0.25**2, rel=0.02)

    def test_ellipse(self):
        p = parametric_profile(
            IrParametricHole("ellipse", major_diameter=q(1.2),
                             minor_diameter=q(0.6)), L, TOL)
        assert np.allclose(_bbox(p), (-0.6, -0.3, 0.6, 0.3), atol=0.01)
        assert _poly(p).area == pytest.approx(np.pi * 0.6 * 0.3, rel=0.02)

    def test_rectangle_sharp(self):
        p = parametric_profile(
            IrParametricHole("rectangular_hole", height=q(1.0), width=q(0.7),
                             fillet_radius=q(0.0)), L, TOL)
        assert _poly(p).area == pytest.approx(0.7, rel=1e-6)

    def test_rectangle_fillet(self):
        p = parametric_profile(
            IrParametricHole("rectangular_hole", height=q(0.8), width=q(0.6),
                             fillet_radius=q(0.15)), L, TOL)
        expected = 0.8 * 0.6 - (4.0 - np.pi) * 0.15**2
        assert _poly(p).area == pytest.approx(expected, rel=0.02)

    def test_stadium(self):
        p = parametric_profile(
            IrParametricHole("symmetrical_hole", height=q(0.8), width=q(0.6)),
            L, TOL)
        assert np.allclose(_bbox(p), (-0.3, -0.4, 0.3, 0.4), atol=0.01)
        expected = 0.6 * (0.8 - 0.6) + np.pi * 0.3**2
        assert _poly(p).area == pytest.approx(expected, rel=0.02)

    def test_superellipse_exponent_2_matches_ellipse(self):
        p = parametric_profile(
            IrParametricHole("super_elliptical", major_diameter=q(1.2),
                             minor_diameter=q(0.6),
                             exponent=Quantity(2.0, "UDimless")), L, TOL)
        assert _poly(p).area == pytest.approx(np.pi * 0.6 * 0.3, rel=0.02)

    def test_mickey_ears_bigger_than_rectangle(self):
        p = parametric_profile(
            IrParametricHole("rectangular_mickey_mouse_ears", height=q(0.8),
                             width=q(2.0), radius=q(0.05),
                             displacement=q(0.01)), L, TOL)
        assert _poly(p).area > 0.8 * 2.0

    def test_unknown_variant_returns_none(self):
        assert parametric_profile(IrParametricHole("weird"), L, TOL) is None

    def test_missing_dimensions_return_none(self):
        assert parametric_profile(
            IrParametricHole("parametric_circle"), L, TOL) is None
        assert parametric_profile(None, L, TOL) is None


class TestPlaceHole:
    def _frame(self):
        return IrTransformation(origin=IrPoint3D(1.0, 2.0, 3.0, "Um"),
                                primary_axis=IrVector3D(1, 0, 0),
                                secondary_axis=IrVector3D(0, 0, 1))

    def test_unit_square_placement(self):
        square = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        out = place_hole(square, self._frame(), L)
        assert np.allclose(out[0], [1.0, 2.0, 3.0])
        assert np.allclose(out[1], [2.0, 2.0, 3.0])   # +x along primary
        assert np.allclose(out[2], [2.0, 2.0, 4.0])   # +y along secondary

    def test_secondary_axis_is_orthogonalized(self):
        t = IrTransformation(origin=IrPoint3D(0, 0, 0, "Um"),
                             primary_axis=IrVector3D(1, 0, 0),
                             secondary_axis=IrVector3D(1, 1, 0))
        out = place_hole(np.array([[0.0, 1.0]]), t, L)
        assert np.allclose(out[0], [0.0, 1.0, 0.0], atol=1e-9)

    def test_degenerate_frames_return_none(self):
        sq = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        assert place_hole(sq, None, L) is None
        t = IrTransformation(origin=IrPoint3D(0, 0, 0, "Um"),
                             primary_axis=IrVector3D(1, 0, 0),
                             secondary_axis=IrVector3D(1, 0, 0))  # parallel
        assert place_hole(sq, t, L) is None
