"""Trim a triangle mesh to the region bounded by closed 3-D rings.

A multi-member panel is meshed once (the chart mesh).  A plate is the part
of that mesh enclosed by its contour, minus its holes.  Instead of
flattening the region (conformal charts fail on large doubly-curved
plates), each ring is walked over the mesh, the triangles it crosses are
split along it, and the two sides are told apart by connectivity.  The
result follows the contour exactly, whatever the curvature.
"""
from __future__ import annotations

import math
from collections import defaultdict

import mapbox_earcut
import numpy as np
import shapely
import shapely.ops
import trimesh
from loguru import logger
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

_GRID = 1e-9            # shapely snapping grid inside a triangle's 2-D frame
_MAX_REFINE = 12
_MIN_GAP = 1e-4         # smallest ring step worth refining across a slit


def _edge_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _shared_counts(fa: np.ndarray, fb: np.ndarray) -> np.ndarray:
    return (fa[:, :, None] == fb[:, None, :]).sum(axis=(1, 2))


class _Mesh:
    """Indexed triangle mesh with per-vertex normals and edge topology."""

    def __init__(self, V: np.ndarray, F: np.ndarray, N: np.ndarray):
        self.V = np.asarray(V, dtype=float)
        self.F = np.asarray(F, dtype=np.int64)
        self.N = np.asarray(N, dtype=float)
        self.tm = trimesh.Trimesh(self.V, self.F, process=False)
        self.edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
        for fi, f in enumerate(self.F):
            for k in range(3):
                self.edge_faces[_edge_key(int(f[k]), int(f[(k + 1) % 3]))
                                ].append(fi)


def _frame(V: np.ndarray, f: np.ndarray):
    """Origin, in-plane axes and 2-D corner coordinates of a triangle."""
    p0, p1, p2 = V[f[0]], V[f[1]], V[f[2]]
    e1 = p1 - p0
    l1 = float(np.linalg.norm(e1))
    e1 = e1 / l1
    n = np.cross(p1 - p0, p2 - p0)
    n = n / np.linalg.norm(n)
    e2 = np.cross(n, e1)
    d = p2 - p0
    corners = np.array([[0.0, 0.0], [l1, 0.0], [d @ e1, d @ e2]])
    return p0, e1, e2, corners


def _to2d(pts: np.ndarray, o: np.ndarray, e1: np.ndarray,
          e2: np.ndarray) -> np.ndarray:
    d = np.atleast_2d(pts) - o
    return np.column_stack([d @ e1, d @ e2])


def _densify(ring: np.ndarray, step: float) -> np.ndarray:
    ring = np.asarray(ring, dtype=float)
    if len(ring) > 1 and np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    nxt = np.roll(ring, -1, axis=0)
    out = []
    for a, b in zip(ring, nxt):
        n = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / step)))
        out.append(a + (b - a) * (np.arange(n) / n)[:, None])
    return np.vstack(out)


