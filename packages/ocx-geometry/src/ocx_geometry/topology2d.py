"""Shapely-based 2-D polygon topology helpers (no meshing).

All polygons are (N, 2) float arrays without a repeated last point; cuts are
open (N, 2) polylines. The 3-D point/polyline distance works on (N, 3) arrays.
All helpers degrade gracefully on invalid input instead of raising.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union


def polygon_ok(ring: np.ndarray | None) -> str | None:
    """None if *ring* is a valid simple polygon, else a short reason."""
    if ring is None or len(np.atleast_1d(ring)) < 3:
        return "fewer than 3 vertices"
    try:
        poly = Polygon(np.asarray(ring, dtype=float))
        if poly.is_valid and poly.area > 0.0:
            return None
        from shapely.validation import explain_validity

        return explain_validity(poly)
    except Exception:  # NaNs / wrong-shaped arrays etc.
        return "unconstructible ring"


def region_count(outer: np.ndarray, cuts: list[np.ndarray]) -> int:
    """Number of regions the *cuts* partition *outer* into.

    Invalid/degenerate inputs degrade to 1 (lean-pass: cannot prove a split).
    """
    if polygon_ok(outer) is not None:
        return 1
    try:
        poly = Polygon(np.asarray(outer, dtype=float))
        lines = [LineString(np.asarray(c, dtype=float)[:, :2]) for c in cuts
                 if c is not None and np.ndim(c) == 2 and len(c) >= 2]
        if not lines:
            return 1
        pieces = split(poly, unary_union(lines))
        return max(1, sum(1 for g in pieces.geoms if g.area > 1e-12))
    except Exception:  # shapely GEOS edge cases degrade to "no split proven"
        return 1


def point_polyline_distance(point: np.ndarray, polyline: np.ndarray) -> float:
    """Min distance from a 3-D point to a 3-D polyline (exact per segment).

    Returns ``inf`` when the polyline is missing or empty.
    """
    if polyline is None or np.ndim(polyline) != 2 or len(polyline) == 0:
        return float("inf")
    p = np.asarray(point, dtype=float)
    pts = np.asarray(polyline, dtype=float)
    if len(pts) == 1:
        return float(np.linalg.norm(p - pts[0]))
    a, b = pts[:-1], pts[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    t = np.zeros(len(a))
    nz = denom > 0
    t[nz] = np.einsum("ij,ij->i", (p - a)[nz], ab[nz]) / denom[nz]
    t = np.clip(t, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return float(np.min(np.linalg.norm(closest - p, axis=1)))
