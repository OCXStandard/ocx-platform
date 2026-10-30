"""Tests for the LSCM multi-patch chart (ocx_geometry.lscm)."""
from pathlib import Path

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


def _paraboloid_patch(radius=10.0, size=10.0):
    """Bicubic Bezier patch z = (x^2 + y^2) / (2 radius), exact (curvature
    1/radius everywhere), on [0, size]^2."""
    cz = [0.0, 0.0, 1.0 / 3.0, 1.0]       # Bezier ordinates of t^2
    k = size * size / (2.0 * radius)
    return IrNurbsSurface(
        id="paraboloid", u_degree=3, v_degree=3,
        u_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
        v_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
        control_points=[[pt(size * i / 3.0, size * j / 3.0, k * (cz[i] + cz[j]))
                         for j in range(4)] for i in range(4)])


class TestPolygonRepair:
    def test_make_valid_collection_with_nested_multipolygon_is_kept(self):
        """A plate whose hole rings cross the exterior repairs to a
        GeometryCollection; its polygons must survive, not be dropped."""
        import shapely
        from ocx_geometry.uv_tessellator import _clean_polygon, _polygon_parts
        nested = shapely.GeometryCollection([
            shapely.MultiPolygon([shapely.box(0, 0, 1, 1),
                                  shapely.box(2, 0, 3, 1)]),
            shapely.LineString([(0, 0), (1, 1)])])
        assert len(_polygon_parts(nested)) == 2
        ext = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
        bowtie = np.array([[1, 1], [3, 3], [3, 1], [1, 3]], dtype=float)
        assert _clean_polygon(ext, [bowtie])


class TestFacetSag:
    def test_collapsed_edge_keeps_source_uv_consistent(self):
        """A patch with a pole (one edge collapsed to a point) welds its
        grid vertices there; the per-vertex source UV must not make the
        fan triangles evaluate away from the mesh."""
        from ocx_geometry.lscm import _build_mesh
        tol = 0.01
        size = 10.0
        rows = []
        for i in range(4):
            th = i * np.pi / 6.0
            rows.append([pt(0.0, 0.0, 0.0) if j == 0 else
                         pt(size * j / 3.0 * np.cos(th),
                            size * j / 3.0 * np.sin(th),
                            3.0 * (j / 3.0) ** 2)
                         for j in range(4)])
        patch = IrNurbsSurface(
            id="pole", u_degree=3, v_degree=3,
            u_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
            v_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1], control_points=rows)
        member = make_param(patch, LR, tol_m=tol)
        cm = _build_mesh([member], tol, None, require_connected=False)
        rng = np.random.default_rng(0)
        pole_fan = np.flatnonzero(
            (np.linalg.norm(cm.V[cm.F], axis=2) < 1e-6).any(axis=1))
        assert len(pole_fan) > 0
        tri = rng.choice(pole_fan, 3000)
        w = rng.dirichlet([1.0, 1.0, 1.0], 3000)
        corners = cm.F[tri]
        luv = np.array([[cm.src[c][0] for c in row] for row in corners])
        uv = np.einsum("ij,ijk->ik", w, luv)
        flat = np.einsum("ij,ijk->ik", w, cm.V[corners])
        err = np.linalg.norm(member.evaluate(uv) - flat, axis=1)
        assert err.max() <= 2.0 * tol

    def test_nurbs_facets_stay_within_tolerance_inside_triangles(self):
        from ocx_geometry.lscm import _facet_member, _member_domain
        tol = 0.05
        member = make_param(_paraboloid_patch(), LR, tol_m=tol)
        pts, uvs, faces = _facet_member(member, _member_domain(member), tol)
        rng = np.random.default_rng(0)
        tri = rng.integers(0, len(faces), 4000)
        w = rng.dirichlet([1.0, 1.0, 1.0], 4000)
        uv = np.einsum("ij,ijk->ik", w, uvs[faces[tri]])
        flat = np.einsum("ij,ijk->ik", w, pts[faces[tri]])
        sag = np.linalg.norm(member.evaluate(uv) - flat, axis=1)
        assert sag.max() <= 1.1 * tol


