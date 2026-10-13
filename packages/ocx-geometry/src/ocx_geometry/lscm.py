"""LSCM chart over multi-patch surface collections.

Replaces the developed-chart ``CompositeParam``: all member surfaces are
faceted into one welded triangle mesh with per-vertex back-pointers to
``(member, local uv)``; the mesh is flattened with Least Squares Conformal
Maps into a single metric 2-D chart.  Queries route through the mesh:

- ``inverse``  — closest 3-D triangle -> barycentric -> chart UV
- ``evaluate`` — chart-UV triangle -> barycentric -> source member local uv
  -> exact member evaluation, so points stay on the true surface and
  curvature-driven subdivision refines onto real geometry.

Reference: GeniE ``LSCMParameterizedSurface.cpp`` (DNV, libigl-based).
"""
from __future__ import annotations

import math

import numpy as np
import shapely
import trimesh
from loguru import logger
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.sparse.linalg import factorized, spsolve
from scipy.spatial import cKDTree
from shapely.strtree import STRtree

from ocx_geometry.surfaces import SurfaceParam, _member_fit

_MAX_GRID = 96            # max facet cells per axis per member
_MAX_SCALE_RATIO = 100.0  # reject charts with larger per-triangle scale spread
_MAX_FLIPPED = 0.005      # tolerated fraction of flipped UV triangles
_STITCH_PASSES = 32


class _ChartMesh:
    """Welded facet mesh of all members with per-vertex source params."""

    def __init__(self, V: np.ndarray, F: np.ndarray,
                 src: list[dict[int, tuple[float, float]]],
                 tri_member: np.ndarray) -> None:
        self.V = V                      # (n, 3) vertices, metres
        self.F = F                      # (m, 3) triangle vertex indices
        self.src = src                  # per vertex: {member index: local uv}
        self.tri_member = tri_member    # (m,) member per triangle, -1 = none


def _member_domain(member: SurfaceParam):
    """Intrinsic UV sampling domain (NURBS knot range), or None."""
    du, dv = getattr(member, "du", None), getattr(member, "dv", None)
    if du is not None and dv is not None:
        return (float(du[0]), float(du[1])), (float(dv[0]), float(dv[1]))
    return None


def _facet_member(member: SurfaceParam, dom, tol_m: float):
    """Sample a member on a UV grid -> (pts (n,3), uvs (n,2), faces (m,3))."""
    (u0, u1), (v0, v1) = dom
    su, sv = member.uv_scale()
    edge = member.max_edge_m(tol_m)

    def n_cells(span_m: float) -> int:
        if edge is None or edge <= 0.0:
            return 1                    # flat direction: one cell suffices
        return int(np.clip(math.ceil(span_m / edge), 1, _MAX_GRID))

    nu, nv = n_cells((u1 - u0) * su), n_cells((v1 - v0) * sv)
    us = np.linspace(u0, u1, nu + 1)
    vs = np.linspace(v0, v1, nv + 1)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    uvs = np.column_stack([uu.ravel(), vv.ravel()])
    pts = np.asarray(member.evaluate(uvs), dtype=float)
    faces = []
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            b = (i + 1) * (nv + 1) + j
            faces.append((a, b, b + 1))
            faces.append((a, b + 1, a + 1))
    return pts, uvs, np.asarray(faces, dtype=int)


def _facet_trimmed(member: SurfaceParam, hull_uv: np.ndarray, tol_m: float):
    """Facet an unbounded member (plane, cylinder) clipped to the convex
    hull of its assigned on-surface hint points in member-local UV.  The
    bbox of those points badly overshoots non-rectangular regions (e.g. a
    tapering flat bottom), creating flaps that overlap neighbouring
    members in 3-D and fold the chart."""
    hull_uv = np.asarray(hull_uv, dtype=float)
    if getattr(member, "periodic_u", False):
        # inverse() unwraps u per polyline, so points from different hint
        # runs can land on different 2*pi branches; the hull then becomes
        # a slanted band wrapping the surface. Fold everything onto one
        # branch centred on the circular mean.
        two_pi = 2.0 * np.pi
        ang = hull_uv[:, 0] % two_pi
        centre = math.atan2(np.sin(ang).mean(), np.cos(ang).mean())
        hull_uv = hull_uv.copy()
        hull_uv[:, 0] = centre + (ang - centre + np.pi) % two_pi - np.pi
    mp = shapely.MultiPoint(hull_uv)
    # the member's true region is usually concave (e.g. a flat bottom
    # bounded by the curved bilge chine): a convex hull overshoots onto
    # neighbouring curved members, creating overlapping flaps that can
    # neither be stitched nor welded. Hint contours sample the region
    # boundary densely, so a concave hull follows it closely.
    try:
        hull = shapely.concave_hull(mp, ratio=0.3)
    except Exception:  # noqa: BLE001 — shapely < 2.0 or qhull failure
        hull = mp.convex_hull
    if getattr(hull, "area", 0.0) < 1e-12:
        hull = mp.convex_hull
    if getattr(hull, "area", 0.0) < 1e-12:
        return None                     # degenerate: no 2-D extent
    u0, v0, u1, v1 = hull.bounds
    su, sv = member.uv_scale()
    edge = member.max_edge_m(tol_m)

    def n_cells(span_m: float) -> int:
        if edge is None or edge <= 0.0:
            # flat direction: still use a grid so the hull outline is
            # resolved and duplicate-face removal stays local
            return int(np.clip(math.ceil(span_m / max(20.0 * tol_m, 0.5)),
                               8, _MAX_GRID))
        return int(np.clip(math.ceil(span_m / edge), 1, _MAX_GRID))

    nu, nv = n_cells((u1 - u0) * su), n_cells((v1 - v0) * sv)
    us = np.linspace(u0, u1, nu + 1)
    vs = np.linspace(v0, v1, nv + 1)
    pts2: list[tuple[float, float]] = []
    faces: list[tuple[int, int, int]] = []
    index: dict[tuple[float, float], int] = {}

    def vid(p) -> int:
        key = (round(float(p[0]), 12), round(float(p[1]), 12))
        if key not in index:
            index[key] = len(pts2)
            pts2.append((float(p[0]), float(p[1])))
        return index[key]

    for i in range(nu):
        for j in range(nv):
            cell = shapely.box(us[i], vs[j], us[i + 1], vs[j + 1])
            piece = cell.intersection(hull)
            if piece.is_empty or piece.area < 1e-12:
                continue
            geoms = getattr(piece, "geoms", [piece])
            for g in geoms:
                if not isinstance(g, shapely.Polygon):
                    continue
                ring = np.asarray(g.exterior.coords)[:-1]
                # GEOS does not normalize intersection-output ring
                # orientation: fanning rings as-is yields mixed triangle
                # winding, which breaks the conformal flattening
                area2 = float(
                    (ring[:, 0] * np.roll(ring[:, 1], -1)
                     - np.roll(ring[:, 0], -1) * ring[:, 1]).sum())
                if area2 < 0.0:
                    ring = ring[::-1]
                ids = [vid(p) for p in ring]
                for t in range(1, len(ids) - 1):   # convex piece: fan
                    faces.append((ids[0], ids[t], ids[t + 1]))
    if not faces:
        return None
    uvs = np.asarray(pts2, dtype=float)
    pts = np.asarray(member.evaluate(uvs), dtype=float)
    return pts, uvs, np.asarray(faces, dtype=int)


