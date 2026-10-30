from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from ocx_geometry.mesh_trim import MeshTrimmer


def _grid(n=20, size=10.0):
    xs = np.linspace(0, size, n + 1)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    V = np.column_stack([X.ravel(), Y.ravel(), 0.1 * X.ravel() ** 2 / size])
    F = []
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b, c, d = a + 1, a + n + 1, a + n + 2
            F += [[a, c, b], [b, c, d]]
    return V, np.array(F)


def _square(x0, x1, y0, y1):
    xs = np.array([x0, x1, x1, x0])
    ys = np.array([y0, y0, y1, y1])
    return np.column_stack([xs, ys, 0.1 * xs ** 2 / 10.0])


def _area(V, F):
    a = V[F[:, 1]] - V[F[:, 0]]
    b = V[F[:, 2]] - V[F[:, 0]]
    return float(np.linalg.norm(np.cross(a, b), axis=1).sum() / 2)


class TestMeshTrim:
    def test_region_inside_ring(self):
        V, F = _grid()
        tr = MeshTrimmer(V, F, 0.05)
        out = tr.trim(_square(2.3, 6.7, 3.1, 7.9), [],
                      seed=np.array([4.0, 5.0, 0.16]))
        assert out is not None
        v, f, n = out
        assert v[:, 0].min() == pytest.approx(2.3, abs=1e-3)
        assert v[:, 0].max() == pytest.approx(6.7, abs=1e-3)
        assert v[:, 1].min() == pytest.approx(3.1, abs=1e-3)
        assert v[:, 1].max() == pytest.approx(7.9, abs=1e-3)
        assert _area(v, f) > 4.4 * 4.8 * 0.99

    def test_hole_removed(self):
        V, F = _grid()
        tr = MeshTrimmer(V, F, 0.05)
        outer = _square(1.0, 9.0, 1.0, 9.0)
        full = tr.trim(outer, [], seed=np.array([2.0, 2.0, 0.0]))
        holed = tr.trim(outer, [_square(4.1, 5.9, 4.1, 5.9)],
                        seed=np.array([2.0, 2.0, 0.0]))
        assert _area(*holed[:2]) < _area(*full[:2]) - 1.7 ** 2

    def test_ring_off_mesh_returns_none(self):
        V, F = _grid()
        tr = MeshTrimmer(V, F, 0.05)
        ring = _square(2, 4, 2, 4) + np.array([0, 0, 5.0])
        assert tr.trim(ring, []) is None


def _seam_edges(v, f, tol=3e-3):
    """Boundary edges whose midpoint lies on another boundary edge —
    unwelded seams and T-junctions."""
    e = np.sort(f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    cnt = Counter(map(tuple, e))
    bnd = [k for k, c in cnt.items() if c == 1]

    def dist(p, a, b):
        ab = b - a
        t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
        return float(np.linalg.norm(p - (a + t * ab)))

    bad = []
    for a, b in bnd:
        if np.linalg.norm(v[b] - v[a]) < 0.01:
            continue
        mid = (v[a] + v[b]) / 2
        for c, d in bnd:
            if (c, d) == (a, b):
                continue
            if dist(mid, v[c], v[d]) < tol:
                bad.append(((a, b), (c, d)))
                break
    return bad


class TestSeamWelding:
    """Cuts crossing a shared chart edge must not leave free-edge seams.

    ``_cut`` pulls cut ends that fall just short of a face border onto
    that border independently in each face's 2-D frame.  Across a
    dihedral (e.g. the hull's flat-of-side tangent line) the pulled
    points differ by up to a couple of millimetres per side, so the
    exact-duplicate weld in ``_assemble`` cannot merge them, leaving
    coincident boundary edges that CAD viewers draw as skew lines.
    """

    def test_cut_across_dihedral_leaves_no_seam_edges(self):
        ang = np.radians(2.0)
        axis = np.array([20.0, 10.0, 0.0])
        axis /= np.linalg.norm(axis)
        # fold the upper triangle about the shared diagonal by 2 deg
        p = np.array([0.0, 10.0, 0.0])
        folded = (p * np.cos(ang) + np.cross(axis, p) * np.sin(ang)
                  + axis * (axis @ p) * (1 - np.cos(ang)))
        V = np.array([[0, 0, 0], [20, 0, 0], [20, 10, 0], folded])
        F = np.array([[0, 1, 2], [0, 2, 3]])
        # ring points slightly off-surface, as sampled contours are
        ring = np.array([[2, 2, 5e-4], [18, 2, 5e-4],
                         [18, 8, 5e-4], [2, 8, 5e-4]])
        out = MeshTrimmer(V, F, 0.05).trim(ring, [])
        assert out is not None
        v, f, _ = out
        assert _seam_edges(v, f) == []


def _ring_area(ring):
    return 0.5 * float(np.linalg.norm(
        np.cross(ring, np.roll(ring, -1, axis=0)).sum(axis=0)))


class TestSliverChartSide:
    """Regression (tr05_tc18 ropax, plates nplcid8174/nplcid8568): on a
    coarse chart of 60-80 m sliver triangles, far-away outside pieces were
    assigned their side from a clipped segment end, out-voted the correct
    pieces, and the whole 5143 m2 superstructure side was kept as plate."""

    FIXTURE = (Path(__file__).parent / "data" / "mesh_trim"
               / "ropax_superstructure_side.npz")

    @pytest.mark.parametrize("suffix", ["", "2"])
    def test_unseeded_trim_keeps_only_the_ring_region(self, suffix):
        d = np.load(self.FIXTURE)
        V, F, ring = d["V" + suffix], d["F" + suffix], d["ring" + suffix]
        out = MeshTrimmer(V, F, 0.05).trim(ring, [], None)
        assert out is not None
        v, f, _ = out
        assert _area(v, f) == pytest.approx(_ring_area(ring), rel=0.02)
        lo, hi = ring.min(axis=0) - 0.05, ring.max(axis=0) + 0.05
        assert np.all((v >= lo) & (v <= hi))


class TestUncutBridge:
    """Regression (tr05_tc18 ropax): a face the ring never cuts, yet lying
    on an edge the ring crosses, joined the inside and outside pieces into
    one component and the whole chart was kept.  ``deck`` (nplcid5964):
    two member sheets overlap and the ring jumps between them, leaving a
    straddling face of the first sheet uncut.  ``shell`` (nplcid4241,
    chart cropped around the ring): a folded sliver on a non-manifold edge
    the ring crosses.  Areas are compared as vector areas, which match the
    ring's exactly for a trimmed curved surface (the shell is curved)."""

    FIXTURE = (Path(__file__).parent / "data" / "mesh_trim"
               / "ropax_uncut_bridge.npz")

    @pytest.mark.parametrize("key", ["deck", "shell"])
    def test_unseeded_trim_keeps_only_the_ring_region(self, key):
        d = np.load(self.FIXTURE)
        V, F, ring = d["V_" + key], d["F_" + key], d["ring_" + key]
        out = MeshTrimmer(V, F, 0.05).trim(ring, [], None)
        assert out is not None
        v, f, _ = out
        t = v[f]
        vector_area = 0.5 * float(np.linalg.norm(np.cross(
            t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]).sum(axis=0)))
        assert vector_area == pytest.approx(_ring_area(ring), rel=0.02)
        assert _area(v, f) < 1.1 * _ring_area(ring)
