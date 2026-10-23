"""Planar bracket tessellation.

Brackets are planar parts: an outer contour on a plane (given in the
model or fitted here), optionally extruded by the plate thickness into
a closed prism. No hole support — no known model cuts brackets.
"""
from __future__ import annotations

import mapbox_earcut
import numpy as np

# contour points may deviate this many tolerance-multiples from the
# plane before the bracket is rejected as non-planar
_PLANARITY_FACTOR = 5.0


def _fit_plane(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Best-fit (origin, unit normal) through ``pts`` via SVD."""
    origin = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - origin)
    return origin, vt[2]


def tessellate_bracket(contour: np.ndarray,
                       plane: tuple[np.ndarray, np.ndarray] | None,
                       thickness_m: float | None,
                       offset_m: float | None,
                       tol: float
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Tessellate one bracket.

    ``contour`` — (N, 3) closed loop in metres, no repeated last point
    required. ``plane`` — optional (point, normal); fitted from the
    contour when absent. ``thickness_m`` — extrude into a prism when
    given, else emit a flat sheet. ``offset_m`` — base-face offset along
    the plane normal; symmetric (−t/2) when ``None``.

    Returns ``(vertices, triangles, normals)`` or ``None`` for
    degenerate or non-planar contours.
    """
    pts = np.asarray(contour, dtype=np.float64)
    if len(pts) >= 2 and np.linalg.norm(pts[0] - pts[-1]) < 1e-12:
        pts = pts[:-1]
    if len(pts) < 3:
        return None

    normal = None
    if plane is not None:
        origin = np.asarray(plane[0], dtype=np.float64)
        normal = np.asarray(plane[1], dtype=np.float64)
        ln = np.linalg.norm(normal)
        normal = normal / ln if ln > 1e-12 else None
    if normal is None:
        origin, normal = _fit_plane(pts)

    # planarity: spread of signed distances about their mean (the mean
    # absorbs a contour authored offset from the stated plane)
    d = (pts - origin) @ normal
    if np.max(np.abs(d - d.mean())) > max(_PLANARITY_FACTOR * tol, 1e-3):
        return None
    base_origin = origin + d.mean() * normal

    # 2-D frame in the contour plane; (e1, e2, normal) is right-handed
    # since e2 = normal x e1 implies e1 x e2 = normal.
    tmp = np.array([1.0, 0.0, 0.0])
    if abs(normal[0]) > 0.9:
        tmp = np.array([0.0, 1.0, 0.0])
    e1 = np.cross(normal, tmp)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    rel = pts - base_origin
    xy = np.column_stack([rel @ e1, rel @ e2])

    # enforce CCW winding about the normal (walls face outward below);
    # shoelace written out to avoid np.cross 2-D deprecation
    nxt_xy = np.roll(xy, -1, axis=0)
    area2 = float((xy[:, 0] * nxt_xy[:, 1] - nxt_xy[:, 0] * xy[:, 1]).sum())
    if abs(area2) < 1e-9:
        return None
    if area2 < 0.0:
        xy = xy[::-1]

    tris = np.asarray(
        mapbox_earcut.triangulate_float64(
            xy, np.array([len(xy)], dtype=np.uint32)),
        dtype=np.int64).reshape(-1, 3)
    if len(tris) == 0:
        return None

    ring = base_origin + xy[:, :1] * e1 + xy[:, 1:] * e2
    m = len(ring)

    if thickness_m is None or thickness_m <= 0.0:
        # flat sheet
        normals = np.tile(normal, (m, 1))
        return ring, tris, normals

    base = offset_m if offset_m is not None else -thickness_m / 2.0
    bot = ring + base * normal
    top = ring + (base + thickness_m) * normal

    verts = [bot, top]
    norms = [np.tile(-normal, (m, 1)), np.tile(normal, (m, 1))]
    # caps: bottom reversed so it faces -normal, top as triangulated
    faces = [tris[:, ::-1], tris + m]
    nxt = 2 * m
    # walls: one quad (two triangles) per contour edge, flat normals
    for i in range(m):
        j = (i + 1) % m
        edge = ring[j] - ring[i]
        wn = np.cross(edge, normal)
        wl = np.linalg.norm(wn)
        if wl < 1e-15:
            continue
        wn = wn / wl
        quad = np.array([bot[i], bot[j], top[j], top[i]])
        verts.append(quad)
        norms.append(np.tile(wn, (4, 1)))
        faces.append(np.array([[nxt, nxt + 1, nxt + 2],
                               [nxt, nxt + 2, nxt + 3]]))
        nxt += 4

    return np.vstack(verts), np.vstack(faces), np.vstack(norms)
