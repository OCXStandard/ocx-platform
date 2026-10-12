"""Sample IR curves into 3D polylines (metres).

``sample_curve`` returns an (N, 3) float64 array or ``None`` for unsupported
curve types.  ``sample_contour`` additionally stitches composite segments
tip-to-tail, snaps small gaps and guarantees a *closed* contour (returned
WITHOUT a repeated last point), or returns ``None`` with a logged reason.
"""
from __future__ import annotations

import math

import numpy as np
from loguru import logger

from ocx_model_core.model.ir.geometry import (
    IrCircle3D,
    IrCircumArc3D,
    IrCompositeCurve3D,
    IrEllipse3D,
    IrLine3D,
    IrNurbs3D,
    IrPolyLine3D,
)
from ocx_geometry.measure import LengthResolver

_MIN_ARC_SEGS = 8
_MAX_ARC_SEGS = 512


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return v / n


def _any_perp(n: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array(
        [0.0, 1.0, 0.0]
    )
    return _unit(np.cross(n, ref))


def _angular_step(radius: float, tol_m: float) -> int:
    """Segment count for a full circle so chord sagitta <= tol."""
    if radius <= tol_m:
        return _MIN_ARC_SEGS
    dtheta = 2.0 * math.acos(max(1.0 - tol_m / radius, -1.0))
    return int(
        np.clip(math.ceil(2.0 * math.pi / dtheta), _MIN_ARC_SEGS, _MAX_ARC_SEGS)
    )


def _sample_arc3(
    p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, tol_m: float
) -> np.ndarray:
    """Sample the circular arc through three points (start, intermediate, end)."""
    a, b = p1 - p0, p2 - p0
    n = np.cross(a, b)
    if np.linalg.norm(n) < 1e-12:  # collinear → straight segment
        return np.array([p0, p2])
    n = _unit(n)
    e1 = _unit(a)
    e2 = _unit(np.cross(n, e1))
    # 2D coords in the arc plane (origin p0): p0=(0,0), p1=(ax,0), p2=(bx,by)
    ax, bx, by = a @ e1, b @ e1, b @ e2
    # circumcenter of (0,0), (ax,0), (bx,by)
    d = 2.0 * (ax * by)
    if abs(d) < 1e-15:
        return np.array([p0, p2])
    cx = ax / 2.0
    cy = (bx * bx + by * by - bx * ax) / (2.0 * by)
    center = p0 + cx * e1 + cy * e2
    r = float(np.linalg.norm(p0 - center))
    ang = [math.atan2((p - center) @ e2, (p - center) @ e1) for p in (p0, p1, p2)]
    a0, a1, a2 = ang
    # choose sweep direction passing through a1
    ccw_mid = (a1 - a0) % (2 * math.pi)
    ccw_end = (a2 - a0) % (2 * math.pi)
    if ccw_mid <= ccw_end:  # counter-clockwise
        sweep = ccw_end
    else:  # clockwise
        sweep = -((a0 - a2) % (2 * math.pi))
    nseg = max(
        2, int(math.ceil(abs(sweep) / (2 * math.pi) * _angular_step(r, tol_m)))
    )
    t = a0 + sweep * np.linspace(0.0, 1.0, nseg + 1)
    pts = center + r * (np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2))
    pts[0], pts[-1] = p0, p2  # exact endpoints
    return pts


def _sample_nurbs(
    curve: IrNurbs3D, length: LengthResolver, tol_m: float
) -> np.ndarray | None:
    if (
        curve.degree is None
        or not curve.control_points
        or not curve.knot_vector
    ):
        return None
    if len(curve.knot_vector) != curve.degree + len(curve.control_points) + 1:
        logger.debug(
            "NURBS knot vector length {} != degree {} + ctrlpts {} + 1",
            len(curve.knot_vector), curve.degree, len(curve.control_points))
        return None
    from geomdl import NURBS, BSpline
    from geomdl.exceptions import GeomdlException

    try:
        if curve.is_rational and curve.weights:
            c = NURBS.Curve()
        else:
            c = BSpline.Curve()
        c.degree = curve.degree
        c.ctrlpts = [list(length.point(p)) for p in curve.control_points]
        if curve.is_rational and curve.weights:
            c.weights = list(curve.weights)
        c.knotvector = list(curve.knot_vector)
        lo, hi = c.knotvector[c.degree], c.knotvector[-c.degree - 1]
        # start with 32 samples, adaptively bisect while chord sagitta > tol
        us = list(np.linspace(lo, hi, 33))
        for _ in range(6):
            pts = np.array(c.evaluate_list(us))
            mids = [(us[i] + us[i + 1]) / 2.0 for i in range(len(us) - 1)]
            mid_pts = np.array(c.evaluate_list(mids))
            chord_mid = 0.5 * (pts[:-1] + pts[1:])
            sag = np.linalg.norm(mid_pts - chord_mid, axis=1)
            bad = np.where(sag > tol_m)[0]
            if len(bad) == 0 or len(us) > 2048:
                break
            us = sorted(set(us) | {mids[i] for i in bad})
        return np.array(c.evaluate_list(us))
    except (GeomdlException, IndexError, ValueError, ZeroDivisionError) as exc:
        logger.debug("Malformed NURBS curve rejected: {}", exc)
        return None


