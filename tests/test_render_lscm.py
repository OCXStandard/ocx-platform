"""Tests for the LSCM multi-patch chart (ocx_geometry.lscm)."""
import numpy as np
import pytest
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


class TestLscmFlat:
    def test_single_patch_chart_is_metric_and_exact(self):
        from ocx_geometry.lscm import make_lscm
        m = make_param(_grid_patch("p", 0.0, 0.0, 4.0), LR, tol_m=0.01)
        chart = make_lscm([m], tol_m=0.01)
        assert chart is not None
        pts = np.array([[0.0, 0, 0], [4.0, 0, 0], [4.0, 4, 0],
                        [0.0, 4, 0], [2.0, 2, 0]])
        uv = chart.inverse(pts)
        # metric chart: UV distances match 3-D distances
        assert np.linalg.norm(uv[1] - uv[0]) == pytest.approx(4.0, rel=0.05)
        np.testing.assert_allclose(chart.evaluate(uv), pts, atol=1e-6)

    def test_normals_are_unit_and_perpendicular(self):
        from ocx_geometry.lscm import make_lscm
        chart = make_lscm(_grid_members(), tol_m=0.01)
        assert chart is not None
        uv = chart.inverse(np.array([[1.0, 1.0, 0.0], [3.0, 3.0, 0.0]]))
        n = chart.normals(uv)
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-9)
        np.testing.assert_allclose(np.abs(n[:, 2]), 1.0, atol=1e-9)


class TestLscm2DGrid:
    """Chart over a 2-D patch grid — the TR04 hull patch-layout regression
    (replaces TestComposite2DGrid)."""

    def _chart(self):
        from ocx_geometry.lscm import make_lscm
        chart = make_lscm(_grid_members(), tol_m=0.01)
        assert chart is not None, "LSCM chart failed to build"
        return chart

    def _contour(self):
        t = np.arange(0.0, 4.0, 0.25)
        z = np.zeros_like(t)
        return np.concatenate([
            np.column_stack([t, z, z]),
            np.column_stack([np.full_like(t, 4.0), t, z]),
            np.column_stack([4.0 - t, np.full_like(t, 4.0), z]),
            np.column_stack([z, 4.0 - t, z]),
        ])

    def test_roundtrip_on_contour(self):
        chart = self._chart()
        contour = self._contour()
        out = chart.evaluate(chart.inverse(contour))
        err = np.linalg.norm(out - contour, axis=1)
        assert err.max() < 1e-6, f"max round-trip error {err.max():.2e} m"

    def test_roundtrip_on_interior_points(self):
        chart = self._chart()
        xs = np.linspace(0.2, 3.8, 7)            # includes the seam at 2.0
        pts = np.array([[x, y, 0.0] for x in xs for y in xs])
        out = chart.evaluate(chart.inverse(pts))
        err = np.linalg.norm(out - pts, axis=1)
        assert err.max() < 1e-6, f"max round-trip error {err.max():.2e} m"


class TestLscmCurved:
    def test_evaluation_stays_exactly_on_member_surfaces(self):
        """Bottom plane + bilge cylinder + side plane: every evaluated point
        must lie exactly on one of the true member surfaces (not on the
        chart facets), and round-trip near the original."""
        from ocx_geometry.lscm import make_lscm
        members, hints = _bilge_members_and_hints()
        chart = make_lscm(members, tol_m=0.01, hint_pts=hints)
        assert chart is not None
        out = chart.evaluate(chart.inverse(hints))
        d_bot = np.abs(out[:, 2])
        d_side = np.abs(out[:, 1] - 2.0)
        d_cyl = np.abs(
            np.linalg.norm(out[:, 1:] - [1.0, 1.0], axis=1) - 1.0)
        d = np.minimum(np.minimum(d_bot, d_side), d_cyl)
        assert d.max() < 1e-9, f"off-surface by {d.max():.2e} m"
        err = np.linalg.norm(out - hints, axis=1)
        assert err.max() < 0.05, f"round-trip error {err.max():.3f} m"


