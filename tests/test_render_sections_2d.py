"""Tests for section → 2D profile polygons."""
import numpy as np
import pytest
from ocx_geometry.measure import LengthResolver
from ocx_geometry.sections_2d import fallback_polygon, section_polygon
from ocx_model_core.model.ir.base import Quantity
from ocx_model_core.model.ir.sections import (
    IrAngleSection,
    IrBulbFlatSection,
    IrFlatBarSection,
    IrGenericSection,
    IrISection,
    IrLSection,
    IrRoundSection,
    IrTSection,
    IrTubeSection,
    IrUSection,
)

LR = LengthResolver({})


def q(v):
    return Quantity(v, "Um")


def polygon_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


class TestProfiles:
    def test_flat_bar(self):
        p = section_polygon(IrFlatBarSection(id="s", height=q(0.2), width=q(0.01)), LR)
        assert p is not None
        assert polygon_area(p) == pytest.approx(0.2 * 0.01)
        assert p[:, 1].min() == pytest.approx(0.0)      # starts at the plate
        assert p[:, 1].max() == pytest.approx(0.2)

    def test_t_section_area(self):
        p = section_polygon(IrTSection(id="s", height=q(0.3), width=q(0.1),
                                       web_thickness=q(0.01),
                                       flange_thickness=q(0.02)), LR)
        # web (h - tf) * tw + flange w * tf
        expected = (0.3 - 0.02) * 0.01 + 0.1 * 0.02
        assert polygon_area(p) == pytest.approx(expected)

    def test_l_section_is_asymmetric(self):
        p = section_polygon(IrLSection(id="s", height=q(0.2), width=q(0.08),
                                       web_thickness=q(0.01),
                                       flange_thickness=q(0.012)), LR)
        assert polygon_area(p) == pytest.approx((0.2 - 0.012) * 0.01 + 0.08 * 0.012)
        # flange extends to one side only
        assert p[:, 0].max() > 0.05 and p[:, 0].min() >= -0.01

    def test_bulb_flat_has_bump(self):
        p = section_polygon(IrBulbFlatSection(id="s", height=q(0.24),
                                              web_thickness=q(0.011),
                                              flange_width=q(0.035)), LR)
        assert p is not None
        assert p[:, 0].max() == pytest.approx(0.035 - 0.011 / 2.0)
        assert p[:, 1].max() == pytest.approx(0.24)

    def test_angle(self):
        p = section_polygon(IrAngleSection(id="s", leg_length=q(0.1),
                                           leg_thickness=q(0.01)), LR)
        assert polygon_area(p) == pytest.approx(0.1 * 0.01 + (0.1 - 0.01) * 0.01)

    def test_tube_is_polygonized_circle(self):
        p = section_polygon(IrTubeSection(id="s", diameter=q(0.2)), LR)
        assert len(p) >= 16
        radii = np.linalg.norm(p - [0.0, 0.1], axis=1)   # centred at (0, d/2)
        np.testing.assert_allclose(radii, 0.1, atol=1e-9)

    def test_round(self):
        p = section_polygon(IrRoundSection(id="s", diameter=q(0.1)), LR)
        assert len(p) >= 16

    def test_u_and_i(self):
        u = section_polygon(IrUSection(id="s", height=q(0.2), width=q(0.08),
                                       web_thickness=q(0.008),
                                       flange_thickness=q(0.012)), LR)
        i = section_polygon(IrISection(id="s", height=q(0.2), width=q(0.1),
                                       web_thickness=q(0.008),
                                       flange_thickness=q(0.012)), LR)
        assert u is not None and i is not None
        assert polygon_area(i) == pytest.approx(
            2 * 0.1 * 0.012 + (0.2 - 2 * 0.012) * 0.008)

    def test_missing_dims_returns_none(self):
        assert section_polygon(IrFlatBarSection(id="s"), LR) is None

    def test_generic_returns_none(self):
        assert section_polygon(IrGenericSection(id="s"), LR) is None

    def test_fallback(self):
        p = fallback_polygon()
        assert polygon_area(p) > 0
