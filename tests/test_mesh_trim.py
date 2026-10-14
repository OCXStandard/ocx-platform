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