class TestBuildMesh:
    def test_plane_is_clipped_to_exact_bounded_patch_footprint(self):
        import shapely
        from ocx_geometry.lscm import _build_mesh
        from ocx_geometry.surfaces import PlaneParam

        plane = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        patch = make_param(_grid_patch("inner", 2.2, 2.2), LR, tol_m=0.05)
        hints = np.array([[0, 0, 0], [8, 0, 0], [8, 8, 0], [0, 8, 0]])
        cm = _build_mesh([plane, patch], 0.05, hints, require_connected=False)
        assert cm is not None
        triangles = shapely.polygons(cm.V[cm.F][:, :, :2])
        assert shapely.union_all(triangles).area == pytest.approx(64.0)
        assert sum(t.area for t in triangles) == pytest.approx(64.0)

    def test_grid_members_weld_into_one_connected_mesh(self):
        from ocx_geometry.lscm import _build_mesh
        cm = _build_mesh(_grid_members(), tol_m=0.01, hint_pts=None)
        assert cm is not None
        # 4 flat patches of 4x4 cells (0.5 m) = 100 raw grid points;
        # welding the shared seams leaves one 9x9 lattice
        assert len(cm.V) == 81
        assert len(cm.F) == 128
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

    def test_stitch_does_not_fold_a_patch_at_its_pole_row(self):
        """Regression (tr05_tc18 ropax SHELL_S/SHELL_P member 181): a
        triangular patch's thin pole row puts a vertex 1 cm beside the end
        of its top edge, inside the snap tolerance.  That is no T-junction:
        splitting the edge there folded the patch over its seam sliver, and
        the overlapping layers leaked plate trims along the seam."""
        from ocx_geometry.lscm import _stitch
        V = np.array([[133.9266, 0.0, 10.0],     # thin pole row, v0
                      [133.9265, 0.0, 9.99],     # thin pole row, v1
                      [119.0262, 0.0, 10.0],
                      [119.0262, 0.0, 7.834]])
        F = np.array([[0, 2, 3], [0, 3, 1]])
        src = [{0: (0.0, 0.0)} for _ in V]

        def area(F):
            t = V[F]
            return 0.5 * np.linalg.norm(np.cross(
                t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum()

        out = _stitch(V, F, src, snap_tol=0.025)
        assert area(out) == pytest.approx(area(F), rel=1e-9)
        assert len(out) == 2

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


class TestHintContourLoops:
    """Hints passed as per-plate closed contour loops bound each plane
    trim by the loop polygons, so the concave hull of sparse hint points
    can never carve a cavity out of a real plate interior (regression for
    knuckled inner-skin panels rendering with missing plate halves)."""

    @staticmethod
    def _knuckle_panel_loops():
        """Two-strake panel on plane A (z=0) whose upper strake crosses a
        knuckle at y=8.4 onto a 60-degree plane B. Along the knuckle, the
        on-A hint points sit only at plate corners 18 m apart — sparse
        enough that concave_hull(ratio=0.3) tunnels into the upper-strake
        plate interiors down to their bottom edges."""
        from ocx_geometry.surfaces import PlaneParam
        plane_a = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        knee = np.array([0.0, 8.4, 0.0])
        plane_b = PlaneParam(
            knee, np.array([0.0, -np.sin(np.pi / 3), np.cos(np.pi / 3)]))
        up = np.array([0.0, np.cos(np.pi / 3), np.sin(np.pi / 3)])

        def rect_loop(x0, x1, y0, y1):
            loop = []
            for x in np.linspace(x0, x1, 7)[:-1]:
                loop.append([x, y0, 0.0])
            for y in np.linspace(y0, y1, 8)[:-1]:
                loop.append([x1, y, 0.0])
            for x in np.linspace(x1, x0, 7)[:-1]:
                loop.append([x, y1, 0.0])
            for y in np.linspace(y1, y0, 8)[:-1]:
                loop.append([x0, y, 0.0])
            return np.asarray(loop)

        def knuckle_loop(x0, x1):
            y0, yk = 4.2, 8.4
            top = knee + 0.2 * up
            loop = []
            for x in np.linspace(x0, x1, 7)[:-1]:
                loop.append([x, y0, 0.0])
            for y in np.linspace(y0, yk, 8)[:-1]:
                loop.append([x1, y, 0.0])
            loop.append([x1, yk, 0.0])
            loop.append([x1, *(knee + 0.1 * up)[1:]])
            for x in np.linspace(x1, x0, 7)[:-1]:
                loop.append([x, top[1], top[2]])
            loop.append([x0, top[1], top[2]])
            loop.append([x0, *(knee + 0.1 * up)[1:]])
            loop.append([x0, yk, 0.0])
            for y in np.linspace(yk, y0, 8)[1:-1]:
                loop.append([x0, y, 0.0])
            return np.asarray(loop)

        loops = ([rect_loop(18.0 * i, 18.0 * (i + 1), 0.0, 4.2)
                  for i in range(3)]
                 + [knuckle_loop(18.0 * i, 18.0 * (i + 1))
                    for i in range(3)])
        return [plane_a, plane_b], loops

    def test_contour_loops_keep_plate_interiors(self):
        from ocx_geometry.lscm import _boundary_edges, _build_mesh
        members, loops = self._knuckle_panel_loops()
        cm = _build_mesh(members, tol_m=0.05, hint_pts=loops,
                         require_connected=False)
        assert cm is not None
        bnd = _boundary_edges(cm.F)
        mids = 0.5 * (cm.V[bnd[:, 0]] + cm.V[bnd[:, 1]])
        interior = ((mids[:, 0] > 0.5) & (mids[:, 0] < 53.5)
                    & (mids[:, 1] > 0.5) & (mids[:, 1] < 8.0)
                    & (np.abs(mids[:, 2]) < 1e-6))
        assert int(interior.sum()) == 0, (
            f"{int(interior.sum())} slit edges inside the panel interior")

    def test_stacked_hints_still_carve_without_loop_info(self):
        """Back-compat: a single stacked hint array carries no loop
        structure; the concave hull still carves (documents why the
        renderer must pass per-plate loops)."""
        from ocx_geometry.lscm import _boundary_edges, _build_mesh
        members, loops = self._knuckle_panel_loops()
        cm = _build_mesh(members, tol_m=0.05, hint_pts=np.vstack(loops),
                         require_connected=False)
        assert cm is not None
        bnd = _boundary_edges(cm.F)
        mids = 0.5 * (cm.V[bnd[:, 0]] + cm.V[bnd[:, 1]])
        interior = ((mids[:, 0] > 0.5) & (mids[:, 0] < 53.5)
                    & (mids[:, 1] > 0.5) & (mids[:, 1] < 8.0)
                    & (np.abs(mids[:, 2]) < 1e-6))
        assert int(interior.sum()) > 0


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
    @pytest.fixture
    def folded_chart(self):
        from ocx_geometry.lscm import LscmParam, _ChartMesh
        from ocx_geometry.surfaces import PlaneParam

        members = [
            PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0])),
            PlaneParam(np.array([1.0, 0.0, 0.0]), np.array([-1.0, 0.0, 0.0])),
        ]
        vertices = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [1, 1, 0], [1, 0, 1], [1, 1, 1],
        ], dtype=float)
        faces = np.array([[0, 1, 3], [0, 3, 2], [1, 4, 5], [1, 5, 3]])
        src = []
        for i, v in enumerate(vertices):
            keys = [0, 1] if i in (1, 3) else [0] if i in (0, 2) else [1]
            src.append({k: tuple(members[k].inverse(v[None, :])[0]) for k in keys})
        uv = np.array([[0, 0], [1, 0], [0, 1], [1, 1], [2, 0], [2, 1]])
        return LscmParam(members, _ChartMesh(vertices, faces, src, np.array([0, 0, 1, 1])), uv)

    @pytest.mark.parametrize("with_hole", [False, True])
    def test_tessellation_conforms_to_source_faces(self, folded_chart, with_hole):
        from ocx_geometry.backend import TessellationOptions
        from ocx_geometry.uv_tessellator import UvTessellator

        contour_uv = np.array([[0, 0], [2, 0], [2, 1], [0, 1]])
        holes = [folded_chart.evaluate(np.array([
            [0.75, 0.25], [1.25, 0.25], [1.25, 0.75], [0.75, 0.75],
        ]))] if with_hole else []
        mesh = UvTessellator().tessellate_trimmed_surface(
            "fold", "fold", "plate", folded_chart.evaluate(contour_uv),
            holes, folded_chart, TessellationOptions())
        assert mesh is not None
        triangles = mesh.vertices[mesh.triangles]
        on_bottom = np.isclose(triangles[:, :, 2], 0).all(axis=1)
        on_side = np.isclose(triangles[:, :, 0], 1).all(axis=1)
        assert (on_bottom | on_side).all(), "a triangle bridges the patch seam"
        cross = np.cross(triangles[:, 1] - triangles[:, 0],
                         triangles[:, 2] - triangles[:, 0])
        area = 0.5 * np.linalg.norm(cross, axis=1).sum()
        assert area == pytest.approx(1.75 if with_hole else 2.0)

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
    def test_concave_trim_cells_do_not_overlap_or_cross_boundary(self, monkeypatch):
        import shapely
        from ocx_geometry.lscm import _facet_trimmed
        from ocx_geometry.surfaces import PlaneParam

        hull = shapely.Polygon([
            (0, 0), (8, 0), (8, 8), (0, 8),
            (0, 0.8), (0.2, 0.8), (0.2, 0.2), (0, 0.2),
        ])
        monkeypatch.setattr(shapely, "concave_hull", lambda *args, **kwargs: hull)
        member = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        _, uv, faces = _facet_trimmed(
            member, np.asarray(hull.exterior.coords)[:-1], tol_m=0.05)
        triangles = shapely.polygons(uv[faces])
        domain = shapely.union_all(triangles)
        assert domain.difference(hull).area < 1e-10
        assert hull.difference(domain).area < 1e-10
        assert sum(t.area for t in triangles) == pytest.approx(hull.area)

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
    def test_sparse_straight_contour_covers_plate_interior(self):
        import shapely
        from ocx_geometry.lscm import LscmChart, _ChartMesh
        from ocx_geometry.surfaces import PlaneParam

        member = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        vertices = np.array([[x, y, 0.0] for x in range(13) for y in range(5)])
        faces = []
        for x in range(12):
            for y in range(4):
                a = 5 * x + y
                faces.extend([(a, a + 5, a + 6), (a, a + 6, a + 1)])
        faces = np.asarray(faces)
        src = [{0: tuple(uv)} for uv in member.inverse(vertices)]
        chart = LscmChart(
            [member], _ChartMesh(vertices, faces, src, np.zeros(len(faces), dtype=int)),
            tol_m=0.05)
        contour = np.array([
            [0.5, 0.5, 0], [11.5, 0.5, 0], [11.5, 2.5, 0], [0.5, 2.5, 0],
        ])
        param = chart.param_for(contour)
        assert param is not None
        domain = shapely.union_all(shapely.polygons(param._V[param._F][:, :, :2]))
        assert shapely.box(0.5, 0.5, 11.5, 2.5).difference(domain).area < 1e-10

    def test_wide_plate_with_short_collinear_edges_covers_interior(self):
        """A contour whose nearest-neighbour spacing (short collinear edge
        pieces, as on a cambered deck) is far below the plate width must
        still select the whole interior, not just a ring around its rim."""
        import shapely
        from ocx_geometry.lscm import LscmChart, _ChartMesh
        from ocx_geometry.surfaces import PlaneParam

        member = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        nx, ny = 10, 20
        vertices = np.array([[x, y - 10.0, 0.0]
                             for x in range(nx + 1) for y in range(ny + 1)])
        faces = []
        for x in range(nx):
            for y in range(ny):
                a = (ny + 1) * x + y
                b = a + ny + 1
                faces.extend([(a, b, b + 1), (a, b + 1, a + 1)])
        faces = np.asarray(faces)
        src = [{0: tuple(uv)} for uv in member.inverse(vertices)]
        chart = LscmChart(
            [member],
            _ChartMesh(vertices, faces, src, np.zeros(len(faces), dtype=int)),
            tol_m=0.05)
        contour = np.array([
            [9.75, 6.2, 0], [9.75, 10, 0], [0, 10, 0], [0, 6.2, 0],
            [0, -6.2, 0], [0, -10, 0], [9.75, -10, 0], [9.75, -6.2, 0],
        ])
        param = chart.param_for(contour)
        assert param is not None
        domain = shapely.union_all(shapely.polygons(param._V[param._F][:, :, :2]))
        plate = shapely.Polygon(contour[:, :2])
        assert plate.difference(domain).area < 1e-6

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


