"""OCX-TOP-001 helpers: boundary-ref reason fragments and the arrangement
path for panels bounded by GridRefs.

A GridRef names a plane, not a curve, and LimitedBy order is not cyclic,
so the boundary is found as a planar arrangement in the panel surface's uv
space: every boundary (plus surface parameter edges inside the window)
becomes uv linework, the linework is polygonized, and the union of the faces
inside the OuterContour is the panel region.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from ocx_geometry.intersect import intersect_surface_plane
from ocx_geometry.topology2d import points_polyline_distances
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

_SAMPLE_TOL_M = 0.001
# Max area of (region XOR OuterContour), as a fraction of the contour area,
# for the arrangement region to count as enclosing the panel; absorbs
# sampling and marching-squares discretisation.
_REGION_MISMATCH = 0.01
NOT_CLOSED = "Panel boundary is not closed: LimitedBy does not enclose the panel"


def boundary_reasons(dangling: Counter[str], no_curve: Counter[str],
                     unsampleable: int) -> list[str]:
    """Reason fragments for LimitedBy refs that cannot be evaluated."""
    def by_type(counts: Counter[str]) -> str:
        return ", ".join(f"{t}×{n}" for t, n in sorted(counts.items()))

    reasons = []
    if dangling:
        reasons.append(f"{dangling.total()} dangling boundary ref(s) "
                       f"({by_type(dangling)})")
    if no_curve:
        reasons.append(f"{no_curve.total()} boundary ref(s) without explicit "
                       f"curve ({by_type(no_curve)})")
    if unsampleable:
        reasons.append(f"{unsampleable} unsampleable boundary curve(s)")
    return reasons


def grid_panel_outcome(geo, panel, tol_m: float) -> tuple[str | None, list[str]]:
    """``(unchecked reason, finding messages)`` for a panel with GridRefs.

    The panel region is the union of arrangement faces inside the
    OuterContour; it must match the contour (else not closed), and every
    boundary must touch its rings — GridRefs by analytic plane distance,
    explicit curves by polyline distance. Exceptions propagate; the caller
    reports them as unchecked.
    """
    planes: list[tuple[str, tuple[np.ndarray, np.ndarray]]] = []
    explicit: list[tuple[str, np.ndarray]] = []
    dangling: Counter[str] = Counter()
    no_curve: Counter[str] = Counter()
    unsampleable = 0
    for ref in panel.limited_by:
        label = " ".join(x for x in (ref.ref_type, ref.local_ref) if x)
        if ref.ref_type == "GridRef":
            plane = geo.grid_ref_plane(ref)
            if plane is None:
                dangling["GridRef"] += 1
            else:
                planes.append((label, plane))
            continue
        curve = geo.boundary_curve_for_ref(ref)
        if curve is None:
            bucket = (dangling if ref.ref_type in ("SeamRef", "StiffenerRef")
                      else no_curve)
            bucket[ref.ref_type] += 1
            continue
        pts = geo.sample(curve, _SAMPLE_TOL_M)
        if pts is None or len(pts) < 2:
            unsampleable += 1
        else:
            explicit.append((label, _extend_open_ends(pts, tol_m)))
    reasons = boundary_reasons(dangling, no_curve, unsampleable)
    if reasons:
        return "; ".join(reasons), []
    if not panel.outer_contours:
        return "cannot determine panel extent", []

    param = geo.surface_param(geo.panel_surface(panel))
    if param is None:
        return "no buildable panel surface", []
    window = geo.panel_uv_window(panel, param, [p for _, p in explicit])
    if window is None:
        return "cannot determine panel extent", []
    contour = _contour_uv(geo, panel, param, window)
    if contour is None:
        return "unusable OuterContour", []

    boundaries = [(label, [pts]) for label, pts in explicit]
    cuts = [(label, intersect_surface_plane(param, p, n, window,
                                            _SAMPLE_TOL_M))
            for label, (p, n) in planes]
    lines = [LineString(_to_uv(param, pl, window))
             for _, pls in boundaries + cuts for pl in pls if len(pl) >= 2]
    lines += _domain_edges(param, window)
    faces = [f for f in polygonize(unary_union(lines))
             if contour.contains(f.representative_point())]
    region = unary_union(faces) if faces else None
    if (region is None or region.is_empty
            or region.symmetric_difference(contour).area
            > _REGION_MISMATCH * contour.area):
        return None, [NOT_CLOSED]
    ring = param.evaluate(np.vstack([
        np.asarray(r.coords) for poly in getattr(region, "geoms", [region])
        for r in (poly.exterior, *poly.interiors)]))
    messages = []
    for label, pls in boundaries:
        dist = min((float(points_polyline_distances(ring, pl).min())
                    for pl in pls), default=np.inf)
        if dist > tol_m:
            messages.append(f"LimitedBy boundary {label} does not bound "
                            f"the panel")
    for label, (p, n) in planes:
        if float(np.abs((ring - p) @ n).min()) > tol_m:
            messages.append(f"LimitedBy boundary {label} does not bound "
                            f"the panel")
    return None, messages


def _domain_edges(param, window) -> list[LineString]:
    """Window edges lying on a finite ``param.uv_domain()`` bound: real
    surface edges, where a plane cut beyond the domain finds no sign change."""
    domain = param.uv_domain()
    if domain is None:
        return []
    u0, u1, v0, v1 = window
    du0, du1, dv0, dv1 = domain
    edges = [LineString([(u, v0), (u, v1)])
             for u, d in ((u0, du0), (u1, du1)) if np.isfinite(d) and u == d]
    edges += [LineString([(u0, v), (u1, v)])
              for v, d in ((v0, dv0), (v1, dv1)) if np.isfinite(d) and v == d]
    return edges


def _extend_open_ends(pts: np.ndarray, d: float) -> np.ndarray:
    """Extend an open polyline by ``d`` along its end tangents so boundaries
    meeting within tolerance cross in the arrangement."""
    if np.linalg.norm(pts[0] - pts[-1]) <= d:
        return pts
    head, tail = pts[0] - pts[1], pts[-1] - pts[-2]
    nh, nt = np.linalg.norm(head), np.linalg.norm(tail)
    start = pts[0] + head / nh * d if nh > 1e-12 else pts[0]
    end = pts[-1] + tail / nt * d if nt > 1e-12 else pts[-1]
    return np.vstack([start, pts, end])


def _to_uv(param, pts: np.ndarray, window) -> np.ndarray:
    """3D -> uv; on periodic surfaces shift u by whole periods so the
    polyline lies in the window."""
    uv = param.inverse(np.asarray(pts, dtype=float))
    if param.periodic_u:
        mid = 0.5 * (window[0] + window[1])
        k = np.round((uv[:, 0].mean() - mid) / (2.0 * np.pi))
        uv[:, 0] -= 2.0 * np.pi * k
    return uv


def _contour_uv(geo, panel, param, window) -> Polygon | None:
    """First OuterContour as a uv polygon; None unless valid with area."""
    pts = geo.sample(panel.outer_contours[0], _SAMPLE_TOL_M)
    if pts is not None and len(pts) >= 3:
        poly = Polygon(_to_uv(param, pts, window))
        if poly.is_valid and poly.area > 0:
            return poly
    return None