class TestChartMeshHygiene:
    def test_consistent_winding_across_members(self):
        """Fan triangulation of trimmed shapely pieces must normalize ring
        orientation: GEOS does not guarantee CCW exterior rings, and mixed
        winding breaks the boundary-loop walk in LSCM and Tutte."""
        from ocx_geometry.lscm import _build_mesh
        members, hints = _bilge_members_and_hints()
        cm = _build_mesh(members, tol_m=0.01, hint_pts=hints)
        assert cm is not None
        e = np.vstack([cm.F[:, [0, 1]], cm.F[:, [1, 2]], cm.F[:, [2, 0]]])
        key = np.sort(e, axis=1)
        _, inv, cnt = np.unique(key, axis=0, return_inverse=True,
                                return_counts=True)
        bad = 0
        for ei in np.nonzero(cnt == 2)[0]:
            occ = e[inv == ei]
            if (occ[0] == occ[1]).all():
                bad += 1
        assert bad == 0, f"{bad} interior edges with same-direction faces"

    def test_split_pinch_vertices(self):
        """A bowtie (two fans sharing only a vertex) breaks disk topology
        and wraps the flattening; the shared vertex must be duplicated."""
        from ocx_geometry.lscm import _split_pinch_vertices
        V = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0],
                      [2.0, 0, 0], [2.0, 1, 0]])
        F = np.array([[0, 1, 2], [1, 3, 4]])      # share only vertex 1
        src = [{0: (0.0, 0.0)} for _ in range(5)]
        V2, F2, src2 = _split_pinch_vertices(V, F, src)
        assert len(V2) == 6
        assert len(src2) == 6
        # the two faces no longer share a vertex index
        assert not set(map(int, F2[0])) & set(map(int, F2[1]))
        # geometry unchanged: the duplicate sits exactly on the original
        np.testing.assert_allclose(
            np.sort(V2[F2[1]], axis=0), np.sort(V[F[1]], axis=0))

    def test_split_pinch_keeps_regular_mesh_untouched(self):
        from ocx_geometry.lscm import _split_pinch_vertices
        V = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [1.0, 1, 0]])
        F = np.array([[0, 1, 2], [1, 3, 2]])
        src = [{0: (0.0, 0.0)} for _ in range(4)]
        V2, F2, src2 = _split_pinch_vertices(V, F, src)
        assert len(V2) == 4
        np.testing.assert_array_equal(F2, F)


class TestContourRadius:
    def test_long_thin_contour_radius_capped_by_width(self):
        """Index-ring distance degrades on non-uniformly sampled contours
        (straight edges carry few samples): the PCA second-principal cap
        must keep the region radius near the plate width, not its length."""
        from ocx_geometry.lscm import make_lscm_chart
        m = make_param(_grid_patch("p", 0.0, 0.0, 12.0), LR, tol_m=0.05)
        chart = make_lscm_chart([m], tol_m=0.05)
        assert chart is not None
        # 11 x 2 m plate: dense samples on the short ends, sparse on the
        # long edges — mimics curvature-adaptive contour sampling
        ys = np.linspace(0.0, 2.0, 24)
        xs = np.linspace(0.5, 11.5, 4)
        contour = np.concatenate([
            np.column_stack([np.full_like(ys, 0.5), ys]),
            np.column_stack([xs[1:-1], np.full(2, 2.0)]),
            np.column_stack([np.full_like(ys, 11.5), ys[::-1]]),
            np.column_stack([xs[1:-1][::-1], np.zeros(2)]),
        ])
        contour = np.column_stack([contour, np.zeros(len(contour))])
        radius = chart._contour_radius(contour)
        assert radius < 3.0, f"radius {radius:.2f} m ~ plate length"


class TestParamForSeams:
    def test_plate_spanning_tangent_seam_roundtrips(self):
        """A plate across the bottom-plane/bilge-cylinder seam, sampled at
        differing densities per member, must get a validated chart (zip +
        stitch + reorientation + pinch handling), not the fallback."""
        from ocx_geometry.lscm import make_lscm_chart
        members, hints = _bilge_members_and_hints()
        chart = make_lscm_chart(members, tol_m=0.01, hint_pts=hints)
        assert chart is not None

        def girth_pt(th, x):
            return [x, 1.0 + np.sin(th), 1.0 - np.cos(th)]

        # plate spanning bottom plane (y < 1) and the lower bilge arc
        ths = np.linspace(0.0, np.pi / 4, 8)
        contour = np.array(
            [[0.5, y, 0.0] for y in np.linspace(0.2, 1.0, 5)]
            + [girth_pt(th, 0.5) for th in ths[1:]]
            + [girth_pt(np.pi / 4, x) for x in np.linspace(0.5, 3.5, 5)[1:]]
            + [girth_pt(th, 3.5) for th in ths[::-1][1:]]
            + [[3.5, y, 0.0] for y in np.linspace(1.0, 0.2, 5)[1:]]
            + [[x, 0.2, 0.0] for x in np.linspace(3.5, 0.5, 7)[1:-1]])
        param = chart.param_for(contour)
        assert param is not None, "param_for fell back on a seam plate"
        uv = param.inverse(contour)
        err = np.linalg.norm(param.evaluate(uv) - contour, axis=1)
        assert err.max() < 0.02, f"roundtrip {err.max():.4f} m"


class TestLscmFailure:
    def test_make_lscm_disconnected_returns_none(self):
        from ocx_geometry.lscm import make_lscm
        a = make_param(_grid_patch("a", 0.0, 0.0), LR, tol_m=0.01)
        b = make_param(_grid_patch("b", 10.0, 0.0), LR, tol_m=0.01)
        assert make_lscm([a, b], tol_m=0.01) is None

    def test_make_lscm_never_raises(self):
        from ocx_geometry.lscm import make_lscm
        from ocx_geometry.surfaces import PlaneParam
        p = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        # unbounded member, no hints -> None, no exception
        assert make_lscm([p, p], tol_m=0.01, hint_pts=None) is None
        # degenerate hints (collinear) -> None, no exception
        hints = np.array([[x, 0.0, 0.0] for x in np.linspace(0, 1, 5)])
        assert make_lscm([p, p], tol_m=0.01, hint_pts=hints) is None