def _walk_ring(mesh: _Mesh, ring: np.ndarray, step: float):
    """Snap a closed ring onto the mesh and cut it at triangle borders.

    Returns ``(segments, max_snap)`` where ``segments`` maps a face index to
    the 3-D segments of the ring inside that face, in ring direction.
    """
    pts = _densify(ring, step)
    snapped = dist = tri = None
    for _ in range(_MAX_REFINE):
        snapped, dist, tri = trimesh.proximity.closest_point(mesh.tm, pts)
        nxt = np.roll(np.arange(len(pts)), -1)
        share = _shared_counts(mesh.F[tri], mesh.F[tri[nxt]])
        gap = np.linalg.norm(pts[nxt] - pts, axis=1)
        bad = np.flatnonzero((share == 0) & (gap > _MIN_GAP))
        for i in np.flatnonzero((share == 1) & (gap > _MIN_GAP)):
            j = nxt[i]
            q = mesh.V[list(set(mesh.F[tri[i]]) & set(mesh.F[tri[j]]))[0]]
            d = pts[j] - pts[i]
            t = float(np.clip((q - pts[i]) @ d / (d @ d), 0.0, 1.0))
            if float(np.linalg.norm(pts[i] + t * d - q)) > 1e-6:
                bad = np.append(bad, i)
        bad = np.sort(bad)
        if len(bad) == 0 or _ == _MAX_REFINE - 1:
            break
        mid = 0.5 * (pts[bad] + pts[nxt[bad]])
        pts = np.insert(pts, bad + 1, mid, axis=0)
    segs: dict[int, list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    n = len(pts)
    span = float(np.ptp(mesh.V, axis=0).max())
    for i in range(n):
        j = (i + 1) % n
        a, b, ti, tj = snapped[i], snapped[j], int(tri[i]), int(tri[j])
        if float(np.linalg.norm(b - a)) < 1e-12 and ti == tj:
            continue
        if ti == tj:
            segs[ti].append((a, b))
            continue
        common = sorted(set(mesh.F[ti]) & set(mesh.F[tj]))
        if len(common) >= 3:
            segs[ti].append((a, b))
        elif len(common) == 2:
            u, w = mesh.V[common[0]], mesh.V[common[1]]
            d, e = b - a, w - u
            # closest approach of the two lines: a + s d  vs  u + t e
            m = np.array([[d @ d, -(d @ e)], [d @ e, -(e @ e)]])
            rhs = np.array([(u - a) @ d, (u - a) @ e])
            if abs(np.linalg.det(m)) < 1e-12 * max(1.0, (d @ d) * (e @ e)):
                segs[ti].append((a, b))      # runs along the shared edge
            else:
                t = float(np.clip(np.linalg.solve(m, rhs)[1], 0.0, 1.0))
                q = u + t * e
                segs[ti].append((a, q))
                segs[tj].append((q, b))
        elif len(common) == 1:
            q = mesh.V[common[0]]
            segs[ti].append((a, q))
            segs[tj].append((q, b))
        else:
            # ring jumps a slit between sheets: carry it across both ends
            d = b - a
            ln = float(np.linalg.norm(d))
            if ln < 1e-12:
                continue
            d = d / ln
            segs[ti].append((a, a + d * span))
            segs[tj].append((b - d * span, b))
    return segs, float(dist.max()) if len(dist) else 0.0


def _on_edge(mesh: _Mesh, f: int, seg) -> tuple[int, int] | None:
    """The mesh edge of face ``f`` that a segment lies along, if any."""
    a, b = seg
    for k in range(3):
        u, w = int(mesh.F[f][k]), int(mesh.F[f][(k + 1) % 3])
        pu, pw = mesh.V[u], mesh.V[w]
        e = pw - pu
        le = float(e @ e)
        if le < 1e-18:
            continue
        ok = True
        for p in (a, b):
            t = float((p - pu) @ e) / le
            if not -1e-6 <= t <= 1.0 + 1e-6:
                ok = False
                break
            if float(np.linalg.norm(p - (pu + t * e))) > 1.5e-3:
                ok = False
                break
        if ok:
            return _edge_key(u, w)
    return None


def _edge_intervals(piece_geoms, o2d: np.ndarray, u2: np.ndarray,
                    w2: np.ndarray, length: float):
    """(unit, t0, t1) for each piece that touches the edge u2-w2."""
    line = shapely.LineString([u2, w2]).buffer(1e-8)
    d = w2 - u2
    dd = float(d @ d)
    out = []
    for unit, geom in piece_geoms:
        inter = shapely.intersection(geom, line)
        if inter.is_empty:
            continue
        parts = inter.geoms if hasattr(inter, "geoms") else [inter]
        for part in parts:
            if part.geom_type != "Polygon":
                continue
            xy = np.asarray(part.exterior.coords)
            t = ((xy - u2) @ d) / dd
            t0, t1 = float(t.min()), float(t.max())
            if (t1 - t0) * length > 1e-6:
                out.append((unit, t0, t1))
    return out


class MeshTrimmer:
    """Cuts plate regions out of a triangle mesh by closed 3-D rings."""

    def __init__(self, V: np.ndarray, F: np.ndarray, tol: float):
        tm = trimesh.Trimesh(np.asarray(V, dtype=float),
                             np.asarray(F, dtype=np.int64), process=False)
        trimesh.repair.fix_normals(tm)          # consistent winding
        self._tol = tol
        self._mesh = _Mesh(tm.vertices, tm.faces,
                           np.asarray(tm.vertex_normals))

    # -- one ring ------------------------------------------------------
    def _cut(self, mesh: _Mesh, ring: np.ndarray, seed: np.ndarray | None,
             max_snap: float):
        step = max(0.25, 5.0 * self._tol)
        r = np.asarray(ring, dtype=float)
        ring_area = max(0.5 * float(np.linalg.norm(
            np.cross(r, np.roll(r, -1, axis=0)).sum(axis=0))), 1e-9)
        segs, snap = _walk_ring(mesh, ring, step)
        if snap > max_snap:
            return None, snap
        if not segs:
            return None, snap
        V, F = mesh.V, mesh.F

        # segments lying along an edge separate the faces on both sides
        barrier: set[tuple[int, int]] = set()
        extra: dict[int, list] = defaultdict(list)
        for f, lst in list(segs.items()):
            for seg in lst:
                key = _on_edge(mesh, f, seg)
                if key is None:
                    continue
                barrier.add(key)
                for g in mesh.edge_faces[key]:
                    if g != f:
                        extra[g].append(seg)
        for g, lst in extra.items():
            segs[g].extend(lst)

        # -- split cut faces into pieces
        n_face = len(F)
        unit_face: list[int] = []
        unit_side: list[int] = []
        unit_poly: list = []                 # shapely polygon in face frame
        unit_area: list[float] = []
        frames: dict[int, tuple] = {}
        pieces_of: dict[int, list[int]] = {}
        for f, lst in segs.items():
            o, e1, e2, corners = _frame(V, F[f])
            frames[f] = (o, e1, e2, corners)
            tri_poly = shapely.Polygon(corners)
            lines = []
            seg2d = []
            for a, b in lst:
                xy = _to2d(np.array([a, b]), o, e1, e2)
                ln = shapely.LineString(xy)
                if ln.length < 1e-12:
                    continue
                ln = shapely.intersection(ln, tri_poly.buffer(1e-9))
                if ln.is_empty or ln.geom_type != "LineString":
                    continue
                xy = np.asarray(ln.coords)
                # ends that fall just short of the face border are pulled
                # onto it so the cut line fully separates the face
                for end in (0, -1):
                    pt = shapely.Point(xy[end])
                    if 1e-7 < tri_poly.boundary.distance(pt) < 1.5e-3:
                        near = shapely.ops.nearest_points(
                            tri_poly.boundary, pt)[0]
                        xy[end] = (near.x, near.y)
                seg2d.append((xy[0], xy[-1]))
                lines.append(shapely.LineString(xy))
            if not lines:
                continue
            union = shapely.union_all([tri_poly.boundary, *lines],
                                      grid_size=_GRID)
            polys = [p for p in shapely.polygonize([union]).geoms
                     if p.area > 1e-12 * tri_poly.area]
            if not polys:
                polys = [tri_poly]
            ids = []
            for p in polys:
                rp = np.asarray(p.representative_point().coords[0])
                best, sign = 1e300, 1
                for a, b in seg2d:
                    ab = b - a
                    l2 = float(ab @ ab)
                    t = float(np.clip((rp - a) @ ab / l2, 0.0, 1.0)) \
                        if l2 > 0 else 0.0
                    dd = float(np.linalg.norm(rp - (a + t * ab)))
                    if dd < best:
                        cr = ab[0] * (rp - a)[1] - ab[1] * (rp - a)[0]
                        best, sign = dd, (1 if cr > 0 else -1)
                ids.append(len(unit_face))
                unit_face.append(f)
                unit_side.append(sign)
                unit_poly.append(p)
                unit_area.append(p.area)
            pieces_of[f] = ids
        if not pieces_of:
            return None, snap
        cut = np.zeros(n_face, dtype=bool)
        cut[list(pieces_of)] = True

        # unit ids: faces first (uncut ones are live), pieces after
        n_units = n_face + len(unit_face)
        pid = lambda k: n_face + k           # noqa: E731
        rows, cols = [], []
        # uncut-uncut adjacency; cut-involving edges matched by interval
        piece_geoms: dict[int, list] = {
            f: [(pid(k), unit_poly[k]) for k in ks]
            for f, ks in pieces_of.items()}
        for key, fs in mesh.edge_faces.items():
            if key in barrier or len(fs) < 2:
                continue
            for i in range(len(fs)):
                for j in range(i + 1, len(fs)):
                    fa, fb = fs[i], fs[j]
                    if not cut[fa] and not cut[fb]:
                        rows.append(fa)
                        cols.append(fb)
                        continue
                    u, w = key
                    sides = []
                    for f in (fa, fb):
                        if not cut[f]:
                            sides.append([(f, 0.0, 1.0)])
                            continue
                        o, e1, e2, _ = frames[f]
                        pu = _to2d(V[u], o, e1, e2)[0]
                        pw = _to2d(V[w], o, e1, e2)[0]
                        ln = float(np.linalg.norm(V[w] - V[u]))
                        iv = _edge_intervals(piece_geoms[f], o, pu, pw, ln)
                        sides.append(iv)
                    ln = float(np.linalg.norm(V[key[1]] - V[key[0]]))
                    for ua, a0, a1 in sides[0]:
                        for ub, b0, b1 in sides[1]:
                            if (min(a1, b1) - max(a0, b0)) * ln > 5e-3:
                                rows.append(ua)
                                cols.append(ub)

        graph = coo_matrix((np.ones(len(rows)), (rows, cols)),
                           shape=(n_units, n_units))
        _, comp = connected_components(graph, directed=False)
        live = np.ones(n_units, dtype=bool)
        live[np.flatnonzero(cut)] = False        # whole faces replaced
        live[n_face:] = True

        side = np.zeros(n_units)
        for k, s in enumerate(unit_side):
            side[pid(k)] = s * max(unit_area[k], 1e-12)
        vote = np.bincount(comp, weights=side, minlength=comp.max() + 1)
        has_cut = np.zeros(comp.max() + 1, dtype=bool)
        has_cut[comp[n_face:]] = True
        comp_side = np.where(vote >= 0, 1, -1)

        # unit label (+1/-1, 0 = unreachable from the ring)
        label = np.zeros(n_units, dtype=int)
        label[live] = np.where(has_cut[comp[live]], comp_side[comp[live]], 0)

        # centroid of every live unit (3-D) for seed lookup / area sums
        def unit_geometry(u: int):
            if u < n_face:
                return V[F[u]], float(np.linalg.norm(np.cross(
                    V[F[u][1]] - V[F[u][0]], V[F[u][2]] - V[F[u][0]])) / 2.0)
            k = u - n_face
            o, e1, e2, _ = frames[unit_face[k]]
            xy = np.asarray(unit_poly[k].exterior.coords)[:-1]
            return o + xy[:, :1] * e1 + xy[:, 1:] * e2, unit_area[k]

        live_ids = np.flatnonzero(live & (label != 0))
        if len(live_ids) == 0:
            return None, snap
        cents = np.empty((len(live_ids), 3))
        areas = np.empty(len(live_ids))
        for i, u in enumerate(live_ids):
            g, a = unit_geometry(int(u))
            cents[i] = g.mean(axis=0)
            areas[i] = a
        lab = label[live_ids]
        if seed is not None:
            inside = 0
            sp, _, st_ = trimesh.proximity.closest_point(mesh.tm, [seed])
            fi = int(st_[0])
            if fi in pieces_of:
                o, e1, e2, _c = frames[fi]
                q = shapely.Point(_to2d(sp[0], o, e1, e2)[0])
                k = min(pieces_of[fi],
                        key=lambda k: shapely.distance(unit_poly[k], q))
                inside = int(label[pid(k)])
            else:
                inside = int(label[fi])
            if inside == 0:
                inside = int(lab[int(np.argmin(
                    np.linalg.norm(cents - seed, axis=1)))])
        else:
            inside = 1 if abs(math.log(max(areas[lab == 1].sum(), 1e-9)
                                       / ring_area)) \
                <= abs(math.log(max(areas[lab == -1].sum(), 1e-9)
                                / ring_area)) else -1
        inside_units = live_ids[lab == inside]
        outside_units = np.flatnonzero(live & (label != inside))
        state = {"inside": inside_units, "outside": outside_units,
                 "frames": frames, "unit_face": unit_face,
                 "unit_poly": unit_poly, "n_face": n_face}
        return state, snap

    # -- assemble kept units back into a mesh --------------------------
    def _assemble(self, mesh: _Mesh, state, which: str = "inside"
                  ) -> _Mesh | None:
        keep_units = state[which]
        frames, unit_face = state["frames"], state["unit_face"]
        n_face = state["n_face"]
        pos, nrm, tri = [], [], []
        base = 0
        for u in keep_units:
            u = int(u)
            if u < n_face:
                f = mesh.F[u]
                pos.append(mesh.V[f])
                nrm.append(mesh.N[f])
                tri.append([base, base + 1, base + 2])
                base += 3
                continue
            k = u - n_face
            f = unit_face[k]
            o, e1, e2, corners = frames[f]
            poly = state["unit_poly"][k]
            ext = np.asarray(poly.exterior.coords)[:-1]
            holes = [np.asarray(r.coords)[:-1] for r in poly.interiors]
            rings = [ext] + holes
            xy = np.vstack(rings).astype(np.float64)
            ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
            t = np.asarray(mapbox_earcut.triangulate_float64(xy, ends),
                           dtype=np.int64).reshape(-1, 3)
            if len(t) == 0:
                continue
            p3 = o + xy[:, :1] * e1 + xy[:, 1:] * e2
            # barycentric weights in the source face -> interpolated normals
            (x0, y0), (x1, y1), (x2, y2) = corners
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            l0 = ((y1 - y2) * (xy[:, 0] - x2) + (x2 - x1) * (xy[:, 1] - y2)) / den
            l1 = ((y2 - y0) * (xy[:, 0] - x2) + (x0 - x2) * (xy[:, 1] - y2)) / den
            l2 = 1.0 - l0 - l1
            fn = mesh.N[mesh.F[f]]
            n3 = l0[:, None] * fn[0] + l1[:, None] * fn[1] + l2[:, None] * fn[2]
            n3 /= np.maximum(np.linalg.norm(n3, axis=1, keepdims=True), 1e-12)
            pos.append(p3)
            nrm.append(n3)
            tri.append(t + base)
            base += len(p3)
        if not tri:
            return None
        P = np.vstack(pos)
        N = np.vstack(nrm)
        T = np.vstack([np.asarray(t, dtype=np.int64).reshape(-1, 3)
                       for t in tri])
        key = np.round(P / 1e-7).astype(np.int64)
        _, first, inv = np.unique(key, axis=0, return_index=True,
                                  return_inverse=True)
        inv = np.asarray(inv).ravel()
        P2, N2, T2 = P[first], N[first], inv[T]
        good = ((T2[:, 0] != T2[:, 1]) & (T2[:, 1] != T2[:, 2])
                & (T2[:, 2] != T2[:, 0]))
        T2 = T2[good]
        a = P2[T2[:, 1]] - P2[T2[:, 0]]
        b = P2[T2[:, 2]] - P2[T2[:, 0]]
        T2 = T2[np.linalg.norm(np.cross(a, b), axis=1) > 1e-14]
        return _Mesh(P2, T2, N2) if len(T2) else None

    # -- public --------------------------------------------------------
    def trim(self, outer: np.ndarray, holes: list[np.ndarray],
             seed: np.ndarray | None = None):
        """Region of the mesh inside ``outer`` and outside ``holes``.

        Returns ``(vertices, triangles, normals)`` or ``None`` when the
        outer ring does not lie on the mesh.
        """
        max_snap = max(10.0 * self._tol, 0.5)
        state, snap = self._cut(self._mesh, outer, seed, max_snap)
        if state is None:
            logger.debug("Mesh trim: outer ring unusable (snap {:.3f} m)",
                         snap)
            return None
        mesh = self._assemble(self._mesh, state)
        if mesh is None:
            return None
        for h in holes:
            if len(h) < 3:
                continue
            probe = trimesh.proximity.closest_point(
                mesh.tm, h[:: max(1, len(h) // 12)])[1]
            if float(np.median(probe)) > 4.0 * self._tol:
                continue                       # hole is not in this plate
            state, snap = self._cut(mesh, h, None, max_snap)
            if state is None:
                continue
            mesh2 = self._assemble(mesh, state, "outside")
            if mesh2 is not None:
                mesh = mesh2
        return mesh.V, mesh.F, mesh.N
