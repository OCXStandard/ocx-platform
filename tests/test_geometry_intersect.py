"""Tests for ocx_geometry.grid and ocx_geometry.intersect."""
from __future__ import annotations

import numpy as np
import pytest
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import intersect_surface_plane, offset_plane
from ocx_geometry.surfaces import CylinderParam, PlaneParam


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


def _cylinder() -> CylinderParam:
    """Radius 1 m, axis z through the origin; u = angle, v = z."""
    return CylinderParam(np.zeros(3), _Z, 1.0)


class TestMarchingCut:
    def test_plane_through_axis_gives_two_lines(self):
        cyl = _cylinder()
        # plane spanned by the axis and cyl.x: zeros at u = 0 and u = pi
        lines = intersect_surface_plane(cyl, np.zeros(3), cyl.y,
                                        (-1.0, 4.0, 0.0, 1.0), 0.001)
        assert len(lines) == 2
        for line in lines:
            np.testing.assert_allclose(line @ cyl.y, 0.0, atol=1e-3)
            np.testing.assert_allclose(
                np.hypot(line[:, 0], line[:, 1]), 1.0, atol=1e-9)
            assert line[:, 2].min() == pytest.approx(0.0)
            assert line[:, 2].max() == pytest.approx(1.0)
        sides = sorted(float((line @ cyl.x).mean()) for line in lines)
        np.testing.assert_allclose(sides, [-1.0, 1.0], atol=1e-3)

    def test_plane_across_axis_gives_one_circle(self):
        (line,) = intersect_surface_plane(
            _cylinder(), [0.0, 0.0, 1.0], _Z, (-np.pi, np.pi, 0.0, 2.0),
            0.001)
        np.testing.assert_allclose(line[:, 2], 1.0, atol=1e-9)
        np.testing.assert_allclose(
            np.hypot(line[:, 0], line[:, 1]), 1.0, atol=1e-9)
        # spans the whole periodic window: ends meet in 3D
        assert np.linalg.norm(line[0] - line[-1]) < 1e-9
        assert len(line) > 8

    def test_plane_outside_window_gives_nothing(self):
        assert intersect_surface_plane(
            _cylinder(), [0.0, 0.0, 1.0], _Z, (-np.pi, np.pi, 2.0, 3.0),
            0.001) == []

    def test_tilted_plane_gives_one_chain_on_the_plane(self):
        # cylinder axis x, tilted plane through the origin: an ellipse that
        # spans the whole periodic u window -> one chain
        cyl = CylinderParam(np.zeros(3), _X, 1.0)
        normal = np.array([1.0, 0.0, 0.1])
        (line,) = intersect_surface_plane(
            cyl, np.zeros(3), normal, (-np.pi, np.pi, -5.0, 5.0), 0.001)
        np.testing.assert_allclose(line @ normal, 0.0, atol=2e-3)


class TestMarchingInternals:
    def test_saddle_resolved_by_cell_centre(self):
        from ocx_geometry.intersect import _contour_segments
        f = np.array([[1.0, -1.0], [-1.0, 1.0]])  # centre 0 -> same as (0, 0)
        assert _contour_segments(f) == [
            (("u", 0, 0), ("v", 1, 0)), (("u", 0, 1), ("v", 0, 0))]

    def test_link_closes_loops(self):
        from ocx_geometry.intersect import _link
        (chain,) = _link([("a", "b"), ("b", "c"), ("c", "a")])
        assert len(chain) == 4 and chain[0] == chain[-1]
        assert set(chain) == {"a", "b", "c"}

    def test_link_open_chain_starts_at_an_end(self):
        from ocx_geometry.intersect import _link
        (chain,) = _link([("a", "b"), ("b", "c")])
        assert chain in (["a", "b", "c"], ["c", "b", "a"])

    def test_marching_drops_zero_length_segments_on_grid_vertices(self):
        from ocx_geometry.intersect import _marching_cut
        n = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
        p = np.array([0.5, 0.5, 0.0])
        lines = _marching_cut(_xy_plane(), p, n, (0.0, 1.0, 0.0, 1.0), 1e-3)
        assert lines
        for line in lines:
            assert len(line) >= 2
            gaps = np.linalg.norm(np.diff(line, axis=0), axis=1)
            assert gaps.min() > 1e-12
            assert np.allclose((line - p) @ n, 0.0, atol=1e-9)