class TestHullModelChart:
    """Integration: every plate of the stripped tr05 hull model must get
    a validated LSCM chart (regression for the P12 bridge-through-fin
    failure: the island bridge re-added the exact non-manifold face the
    manifold mask had shaved, leaving a non-injective chart corner)."""

    MODEL = (Path(__file__).parent.parent / "models" / "TR05"
             / "tr05_tc09_nast_hull.3docx")

    @pytest.fixture(scope="class")
    def hull_data(self):
        from ocx_geometry.curves import sample_contour
        from ocx_geometry.lscm import make_lscm_chart
        from ocx_model_core.builders.factory import get_builder
        from ocx_model_core.parsers.parser import OcxParser
        from ocx_render.render import TessellationOptions, _resolve_panel_surfaces

        root = OcxParser().parse(str(self.MODEL))
        vessel = get_builder(root.schema_version).build(root)
        options = TessellationOptions()
        tol = options.tolerance_m
        lr = LengthResolver(vessel.unit_registry)
        panel = next(iter(vessel.panels.values()))
        members = [p for p in
                   (make_param(s, lr, tol)
                    for s in _resolve_panel_surfaces(panel, vessel)) if p]
        contours = {}
        for p in vessel.plates.values():
            c = sample_contour(p.outer_contour, lr, tol,
                               options.snap_tolerance_m)
            if c is not None:
                contours[p.name] = c
        assert len(contours) == 25
        chart = make_lscm_chart(members, tol,
                                np.vstack(list(contours.values())))
        assert chart is not None
        return vessel, options, contours, chart

    @pytest.mark.skipif(not MODEL.exists(),
                        reason="tr05 hull test model not present")
    def test_all_hull_plates_chart(self, hull_data):
        _, _, contours, chart = hull_data
        failed = [n for n, c in sorted(contours.items())
                  if chart.param_for(c) is None]
        assert failed == [], f"plates without a validated chart: {failed}"

    @pytest.mark.skipif(not MODEL.exists(),
                        reason="tr05 hull test model not present")
    def test_hull_charts_have_no_artificial_seam_holes(self, hull_data):
        import shapely

        _, _, contours, chart = hull_data
        holes = {}
        for name, contour in contours.items():
            param = chart.param_for(contour)
            assert param is not None
            domain = shapely.union_all(param._tree.geometries)
            count = sum(len(p.interiors) for p in getattr(domain, "geoms", [domain]))
            if count:
                holes[name] = count
        assert not holes, f"artificial seam holes in chart support: {holes}"

    @pytest.mark.skipif(not MODEL.exists(),
                        reason="tr05 hull test model not present")
    def test_rendered_triangle_interiors_follow_hull(self, hull_data):
        import shapely
        import trimesh
        from ocx_render.render import render_model

        vessel, options, contours, chart = hull_data
        result = render_model(vessel, options)
        plate_meshes = [m for m in result.meshes if m.kind == "plate"]
        assert len(plate_meshes) == 25
        assert not result.skipped
        for mesh in plate_meshes:
            contour = contours[mesh.name]
            param = chart.param_for(contour)
            assert param is not None
            triangles = mesh.vertices[mesh.triangles]
            probes3 = np.vstack([
                triangles.mean(axis=1),
                (triangles[:, 0] + triangles[:, 1]) * 0.5,
                (triangles[:, 1] + triangles[:, 2]) * 0.5,
                (triangles[:, 2] + triangles[:, 0]) * 0.5,
            ])
            distance = trimesh.proximity.closest_point(param._mesh, probes3)[1]
            assert distance.max() < options.tolerance_m, (
                f"{mesh.name}: triangle interiors stray {distance.max():.3f} m")

            centre = contour.mean(axis=0)
            _, axes = np.linalg.eigh((contour - centre).T @ (contour - centre))
            contour2 = (contour - centre) @ axes[:, -2:]
            polygon = shapely.make_valid(shapely.Polygon(contour2))
            vertices2 = (mesh.vertices - centre) @ axes[:, -2:]
            coverage = shapely.union_all(shapely.polygons(vertices2[mesh.triangles]))
            x0, y0, x1, y1 = polygon.bounds
            x, y = np.meshgrid(np.linspace(x0, x1, 100), np.linspace(y0, y1, 30))
            probes2 = shapely.points(np.column_stack([x.ravel(), y.ravel()]))
            inside = shapely.covers(polygon, probes2)
            gaps = shapely.distance(coverage, probes2[inside])
            assert gaps.max() < 2 * options.tolerance_m, (
                f"{mesh.name}: uncovered plate region {gaps.max():.3f} m wide")