def _weld(V: np.ndarray, src: list[dict], weld_tol: float):
    """Merge vertices within weld_tol (union-find); src dicts are unioned."""
    pairs = cKDTree(V).query_pairs(weld_tol, output_type="ndarray")
    parent = np.arange(len(V))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in pairs:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    root = np.array([find(i) for i in range(len(V))])
    uniq, remap = np.unique(root, return_inverse=True)
    out_src: list[dict] = [{} for _ in uniq]
    for i, r in enumerate(remap):
        out_src[r].update(src[i])
    return V[uniq], out_src, remap


def _split_pinch_vertices(
        V: np.ndarray, F: np.ndarray,
        src: list[dict]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Duplicate vertices whose incident faces form more than one
    edge-connected fan (bowtie/pinch).  A pinch breaks disk topology:
    the boundary walk passes through the vertex twice, so the pinned
    Tutte boundary is non-convex there and both Tutte and LSCM can
    produce fold-free yet non-injective (wrapped) charts.  Splitting
    the vertex per fan restores disk topology without moving geometry;
    face order is preserved so per-face bookkeeping stays aligned."""
    F = F.copy()
    newV = [V]
    newsrc = list(src)
    nv = len(V)
    incident: dict[int, list[int]] = {}
    for fi, tri in enumerate(F):
        for v in tri:
            incident.setdefault(int(v), []).append(fi)
    for v, fis in incident.items():
        if len(fis) < 2:
            continue
        # two incident faces belong to the same fan iff they share an
        # edge through v, i.e. they share another vertex u with (v,u)
        # an edge of both
        parent = {fi: fi for fi in fis}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        by_other: dict[int, int] = {}
        for fi in fis:
            for u in F[fi]:
                u = int(u)
                if u == v:
                    continue
                if u in by_other:
                    ra, rb = find(by_other[u]), find(fi)
                    if ra != rb:
                        parent[ra] = rb
                else:
                    by_other[u] = fi
        groups: dict[int, list[int]] = {}
        for fi in fis:
            groups.setdefault(find(fi), []).append(fi)
        if len(groups) < 2:
            continue
        fans = sorted(groups.values(), key=len, reverse=True)
        for fan in fans[1:]:            # largest fan keeps the original
            for fi in fan:
                F[fi][F[fi] == v] = nv
            newV.append(V[v:v + 1])
            newsrc.append(dict(src[v]))
            nv += 1
    if nv == len(V):
        return V, F, src
    return np.vstack(newV), F, newsrc


def _boundary_edges(F: np.ndarray) -> np.ndarray:
    """Directed edges that belong to exactly one triangle."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(e, axis=1)
    _, idx, cnt = np.unique(key, axis=0, return_index=True,
                            return_counts=True)
    return e[idx[cnt == 1]]


def _stitch(V: np.ndarray, F: np.ndarray, src: list[dict],
            snap_tol: float) -> np.ndarray:
    """Split triangles whose boundary edge passes through another boundary
    vertex — the T-junctions left where member seams were sampled at
    different densities.  The inserted vertex inherits an interpolated
    local-uv source for every member shared by the edge endpoints."""
    for _ in range(_STITCH_PASSES):
        bnd = _boundary_edges(F)
        if len(bnd) == 0:
            break
        bverts = np.unique(bnd)
        tree = cKDTree(V[bverts])
        splits: dict[tuple[int, int], tuple[int, float]] = {}
        for a, b in bnd:
            key = (min(a, b), max(a, b))
            d = V[b] - V[a]
            seg = float(np.linalg.norm(d))
            if seg < 1e-12:
                continue
            mid = 0.5 * (V[a] + V[b])
            best = None
            for ci in tree.query_ball_point(mid, 0.5 * seg + snap_tol):
                w = int(bverts[ci])
                if w == a or w == b:
                    continue
                t = float((V[w] - V[a]) @ d) / (seg * seg)
                if not 1e-6 < t < 1.0 - 1e-6:
                    continue
                gap = float(np.linalg.norm(V[a] + t * d - V[w]))
                if gap > snap_tol:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, w, t)
            if best is not None:
                t = best[2] if (a, b) == key else 1.0 - best[2]
                splits[key] = (best[1], t)
        if not splits:
            break
        out = []
        for f in F:
            fl = [int(f[0]), int(f[1]), int(f[2])]
            done = False
            for e in range(3):
                a, b = fl[e], fl[(e + 1) % 3]
                key = (min(a, b), max(a, b))
                if key not in splits:
                    continue
                w, t = splits[key]
                if (a, b) != (key[0], key[1]):
                    t = 1.0 - t          # edge stored in opposite direction
                c = fl[(e + 2) % 3]
                out.append((a, w, c))
                out.append((w, b, c))
                for k, lua in src[a].items():
                    if k in src[b] and k not in src[w]:
                        la = np.asarray(lua, dtype=float)
                        lb = np.asarray(src[b][k], dtype=float)
                        luv = la + t * (lb - la)
                        src[w][k] = (float(luv[0]), float(luv[1]))
                done = True
                break                    # one split per face per pass
            if not done:
                out.append(tuple(fl))
        F = np.asarray(out, dtype=int)
    return F


