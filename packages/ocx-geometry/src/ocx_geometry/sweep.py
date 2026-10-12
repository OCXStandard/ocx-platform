"""Sweep a 2D section profile along a 3D trace polyline.

Frames per trace point come from (in priority order):
1. ``IrInclination`` web-direction hints (nearest hint by position, or the
   single hint applied everywhere),
2. projection-transport of an initial perpendicular (rotation-minimizing
   approximation) — never a Frenet frame.
"""
from __future__ import annotations

import mapbox_earcut
import numpy as np
from loguru import logger
from ocx_model_core.model.ir.structural import IrInclination

from ocx_geometry.curves import _any_perp


def _tangents(pts: np.ndarray) -> np.ndarray:
    t = np.gradient(pts, axis=0)
    n = np.linalg.norm(t, axis=1, keepdims=True)
    n[n < 1e-15] = 1.0
    return t / n


def _orthogonalize(web: np.ndarray, tangent: np.ndarray) -> np.ndarray | None:
    w = web - (web @ tangent) * tangent
    nn = np.linalg.norm(w)
    if nn < 1e-9:
        return None
    return w / nn


def _safe_unit(v: np.ndarray) -> np.ndarray | None:
    """Try to normalize v; return None if zero-length."""
    n = np.linalg.norm(v)
    if n < 1e-12:
        return None
    return v / n


def insert_trace_points(pts: np.ndarray, positions: np.ndarray,
                        tol: float = 1e-9) -> np.ndarray:
    """Insert each of ``positions`` (K,3) into polyline ``pts`` (N,3) at its
    nearest segment, preserving order.  Positions already present (within
    ``tol``) are not duplicated."""
    out = [np.asarray(p, dtype=float) for p in pts]
    for q in np.atleast_2d(np.asarray(positions, dtype=float)):
        arr = np.asarray(out)
        if np.linalg.norm(arr - q, axis=1).min() < tol:
            continue
        best_i, best_d = 0, np.inf
        for i in range(len(out) - 1):
            a, b = out[i], out[i + 1]
            ab = b - a
            ll = float(ab @ ab)
            t = 0.0 if ll < 1e-18 else float(np.clip((q - a) @ ab / ll, 0.0, 1.0))
            d = float(np.linalg.norm(q - (a + t * ab)))
            if d < best_d:
                best_i, best_d = i, d
        out.insert(best_i + 1, q)
    return np.asarray(out)