def _ropax_seam_members():
    """tr05_tc18 ropax side-shell patches nplcid2522 (flat, triangular:
    the u0 edge collapses to a pole) and nplcid2525 (curved, pole at the
    other end), sharing the diagonal seam (119.03, 7.834)-(134, 10)."""
    def bicubic(pid, rows):
        return IrNurbsSurface(
            id=pid, u_degree=3, v_degree=3,
            u_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
            v_knot_vector=[0, 0, 0, 0, 1, 1, 1, 1],
            control_points=[[pt(*p) for p in row] for row in rows])

    flat = bicubic("nplcid2522", [
        [(134.0, -13.2, 10.0)] * 4,
        [(129.00874, -13.2, 10.0), (129.00712, -13.2, 9.77224),
         (129.0055, -13.2, 9.5445), (129.00388, -13.2, 9.3202)],
        [(124.0175, -13.2, 10.0), (124.01425, -13.2, 9.5445),
         (124.011, -13.2, 9.08898), (124.00776, -13.2, 8.64038)],
        [(119.02623, -13.2, 10.0), (119.02623, -13.2, 9.27454),
         (119.02623, -13.2, 8.54908), (119.02623, -13.2, 7.834)]])
    curved = bicubic("nplcid2525", [
        [(119.02623, -13.2, 7.834)] * 4,
        [(124.02794, -13.152, 7.834), (124.0204, -13.17397, 8.1023),
         (124.0152, -13.17082, 8.3639), (124.00776, -13.2, 8.64038)],
        [(129.02888, -13.0232, 7.834), (129.01924, -13.16227, 8.32263),
         (129.01243, -13.23586, 8.81457), (129.00388, -13.2, 9.3202)],
        [(134.0, -12.55783, 7.834), (134.0, -12.8845, 8.53352),
         (134.0, -13.2, 9.26676), (134.0, -13.2, 10.0)]])
    members = [make_param(s, LR, tol_m=0.05) for s in (flat, curved)]
    assert all(m is not None for m in members)
    return members