def _zip_boundaries(V: np.ndarray, F: np.ndarray, src: list[dict],
                    tm: np.ndarray, snap_tol: float):
    """Weld boundary vertices across DISCONNECTED components.  Where two
    member sheets sample a shared seam at different densities the sides
    are offset parallel edge chains: no vertex crosses an opposing edge,
    so T-junction stitching cannot close them and the sheets stay
    separate components.  Merging facing boundary vertices of different
    components zips the seam; positions shift by at most ``snap_tol``.
    Merges never happen inside one component, so good sheets keep their
    slits and are not pinched.  Returns ``(F, tri_member)``."""
    for _ in range(4):
        rows = np.concatenate([F[:, 0], F[:, 1], F[:, 2]])
        cols = np.concatenate([F[:, 1], F[:, 2], F[:, 0]])
        adj = coo_matrix((np.ones(len(rows)), (rows, cols)),
                         shape=(len(V), len(V)))
        _, labels = connected_components(adj, directed=False)
        bnd = _boundary_edges(F)
        if len(bnd) == 0:
            return F, tm
        bv = np.unique(bnd)
        pairs = cKDTree(V[bv]).query_pairs(snap_tol, output_type="ndarray")
        if len(pairs) == 0:
            return F, tm
        a = bv[pairs[:, 0]]
        b = bv[pairs[:, 1]]
        cross = labels[a] != labels[b]
        if not cross.any():
            return F, tm
        a, b = a[cross], b[cross]
        parent = np.arange(len(V))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        d = np.linalg.norm(V[a] - V[b], axis=1)
        for pi in np.argsort(d):
            ra, rb = find(int(a[pi])), find(int(b[pi]))
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
        root = np.array([find(i) for i in range(len(V))])
        for i, r in enumerate(root):
            if r != i:
                src[r].update(src[i])
        F = root[F]
        keep = ((F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2])
                & (F[:, 2] != F[:, 0]))
        F, tm = F[keep], tm[keep]
        if len(F) == 0:
            return F, tm
    return F, tm


def _build_mesh(members: list[SurfaceParam], tol_m: float,
                hint_pts: np.ndarray | None,
                require_connected: bool = True) -> _ChartMesh | None:
    weld_tol = max(1e-6, 0.1 * tol_m)
    on_tol = max(10.0 * weld_tol, tol_m)
    # Assign each hint point to its best-fitting member (ties shared):
    # at tangent seams (e.g. bottom plane / bilge cylinder) near-seam arc
    # points lie within on_tol of the plane too and would otherwise
    # inflate its trim region into an overhanging flap.
    fits: list | None = None
    res = min_res = None
    if hint_pts is not None and len(hint_pts) >= 3:
        hint_pts = np.asarray(hint_pts, dtype=float)
        fits = [_member_fit(m, hint_pts) for m in members]
        res = np.full((len(members), len(hint_pts)), np.inf)
        for i, f in enumerate(fits):
            if f is not None:
                res[i] = f[2]
        min_res = res.min(axis=0)
    # Facet intrinsically-bounded members (NURBS) first: they are the
    # authoritative geometry that trimmed unbounded members defer to.
    pieces: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for k, member in enumerate(members):
        dom = _member_domain(member)
        if dom is None:
            continue
        try:
            pts, uvs, faces = _facet_member(member, dom, tol_m)
        except Exception:  # noqa: BLE001 — member disqualifies itself
            continue
        if np.isfinite(pts).all():
            pieces[k] = (pts, uvs, faces)
    ref = None
    if pieces:
        off, rv, rf = 0, [], []
        for pts, _, faces in pieces.values():
            rv.append(pts)
            rf.append(faces + off)
            off += len(pts)
        ref = trimesh.Trimesh(np.vstack(rv), np.vstack(rf), process=False)
    # Unbounded members (planes, cylinders): facet the convex hull of
    # their assigned hint points, then drop faces that duplicate
    # intrinsic geometry — coincident double sheets fold the chart.
    dup_tol = max(2.0 * weld_tol, 0.5 * tol_m)
    for k, member in enumerate(members):
        if k in pieces or _member_domain(member) is not None:
            continue
        if fits is None or fits[k] is None:
            continue
        on = (res[k] <= on_tol) & ((res[k] <= min_res + 1e-9)
                                   | (res[k] <= weld_tol))
        if int(on.sum()) < 3:
            continue
        try:
            out = _facet_trimmed(member, fits[k][0][on], tol_m)
        except Exception:  # noqa: BLE001 — member disqualifies itself
            continue
        if out is None:
            continue
        pts, uvs, faces = out
        if not np.isfinite(pts).all():
            continue
        if ref is not None and len(faces):
            dv = trimesh.proximity.closest_point(ref, pts)[1]
            cent = pts[faces].mean(axis=1)
            dc = trimesh.proximity.closest_point(ref, cent)[1]
            drop = (dv[faces] < dup_tol).all(axis=1) & (dc < dup_tol)
            faces = faces[~drop]
            if len(faces) == 0:
                continue
        pieces[k] = (pts, uvs, faces)
    if not pieces:
        logger.debug("LSCM: no facetable members")
        return None
    pts_all, src_all, faces_all = [], [], []
    offset = 0
    for k in sorted(pieces):
        pts, uvs, faces = pieces[k]
        pts_all.append(pts)
        src_all.extend({k: (float(u), float(v))} for u, v in uvs)
        faces_all.append(faces + offset)
        offset += len(pts)
    V = np.vstack(pts_all)
    F = np.vstack(faces_all)
    V, src, remap = _weld(V, src_all, weld_tol)
    F = remap[F]
    # drop degenerate triangles produced by welding before stitching, so
    # collapsed faces cannot mask genuine boundary edges from the stitcher
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])]
    if len(F):
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        F = F[np.linalg.norm(n, axis=1) > 1e-14]
    # snap: half the tolerance band — seam edges sampled at different
    # densities deviate by the chord sag of the coarser side
    F = _stitch(V, F, src, max(weld_tol, 0.5 * tol_m))
    # drop degenerate triangles
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])]
    if len(F):
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        F = F[np.linalg.norm(n, axis=1) > 1e-14]
    if len(F):
        # welding + stitching can leave exact duplicate faces, which make
        # their edges non-manifold and break the boundary walk
        _, idx = np.unique(np.sort(F, axis=1), axis=0, return_index=True)
        F = F[np.sort(idx)]
    if len(F) == 0:
        logger.debug("LSCM: empty mesh")
        return None
    used = np.unique(F)
    if require_connected:
        # the chart must be a single connected component
        rows = np.concatenate([F[:, 0], F[:, 1], F[:, 2]])
        cols = np.concatenate([F[:, 1], F[:, 2], F[:, 0]])
        adj = coo_matrix((np.ones(len(rows)), (rows, cols)),
                         shape=(len(V), len(V)))
        _, labels = connected_components(adj, directed=False)
        if len(np.unique(labels[used])) > 1:
            logger.debug("LSCM: members do not form a connected mesh")
            return None
    # drop unused vertices and make the winding consistent
    remap2 = -np.ones(len(V), dtype=int)
    remap2[used] = np.arange(len(used))
    V, src = V[used], [src[i] for i in used]
    F = remap2[F]
    mesh = trimesh.Trimesh(V, F, process=False)
    trimesh.repair.fix_normals(mesh)
    F = np.asarray(mesh.faces, dtype=int)
    return _ChartMesh(V, F, src, _tri_members(F, src))


