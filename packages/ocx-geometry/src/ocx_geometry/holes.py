"""Hole-shape profile generation and 3D placement for CutBy openings.

``parametric_profile`` turns an ``IrParametricHole`` into a closed (N, 2)
polygon in metres centred on the local origin; ``place_hole`` maps a 2D
profile onto its 3D placement frame (origin + primary/secondary axes).
"""
from __future__ import annotations

import numpy as np
from loguru import logger
from ocx_model_core.model.ir.catalogues import IrParametricHole
from ocx_model_core.model.ir.geometry import IrTransformation
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import box
from shapely.ops import unary_union

from ocx_geometry.measure import LengthResolver

_MIN_SEGMENTS = 12


def _circle_segments(r: float, tol: float) -> int:
    """Segment count so the sagitta of each chord stays below ``tol / 2``.

    The half-tolerance keeps the inscribed-polygon area deficit well inside
    the chordal tolerance as well (relative area error ~ (2*pi/n)**2 / 6).
    """
    sag = tol / 2.0
    if r <= sag:
        return _MIN_SEGMENTS
    return max(_MIN_SEGMENTS,
               int(np.ceil(2.0 * np.pi / (2.0 * np.arccos(1.0 - sag / r)))))


def _ring(poly) -> np.ndarray | None:
    """Exterior ring of a shapely polygon as an open (N, 2) array."""
    try:
        coords = np.asarray(poly.exterior.coords, dtype=np.float64)[:-1, :2]
    except Exception:  # noqa: BLE001 — degenerate geometry disqualifies itself
        return None
    return coords if len(coords) >= 3 else None


def parametric_profile(hole: IrParametricHole | None, length: LengthResolver,
                       tol: float) -> np.ndarray | None:
    """Closed (N, 2) polygon in metres, centred on the local origin, or None."""
    if hole is None:
        return None
    v = hole.variant

    if v == "parametric_circle":
        d = length.qty(hole.diameter)
        if not d or d <= 0:
            return None
        r = d / 2.0
        t = np.linspace(0.0, 2.0 * np.pi, _circle_segments(r, tol),
                        endpoint=False)
        return np.column_stack([r * np.cos(t), r * np.sin(t)])

    if v in ("ellipse", "super_elliptical"):
        a = length.qty(hole.major_diameter)
        b = length.qty(hole.minor_diameter)
        if not a or not b or a <= 0 or b <= 0:
            return None
        a, b = a / 2.0, b / 2.0
        e = 2.0
        if v == "super_elliptical" and hole.exponent is not None:
            e = hole.exponent.value or 2.0
        t = np.linspace(0.0, 2.0 * np.pi, _circle_segments(max(a, b), tol),
                        endpoint=False)
        c, s = np.cos(t), np.sin(t)
        return np.column_stack([a * np.sign(c) * np.abs(c) ** (2.0 / e),
                                b * np.sign(s) * np.abs(s) ** (2.0 / e)])

    if v in ("rectangular_hole", "symmetrical_hole"):
        h = length.qty(hole.height)
        w = length.qty(hole.width)
        if not h or not w or h <= 0 or w <= 0:
            return None
        if v == "symmetrical_hole":
            rf = min(h, w) / 2.0                       # stadium: semicircular ends
        else:
            rf = length.qty(hole.fillet_radius) or 0.0
        rf = min(rf, h / 2.0, w / 2.0)
        if rf <= 0.0:
            return _ring(box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0))
        q = max(2, _circle_segments(rf, tol) // 4)
        core = box(-(w / 2.0 - rf), -(h / 2.0 - rf), w / 2.0 - rf, h / 2.0 - rf)
        return _ring(core.buffer(rf, quad_segs=q))

    if v == "rectangular_mickey_mouse_ears":
        h = length.qty(hole.height)
        w = length.qty(hole.width)
        r = length.qty(hole.radius)
        disp = length.qty(hole.displacement) or 0.0
        if not h or not w or not r or h <= 0 or w <= 0 or r <= 0:
            return None
        q = max(2, _circle_segments(r, tol) // 4)
        cx, cy = w / 2.0 - disp, h / 2.0 - disp
        ears = [ShapelyPoint(sx * cx, sy * cy).buffer(r, quad_segs=q)
                for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        return _ring(unary_union(
            [box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0), *ears]))

    logger.debug("Unknown parametric hole variant {!r}", v)
    return None


def place_hole(profile_2d: np.ndarray,
               transformation: IrTransformation | None,
               length: LengthResolver) -> np.ndarray | None:
    """Map a local (N, 2) profile onto its 3D placement frame → (N, 3) metres."""
    if transformation is None or transformation.origin is None:
        return None
    p, s = transformation.primary_axis, transformation.secondary_axis
    if p is None or s is None:
        return None
    pv = np.array([p.x, p.y, p.z], dtype=np.float64)
    sv = np.array([s.x, s.y, s.z], dtype=np.float64)
    p_len = np.linalg.norm(pv)
    if p_len < 1e-12:
        return None
    pv /= p_len
    sv = sv - (sv @ pv) * pv                            # re-orthogonalize
    s_len = np.linalg.norm(sv)
    if s_len < 1e-12:
        return None
    sv /= s_len
    origin = length.point(transformation.origin)
    return (origin[None, :]
            + profile_2d[:, :1] * pv[None, :]
            + profile_2d[:, 1:2] * sv[None, :])
