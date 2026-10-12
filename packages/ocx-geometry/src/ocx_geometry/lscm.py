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
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from shapely.strtree import STRtree

from ocx_geometry.surfaces import SurfaceParam, _member_fit

_MAX_GRID = 48            # max facet cells per axis per member
_MAX_SCALE_RATIO = 100.0  # reject charts with larger per-triangle scale spread
_MAX_FLIPPED = 0.005      # tolerated fraction of flipped UV triangles
_STITCH_PASSES = 8


class _ChartMesh:
    """Welded facet mesh of all members with per-vertex source params."""

    def __init__(self, V: np.ndarray, F: np.ndarray,
                 src: list[dict[int, tuple[float, float]]],
                 tri_member: np.ndarray) -> None:
        self.V = V                      # (n, 3) vertices, metres
        self.F = F                      # (m, 3) triangle vertex indices
        self.src = src                  # per vertex: {member index: local uv}
        self.tri_member = tri_member    # (m,) member per triangle, -1 = none


def _member_domain(member: SurfaceParam, hint_pts: np.ndarray | None,
                   on_tol: float):
    """Member UV sampling domain: intrinsic knot domain when available,
    else the bbox of on-surface hint points in member-local UV."""
    du, dv = getattr(member, "du", None), getattr(member, "dv", None)
    if du is not None and dv is not None:
        return (float(du[0]), float(du[1])), (float(dv[0]), float(dv[1]))
    if hint_pts is None or len(hint_pts) < 3:
        return None
    fit = _member_fit(member, hint_pts)
    if fit is None:
        return None
    uv, _, res = fit
    on = res <= on_tol
    if int(on.sum()) < 3:
        return None
    u0, u1 = float(uv[on, 0].min()), float(uv[on, 0].max())
    v0, v1 = float(uv[on, 1].min()), float(uv[on, 1].max())
    if u1 - u0 < 1e-9 or v1 - v0 < 1e-9:
        return None                     # degenerate: no 2-D extent
    return (u0, u1), (v0, v1)


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


def _build_mesh(members: list[SurfaceParam], tol_m: float,
                hint_pts: np.ndarray | None) -> _ChartMesh | None:
    weld_tol = max(1e-6, 0.1 * tol_m)
    on_tol = max(10.0 * weld_tol, tol_m)
    pts_all, src_all, faces_all = [], [], []
    offset = 0
    for k, member in enumerate(members):
        dom = _member_domain(member, hint_pts, on_tol)
        if dom is None:
            continue
        try:
            pts, uvs, faces = _facet_member(member, dom, tol_m)
        except Exception:  # noqa: BLE001 — member disqualifies itself
            continue
        if not np.isfinite(pts).all():
            continue
        pts_all.append(pts)
        src_all.extend({k: (float(u), float(v))} for u, v in uvs)
        faces_all.append(faces + offset)
        offset += len(pts)
    if not pts_all:
        logger.debug("LSCM: no facetable members")
        return None
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
    F = _stitch(V, F, src, max(weld_tol, 0.5 * tol_m))
    # drop degenerate triangles
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])]
    if len(F):
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        F = F[np.linalg.norm(n, axis=1) > 1e-14]
    if len(F) == 0:
        logger.debug("LSCM: empty mesh")
        return None
    # the chart must be a single connected component
    used = np.unique(F)
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
    # per-triangle source member: one present at all three corners
    tri_member = np.full(len(F), -1, dtype=int)
    for i, f in enumerate(F):
        common = set(src[f[0]]) & set(src[f[1]]) & set(src[f[2]])
        if common:
            tri_member[i] = min(common)
    return _ChartMesh(V, F, src, tri_member)


def _longest_boundary_loop(bnd: np.ndarray) -> list[int] | None:
    """Longest closed loop among the directed boundary edges."""
    nxt = {int(a): int(b) for a, b in bnd}
    seen: set[int] = set()
    best: list[int] | None = None
    for start in list(nxt):
        if start in seen:
            continue
        loop, v = [], start
        while v in nxt and v not in seen:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if v != start:
            continue                     # open chain, not a loop
        if best is None or len(loop) > len(best):
            best = loop
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
    p0, p1 = loop[0], loop[len(loop) // 2]
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
        bary = np.clip(bary, 0.0, None)   # outside points snap to the tri
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
        bary = np.clip(bary, 0.0, None)
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


def make_lscm(members: list[SurfaceParam], tol_m: float,
              hint_pts: np.ndarray | None = None) -> LscmParam | None:
    """LSCM chart over collection members, or None if not buildable."""
    try:
        cm = _build_mesh(members, tol_m, hint_pts)
        if cm is None:
            return None
        uv = _lscm_uv(cm.V, cm.F)
        if uv is None:
            logger.debug("LSCM: flattening failed")
            return None
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
            tri3, a3, a2s = tri3[ok], a3[ok], a2s[ok]
            ok = np.ones(len(cm.F), dtype=bool)
        maj = 1.0 if a2s[ok].sum() >= 0.0 else -1.0
        flipped = float((np.sign(a2s[ok]) != maj).mean())
        if flipped > _MAX_FLIPPED:
            logger.debug("LSCM: {:.2%} flipped UV triangles", flipped)
            return None
        ratio = a3[ok] / np.abs(a2s[ok])
        if float(ratio.max() / ratio.min()) > _MAX_SCALE_RATIO:
            logger.debug("LSCM: per-triangle scale spread too large")
            return None
        uv = uv * math.sqrt(float(np.median(ratio)))
        return LscmParam(members, cm, uv)
    except Exception as exc:  # noqa: BLE001 — chart disqualifies itself
        logger.debug("LSCM chart failed: {}", exc)
        return None