class TestRopaxSeamChart:
    """Regression (tr05_tc18 ropax SHELL_S/SHELL_P, plates nplcid2934,
    nplcid2938, nplcid4218, nplcid4222): along this seam the flat patch
    was faceted as a single cell whose seam side, after stitching, became
    a folded fan of 15 m needle triangles.  Plate outlines running along
    the seam jumped between the layers and the trims kept the whole hull
    side or only fragments."""

    def test_outline_across_the_seam_trims_to_its_own_area(self):
        from ocx_geometry.lscm import make_lscm_chart
        from ocx_geometry.mesh_trim import MeshTrimmer
        flat, curved = _ropax_seam_members()
        # a 6 m x 0.8 m outline centred on the seam: the upper half lies
        # on the flat patch, the lower half projected onto the curved one
        x = np.linspace(123.0, 129.0, 61)
        seam = 7.834 + (x - 119.02623) * (10.0 - 7.834) / (134.0 - 119.02623)
        top = np.column_stack([x, np.full_like(x, -13.2), seam + 0.4])
        low = np.column_stack([x, np.full_like(x, -13.2), seam - 0.4])
        low = np.asarray(curved.evaluate(curved.inverse(low)))
        side = lambda p, q: np.linspace(p, q, 9)[1:-1]   # noqa: E731
        ring = np.vstack([low, side(low[-1], top[-1]), top[::-1],
                          side(top[0], low[0])])
        ring[len(low):len(low) + 7] = np.asarray(curved.evaluate(
            curved.inverse(ring[len(low):len(low) + 7])))
        chart = make_lscm_chart([flat, curved], 0.05, [ring])
        assert chart is not None
        out = MeshTrimmer(*chart.mesh, 0.05).trim(ring, [], None)
        assert out is not None
        t = out[0][out[1]]
        kept = 0.5 * np.linalg.norm(np.cross(
            t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]).sum(axis=0))
        want = 0.5 * np.linalg.norm(np.cross(
            ring, np.roll(ring, -1, axis=0)).sum(axis=0))
        assert kept == pytest.approx(want, rel=0.02)
