import numpy as np
import pytest
from ocx_diagnose.analyse import analyse_model
from ocx_diagnose.checks import (
    chart_distortion,
    mesh_health,
    neighbour_overlaps_and_gaps,
    snap_vectors,
    surface_deviation,
)
from ocx_geometry.surfaces import PlaneParam

from tests.test_render_model import make_vessel


def _quad(z=0.0, x0=0.0):
    V = np.array([[x0, 0, z], [x0 + 1, 0, z], [x0 + 1, 1, z], [x0, 1, z]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def test_mesh_health_counts_boundary_and_nonmanifold():
    V, F = _quad()
    h = mesh_health(V, F)
    assert h["boundary_edges"] == 4 and h["non_manifold_edges"] == 0
    # a third triangle on the shared diagonal makes it non-manifold
    V2 = np.vstack([V, [0.5, 0.5, 1.0]])
    F2 = np.vstack([F, [[0, 2, 4]]])
    assert mesh_health(V2, F2)["non_manifold_edges"] == 1


def test_deviation_zero_on_plane_and_offset_detected():
    plane = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
    pts = np.random.default_rng(0).uniform(-1, 1, (50, 3)) * [1, 1, 0]
    assert surface_deviation(pts, [plane]).max() < 1e-9
    assert surface_deviation(pts + [0, 0, 0.01], [plane]).min() == pytest.approx(0.01)


def test_overlap_and_gap_detected_between_plates():
    A = _quad()
    B_overlap = _quad(x0=0.0)                 # coincident with A
    B_gap = _quad(x0=1.0 + 0.002)             # 2 mm gap next to A
    ov = neighbour_overlaps_and_gaps({"A": A, "B": B_overlap}, gap_max_m=0.05)
    assert ov["B"]["overlap_faces"] > 0
    gp = neighbour_overlaps_and_gaps({"A": A, "B": B_gap}, gap_max_m=0.05)
    assert gp["A"]["gap_vertices"] > 0 and gp["A"]["max_gap_m"] == pytest.approx(0.002, abs=1e-6)


def test_snap_vectors_point_to_nearest_mesh_vertex():
    V, F = _quad()
    ring = np.array([[0.1, 0.1, 0.3]])
    starts, ends = snap_vectors(ring, V)
    assert np.allclose(starts[0], ring[0]) and np.allclose(ends[0], V[0])


def test_chart_distortion_flags_flipped_triangle():
    V, F = _quad()
    uv = V[:, :2].copy()
    uv[[2, 3]] = uv[[3, 2]]                    # swap -> second triangle flips
    d = chart_distortion(V, F, uv)
    assert d.flipped.sum() >= 1 and 0 < d.flipped_frac <= 1
    ok = chart_distortion(V, F, V[:, :2])
    assert ok.flipped.sum() == 0 and ok.spread_max == pytest.approx(1.0)


def test_analyse_model_returns_panel_and_plate_results_and_sweep():
    res = analyse_model(make_vessel(), {"pan1"}, 50.0, [25.0, 100.0])
    assert [p.panel_id for p in res] == ["pan1"]
    pr = res[0].plates[0]
    assert pr.plate_id == "pl1" and pr.route == "single"
    assert pr.dev_max_m is not None and pr.dev_max_m <= 0.05 * 2
    assert [s.tol_mm for s in res[0].sweep] == [25.0, 100.0]
    assert res[0].sweep[0].triangles >= res[0].sweep[1].triangles
    assert res[0].tol_m == pytest.approx(0.05)


class _CountingPlane(PlaneParam):
    calls = 0

    def inverse(self, pts):
        type(self).calls += 1
        return super().inverse(pts)


def test_deviation_with_chart_only_queries_nearby_members():
    from ocx_geometry.diagnostics import ChartDiag
    n = 300
    members = [_CountingPlane(np.array([0.0, 0.0, float(k)]), np.array([0.0, 0.0, 1.0]))
               for k in range(n)]
    V = np.vstack([[[0, 0, k], [1, 0, k], [0, 1, k]] for k in range(n)]).astype(float)
    F = np.arange(3 * n).reshape(n, 3)
    chart = ChartDiag(V=V, F=F, tri_member=np.arange(n))
    pts = np.array([[0.2, 0.2, 5.01], [0.2, 0.2, 40.0]])
    _CountingPlane.calls = 0
    full = surface_deviation(pts, members)
    full_calls = _CountingPlane.calls
    _CountingPlane.calls = 0
    fast = surface_deviation(pts, members, chart=chart)
    assert np.allclose(fast, full)
    assert _CountingPlane.calls < full_calls / 5

