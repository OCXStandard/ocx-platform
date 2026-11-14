"""Tests for ocx_geometry.grid and ocx_geometry.intersect."""
from __future__ import annotations

import numpy as np
import pytest
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import intersect_surface_plane, offset_plane
from ocx_geometry.surfaces import PlaneParam


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


_X = np.array([1.0, 0.0, 0.0])
_Z = np.array([0.0, 0.0, 1.0])
_UNIT_WINDOW = (0.0, 1.0, 0.0, 1.0)


def _xy_plane() -> PlaneParam:
    """z = 0 with u = x, v = y."""
    return PlaneParam(np.zeros(3), _Z, _X)


class TestPlaneCut:
    def test_plane_cut_gives_clipped_line(self):
        (line,) = intersect_surface_plane(
            _xy_plane(), [0.5, 0.0, 0.0], _X, _UNIT_WINDOW, 0.001)
        np.testing.assert_allclose(
            sorted(map(tuple, line)), [(0.5, 0.0, 0.0), (0.5, 1.0, 0.0)],
            atol=1e-12)

    def test_parallel_planes_give_nothing(self):
        assert intersect_surface_plane(
            _xy_plane(), [0.0, 0.0, 1.0], _Z, _UNIT_WINDOW, 0.001) == []

    def test_offset_shifts_the_line(self):
        point, normal = offset_plane([0.5, 0.0, 0.0], _X, 0.25)
        (line,) = intersect_surface_plane(
            _xy_plane(), point, normal, _UNIT_WINDOW, 0.001)
        np.testing.assert_allclose(line[:, 0], [0.75, 0.75], atol=1e-12)

    def test_line_outside_window_gives_nothing(self):
        assert intersect_surface_plane(
            _xy_plane(), [2.0, 0.0, 0.0], _X, _UNIT_WINDOW, 0.001) == []

    def test_diagonal_line_clipped_to_window_corners(self):
        (line,) = intersect_surface_plane(
            _xy_plane(), [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], _UNIT_WINDOW,
            0.001)
        np.testing.assert_allclose(
            sorted(map(tuple, line)), [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
            atol=1e-12)

    def test_empty_or_infinite_window_raises(self):
        with pytest.raises(ValueError, match="uv_window"):
            intersect_surface_plane(_xy_plane(), [0.5, 0, 0], _X,
                                    (0.0, 0.0, 0.0, 1.0), 0.001)
        with pytest.raises(ValueError, match="uv_window"):
            intersect_surface_plane(_xy_plane(), [0.5, 0, 0], _X,
                                    (0.0, np.inf, 0.0, 1.0), 0.001)