def _interp_hints(pts: np.ndarray, hints: list[np.ndarray],
                  positions: np.ndarray) -> np.ndarray:
    """Arc-length interpolation of positioned web-direction hints."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    hint_s = np.array([s[int(np.argmin(np.linalg.norm(pts - q, axis=1)))]
                       for q in positions])
    order = np.argsort(hint_s)
    hs = hint_s[order]
    hw = np.asarray(hints)[order]
    return np.column_stack([np.interp(s, hs, hw[:, k]) for k in range(3)])


def resolve_web_dirs(pts: np.ndarray,
                     inclinations: list[IrInclination],
                     incl_positions_m: np.ndarray | None = None) -> np.ndarray:
    """Per-point web directions, orthogonal to the trace tangent, unit length.

    ``incl_positions_m`` — optional (K,3) metre positions matching the
    inclination hints; when given, hints are interpolated along the trace
    arc length so the web rotates smoothly between sampled inclinations.
    """
    tangents = _tangents(pts)
    hints = [np.array([i.web_direction.x, i.web_direction.y, i.web_direction.z])
             for i in inclinations if i.web_direction is not None]

    interp = None
    if (len(hints) >= 2 and incl_positions_m is not None
            and len(incl_positions_m) == len(hints)):
        interp = _interp_hints(pts, hints, incl_positions_m)

    dirs = np.empty_like(pts)
    prev: np.ndarray | None = None
    for i, t in enumerate(tangents):
        t_norm = np.linalg.norm(t)
        # ISSUE 1: Handle zero-tangent case
        if t_norm < 1e-12:
            if prev is not None:
                dirs[i] = prev
            else:
                # Bootstrap with a default perpendicular
                perp = _any_perp(np.array([1.0, 0.0, 0.0]))
                dirs[i] = perp
            continue

        w = None
        if interp is not None:
            w = _orthogonalize(interp[i], t)
        elif hints:
            if incl_positions_m is not None and len(incl_positions_m) == len(hints):
                k = int(np.argmin(np.linalg.norm(incl_positions_m - pts[i], axis=1)))
                w = _orthogonalize(hints[k], t)
            else:
                w = _orthogonalize(hints[0], t)
        if w is None and prev is not None:            # transport previous frame
            w = _orthogonalize(prev, t)
        if w is None:                                 # bootstrap
            perp = _any_perp(t)
            cross = np.cross(t, perp)
            w = _safe_unit(cross)
            if w is None:
                # Degenerate case: use default
                w = _any_perp(t)
        dirs[i] = w
        prev = w
    return dirs


def _signed_area_2d(profile: np.ndarray) -> float:
    """Compute signed area of a 2D polygon (positive=CCW, negative=CW)."""
    x = profile[:, 0]
    y = profile[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def sweep_profile(pts: np.ndarray, web_dirs: np.ndarray,
                  profile: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    """Sweep ``profile`` (M,2) along ``pts`` (N,3); returns (verts, faces).

    Ring vertex = p + s*side + w*web, side = tangent x web.  Sides are
    quads split into triangles; both ends are capped (earcut of the profile).
    """
    n, m = len(pts), len(profile)
    if n < 2 or m < 3:
        return None

    # ISSUE 3: Check for NaN/infinite values early
    if not np.isfinite(pts).all():
        logger.warning("sweep_profile: pts contains NaN or infinite values")
        return None
    if not np.isfinite(web_dirs).all():
        logger.warning("sweep_profile: web_dirs contains NaN or infinite values")
        return None
    if not np.isfinite(profile).all():
        logger.warning("sweep_profile: profile contains NaN or infinite values")
        return None

    tangents = _tangents(pts)

    # ISSUE 1: Check for all-identical points (all tangents zero)
    if np.allclose(tangents, 0.0):
        logger.warning("sweep_profile: degenerate trace (all points identical)")
        return None

    # ISSUE B: Normalize profile winding to CCW (positive signed area)
    signed_area = _signed_area_2d(profile)
    if signed_area < 0:
        profile = profile[::-1]

    rings = []
    prev_side = None
    for i in range(n):
        w = web_dirs[i]
        t = tangents[i]
        t_norm = np.linalg.norm(t)

        # ISSUE 1: Handle zero-tangent at this point
        if t_norm < 1e-12:
            # ISSUE C: Build ring at this point using last valid side direction
            if prev_side is not None:
                rings.append(pts[i]
                             + np.outer(profile[:, 0], prev_side)
                             + np.outer(profile[:, 1], w))
            elif rings:
                # Fallback: reuse previous ring if no valid side yet
                rings.append(rings[-1].copy())
            else:
                # First point is degenerate; try to continue with next
                continue
        else:
            cross = np.cross(t, w)
            cross_norm = np.linalg.norm(cross)
            # ISSUE 1: Guard against cross product being zero
            if cross_norm < 1e-9:
                # Tangent and web are parallel; build ring using previous side or skip
                if prev_side is not None:
                    rings.append(pts[i]
                                 + np.outer(profile[:, 0], prev_side)
                                 + np.outer(profile[:, 1], w))
                elif rings:
                    rings.append(rings[-1].copy())
                else:
                    continue
            else:
                side = cross / cross_norm
                prev_side = side
                rings.append(pts[i]
                             + np.outer(profile[:, 0], side)
                             + np.outer(profile[:, 1], w))

    # If we ended up with fewer rings than expected, the trace is too degenerate
    if len(rings) < 2:
        logger.warning("sweep_profile: degenerate trace resulted in < 2 rings")
        return None

    verts = np.vstack(rings)

    faces: list[list[int]] = []
    for i in range(len(rings) - 1):
        a, b = i * m, (i + 1) * m
        for j in range(m):
            k = (j + 1) % m
            faces.append([a + j, b + j, b + k])
            faces.append([a + j, b + k, a + k])

    # ISSUE B: Profile is now always CCW after normalization; use single winding path
    cap = mapbox_earcut.triangulate_float64(
        profile.astype(np.float64), np.array([m], dtype=np.uint32))
    cap = np.asarray(cap, dtype=np.int64).reshape(-1, 3)

    # For CCW profile: start = cap (points -X), end = cap[:, ::-1] (points +X)
    start = cap
    end = cap[:, ::-1] + (len(rings) - 1) * m

    faces_arr = np.vstack([np.array(faces, dtype=np.int64), start, end])
    return verts, faces_arr
