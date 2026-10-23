"""Tests for the pure-Python UV-domain tessellator."""
import numpy as np
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import make_param
from ocx_geometry.uv_tessellator import UvTessellator
from ocx_model_core.model.ir.base import IrVector3D, Quantity
from ocx_model_core.model.ir.geometry import IrCylinder3D, IrPlane3D, IrPoint3D

LR = LengthResolver({})
OPT = TessellationOptions()


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def plane_param():
    return make_param(
        IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                  normal=IrVector3D(0, 0, 1), udirection=IrVector3D(1, 0, 0)),
        LR, tol_m=OPT.tolerance_m)


def mesh_area(pm):
    v, f = pm.vertices, pm.triangles
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    return 0.5 * float(np.linalg.norm(cross, axis=1).sum())


class TestPlanarPlate:
    def test_rectangle(self):
        contour = np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [0, 2, 0]], dtype=float)
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl1", "Plate 1", "plate", contour, [], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 8.0, atol=1e-9)
        assert pm.normals is not None and np.allclose(np.abs(pm.normals[:, 2]), 1.0)
        assert np.all(np.isfinite(pm.vertices))

    def test_l_shape_with_hole(self):
        contour = np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [2, 2, 0],
                            [2, 4, 0], [0, 4, 0]], dtype=float)       # area 12
        hole = np.array([[0.5, 0.5, 0], [1.5, 0.5, 0],
                         [1.5, 1.5, 0], [0.5, 1.5, 0]], dtype=float)  # area 1
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl2", "L plate", "plate", contour, [hole], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 11.0, atol=1e-6)

    def test_edge_crossing_slot_cuts_boundary_notch(self):
        # Slot contour extends past the plate edge (common for slot cut-outs
        # authored at stiffener penetrations): must remove material, leaving
        # a notch, not refill it with a spurious make_valid fragment.
        contour = np.array([[0, 0, 0], [10, 0, 0], [10, 5, 0], [0, 5, 0]],
                           dtype=float)                            # area 50
        slot = np.array([[4, 4, 0], [6, 4, 0], [6, 6, 0], [4, 6, 0]],
                        dtype=float)                               # 2x1 inside
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl3", "slotted", "plate", contour, [slot], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 48.0, atol=1e-6)

    def test_fully_outside_hole_is_dropped(self):
        contour = np.array([[0, 0, 0], [10, 0, 0], [10, 5, 0], [0, 5, 0]],
                           dtype=float)
        hole = np.array([[20, 1, 0], [21, 1, 0], [21, 2, 0], [20, 2, 0]],
                        dtype=float)
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl4", "plate", "plate", contour, [hole], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 50.0, atol=1e-6)

    def test_degenerate_contour_returns_none(self):
        contour = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)  # zero area
        pm = UvTessellator().tessellate_trimmed_surface(
            "bad", "bad", "plate", contour, [], plane_param(), OPT)
        assert pm is None


