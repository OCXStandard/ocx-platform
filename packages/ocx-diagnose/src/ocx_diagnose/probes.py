"""Cheap source-geometry probes over a panel's chart mesh and a plate's contour."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from ocx_diagnose.checks import _project_distance

_SAMPLES_PER_MEMBER = 6
_NEIGHBOUR_FACES = 8


def duplicate_members(chart, members: list, eps_m: float = 1e-3) -> list[tuple[int, int, int]]:
    """Member pairs (a, b, hits) whose surfaces coincide within ``eps_m``.

    Up to a few face centroids of each member are projected onto the members of
    the nearest other-member chart faces; a pair is a duplicate when at least
    half of a member's samples lie on the other surface.
    """
    if chart is None or chart.F is None or len(chart.F) == 0 or chart.tri_member is None:
        return []
    cent = chart.V[chart.F].mean(axis=1)
    owner = np.asarray(chart.tri_member)
    valid = np.flatnonzero(owner >= 0)
    if len(valid) == 0:
        return []
    tree = cKDTree(cent[valid])
    hits: dict[tuple[int, int], int] = {}
    nsamp: dict[int, int] = {}
    for a in np.unique(owner[valid]):
        faces = np.flatnonzero(owner == a)
        pick = faces[np.linspace(0, len(faces) - 1, min(_SAMPLES_PER_MEMBER, len(faces))).astype(int)]
        pts = cent[pick]
        nsamp[int(a)] = len(pts)
        k = min(_NEIGHBOUR_FACES, len(valid))
        _, near = tree.query(pts, k=k)
        near = np.atleast_2d(near.reshape(len(pts), k))
        for si in range(len(pts)):
            for b in {int(owner[valid[j]]) for j in near[si]} - {int(a)}:
                if b < len(members) and _project_distance(members[b], pts[si:si + 1])[0] < eps_m:
                    key = (int(a), b)
                    hits[key] = hits.get(key, 0) + 1
    out = []
    for (a, b), n in hits.items():
        if a < b and n >= max(2, nsamp[a] // 2) and hits.get((b, a), 0) >= max(2, nsamp[b] // 2):
            out.append((a, b, n))
    return sorted(out, key=lambda t: -t[2])


def degenerate_members(chart, min_area_m2: float = 1e-4) -> list[int]:
    """Members with no chart faces or a total chart area below ``min_area_m2``."""
    if chart is None or chart.F is None:
        return []
    area = np.zeros(chart.n_members)
    if len(chart.F):
        t = chart.V[chart.F]
        a = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        owner = np.asarray(chart.tri_member)
        ok = (owner >= 0) & (owner < chart.n_members)
        np.add.at(area, owner[ok], a[ok])
    return [int(i) for i in np.flatnonzero(area < min_area_m2)]


@dataclass
class ContourProbe:
    touching: int       # non-adjacent contour points closer than 1e-6 m


def contour_probe(contour) -> ContourProbe:
    """Self-contact of a trim contour (k, 3); the ring is implicitly closed."""
    c = None if contour is None else np.asarray(contour, float)
    if c is None or len(c) < 4:
        return ContourProbe(0)
    pairs = cKDTree(c).query_pairs(1e-6, output_type="ndarray")
    n = len(c)
    touching = int(sum(1 for i, j in pairs if (j - i) > 1 and (j - i) < n - 1))
    return ContourProbe(touching)
