"""Surface/plane intersection in metres (IR-independent).

``intersect_surface_plane`` returns the intersection of a parametrized
surface with a plane as 3D polylines restricted to a uv window.
"""
from __future__ import annotations

import numpy as np

from ocx_geometry.surfaces import PlaneParam, SurfaceParam

_PARALLEL_EPS = 1e-9

UVWindow = tuple[float, float, float, float]


def offset_plane(point, normal,
                 offset_m: float) -> tuple[np.ndarray, np.ndarray]:
    """``(point shifted offset_m along the unit normal, unit normal)``."""
    n = np.asarray(normal, dtype=float)
    length = float(np.linalg.norm(n))
    if length < 1e-12:
        raise ValueError("plane normal must be non-zero")
    n = n / length
    return np.asarray(point, dtype=float) + float(offset_m) * n, n


def intersect_surface_plane(param: SurfaceParam, point, normal,
                            uv_window: UVWindow,
                            tol_m: float) -> list[np.ndarray]:
    """Intersection of ``param`` with the plane through ``point`` with
    ``normal``, as (N, 3) polylines in metres (N >= 2) inside
    ``uv_window = (u0, u1, v0, v1)``. Empty list: no intersection."""
    window = tuple(float(x) for x in uv_window)
    u0, u1, v0, v1 = window
    if not np.all(np.isfinite(window)) or u1 <= u0 or v1 <= v0:
        raise ValueError(
            f"uv_window must be finite and non-empty, got {uv_window}")
    p, n = offset_plane(point, normal, 0.0)
    if isinstance(param, PlaneParam):
        return _plane_cut(param, p, n, window)
    raise NotImplementedError(
        f"no intersection for {type(param).__name__} yet")


def _plane_cut(param: PlaneParam, p: np.ndarray, n: np.ndarray,
               window: UVWindow) -> list[np.ndarray]:
    a = float(n @ param.u)
    b = float(n @ param.v)
    c = float(n @ (param.o - p))
    norm2 = a * a + b * b
    if norm2 < _PARALLEL_EPS ** 2:
        return []
    origin = -c / norm2 * np.array([a, b])
    direction = np.array([-b, a])
    span = _clip_line(origin, direction, window)
    if span is None:
        return []
    uv = np.array([origin + t * direction for t in span])
    return [param.evaluate(uv)]


def _clip_line(origin: np.ndarray, direction: np.ndarray,
               window: UVWindow) -> tuple[float, float] | None:
    """Liang–Barsky: ``(t0, t1)`` of ``origin + t * direction`` inside the
    window, or None when the line misses it."""
    u0, u1, v0, v1 = window
    t_lo, t_hi = -np.inf, np.inf
    for o, d, lo, hi in ((origin[0], direction[0], u0, u1),
                         (origin[1], direction[1], v0, v1)):
        if abs(d) < 1e-15:
            if o < lo or o > hi:
                return None
            continue
        ta, tb = sorted(((lo - o) / d, (hi - o) / d))
        t_lo, t_hi = max(t_lo, ta), min(t_hi, tb)
    if t_hi - t_lo <= 1e-12:
        return None
    return float(t_lo), float(t_hi)