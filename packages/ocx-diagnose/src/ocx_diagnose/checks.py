"""Pure numeric diagnostics on meshes and charts (no plotting)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.spatial import cKDTree

_OVERLAP_TOL_M = 1e-3   # a face centroid this close to another plate's surface overlaps it
_GAP_MIN_M = 1e-6       # closer than this is a shared (welded) edge, not a gap


def _edge_counts(F: np.ndarray):
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0, return_counts=True)


def mesh_health(V: np.ndarray, F: np.ndarray) -> dict:
    """Triangle count and boundary / non-manifold edge counts."""
    if len(F) == 0:
        return {"triangles": 0, "boundary_edges": 0, "non_manifold_edges": 0}
    _, cnt = _edge_counts(F)
    return {"triangles": int(len(F)), "boundary_edges": int((cnt == 1).sum()),
            "non_manifold_edges": int((cnt > 2).sum())}


def edge_segments(V: np.ndarray, F: np.ndarray, kind: str) -> np.ndarray:
    """(k, 2, 3) segments of ``kind`` = 'boundary' | 'non_manifold' edges."""
    if len(F) == 0:
        return np.zeros((0, 2, 3))
    edges, cnt = _edge_counts(F)
    sel = edges[(cnt == 1) if kind == "boundary" else (cnt > 2)]
    return V[sel] if len(sel) else np.zeros((0, 2, 3))


def _project_distance(member, pts: np.ndarray) -> np.ndarray:
    try:
        uv = member.inverse(pts)
        d = np.linalg.norm(np.asarray(member.evaluate(uv)) - pts, axis=1)
    except Exception:  # noqa: BLE001 — a member that cannot project is skipped
        return np.full(len(pts), np.inf)
    return np.where(np.isfinite(d), d, np.inf)


def surface_deviation(points: np.ndarray, members: list, max_samples: int = 2000,
                      chart=None, k_faces: int = 6) -> np.ndarray:
    """Distance from points to the nearest exact member surface (inf if none project).

    With ``chart`` (a ChartDiag), each point is projected only onto the members
    of its ``k_faces`` nearest chart faces; without it, onto every member, which
    is prohibitive for panels made of thousands of patches.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) > max_samples:
        pts = pts[np.linspace(0, len(pts) - 1, max_samples).astype(int)]
    best = np.full(len(pts), np.inf)
    if chart is None or chart.F is None or len(chart.F) == 0 or chart.tri_member is None:
        for m in members:
            best = np.minimum(best, _project_distance(m, pts))
        return best
    cent = chart.V[chart.F].mean(axis=1)
    k = min(k_faces, len(cent))
    _, nearest = cKDTree(cent).query(pts, k=k)
    owners = np.asarray(chart.tri_member)[np.atleast_2d(nearest.reshape(len(pts), k))]
    for mi in np.unique(owners[owners >= 0]):
        sel = np.nonzero((owners == mi).any(axis=1))[0]
        best[sel] = np.minimum(best[sel], _project_distance(members[int(mi)], pts[sel]))
    return best


def _subsample(pts: np.ndarray, limit: int = 3000) -> np.ndarray:
    if len(pts) <= limit:
        return pts
    return pts[np.linspace(0, len(pts) - 1, limit).astype(int)]


def neighbour_overlaps_and_gaps(meshes: dict[str, tuple[np.ndarray, np.ndarray]],
                                gap_max_m: float) -> dict[str, dict]:
    """Per plate: faces overlapping another plate, and boundary vertices that
    almost (but do not) touch another plate (a gap in (1e-6, gap_max_m])."""
    out: dict[str, dict] = {}
    for pid, (V, F) in meshes.items():
        res = {"overlap_faces": 0, "gap_vertices": 0, "max_gap_m": 0.0}
        out[pid] = res
        if len(F) == 0:
            continue
        lo, hi = V.min(axis=0) - gap_max_m, V.max(axis=0) + gap_max_m
        others = [(v, f) for k, (v, f) in meshes.items()
                  if k != pid and len(f)
                  and (v.min(axis=0) <= hi).all() and (v.max(axis=0) >= lo).all()]
        if not others:
            continue
        off, ov, of = 0, [], []
        for v, f in others:
            ov.append(v)
            of.append(f + off)
            off += len(v)
        tm = trimesh.Trimesh(np.vstack(ov), np.vstack(of), process=False)
        cent = V[F].mean(axis=1)
        d_c = trimesh.proximity.closest_point(tm, cent)[1]
        res["overlap_faces"] = int((d_c < _OVERLAP_TOL_M).sum())
        edges, cnt = _edge_counts(F)
        bv = np.unique(edges[cnt == 1])
        if len(bv):
            d_b = trimesh.proximity.closest_point(tm, _subsample(V[bv]))[1]
            gap = d_b[(d_b > _GAP_MIN_M) & (d_b <= gap_max_m)]
            res["gap_vertices"] = int(len(gap))
            res["max_gap_m"] = float(gap.max()) if len(gap) else 0.0
    return out


def snap_vectors(ring: np.ndarray, mesh_vertices: np.ndarray, max_vectors: int = 300):
    """Segments from (subsampled) ring points to their nearest mesh vertex."""
    ring = np.asarray(ring, dtype=float)
    if len(ring) > max_vectors:
        ring = ring[np.linspace(0, len(ring) - 1, max_vectors).astype(int)]
    _, idx = cKDTree(mesh_vertices).query(ring)
    return ring, mesh_vertices[idx]


@dataclass
class Distortion:
    flipped: np.ndarray        # (n_faces,) bool
    flipped_frac: float        # flipped 3-D area / total 3-D area
    spread: np.ndarray         # (n_faces,) per-triangle scale / median scale (>= 1)
    spread_max: float


def chart_distortion(V: np.ndarray, F: np.ndarray, uv: np.ndarray) -> Distortion:
    """Flips and per-triangle scale spread of a UV flattening of a 3-D mesh."""
    t3 = V[F]
    a3 = 0.5 * np.linalg.norm(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]), axis=1)
    t2 = uv[F]
    a2 = 0.5 * ((t2[:, 1, 0] - t2[:, 0, 0]) * (t2[:, 2, 1] - t2[:, 0, 1])
                - (t2[:, 2, 0] - t2[:, 0, 0]) * (t2[:, 1, 1] - t2[:, 0, 1]))
    major = 1.0 if a2.sum() >= 0.0 else -1.0
    flipped = np.sign(a2) != major
    ratio = a3 / np.maximum(np.abs(a2), 1e-300)
    med = float(np.median(ratio))
    spread = np.maximum(ratio / med, med / np.maximum(ratio, 1e-300))
    return Distortion(flipped=flipped,
                      flipped_frac=float(a3[flipped].sum() / max(a3.sum(), 1e-300)),
                      spread=spread, spread_max=float(spread.max()))