def _tri_members(F: np.ndarray, src: list[dict]) -> np.ndarray:
    """Per-triangle source member: one present at all three corners."""
    tri_member = np.full(len(F), -1, dtype=int)
    for i, f in enumerate(F):
        common = set(src[f[0]]) & set(src[f[1]]) & set(src[f[2]])
        if common:
            tri_member[i] = min(common)
    return tri_member


def _longest_boundary_loop(bnd: np.ndarray) -> list[int] | None:
    """Longest closed loop among the directed boundary edges.

    Walks edges (not a vertex successor map): at pinch vertices — boundary
    vertices with several outgoing boundary edges — a successor map
    overwrites forks and fragments the outer boundary into tiny loops."""
    out: dict[int, list[int]] = {}
    for i, (a, b) in enumerate(bnd):
        out.setdefault(int(a), []).append(i)
    used = np.zeros(len(bnd), dtype=bool)
    best: list[int] | None = None
    for i0 in range(len(bnd)):
        if used[i0]:
            continue
        loop: list[int] = []
        i = i0
        start = int(bnd[i0][0])
        while True:
            used[i] = True
            loop.append(int(bnd[i][0]))
            v = int(bnd[i][1])
            if v == start:
                if best is None or len(loop) > len(best):
                    best = loop
                break
            nxt = next((j for j in out.get(v, []) if not used[j]), None)
            if nxt is None:
                break                    # open chain, not a loop
            i = nxt
    return best


def _lscm_uv(V: np.ndarray, F: np.ndarray) -> np.ndarray | None:
    """Flatten the mesh with LSCM: minimize conformal energy
    x' (L_flat - 2A) x with two pinned boundary vertices.
    x = [u_0..u_{n-1}, v_0..v_{n-1}]."""
    n = len(V)
    i0, i1, i2 = F[:, 0], F[:, 1], F[:, 2]

    def cot(a, b):
        cr = np.linalg.norm(np.cross(a, b), axis=1)
        return (a * b).sum(axis=1) / np.maximum(cr, 1e-15)

    e0, e1, e2 = V[i2] - V[i1], V[i0] - V[i2], V[i1] - V[i0]
    c0, c1, c2 = cot(e2, -e1), cot(e0, -e2), cot(e1, -e0)
    rows = np.concatenate([i1, i2, i2, i0, i0, i1])
    cols = np.concatenate([i2, i1, i0, i2, i1, i0])
    vals = 0.5 * np.concatenate([c0, c0, c1, c1, c2, c2])
    W = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    L = diags(np.asarray(W.sum(axis=1)).ravel()) - W

    bnd = _boundary_edges(F)
    if len(bnd) < 2:
        return None
    ar, ac, av = [], [], []
    for a, b in bnd:                     # x'Ax = sum 0.5 (u_a v_b - u_b v_a)
        ar += [a, n + b, b, n + a]
        ac += [n + b, a, n + a, b]
        av += [0.25, 0.25, -0.25, -0.25]
    A = coo_matrix((av, (ar, ac)), shape=(2 * n, 2 * n)).tocsr()
    Q = (bmat([[L, None], [None, L]]) - 2.0 * A).tocsr()

    loop = _longest_boundary_loop(bnd)
    if loop is None or len(loop) < 2:
        return None
    # pin the two most mutually distant loop vertices: badly separated
    # pins let the conformal solution wrap around a boundary point
    # (non-injective yet fold-free)
    pts = V[loop]
    a = int(np.argmax(np.linalg.norm(pts - pts[0], axis=1)))
    b = int(np.argmax(np.linalg.norm(pts - pts[a], axis=1)))
    p0, p1 = loop[a], loop[b]
    fixed = np.array([p0, p1, n + p0, n + p1])
    xb = np.array([0.0, 1.0, 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * n), fixed)
    rhs = -Q[free][:, fixed] @ xb
    xf = spsolve(Q[free][:, free].tocsc(), rhs)
    x = np.empty(2 * n)
    x[fixed], x[free] = xb, xf
    if not np.isfinite(x).all():
        return None
    return np.column_stack([x[:n], x[n:]])