class TestCylindricalPlate:
    def test_curved_patch_is_subdivided_and_on_surface(self):
        r = 2.0
        param = make_param(
            IrCylinder3D(id="c", origin=pt(0, 0, 0), axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um")),
            LR, tol_m=OPT.tolerance_m)
        # half-shell boundary: angles 0..pi at z=0 and z=3 (on-surface polyline)
        ang = np.linspace(0.0, np.pi, 20)
        bottom = np.column_stack([r * np.cos(ang), r * np.sin(ang), np.zeros(20)])
        top = bottom[::-1] + [0, 0, 3.0]
        contour = np.vstack([bottom, top])
        pm = UvTessellator().tessellate_trimmed_surface(
            "cp", "curved", "plate", contour, [], param, OPT)
        assert pm is not None
        # interior vertices must lie on the cylinder, not on boundary chords
        radii = np.linalg.norm(pm.vertices[:, :2], axis=1)
        np.testing.assert_allclose(radii, r, atol=1e-6)
        # subdivision must create interior vertices beyond the boundary samples
        assert len(pm.vertices) > len(contour)
        # analytic area of the half shell: pi * r * h
        assert abs(mesh_area(pm) - np.pi * r * 3.0) / (np.pi * r * 3.0) < 0.02

    def test_issue1_hole_on_periodic_seam(self):
        """Issue 1: hole on periodic-u surface near seam lands in wrong 2π branch.
        After fix, hole should be shifted into exterior's u-branch and properly carved.
        """
        r = 2.0
        param = make_param(
            IrCylinder3D(id="c", origin=pt(0, 0, 0), axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um")),
            LR, tol_m=OPT.tolerance_m)
        # Rectangular patch crossing the ±π seam, with a hole entirely past the seam.
        # Patch: u ∈ [2.6, 3.6] (crosses u = π), v ∈ [0.0, 1.0]
        u_patch = np.array([2.6, 3.6, 3.6, 2.6])
        v_patch = np.array([0.0, 0.0, 1.0, 1.0])
        patch_uv = np.column_stack([u_patch, v_patch])
        patch_3d = param.evaluate(patch_uv)
        # Hole: u ∈ [3.2, 3.5] — inverts into the wrong 2π branch (u ≈ -3.08..-2.78)
        u_hole = np.array([3.2, 3.5, 3.5, 3.2])
        v_hole = np.array([0.3, 0.3, 0.7, 0.7])
        hole_uv = np.column_stack([u_hole, v_hole])
        hole_3d = param.evaluate(hole_uv)
        # Precondition: the hole's independent inversion lands in the opposite branch
        hole_inv_u = param.inverse(hole_3d)[:, 0]
        assert hole_inv_u.max() < 0.0 < 2.6
        pm = UvTessellator().tessellate_trimmed_surface(
            "cp_hole", "curved with hole", "plate", patch_3d, [hole_3d], param, OPT)
        assert pm is not None
        # Patch area = Δu * r * Δv = 1.0 * 2 * 1.0 = 2.0
        # Hole area  = 0.3 * 2 * 0.4 = 0.24 → expected carved area ≈ 1.76
        # Without the fix the hole is silently dropped and the area is ≈ 2.0.
        area = mesh_area(pm)
        assert abs(area - 1.76) / 1.76 < 0.03, (
            f"Area {area:.3f} != 1.76; hole not carved on seam-crossing patch")

    def test_issue2_subdivision_max_iter_exceeded(self):
        """Issue 2: trimesh.remesh.subdivide_to_size raises ValueError on high ratio.
        Cylinder r=0.1 m, 20 m tall, tight tolerance 0.001 m → must not raise.
        """
        r = 0.1
        h = 20.0
        opt = TessellationOptions(tolerance_m=0.001)
        param = make_param(
            IrCylinder3D(id="c", origin=pt(0, 0, 0), axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um")),
            LR, tol_m=opt.tolerance_m)
        # Half-shell contour covering the tall cylinder
        ang = np.linspace(0.0, np.pi, 10)
        bottom = np.column_stack([r * np.cos(ang), r * np.sin(ang), np.zeros(10)])
        top = bottom[::-1] + [0, 0, h]
        contour = np.vstack([bottom, top])
        # Must not raise ValueError; returns PartMesh or None, not exception
        pm = UvTessellator().tessellate_trimmed_surface(
            "tall", "tall cylinder", "plate", contour, [], param, opt)
        # Should return a mesh (even if unsubdivided due to fallback)
        assert pm is not None


class TestNonFiniteUV:
    def test_issue3_nan_in_exterior_contour(self):
        """Issue 3: non-finite UVs (NaN) from inverse() → shapely GEOSException.
        PlaneParam with a contour containing one NaN point → returns None, no exception.
        """
        contour = np.array([
            [0, 0, 0],
            [4, 0, 0],
            [np.nan, 2, 0],  # NaN point
            [0, 2, 0],
        ], dtype=float)
        pm = UvTessellator().tessellate_trimmed_surface(
            "bad_nan", "bad contour", "plate", contour, [], plane_param(), OPT)
        # Must return None gracefully (not raise)
        assert pm is None
