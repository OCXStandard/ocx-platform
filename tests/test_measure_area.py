"""Tests for quadrature-based trimmed surface area."""
from __future__ import annotations

import math

import numpy as np
from ocx_geometry.measure import surface_area
from ocx_geometry.surfaces import CylinderParam, PlaneParam


def _plane():
    return PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]),
                      np.array([1.0, 0.0, 0.0]))


class TestPlaneArea:
    def test_unit_square(self):
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        assert abs(surface_area(_plane(), uv) - 1.0) < 1e-9

    def test_square_with_hole(self):
        outer = np.array([[0, 0], [2, 0], [2, 2], [0, 2]], dtype=float)
        hole = np.array([[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]],
                        dtype=float)
        a = surface_area(_plane(), outer, holes_uv=[hole])
        assert abs(a - (4.0 - 0.25)) < 1e-9

    def test_concave_polygon(self):
        # L-shape, area 3
        uv = np.array([[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]],
                      dtype=float)
        assert abs(surface_area(_plane(), uv) - 3.0) < 1e-9

    def test_degenerate_returns_zero(self):
        uv = np.array([[0, 0], [1, 0]], dtype=float)
        assert surface_area(_plane(), uv) == 0.0


class TestCylinderArea:
    def test_quarter_patch(self):
        # u = angle in radians, v = metres along the axis; metric = r du dv
        r, h = 2.0, 3.0
        param = CylinderParam(np.zeros(3), np.array([0.0, 0.0, 1.0]), r)
        uv = np.array([[0, 0], [math.pi / 2, 0], [math.pi / 2, h], [0, h]],
                      dtype=float)
        expected = r * (math.pi / 2) * h
        assert abs(surface_area(param, uv) - expected) / expected < 1e-3