class LscmParam(SurfaceParam):
    """Metric LSCM chart over a welded multi-member facet mesh."""

    def __init__(self, members: list[SurfaceParam], cm: _ChartMesh,
                 uv: np.ndarray) -> None:
        self.members = members
        self._V, self._F = cm.V, cm.F
        self._src, self._tri_member = cm.src, cm.tri_member
        self._uv = uv
        self._mesh = trimesh.Trimesh(self._V, self._F, process=False)
        self._tree = STRtree([shapely.Polygon(t) for t in uv[self._F]])

    def _locate_uv(self, uv):
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        tid = np.asarray(self._tree.nearest(
            [shapely.Point(p) for p in uv]), dtype=int)
        tri2 = self._uv[self._F[tid]]

        def pad(a):
            return np.concatenate(
                [a, np.zeros(a.shape[:-1] + (1,))], axis=-1)

        bary = trimesh.triangles.points_to_barycentric(pad(tri2), pad(uv))
        bary = np.clip(np.nan_to_num(bary, nan=1.0 / 3.0,
                                     posinf=1.0, neginf=0.0), 0.0, None)
        bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-300)
        return tid, bary

    def _source_eval(self, tid, bary, fn, fallback):
        """fn(member, local_uv) per point grouped by source member;
        rows stay on ``fallback`` where no source exists or fn fails."""
        corners = self._F[tid]
        ks = self._tri_member[tid]
        out = np.array(fallback, dtype=float, copy=True)
        for k in np.unique(ks[ks >= 0]):
            sel = np.nonzero(ks == k)[0]
            luv = np.array([[self._src[c][k] for c in corners[i]]
                            for i in sel])
            local = np.einsum("ij,ijk->ik", bary[sel], luv)
            try:
                val = np.asarray(fn(self.members[k], local), dtype=float)
            except Exception:  # noqa: BLE001 — keep the mesh fallback
                continue
            good = np.isfinite(val).all(axis=1)
            out[sel[good]] = val[good]
        return out

    def evaluate(self, uv):
        tid, bary = self._locate_uv(uv)
        fallback = np.einsum("ij,ijk->ik", bary, self._V[self._F[tid]])
        return self._source_eval(tid, bary,
                                 lambda m, luv: m.evaluate(luv), fallback)

    def inverse(self, pts):
        pts = np.atleast_2d(np.asarray(pts, dtype=float))
        closest, _, tid = trimesh.proximity.closest_point(self._mesh, pts)
        bary = trimesh.triangles.points_to_barycentric(
            self._V[self._F[tid]], np.asarray(closest, dtype=float))
        bary = np.clip(np.nan_to_num(bary, nan=1.0 / 3.0,
                                     posinf=1.0, neginf=0.0), 0.0, None)
        bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-300)
        return np.einsum("ij,ijk->ik", bary, self._uv[self._F[tid]])

    def normals(self, uv):
        tid, bary = self._locate_uv(uv)
        fallback = np.asarray(self._mesh.face_normals)[tid]
        n = self._source_eval(tid, bary,
                              lambda m, luv: m.normals(luv), fallback)
        flip = (n * fallback).sum(axis=1) < 0.0   # orient with mesh winding
        n[flip] *= -1.0
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True),
                              1e-15)

    def max_edge_m(self, tol_m):
        edges = [e for e in (m.max_edge_m(tol_m) for m in self.members)
                 if e is not None]
        return min(edges) if edges else None


def _apply_gates(cm: _ChartMesh, uv: np.ndarray,
                 scale_gate: bool = True,
                 reject: bool = True) -> np.ndarray | None:
    """Quality gates and metric rescale for a flattened chart mesh.
    Mutates ``cm`` to drop UV-collapsed triangles.  Returns metric UV
    coordinates or None when the flattening is unusable.  With
    ``reject=False`` bad triangles are only dropped, never fatal — for
    fallback paths whose output is validated functionally anyway."""
    tri3 = cm.V[cm.F]
    a3 = 0.5 * np.linalg.norm(
        np.cross(tri3[:, 1] - tri3[:, 0], tri3[:, 2] - tri3[:, 0]),
        axis=1)
    t2 = uv[cm.F]
    a2s = 0.5 * ((t2[:, 1, 0] - t2[:, 0, 0])
                 * (t2[:, 2, 1] - t2[:, 0, 1])
                 - (t2[:, 2, 0] - t2[:, 0, 0])
                 * (t2[:, 1, 1] - t2[:, 0, 1]))
    ok = (np.abs(a2s) > 1e-18) & (a3 > 1e-18)
    if not ok.any():
        logger.debug("LSCM: chart collapsed")
        return None
    if not ok.all():
        # drop UV-collapsed triangles: they would bypass the quality
        # gates yet yield NaN barycentrics on queries
        cm.F, cm.tri_member = cm.F[ok], cm.tri_member[ok]
        a3, a2s = a3[ok], a2s[ok]
        ok = np.ones(len(cm.F), dtype=bool)
    maj = 1.0 if a2s.sum() >= 0.0 else -1.0
    flipped = np.sign(a2s) != maj
    if flipped.any():
        # Tiny flipped slivers appear where nearly-coincident member
        # sheets weld; they carry negligible 3-D area and do not affect
        # injectivity.  Reject only genuine folds (noticeable flipped
        # area), otherwise drop the slivers from the chart.
        frac = float(a3[flipped].sum()) / max(float(a3.sum()), 1e-300)
        if reject and frac > _MAX_FLIPPED:
            logger.debug("LSCM: {:.2%} flipped UV area", frac)
            return None
        keepf = ~flipped
        if not keepf.any():
            logger.debug("LSCM: chart collapsed")
            return None
        cm.F, cm.tri_member = cm.F[keepf], cm.tri_member[keepf]
        a3, a2s = a3[keepf], a2s[keepf]
    ratio = a3 / np.abs(a2s)
    if scale_gate:
        med = float(np.median(ratio))
        spread = math.sqrt(_MAX_SCALE_RATIO)
        outlier = (ratio > med * spread) | (ratio < med / spread)
        if outlier.any():
            # Same policy as flips: needle UV slivers at weld seams give
            # extreme per-triangle scale; tolerate them when their 3-D
            # area is negligible, reject genuine broad distortion.
            frac = float(a3[outlier].sum()) / max(float(a3.sum()), 1e-300)
            if reject and frac > _MAX_FLIPPED:
                logger.debug(
                    "LSCM: per-triangle scale spread too large "
                    "({:.2%} of area)", frac)
                return None
            keepf = ~outlier
            if not keepf.any():
                logger.debug("LSCM: chart collapsed")
                return None
            cm.F, cm.tri_member = cm.F[keepf], cm.tri_member[keepf]
            a3, a2s, ratio = a3[keepf], a2s[keepf], ratio[keepf]
    return uv * math.sqrt(float(np.median(ratio)))


