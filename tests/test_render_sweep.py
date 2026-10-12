"""Tests for the section sweep along trace polylines."""
import numpy as np
import trimesh
from ocx_geometry.sweep import resolve_web_dirs, sweep_profile
from ocx_model_core.model.ir.base import IrVector3D
from ocx_model_core.model.ir.structural import IrInclination

# CCW profile (positive signed area)
SQUARE = np.array([[-0.05, 0.0], [0.05, 0.0], [0.05, 0.1], [-0.05, 0.1]])
# CW profile (negative signed area)
SQUARE_CW = np.array([[0.05, 0.1], [0.05, 0.0], [-0.05, 0.0], [-0.05, 0.1]])


def straight_trace(n=5, length=4.0):
    t = np.linspace(0.0, length, n)
    return np.column_stack([t, np.zeros(n), np.zeros(n)])


class TestResolveWebDirs:
    def test_inclination_hint_is_used_and_orthogonalized(self):
        pts = straight_trace()
        incl = [IrInclination(web_direction=IrVector3D(0.1, 0.0, 1.0))]
        dirs = resolve_web_dirs(pts, incl)
        assert dirs.shape == pts.shape
        # orthogonal to the +x tangent and normalized
        np.testing.assert_allclose(dirs @ np.array([1.0, 0, 0]), 0.0, atol=1e-9)
        np.testing.assert_allclose(np.linalg.norm(dirs, axis=1), 1.0, atol=1e-9)
        # dominated by +z after orthogonalization
        assert np.all(dirs[:, 2] > 0.9)

    def test_no_inclination_transport_has_no_flips(self):
        # quarter-circle trace in the XY plane
        ang = np.linspace(0.0, np.pi / 2.0, 20)
        pts = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(20)])
        dirs = resolve_web_dirs(pts, [])
        dots = np.einsum("ij,ij->i", dirs[:-1], dirs[1:])
        assert np.all(dots > 0.99)          # consecutive frames nearly parallel

    def test_zero_tangent_handled_gracefully(self):
        # ISSUE 1: zero-length tangents should not raise ValueError
        # Two identical points result in zero tangent
        pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, [])
        assert dirs.shape == pts.shape
        # All dirs should be normalized
        norms = np.linalg.norm(dirs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-9)

    def test_zero_web_directions_handled_gracefully(self):
        # ISSUE 1: resolve_web_dirs with all-zero web_dirs should not raise
        pts = np.zeros((3, 3))
        dirs = resolve_web_dirs(pts, [])
        # Should return normalized directions without raising
        norms = np.linalg.norm(dirs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-9)

    def test_hints_interpolated_between_positions(self):
        """Web directions must blend smoothly between positioned hints —
        not snap to the nearest hint (which causes abrupt web flips)."""
        pts = straight_trace(n=9)                       # x = 0 .. 4
        incl = [IrInclination(web_direction=IrVector3D(0, 0, 1)),
                IrInclination(web_direction=IrVector3D(0, 1, 0))]
        positions = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, incl, positions)
        mid = dirs[4]                                   # at x = 2
        # blended ≈ (0, .707, .707); nearest-hint would give (0,0,1) or (0,1,0)
        assert mid[1] > 0.6 and mid[2] > 0.6, mid
        # ends still match their hints
        np.testing.assert_allclose(dirs[0], [0, 0, 1], atol=1e-9)
        np.testing.assert_allclose(dirs[-1], [0, 1, 0], atol=1e-9)


class TestInsertTracePoints:
    def test_positions_inserted_on_segments(self):
        from ocx_geometry.sweep import insert_trace_points
        pts = np.array([[0.0, 0, 0], [4.0, 0, 0]])
        out = insert_trace_points(pts, np.array([[2.0, 0.0, 0.0]]))
        assert any(np.allclose(p, [2, 0, 0]) for p in out)
        assert np.all(np.diff(out[:, 0]) > 0)           # order preserved

    def test_existing_points_not_duplicated(self):
        from ocx_geometry.sweep import insert_trace_points
        pts = straight_trace(n=5)                       # already contains x=2
        out = insert_trace_points(pts, np.array([[2.0, 0.0, 0.0]]))
        assert len(out) == len(pts)


