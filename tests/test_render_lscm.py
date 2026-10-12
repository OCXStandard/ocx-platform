"""Tests for the LSCM multi-patch chart (ocx_geometry.lscm)."""
import numpy as np
import pytest  # noqa: F401 — used by tests appended in later tasks
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import make_param
from ocx_model_core.model.ir.geometry import IrNurbsSurface, IrPoint3D

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def _grid_patch(pid, x0, y0, size=2.0):
    """Flat bilinear NURBS patch spanning [x0,x0+size] x [y0,y0+size], z=0."""
    return IrNurbsSurface(
        id=pid, u_degree=1, v_degree=1,
        u_knot_vector=[0, 0, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(x0, y0, 0), pt(x0, y0 + size, 0)],
                        [pt(x0 + size, y0, 0), pt(x0 + size, y0 + size, 0)]],
    )


def _grid_members():
    members = [make_param(_grid_patch(f"p{i}{j}", 2.0 * i, 2.0 * j), LR,
                          tol_m=0.01)
               for i in range(2) for j in range(2)]
    assert all(m is not None for m in members)
    return members


def _bilge_members_and_hints():
    """Flat bottom + quarter bilge cylinder + flat side, with plate-contour
    hint points (mirrors test_render_model's spanning-plate scenario)."""
    from ocx_geometry.surfaces import CylinderParam, PlaneParam
    bot = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
    cyl = CylinderParam(np.array([0.0, 1.0, 1.0]),
                        np.array([1.0, 0.0, 0.0]), 1.0)
    side = PlaneParam(np.array([0.0, 2.0, 0.0]), np.array([0.0, 1.0, 0.0]))

    def girth(x):
        rows = [[x, 0.0, 0.0]]
        for th in np.linspace(0.0, np.pi / 2, 9):
            rows.append([x, 1.0 + np.sin(th), 1.0 - np.cos(th)])
        rows.append([x, 2.0, 2.0])
        return rows

    xs = np.linspace(0.0, 4.0, 9)
    hints = np.array(
        girth(0.0) + girth(4.0)
        + [[x, 0.0, 0.0] for x in xs]      # bottom closing edge
        + [[x, 2.0, 2.0] for x in xs])     # top closing edge
    return [bot, cyl, side], hints


class TestBuildMesh:
    def test_grid_members_weld_into_one_connected_mesh(self):
        from ocx_geometry.lscm import _build_mesh
        cm = _build_mesh(_grid_members(), tol_m=0.01, hint_pts=None)
        assert cm is not None
        # 4 one-cell patches = 16 raw corners; welding shared corners
        # leaves the 3x3 lattice of 9 distinct vertices
        assert len(cm.V) == 9
        assert len(cm.F) == 8
        # every triangle knows its source member
        assert (cm.tri_member >= 0).all()

    def test_mismatched_seam_densities_are_stitched(self):
        """Plane edges sample 2 points where the cylinder edge samples many:
        the T-junctions must be split so no boundary edge passes through
        another boundary vertex."""
        from ocx_geometry.lscm import _boundary_edges, _build_mesh
        members, hints = _bilge_members_and_hints()
        cm = _build_mesh(members, tol_m=0.01, hint_pts=hints)
        assert cm is not None
        bnd = _boundary_edges(cm.F)
        bverts = np.unique(bnd)
        for a, b in bnd:
            d = cm.V[b] - cm.V[a]
            ll = float(d @ d)
            for w in bverts:
                if w in (a, b):
                    continue
                t = float((cm.V[w] - cm.V[a]) @ d) / ll
                if not 1e-6 < t < 1 - 1e-6:
                    continue
                gap = np.linalg.norm(cm.V[a] + t * d - cm.V[w])
                assert gap > 1e-4, f"T-junction left at vertex {w}"

    def test_source_backpointers_evaluate_onto_their_vertices(self):
        """Every stored (member, local uv) must evaluate back onto its
        welded vertex — regression for mirrored stitch interpolation."""
        from ocx_geometry.lscm import _build_mesh
        members, hints = _bilge_members_and_hints()
        cm = _build_mesh(members, tol_m=0.01, hint_pts=hints)
        assert cm is not None
        worst = 0.0
        for i, d in enumerate(cm.src):
            for k, luv in d.items():
                p = np.asarray(members[k].evaluate(np.array([luv])))[0]
                worst = max(worst, float(np.linalg.norm(p - cm.V[i])))
        assert worst < 1e-6, f"src back-pointer off by {worst:.2e} m"

    def test_disconnected_members_return_none(self):
        from ocx_geometry.lscm import _build_mesh
        a = make_param(_grid_patch("a", 0.0, 0.0), LR, tol_m=0.01)
        b = make_param(_grid_patch("b", 10.0, 0.0), LR, tol_m=0.01)
        assert _build_mesh([a, b], tol_m=0.01, hint_pts=None) is None

    def test_unbounded_members_without_hints_return_none(self):
        from ocx_geometry.lscm import _build_mesh
        from ocx_geometry.surfaces import PlaneParam
        p1 = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        p2 = PlaneParam(np.array([0.0, 2.0, 0.0]), np.array([0.0, 1.0, 0.0]))
        assert _build_mesh([p1, p2], tol_m=0.01, hint_pts=None) is None