def _flatten_gates(cm: _ChartMesh) -> np.ndarray | None:
    """LSCM-flatten a chart mesh, apply quality gates and metric rescale.
    Mutates ``cm`` to drop UV-collapsed triangles.  Returns metric UV
    coordinates or None when the flattening is unusable."""
    uv = _lscm_uv(cm.V, cm.F)
    if uv is None:
        logger.debug("LSCM: flattening failed")
        return None
    return _apply_gates(cm, uv, scale_gate=True)


def _tutte_uv(V: np.ndarray, F: np.ndarray) -> np.ndarray | None:
    """Uniform-weight Tutte embedding: the outer boundary loop is pinned
    to a circle (arc length proportional to 3-D edge length) and interior
    vertices solve a positive-weight Laplace system. Convex boundary +
    positive weights give an injective map on disk topology (Floater) at
    the cost of metric distortion — a robust fallback where conformal
    flattening folds or wraps."""
    bnd = _boundary_edges(F)
    if len(bnd) < 3:
        return None
    loop = _longest_boundary_loop(bnd)
    if loop is None or len(loop) < 3:
        return None
    n = len(V)
    P = V[loop]
    seg = np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)
    total = float(seg.sum())
    if total <= 0.0:
        return None
    theta = 2.0 * np.pi * np.concatenate(
        [[0.0], np.cumsum(seg)[:-1]]) / total
    r = total / (2.0 * np.pi)
    buv = np.column_stack([r * np.cos(theta), r * np.sin(theta)])
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.unique(np.sort(e, axis=1), axis=0)
    W = coo_matrix(
        (np.ones(2 * len(e)),
         (np.concatenate([e[:, 0], e[:, 1]]),
          np.concatenate([e[:, 1], e[:, 0]]))), shape=(n, n)).tocsr()
    L = diags(np.asarray(W.sum(axis=1)).ravel()) - W
    fixed = np.asarray(loop, dtype=int)
    free = np.setdiff1d(np.arange(n), fixed)
    uv = np.empty((n, 2))
    uv[fixed] = buv
    if len(free):
        rhs = -L[free][:, fixed] @ buv
        try:
            solve = factorized(L[free][:, free].tocsc())
            uv[free, 0] = solve(np.ascontiguousarray(rhs[:, 0]))
            uv[free, 1] = solve(np.ascontiguousarray(rhs[:, 1]))
        except RuntimeError:            # singular: loop misses a component
            return None
    if not np.isfinite(uv).all():
        return None
    return uv


