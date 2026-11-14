"""Tests for ocx_geometry.grid and ocx_geometry.intersect."""
from __future__ import annotations

import numpy as np
import pytest
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import offset_plane


class TestGridPlane:
    @pytest.mark.parametrize(("axis", "normal"), [
        ("x", [1.0, 0.0, 0.0]),
        ("y", [0.0, 1.0, 0.0]),
        ("z", [0.0, 0.0, 1.0]),
    ])
    def test_positive_axis_normal_and_point_at_location(self, axis, normal):
        point, n = grid_plane(axis, 2.5)
        np.testing.assert_allclose(n, normal)
        np.testing.assert_allclose(point, 2.5 * np.array(normal))

    def test_unknown_axis_raises(self):
        with pytest.raises(ValueError, match="axis"):
            grid_plane("w", 1.0)


class TestOffsetPlane:
    def test_normalizes_and_shifts_along_normal(self):
        point, n = offset_plane([0.0, 0.0, 1.0], [0.0, 0.0, 2.0], 0.05)
        np.testing.assert_allclose(n, [0.0, 0.0, 1.0])
        np.testing.assert_allclose(point, [0.0, 0.0, 1.05])

    def test_negative_offset_moves_against_normal(self):
        point, _ = offset_plane([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], -0.25)
        np.testing.assert_allclose(point, [0.75, 0.0, 0.0])

    def test_zero_normal_raises(self):
        with pytest.raises(ValueError, match="normal"):
            offset_plane([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0.0)