class TestSweepProfile:
    def test_vertex_and_face_counts(self):
        pts = straight_trace(n=5)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE)
        m, n = len(SQUARE), len(pts)
        assert len(verts) == m * n
        # sides: 2 tris per profile edge per span; caps: earcut of a quad = 2 tris each
        assert len(faces) == 2 * m * (n - 1) + 2 * 2

    def test_watertight_straight_sweep(self):
        pts = straight_trace(n=3)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
        assert mesh.is_watertight
        # abs(): winding sign is not guaranteed, only closedness
        assert np.isclose(abs(mesh.volume), 4.0 * 0.1 * 0.1, rtol=1e-6)

    def test_too_short_trace_returns_none(self):
        assert sweep_profile(np.zeros((1, 3)), np.zeros((1, 3)), SQUARE) is None

    def test_zero_tangent_in_trace_returns_none_or_mesh(self):
        # ISSUE 1: zero-length tangents should not raise ValueError
        pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, [])
        result = sweep_profile(pts, dirs, SQUARE)
        # Should return None or a valid mesh, not raise
        if result is not None:
            verts, faces = result
            assert verts.shape[0] > 0

    def test_identical_points_returns_none(self):
        # ISSUE 1: all identical points should return None gracefully
        pts = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, [])
        result = sweep_profile(pts, dirs, SQUARE)
        # Should return None for degenerate case
        assert result is None

    def test_nan_pts_returns_none(self):
        # ISSUE 3: NaN points should return None without silently propagating
        pts = np.array([[0.0, 0.0, 0.0], [np.nan, 0.0, 0.0], [1.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, [])
        result = sweep_profile(pts, dirs, SQUARE)
        # Should return None, not silently propagate NaN
        assert result is None

    def test_winding_consistency_ccw_profile(self):
        # ISSUE 2: CCW profile should produce consistent winding with positive volume
        pts = straight_trace(n=3)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        # Check winding consistency without repairing
        assert mesh.is_winding_consistent, "CCW profile should produce winding-consistent mesh"
        # Positive volume for outward-facing normals
        assert mesh.volume > 0, "Straight sweep should have positive volume (outward normals)"

    def test_winding_consistency_cw_profile(self):
        # ISSUE 2: CW profile should produce consistent winding with positive volume (reversed to CCW)
        pts = straight_trace(n=3)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE_CW)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        # Check winding consistency
        assert mesh.is_winding_consistent, "CW profile should produce winding-consistent mesh"
        # Positive volume: CW should be reversed to CCW so outward normals point out
        assert mesh.volume > 0, "CW sweep should be reversed to produce positive volume (outward normals)"

    def test_off_origin_ccw_profile_winding_and_volume(self):
        # ISSUE A: off-origin CCW profile should have winding consistent and volume > 0
        # Profile shifted by +10 in x: should still compute signed area correctly
        shifted_square = SQUARE + np.array([10.0, 0.0])  # shift by +10 in x
        pts = straight_trace(n=3)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, shifted_square)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        assert mesh.is_winding_consistent, "Off-origin CCW profile should be winding-consistent (Issue A)"
        assert mesh.volume > 0, "Off-origin CCW profile should have positive volume (Issue A)"

    def test_reversal_trace_ring_placement(self):
        # ISSUE C: reversal trace [[0,0,0],[1,0,0],[0,0,0]] should have rings at all non-degenerate points
        pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        dirs = resolve_web_dirs(pts, [])
        result = sweep_profile(pts, dirs, SQUARE)
        # Should successfully produce a mesh (not None)
        assert result is not None, "Reversal trace should produce a mesh (Issue C)"
        verts, faces = result
        # Verify that we have vertices at the middle point (x ≈ 1.0 ± profile extent ≈ 1.05 or >= 1.0)
        max_x = np.max(verts[:, 0])
        assert max_x >= 1.0 - 0.1, f"Reversal trace verts should reach middle point; max_x={max_x} (Issue C)"
