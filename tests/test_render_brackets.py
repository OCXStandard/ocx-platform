"""Tests for ocx_geometry.bracket — planar bracket tessellation."""
from collections import Counter

import numpy as np
import pytest
from ocx_geometry.bracket import tessellate_bracket

# 4 x 2 rectangle in the XY plane
RECT = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0],
                 [4.0, 2.0, 0.0], [0.0, 2.0, 0.0]])
PLANE = (np.zeros(3), np.array([0.0, 0.0, 1.0]))
TOL = 0.005


def _welded(v, f, grid=1e-9):
    """Weld exact-duplicate vertices so edge adjacency is countable."""
    key = np.round(v / grid).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True,
                              return_inverse=True)
    return v[first], np.asarray(inv).ravel()[f]


def _edge_counts(f):
    e = np.sort(f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    return Counter(map(tuple, e))


def _volume(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


class TestSolid:
    def test_prism_is_watertight(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert all(c == 2 for c in _edge_counts(wf).values())

    def test_prism_volume_matches_area_times_thickness(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert abs(_volume(wv, wf)) == pytest.approx(4 * 2 * 0.02, rel=0.01)

    def test_symmetric_placement_without_offset(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        assert v[:, 2].min() == pytest.approx(-0.01, abs=1e-9)
        assert v[:, 2].max() == pytest.approx(+0.01, abs=1e-9)

    def test_offset_places_base_face(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, 0.005, TOL)
        assert v[:, 2].min() == pytest.approx(0.005, abs=1e-9)
        assert v[:, 2].max() == pytest.approx(0.025, abs=1e-9)

    def test_normals_aligned_with_vertices(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        assert n.shape == v.shape
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0,
                                   atol=1e-9)


class TestSheetFallback:
    def test_no_thickness_gives_flat_sheet(self):
        v, f, n = tessellate_bracket(RECT, PLANE, None, None, TOL)
        assert np.allclose(v[:, 2], 0.0)
        # area of the triangulation == rectangle area
        a = v[f[:, 1]] - v[f[:, 0]]
        b = v[f[:, 2]] - v[f[:, 0]]
        area = float(np.linalg.norm(np.cross(a, b), axis=1).sum() / 2)
        assert area == pytest.approx(8.0, rel=1e-6)


class TestPlaneHandling:
    def test_best_fit_plane_when_none_given(self):
        # same rectangle, tilted 30 deg about x — no plane passed in
        ang = np.radians(30.0)
        rot = np.array([[1, 0, 0],
                        [0, np.cos(ang), -np.sin(ang)],
                        [0, np.sin(ang), np.cos(ang)]])
        pts = RECT @ rot.T
        v, f, n = tessellate_bracket(pts, None, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert abs(_volume(wv, wf)) == pytest.approx(4 * 2 * 0.02, rel=0.01)

    def test_non_planar_contour_returns_none(self):
        pts = RECT.copy()
        pts[2, 2] = 1.0  # one corner lifted 1 m out of plane
        assert tessellate_bracket(pts, PLANE, 0.02, None, TOL) is None

    def test_degenerate_contour_returns_none(self):
        line = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
        assert tessellate_bracket(line, PLANE, 0.02, None, TOL) is None
