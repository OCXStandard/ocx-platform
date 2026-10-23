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


class TestRenderModelBrackets:
    @staticmethod
    def _vessel():
        from ocx_model_core.model.ir.base import (IrVector3D, ParentKind,
                                                  ParentRef, Quantity)
        from ocx_model_core.model.ir.geometry import (IrCompositeCurve3D,
                                                      IrLine3D, IrPlane3D,
                                                      IrPoint3D)
        from ocx_model_core.model.ir.structural import IrBracket, IrVessel

        def pt(x, y, z):
            return IrPoint3D(x, y, z, "Um")

        contour = IrCompositeCurve3D(curve_length=None, segments=[
            IrLine3D(curve_length=None, start=pt(0, 0, 0), end=pt(1, 0, 0)),
            IrLine3D(curve_length=None, start=pt(1, 0, 0), end=pt(1, 1, 0)),
            IrLine3D(curve_length=None, start=pt(1, 1, 0), end=pt(0, 0, 0)),
        ])
        plane = IrPlane3D(point_on_surface=pt(0, 0, 0),
                          normal=IrVector3D(0, 0, 1))
        parent = ParentRef(kind=ParentKind.VESSEL, id="v1")
        v = IrVessel(id="v1", name="V")
        v.brackets["br1"] = IrBracket(
            id="br1", parent_ref=parent, name="BR1",
            thickness=Quantity(0.01, "Um"),
            outer_contour=contour, plane=plane)
        v.brackets["br2"] = IrBracket(id="br2", parent_ref=parent)
        return v

    def test_bracket_rendered_as_solid(self):
        from ocx_render.render import render_model

        result = render_model(self._vessel())
        brackets = [m for m in result.meshes if m.kind == "bracket"]
        assert len(brackets) == 1
        pm = brackets[0]
        assert pm.part_id == "br1"
        # solid: both sides of the plane present
        assert pm.vertices[:, 2].min() == pytest.approx(-0.005, abs=1e-9)
        assert pm.vertices[:, 2].max() == pytest.approx(+0.005, abs=1e-9)
        assert pm.normals is not None

    def test_bracket_without_contour_is_skipped_with_reason(self):
        from ocx_render.render import render_model

        result = render_model(self._vessel())
        assert result.skipped.get("br2") == "no outer contour"