def _manifold_mask(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Keep at most the two largest-area faces per edge.  Overlapping
    member sheets weld into non-manifold fins; a single fin triangle
    breaks the boundary-loop walk and couples distant sheets in the
    conformal system, folding the whole chart."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e.sort(axis=1)
    _, inv, cnt = np.unique(e, axis=0, return_inverse=True,
                            return_counts=True)
    keep = np.ones(len(F), dtype=bool)
    bad = np.nonzero(cnt > 2)[0]
    if len(bad) == 0:
        return keep
    tri3 = V[F]
    area = 0.5 * np.linalg.norm(
        np.cross(tri3[:, 1] - tri3[:, 0], tri3[:, 2] - tri3[:, 0]),
        axis=1)
    face_of = np.tile(np.arange(len(F)), 3)
    for ei in bad:
        faces = np.unique(face_of[inv == ei])
        order = faces[np.argsort(area[faces])[::-1]]
        keep[order[2:]] = False
    return keep


def _face_components(F: np.ndarray) -> np.ndarray:
    """Connected-component label per face (faces sharing an edge)."""
    parent = np.arange(len(F))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[tuple[int, int], int] = {}
    for fi, f in enumerate(F):
        a, b, c = int(f[0]), int(f[1]), int(f[2])
        for e in ((a, b), (b, c), (c, a)):
            key = (min(e), max(e))
            o = owner.get(key)
            if o is None:
                owner[key] = fi
            else:
                ra, rb = find(fi), find(o)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return np.array([find(i) for i in range(len(F))])


class LscmChart:
    """Per-panel chart mesh that flattens plate-local submeshes on demand.

    A single conformal flattening of a whole panel (e.g. one hull side)
    carries exponential scale variation wherever the surface has Gaussian
    curvature — distant regions collapse below floating-point resolution
    and the quality gates rightly reject the chart.  Flattening only the
    mesh neighbourhood of one plate contour keeps every chart small and
    near-developable, so it stays injective and metric."""

    def __init__(self, members: list[SurfaceParam], cm: _ChartMesh,
                 tol_m: float) -> None:
        self.members = members
        self._cm = cm
        self._tol = tol_m
        self._cent = cm.V[cm.F].mean(axis=1)
        self._ctree = cKDTree(self._cent)
        self._adj = self._face_adjacency()

    def _face_adjacency(self):
        """Sparse face-adjacency graph weighted by centroid distance."""
        F = self._cm.F
        owner: dict[tuple[int, int], int] = {}
        rows, cols, vals = [], [], []
        for fi, f in enumerate(F):
            a, b, c = int(f[0]), int(f[1]), int(f[2])
            for e in ((a, b), (b, c), (c, a)):
                key = (min(e), max(e))
                o = owner.get(key)
                if o is None:
                    owner[key] = fi
                elif o != fi:
                    w = float(np.linalg.norm(self._cent[fi]
                                             - self._cent[o]))
                    rows.append(fi)
                    cols.append(o)
                    vals.append(max(w, 1e-12))
        n = len(F)
        return coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()

    def _contour_radius(self, contour: np.ndarray) -> float:
        """Local region radius: the plate's across-width estimated as the
        max over contour samples of the distance to the far side of the
        contour ring (points at least an eighth of the ring away), capped
        by the contour's second principal extent.  The ring estimate
        degrades on non-uniformly sampled contours (straight edges carry
        few samples, so index distance is not arc distance) and can
        return the plate length instead of its width; an oversized ball
        drags half the hull side into the submesh, whose flattening then
        collapses the plate's own region below resolution."""
        n = len(contour)
        step = max(1, n // 64)
        si = np.arange(0, n, step)
        d = np.linalg.norm(contour[si][:, None, :] - contour[None, :, :],
                           axis=2)
        ring = np.abs(np.arange(n)[None, :] - si[:, None])
        ring = np.minimum(ring, n - ring)
        d[ring < max(1, n // 8)] = np.inf
        width = d.min(axis=1)
        width = width[np.isfinite(width)]
        w = float(width.max()) if len(width) else 0.0
        c = contour - contour.mean(axis=0)
        ext = 4.0 * np.sqrt(np.linalg.eigvalsh(c.T @ c / len(c)))
        if ext[-2] > 0.0:               # second principal extent
            w = min(w, float(ext[-2]))
        return max(10.0 * self._tol, 0.75 * w)

    def param_for(self, contour: np.ndarray) -> LscmParam | None:
        """Metric chart over the submesh around one plate contour."""
        try:
            contour = np.asarray(contour, dtype=float)
            if contour.ndim != 2 or len(contour) < 3:
                return None
            radius = self._contour_radius(contour)
            # geodesic ball: grow along face adjacency from the faces
            # nearest the contour. A Euclidean ball catches geodesically
            # far faces (e.g. the opposite side of the bow) as separate
            # components; LSCM pins live in one component and unpinned
            # components collapse in UV, silently losing coverage.
            step = contour[:: max(1, len(contour) // 128)]
            _, seeds = self._ctree.query(step)
            seeds = np.unique(seeds)
            sub_f = sel = None
            for _ in range(4):
                dist = dijkstra(self._adj, directed=False, indices=seeds,
                                limit=radius, min_only=True)
                sel = np.nonzero(np.isfinite(dist))[0]
                if len(sel) == 0:
                    return None
                sub_f = self._cm.F[sel]
                comp = _face_components(sub_f)
                # keep every component that holds a seed face: a plate
                # can span sheets that only meet across an open member
                # seam — they are zipped together below
                pos = np.searchsorted(sel, seeds)
                keep = np.isin(comp, np.unique(comp[pos]))
                sub_f, sel = sub_f[keep], sel[keep]
                if len(np.unique(comp[keep])) == 1:
                    break
                # several islands: the ball may only cover an annulus
                # around the contour — widen it to fill the interior
                radius *= 1.3
            # overlapping-sheet fins make the submesh non-manifold,
            # which folds the conformal flattening; shave them before
            # bridging — the mask can cut the very face that connects
            # two sheets, so connectivity repair must come after it
            keep = _manifold_mask(self._cm.V, sub_f)
            banned = sel[~keep]
            sub_f, sel = sub_f[keep], sel[keep]
            if len(sub_f) == 0:
                return None
            comp = _face_components(sub_f)
            labels, counts = np.unique(comp, return_counts=True)
            if len(labels) > 1:
                # the ball or the fin shave can slice the chart between
                # sheets that are edge-connected only through a distant
                # or non-manifold seam (tangent contact sampled
                # sparsely): bridge each island to the dominant
                # component along the full-mesh shortest face path
                # instead of widening the ball further
                main = labels[int(np.argmax(counts))]
                # route bridges around the shaved fin faces: the
                # unrestricted shortest path happily runs through the
                # very face the manifold shave removed, restoring a
                # non-manifold edge in a submesh that is now single-
                # component — so the zip-stage cleanup never runs and
                # the flattening loses injectivity exactly there
                adj = self._adj
                if len(banned):
                    mask = np.ones(adj.shape[0])
                    mask[banned] = 0.0
                    d = diags(mask)
                    adj = (d @ adj @ d).tocsr()
                    adj.eliminate_zeros()
                dist2, pred, _srcs = dijkstra(
                    adj, directed=False, indices=sel[comp == main],
                    min_only=True, return_predecessors=True)
                full = None         # lazy fallback over the full graph
                bridge: set[int] = set()
                for lbl in labels:
                    if lbl == main:
                        continue
                    isl = sel[comp == lbl]
                    d2, pr = dist2, pred
                    fin = isl[np.isfinite(d2[isl])]
                    if len(fin) == 0 and adj is not self._adj:
                        # island reachable only through a fin: a
                        # non-manifold bridge beats losing coverage
                        if full is None:
                            full = dijkstra(
                                self._adj, directed=False,
                                indices=sel[comp == main], min_only=True,
                                return_predecessors=True)
                        d2, pr = full[0], full[1]
                        fin = isl[np.isfinite(d2[isl])]
                    if len(fin) == 0:
                        continue
                    f = int(fin[np.argmin(d2[fin])])
                    while f >= 0 and f not in bridge:
                        bridge.add(f)
                        f = int(pr[f])
                if bridge:
                    sel = np.unique(np.concatenate(
                        [sel, np.fromiter(bridge, dtype=int)]))
                    sub_f = self._cm.F[sel]
            used = np.unique(sub_f)
            remap = -np.ones(len(self._cm.V), dtype=int)
            remap[used] = np.arange(len(used))
            subV = self._cm.V[used]
            subF = remap[sub_f]
            # deep-copy: zipping merges src dicts and must not pollute
            # the shared panel chart across plates
            sub_src = [dict(self._cm.src[i]) for i in used]
            sub_tm = self._cm.tri_member[sel]
            if len(np.unique(_face_components(subF))) > 1:
                # zip sheets across open seams, then keep the dominant
                # component: LSCM is singular on face-disconnected or
                # pinch-connected meshes (independent similarity per
                # sheet), so face connectivity is required.  Zipping
                # merges facing boundary vertices, which alone yields
                # only vertex (pinch) connectivity where the seam chains
                # are sampled at different densities; T-junction
                # stitching then splits edges through the merged
                # vertices, turning them into shared edges.
                for _ in range(4):
                    subF, sub_tm = _zip_boundaries(subV, subF, sub_src,
                                                   sub_tm, 4.0 * self._tol)
                    if len(subF) == 0:
                        return None
                    if len(np.unique(_face_components(subF))) == 1:
                        break
                    subF = _stitch(subV, subF, sub_src, 4.0 * self._tol)
                    # stitching rebuilds the face list: realign members
                    sub_tm = _tri_members(subF, sub_src)
                    if len(np.unique(_face_components(subF))) == 1:
                        break
                comp = _face_components(subF)
                labels, counts = np.unique(comp, return_counts=True)
                if len(labels) > 1:
                    keep = comp == labels[int(np.argmax(counts))]
                    subF, sub_tm = subF[keep], sub_tm[keep]
                # zip merges shift vertices by up to its snap tolerance:
                # collinear (zero-area) triangles and duplicate faces
                # appear along the closed seam. Their cotangents blow up
                # and make the conformal system exactly singular.
                if len(subF):
                    n = np.cross(subV[subF[:, 1]] - subV[subF[:, 0]],
                                 subV[subF[:, 2]] - subV[subF[:, 0]])
                    good = np.linalg.norm(n, axis=1) > 1e-14
                    subF, sub_tm = subF[good], sub_tm[good]
                if len(subF):
                    _, idx = np.unique(np.sort(subF, axis=1), axis=0,
                                       return_index=True)
                    idx = np.sort(idx)
                    subF, sub_tm = subF[idx], sub_tm[idx]
                    comp = _face_components(subF)
                    labels, counts = np.unique(comp, return_counts=True)
                    if len(labels) > 1:
                        keep = comp == labels[int(np.argmax(counts))]
                        subF, sub_tm = subF[keep], sub_tm[keep]
                if len(subF):
                    # the sheets were oriented independently (fix_normals
                    # runs per connected component before zipping): the
                    # merged mesh may mix windings across the new seam,
                    # which breaks the directed boundary-loop walk that
                    # both LSCM pinning and Tutte rely on. Reorient the
                    # now-connected submesh; flips keep sorted-face
                    # identity, so sub_tm and sub_src stay valid.
                    tm = trimesh.Trimesh(subV, subF, process=False)
                    trimesh.repair.fix_normals(tm)
                    subF = np.asarray(tm.faces, dtype=subF.dtype)
            if len(subF) == 0:
                return None
            # pinch (bowtie) vertices break disk topology and wrap the
            # flattening even when every face has consistent winding
            subV, subF, sub_src = _split_pinch_vertices(subV, subF,
                                                        sub_src)
            # drop vertices orphaned by zipping / component keeps:
            # zero Laplacian rows make LSCM and Tutte exactly singular
            used2 = np.unique(subF)
            if len(used2) < len(subV):
                remap2 = -np.ones(len(subV), dtype=int)
                remap2[used2] = np.arange(len(used2))
                subV = subV[used2]
                subF = remap2[subF]
                sub_src = [sub_src[i] for i in used2]

            def fresh() -> _ChartMesh:
                # the gates mutate the mesh they are given; every
                # flattening attempt must start from the pristine submesh
                return _ChartMesh(subV, subF.copy(), sub_src,
                                  sub_tm.copy())

            def validated(cm: _ChartMesh,
                          uv: np.ndarray | None) -> LscmParam | None:
                # functional acceptance: the chart must roundtrip this
                # plate's own contour (inverse -> evaluate). Geometric
                # proxies (flip counts, scale spread) miss fold-free
                # non-injective wraps and falsely reject harmless pinches.
                if uv is None:
                    return None
                param = LscmParam(self.members, cm, uv)
                uvc = param.inverse(contour)
                err = np.linalg.norm(param.evaluate(uvc) - contour, axis=1)
                if float(err.max()) > 2.0 * self._tol:
                    logger.debug("LSCM: contour roundtrip {:.3f} m",
                                 float(err.max()))
                    return None
                return param

            sub = fresh()
            param = validated(sub, _flatten_gates(sub))
            if param is None:
                # conformal flattening folded or wrapped: retry without
                # rejection gates — flips between welded coincident
                # sheets are harmless and the roundtrip check decides
                sub = fresh()
                uv = _lscm_uv(sub.V, sub.F)
                if uv is not None:
                    uv = _apply_gates(sub, uv, scale_gate=False,
                                      reject=False)
                param = validated(sub, uv)
            if param is None:
                # last resort: Tutte embedding — injective on disk
                # topology, so the chart still tracks, less isometric
                sub = fresh()
                uv = _tutte_uv(sub.V, sub.F)
                if uv is not None:
                    uv = _apply_gates(sub, uv, scale_gate=False,
                                      reject=False)
                param = validated(sub, uv)
            return param
        except Exception as exc:  # noqa: BLE001 — chart disqualifies itself
            logger.debug("LSCM plate chart failed: {}", exc)
            return None


def make_lscm_chart(members: list[SurfaceParam], tol_m: float,
                    hint_pts: np.ndarray | None = None) -> LscmChart | None:
    """Chart mesh over collection members for per-plate flattening, or
    None if no usable mesh can be built."""
    try:
        cm = _build_mesh(members, tol_m, hint_pts, require_connected=False)
        if cm is None:
            return None
        return LscmChart(members, cm, tol_m)
    except Exception as exc:  # noqa: BLE001 — chart disqualifies itself
        logger.debug("LSCM chart mesh failed: {}", exc)
        return None


def make_lscm(members: list[SurfaceParam], tol_m: float,
              hint_pts: np.ndarray | None = None) -> LscmParam | None:
    """LSCM chart over collection members, or None if not buildable."""
    try:
        cm = _build_mesh(members, tol_m, hint_pts)
        if cm is None:
            return None
        uv = _flatten_gates(cm)
        if uv is None:
            return None
        return LscmParam(members, cm, uv)
    except Exception as exc:  # noqa: BLE001 — chart disqualifies itself
        logger.debug("LSCM chart failed: {}", exc)
        return None
