"""Surface/plane intersection in metres (IR-independent).

``intersect_surface_plane`` returns the intersection of a parametrized
surface with a plane as 3D polylines restricted to a uv window.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from ocx_geometry.surfaces import PlaneParam, SurfaceParam

_PARALLEL_EPS = 1e-9
_DEFAULT_CELLS = 200
_MIN_CELLS = 8
_MAX_CELLS = 1000

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
    return _marching_cut(param, p, n, window, tol_m)


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


def _cells(span_uv: float, scale: float, edge_m: float | None) -> int:
    if edge_m is None or edge_m <= 0:
        return _DEFAULT_CELLS
    return int(np.clip(np.ceil(span_uv * scale / edge_m),
                       _MIN_CELLS, _MAX_CELLS))


def _marching_cut(param: SurfaceParam, p: np.ndarray, n: np.ndarray,
                  window: UVWindow, tol_m: float) -> list[np.ndarray]:
    u0, u1, v0, v1 = window
    su, sv = param.uv_scale()
    edge = param.max_edge_m(tol_m)
    us = np.linspace(u0, u1, _cells(u1 - u0, su, edge) + 1)
    vs = np.linspace(v0, v1, _cells(v1 - v0, sv, edge) + 1)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    pts = param.evaluate(np.column_stack([uu.ravel(), vv.ravel()]))
    f = ((pts - p) @ n).reshape(uu.shape)
    segments = _contour_segments(f)
    if not segments:
        return []

    def uv_at(key: tuple[str, int, int]) -> np.ndarray:
        kind, i, j = key
        i2, j2 = (i + 1, j) if kind == "u" else (i, j + 1)
        t = f[i, j] / (f[i, j] - f[i2, j2])
        return np.array([uu[i, j] + t * (uu[i2, j2] - uu[i, j]),
                         vv[i, j] + t * (vv[i2, j2] - vv[i, j])])

    return [param.evaluate(np.array([uv_at(k) for k in chain]))
            for chain in _link(segments)]


def _contour_segments(f: np.ndarray) -> list[tuple[tuple, tuple]]:
    """Marching-squares segments as pairs of grid-edge keys."""
    pos = f >= 0.0
    bottom = pos[:-1, :-1] != pos[1:, :-1]
    top = pos[:-1, 1:] != pos[1:, 1:]
    left = pos[:-1, :-1] != pos[:-1, 1:]
    right = pos[1:, :-1] != pos[1:, 1:]
    segments = []
    for i, j in np.argwhere(bottom | top | left | right):
        i, j = int(i), int(j)
        keys = {"b": ("u", i, j), "r": ("v", i + 1, j),
                "t": ("u", i, j + 1), "l": ("v", i, j)}
        cut = [k for k, mask in (("b", bottom), ("r", right),
                                 ("t", top), ("l", left)) if mask[i, j]]
        if len(cut) == 2:
            segments.append((keys[cut[0]], keys[cut[1]]))
            continue
        centre = 0.25 * (f[i, j] + f[i + 1, j] + f[i + 1, j + 1] + f[i, j + 1])
        if (centre >= 0.0) == pos[i, j]:
            pairs = (("b", "r"), ("t", "l"))
        else:
            pairs = (("b", "l"), ("r", "t"))
        segments.extend((keys[a], keys[b]) for a, b in pairs)
    return segments


def _link(segments: list[tuple[tuple, tuple]]) -> list[list[tuple]]:
    """Chain segments sharing edge keys: open chains first, then loops."""
    adj: dict[tuple, list[tuple]] = defaultdict(list)
    for a, b in segments:
        adj[a].append(b)
        adj[b].append(a)

    def walk(start: tuple) -> list[tuple]:
        chain = [start]
        cur = start
        while adj[cur]:
            nxt = adj[cur].pop()
            adj[nxt].remove(cur)
            chain.append(nxt)
            cur = nxt
            if nxt == start:
                break
        return chain

    chains = [walk(k) for k in [k for k, nb in adj.items() if len(nb) == 1]
              if adj[k]]
    for k in list(adj):
        while adj[k]:
            chains.append(walk(k))
    return chains