def sample_curve(
    curve, length: LengthResolver, tol_m: float
) -> np.ndarray | None:
    """Dispatch on curve type; return (N, 3) metres polyline or None."""
    if isinstance(curve, IrLine3D):
        if curve.start is None or curve.end is None:
            return None
        return np.array([length.point(curve.start), length.point(curve.end)])

    if isinstance(curve, IrPolyLine3D):
        if len(curve.vertices) < 2:
            return None
        return np.array([length.point(p) for p in curve.vertices])

    if isinstance(curve, IrCircumArc3D):
        if curve.start is None or curve.intermediate is None or curve.end is None:
            return None
        return _sample_arc3(
            length.point(curve.start),
            length.point(curve.intermediate),
            length.point(curve.end),
            tol_m,
        )

    if isinstance(curve, IrCircle3D):
        if curve.center is None or curve.diameter is None or curve.normal is None:
            return None
        n_vec = np.array([curve.normal.x, curve.normal.y, curve.normal.z])
        if np.linalg.norm(n_vec) < 1e-12:
            logger.debug("Circle has zero-length normal vector")
            return None
        center = length.point(curve.center)
        r = length.qty(curve.diameter) / 2.0
        n = _unit(n_vec)
        e1 = _any_perp(n)
        e2 = np.cross(n, e1)
        t = np.linspace(0.0, 2 * math.pi, _angular_step(r, tol_m) + 1)
        return center + r * (
            np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2)
        )

    if isinstance(curve, IrEllipse3D):
        if (
            curve.center is None
            or curve.major_diameter is None
            or curve.minor_diameter is None
            or curve.major_axis is None
            or curve.normal is None
        ):
            return None
        n_vec = np.array([curve.normal.x, curve.normal.y, curve.normal.z])
        e1_vec = np.array(
            [curve.major_axis.x, curve.major_axis.y, curve.major_axis.z]
        )
        if np.linalg.norm(n_vec) < 1e-12:
            logger.debug("Ellipse has zero-length normal vector")
            return None
        if np.linalg.norm(e1_vec) < 1e-12:
            logger.debug("Ellipse has zero-length major_axis vector")
            return None
        center = length.point(curve.center)
        ra = length.qty(curve.major_diameter) / 2.0
        rb = length.qty(curve.minor_diameter) / 2.0
        n = _unit(n_vec)
        e1 = _unit(e1_vec)
        e2 = np.cross(n, e1)
        if np.linalg.norm(e2) < 1e-12:
            logger.debug("Ellipse has major_axis parallel to normal (collapsed)")
            return None
        t = np.linspace(0.0, 2 * math.pi, _angular_step(max(ra, rb), tol_m) + 1)
        return (
            center
            + np.outer(ra * np.cos(t), e1)
            + np.outer(rb * np.sin(t), e2)
        )

    if isinstance(curve, IrNurbs3D):
        return _sample_nurbs(curve, length, tol_m)

    if isinstance(curve, IrCompositeCurve3D):
        return _sample_composite(curve, length, tol_m, snap_tol_m=tol_m)

    logger.debug("Unsupported curve type for sampling: {}", type(curve).__name__)
    return None


def _sample_composite(
    curve: IrCompositeCurve3D,
    length: LengthResolver,
    tol_m: float,
    snap_tol_m: float,
) -> np.ndarray | None:
    """Stitch composite segments tip-to-tail, reversing segments as needed."""
    parts: list[np.ndarray] = []
    for seg in curve.segments:
        pts = sample_curve(seg, length, tol_m)
        if pts is None or len(pts) < 2:
            logger.debug("Composite segment {} unsampleable", type(seg).__name__)
            return None
        parts.append(pts)
    if not parts:
        return None
    out = parts[0]
    remaining = parts[1:]
    while remaining:
        head, tail = out[0], out[-1]
        # greedy: pick the unused segment whose nearest endpoint is closest
        # to either end of the current chain
        best_i, best_d, best_rev, best_at_head = -1, np.inf, False, False
        for i, pts in enumerate(remaining):
            for rev, p_join in ((False, pts[0]), (True, pts[-1])):
                d = np.linalg.norm(p_join - tail)
                if d < best_d:
                    best_i, best_d, best_rev, best_at_head = i, d, rev, False
            for rev, p_join in ((False, pts[-1]), (True, pts[0])):
                d = np.linalg.norm(p_join - head)
                if d < best_d:
                    best_i, best_d, best_rev, best_at_head = i, d, rev, True
        if best_d > snap_tol_m:
            logger.debug("Composite gap {:.4f} m exceeds snap tolerance", best_d)
            return None
        pts = remaining.pop(best_i)
        if best_rev:
            pts = pts[::-1]
        # snap: the joining endpoint merges with the chain end it attaches to
        if best_at_head:
            out = np.vstack([pts[:-1], out])
        else:
            out = np.vstack([out, pts[1:]])
    return _dedupe(out)


def _dedupe(pts: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) > eps:
            keep.append(i)
    return pts[keep]


def sample_contour(
    curve, length: LengthResolver, tol_m: float, snap_tol_m: float
) -> np.ndarray | None:
    """Sample a *closed* boundary contour.

    Returns the closed loop WITHOUT a repeated last point, or None if the
    curve cannot be sampled or does not close within ``snap_tol_m``.
    """
    if isinstance(curve, IrCompositeCurve3D):
        pts = _sample_composite(curve, length, tol_m, snap_tol_m)
    else:
        pts = sample_curve(curve, length, tol_m)
    if pts is None or len(pts) < 3:
        return None
    pts = _dedupe(pts)
    gap = np.linalg.norm(pts[0] - pts[-1])
    if gap <= snap_tol_m:
        pts = pts[:-1]
    else:
        logger.debug("Contour does not close: gap {:.4f} m", gap)
        return None
    if len(pts) < 3:
        return None
    return pts
