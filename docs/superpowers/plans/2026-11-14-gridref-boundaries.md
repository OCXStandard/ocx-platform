# GridRef Panel Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OCX-TOP-001 checks closure of panels bounded by `GridRef`s (today reported *unchecked*) by intersecting the panel's support surface with the — optionally offset — grid planes.

**Architecture:** ocx-geometry gets two IR-independent modules: `grid.py` (axis + location → plane) and `intersect.py` (surface ∩ plane → 3D polylines; analytic for planes, marching squares otherwise), plus `SurfaceParam.uv_domain()`. ocx-rules' `GeometryContext` synthesizes planes for location-only ref planes, resolves GridRef planes (with `Offset`) and computes a panel uv window. A new check module `limited_by_region.py` builds a planar arrangement of all boundaries in uv (shapely `unary_union` + `polygonize`) and picks the face containing a seed point inside the panel's OuterContour; TOP-001 routes panels with any GridRef through it.

**Tech Stack:** Python 3.12, numpy, shapely ≥ 2.2 (already an ocx-geometry dependency), pytest, ruff, uv workspace.

**Spec:** `docs/superpowers/specs/2026-11-14-gridref-boundaries-design.md`

---

## Conventions for every task

- Work in the worktree `C:\PythonDev\ocx-platform\.worktrees\gridref-boundaries`
  (branch `feat/gridref-boundaries`). Every shell command below starts with
  `cd C:\PythonDev\ocx-platform\.worktrees\gridref-boundaries;` (PowerShell).
- Run tests with `uv run pytest <path> -q`; lint with
  `uv run ruff check packages tests`.
- Commit only the files the task names (`git add <paths>`), and end every
  commit message with the trailer line
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- All geometry inside ocx-geometry is in metres. IR coordinates carry units
  (`IrPoint3D.unit`, `Quantity.unit`); convert with `LengthResolver` /
  `GeometryContext.to_si`.

## File structure

| File | Responsibility |
| --- | --- |
| Create `packages/ocx-geometry/src/ocx_geometry/grid.py` | `grid_plane(axis, location)` → axis-aligned plane |
| Create `packages/ocx-geometry/src/ocx_geometry/intersect.py` | `offset_plane`, `intersect_surface_plane` (analytic plane path + marching squares) |
| Modify `packages/ocx-geometry/src/ocx_geometry/surfaces.py` | `SurfaceParam.uv_domain()` (base, `ExtrudedParam`, `NurbsSurfaceParam`) |
| Modify `packages/ocx-rules/src/ocx_rules/geometry_context.py` | `ref_plane_axis`, grid-plane synthesis in `panel_surface`, `grid_ref_plane`, `panel_uv_window` |
| Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/limited_by_region.py` | `boundary_reasons` formatter + `grid_panel_outcome` arrangement path |
| Modify `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py` | TOP-001 routes GridRef panels to `grid_panel_outcome`; uses `boundary_reasons` |
| Create `tests/test_geometry_intersect.py` | grid/offset/intersection known-answer tests |
| Modify `tests/test_render_surfaces_ext.py` | `uv_domain` tests |
| Create `tests/test_rules_geometry_context_grid.py` | GeometryContext grid tests |
| Create `tests/test_rules_limited_by_region.py` | TOP-001 GridRef panel tests |
| Modify `tests/test_rules_checks_topology.py:117-127` | GridRef reason test now expects "dangling" |
| Modify `packages/ocx-geometry/CHANGELOG.md`, `packages/ocx-rules/CHANGELOG.md` | changelog entries |

---

### Task 1: `grid_plane` and `offset_plane`

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/grid.py`
- Create: `packages/ocx-geometry/src/ocx_geometry/intersect.py`
- Test: `tests/test_geometry_intersect.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_geometry_intersect.py`:

```python
"""Tests for ocx_geometry.grid and ocx_geometry.intersect."""
from __future__ import annotations

import numpy as np
import pytest
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import offset_plane


class TestGridPlane:
    @pytest.mark.parametrize(("axis", "normal"), [
        ("x", [1.0, 0.0, 0.0]),
        ("y", [0.0, 1.0, 0.0]),
        ("z", [0.0, 0.0, 1.0]),
    ])
    def test_positive_axis_normal_and_point_at_location(self, axis, normal):
        point, n = grid_plane(axis, 2.5)
        np.testing.assert_allclose(n, normal)
        np.testing.assert_allclose(point, 2.5 * np.array(normal))

    def test_unknown_axis_raises(self):
        with pytest.raises(ValueError, match="axis"):
            grid_plane("w", 1.0)


class TestOffsetPlane:
    def test_normalizes_and_shifts_along_normal(self):
        point, n = offset_plane([0.0, 0.0, 1.0], [0.0, 0.0, 2.0], 0.05)
        np.testing.assert_allclose(n, [0.0, 0.0, 1.0])
        np.testing.assert_allclose(point, [0.0, 0.0, 1.05])

    def test_negative_offset_moves_against_normal(self):
        point, _ = offset_plane([1.0, 0.0, 0.0], [1.0, 0.0, 0.0], -0.25)
        np.testing.assert_allclose(point, [0.75, 0.0, 0.0])

    def test_zero_normal_raises(self):
        with pytest.raises(ValueError, match="normal"):
            offset_plane([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_geometry_intersect.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'ocx_geometry.grid'`.

- [ ] **Step 3: Write the implementation**

Create `packages/ocx-geometry/src/ocx_geometry/grid.py`:

```python
"""Grid reference planes: an axis-aligned plane from an axis and a location."""
from __future__ import annotations

import numpy as np

_AXES = {"x": 0, "y": 1, "z": 2}


def grid_plane(axis: str, location: float) -> tuple[np.ndarray, np.ndarray]:
    """``(point, unit_normal)`` of the grid plane ``axis = location``.

    The normal is the positive axis (the ocx-render convention); the point
    is ``location`` along it, in the same length unit as ``location``.
    """
    try:
        k = _AXES[axis]
    except KeyError:
        raise ValueError(
            f"unknown grid axis {axis!r}; expected 'x', 'y' or 'z'") from None
    normal = np.zeros(3)
    normal[k] = 1.0
    return float(location) * normal, normal
```

Create `packages/ocx-geometry/src/ocx_geometry/intersect.py`:

```python
"""Surface/plane intersection in metres (IR-independent)."""
from __future__ import annotations

import numpy as np


def offset_plane(point, normal,
                 offset_m: float) -> tuple[np.ndarray, np.ndarray]:
    """``(point shifted offset_m along the unit normal, unit normal)``."""
    n = np.asarray(normal, dtype=float)
    length = float(np.linalg.norm(n))
    if length < 1e-12:
        raise ValueError("plane normal must be non-zero")
    n = n / length
    return np.asarray(point, dtype=float) + float(offset_m) * n, n
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_geometry_intersect.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-geometry/src/ocx_geometry/grid.py packages/ocx-geometry/src/ocx_geometry/intersect.py tests/test_geometry_intersect.py
git commit -m "feat(geometry): grid_plane and offset_plane" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: `SurfaceParam.uv_domain()`

Needed because `NurbsSurfaceParam.evaluate` and `ExtrudedParam.evaluate`
clamp uv to their domain; a uv window must not extend past it. `bounds()`
cannot be used: it is a 3D box.

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/surfaces.py` (base class
  after `bounds()` ≈ line 77; `ExtrudedParam` after `inverse` ≈ line 319;
  `NurbsSurfaceParam` after `bounds()` ≈ line 374)
- Test: `tests/test_render_surfaces_ext.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_render_surfaces_ext.py` add to `class TestExtruded` (after
`test_roundtrip`):

```python
    def test_uv_domain_is_base_length_by_unbounded_sweep(self):
        u0, u1, v0, v1 = self.make().uv_domain()
        assert (u0, v0, v1) == (0.0, -np.inf, np.inf)
        assert u1 == pytest.approx(4.0)
```

add to `class TestNurbs` (after `test_flat_patch_roundtrip`):

```python
    def test_uv_domain_is_knot_domain(self):
        param = make_param(flat_nurbs_surface(), LR, tol_m=0.01)
        assert param.uv_domain() == (0.0, 1.0, 0.0, 1.0)
```

and at the end of the file:

```python
def test_analytic_surfaces_have_no_uv_domain():
    from ocx_geometry.surfaces import CylinderParam, PlaneParam
    z = np.array([0.0, 0.0, 1.0])
    assert PlaneParam(np.zeros(3), z).uv_domain() is None
    assert CylinderParam(np.zeros(3), z, 1.0).uv_domain() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render_surfaces_ext.py -q -k uv_domain`
Expected: 3 failed with `AttributeError: ... has no attribute 'uv_domain'`.

- [ ] **Step 3: Write the implementation**

In `surfaces.py`, `class SurfaceParam`, directly after `bounds()`:

```python
    def uv_domain(self) -> tuple[float, float, float, float] | None:
        """``(u0, u1, v0, v1)`` parameter domain (entries may be ±inf);
        None when the parametrization is unbounded in both directions."""
        return None
```

In `class ExtrudedParam`, directly after `inverse()`:

```python
    def uv_domain(self):
        return (0.0, float(self.s[-1]), -np.inf, np.inf)
```

In `class NurbsSurfaceParam`, directly after `bounds()`:

```python
    def uv_domain(self):
        return (float(self.du[0]), float(self.du[1]),
                float(self.dv[0]), float(self.dv[1]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_surfaces_ext.py -q`
Expected: all pass (3 new).

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-geometry/src/ocx_geometry/surfaces.py tests/test_render_surfaces_ext.py
git commit -m "feat(geometry): SurfaceParam.uv_domain" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: `intersect_surface_plane` — analytic plane path

For a `PlaneParam` with origin `o` and in-plane axes `U`, `V`, the cutting
plane `n · (x − p) = 0` becomes the uv line `a·u + b·v + c = 0` with
`a = n·U`, `b = n·V`, `c = n·(o − p)`. `hypot(a, b) = |n × n_surface|`, so
`hypot(a, b) < 1e-9` means parallel planes. The infinite line is clipped
to the window with Liang–Barsky.

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/intersect.py`
- Test: `tests/test_geometry_intersect.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_geometry_intersect.py` (add
`from ocx_geometry.intersect import intersect_surface_plane` and
`from ocx_geometry.surfaces import PlaneParam` to the imports):

```python
_X = np.array([1.0, 0.0, 0.0])
_Z = np.array([0.0, 0.0, 1.0])
_UNIT_WINDOW = (0.0, 1.0, 0.0, 1.0)


def _xy_plane() -> PlaneParam:
    """z = 0 with u = x, v = y."""
    return PlaneParam(np.zeros(3), _Z, _X)


class TestPlaneCut:
    def test_plane_cut_gives_clipped_line(self):
        (line,) = intersect_surface_plane(
            _xy_plane(), [0.5, 0.0, 0.0], _X, _UNIT_WINDOW, 0.001)
        np.testing.assert_allclose(
            sorted(map(tuple, line)), [(0.5, 0.0, 0.0), (0.5, 1.0, 0.0)],
            atol=1e-12)

    def test_parallel_planes_give_nothing(self):
        assert intersect_surface_plane(
            _xy_plane(), [0.0, 0.0, 1.0], _Z, _UNIT_WINDOW, 0.001) == []

    def test_offset_shifts_the_line(self):
        point, normal = offset_plane([0.5, 0.0, 0.0], _X, 0.25)
        (line,) = intersect_surface_plane(
            _xy_plane(), point, normal, _UNIT_WINDOW, 0.001)
        np.testing.assert_allclose(line[:, 0], [0.75, 0.75], atol=1e-12)

    def test_line_outside_window_gives_nothing(self):
        assert intersect_surface_plane(
            _xy_plane(), [2.0, 0.0, 0.0], _X, _UNIT_WINDOW, 0.001) == []

    def test_diagonal_line_clipped_to_window_corners(self):
        (line,) = intersect_surface_plane(
            _xy_plane(), [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], _UNIT_WINDOW,
            0.001)
        np.testing.assert_allclose(
            sorted(map(tuple, line)), [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
            atol=1e-12)

    def test_empty_or_infinite_window_raises(self):
        with pytest.raises(ValueError, match="uv_window"):
            intersect_surface_plane(_xy_plane(), [0.5, 0, 0], _X,
                                    (0.0, 0.0, 0.0, 1.0), 0.001)
        with pytest.raises(ValueError, match="uv_window"):
            intersect_surface_plane(_xy_plane(), [0.5, 0, 0], _X,
                                    (0.0, np.inf, 0.0, 1.0), 0.001)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_geometry_intersect.py -q`
Expected: collection error `ImportError: cannot import name 'intersect_surface_plane'`.

- [ ] **Step 3: Write the implementation**

Replace `packages/ocx-geometry/src/ocx_geometry/intersect.py` with:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_geometry_intersect.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-geometry/src/ocx_geometry/intersect.py tests/test_geometry_intersect.py
git commit -m "feat(geometry): analytic plane/plane intersection" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: `intersect_surface_plane` — marching squares for other surfaces

Signed distance `f(u, v) = n · (S(u, v) − p)` on a regular uv grid; cells
whose corners change sign get a segment between interpolated edge points.
Edge keys: `("u", i, j)` is the grid edge `(i, j)–(i+1, j)`, `("v", i, j)`
is `(i, j)–(i, j+1)`. Cell `(i, j)` has bottom `("u", i, j)`, right
`("v", i+1, j)`, top `("u", i, j+1)`, left `("v", i, j)`. Saddle (4
crossings): if the cell-centre mean has the same sign as corner `(i, j)`,
pair bottom–right and top–left, else bottom–left and right–top. Every
edge key is shared by at most two segments, so linking is a walk over an
adjacency dict: open chains (start at degree-1 keys) first, then closed
loops. Grid step: `max_edge_m(tol_m)` converted with `uv_scale()`
(fallback 200 cells), clamped to 8…1000 cells per axis.

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/intersect.py`
- Test: `tests/test_geometry_intersect.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_geometry_intersect.py` (add `CylinderParam` to the
`ocx_geometry.surfaces` import):

```python
def _cylinder() -> CylinderParam:
    """Radius 1 m, axis z through the origin; u = angle, v = z."""
    return CylinderParam(np.zeros(3), _Z, 1.0)


class TestMarchingCut:
    def test_plane_through_axis_gives_two_lines(self):
        cyl = _cylinder()
        # plane spanned by the axis and cyl.x: zeros at u = 0 and u = pi
        lines = intersect_surface_plane(cyl, np.zeros(3), cyl.y,
                                        (-1.0, 4.0, 0.0, 1.0), 0.001)
        assert len(lines) == 2
        for line in lines:
            np.testing.assert_allclose(line @ cyl.y, 0.0, atol=1e-3)
            np.testing.assert_allclose(
                np.hypot(line[:, 0], line[:, 1]), 1.0, atol=1e-9)
            assert line[:, 2].min() == pytest.approx(0.0)
            assert line[:, 2].max() == pytest.approx(1.0)
        sides = sorted(float((line @ cyl.x).mean()) for line in lines)
        np.testing.assert_allclose(sides, [-1.0, 1.0], atol=1e-3)

    def test_plane_across_axis_gives_one_circle(self):
        (line,) = intersect_surface_plane(
            _cylinder(), [0.0, 0.0, 1.0], _Z, (-np.pi, np.pi, 0.0, 2.0),
            0.001)
        np.testing.assert_allclose(line[:, 2], 1.0, atol=1e-9)
        np.testing.assert_allclose(
            np.hypot(line[:, 0], line[:, 1]), 1.0, atol=1e-9)
        # spans the whole periodic window: ends meet in 3D
        assert np.linalg.norm(line[0] - line[-1]) < 1e-9
        assert len(line) > 8

    def test_plane_outside_window_gives_nothing(self):
        assert intersect_surface_plane(
            _cylinder(), [0.0, 0.0, 1.0], _Z, (-np.pi, np.pi, 2.0, 3.0),
            0.001) == []

    def test_tilted_plane_gives_one_chain_on_the_plane(self):
        # cylinder axis x, tilted plane through the origin: an ellipse that
        # spans the whole periodic u window -> one chain
        cyl = CylinderParam(np.zeros(3), _X, 1.0)
        normal = np.array([1.0, 0.0, 0.1])
        (line,) = intersect_surface_plane(
            cyl, np.zeros(3), normal, (-np.pi, np.pi, -5.0, 5.0), 0.001)
        np.testing.assert_allclose(line @ normal, 0.0, atol=2e-3)


class TestMarchingInternals:
    def test_saddle_resolved_by_cell_centre(self):
        from ocx_geometry.intersect import _contour_segments
        f = np.array([[1.0, -1.0], [-1.0, 1.0]])  # centre 0 -> same as (0, 0)
        assert _contour_segments(f) == [
            (("u", 0, 0), ("v", 1, 0)), (("u", 0, 1), ("v", 0, 0))]

    def test_link_closes_loops(self):
        from ocx_geometry.intersect import _link
        (chain,) = _link([("a", "b"), ("b", "c"), ("c", "a")])
        assert len(chain) == 4 and chain[0] == chain[-1]
        assert set(chain) == {"a", "b", "c"}

    def test_link_open_chain_starts_at_an_end(self):
        from ocx_geometry.intersect import _link
        (chain,) = _link([("a", "b"), ("b", "c")])
        assert chain in (["a", "b", "c"], ["c", "b", "a"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_geometry_intersect.py -q -k Marching`
Expected: 7 failed — the four `TestMarchingCut` tests with
`NotImplementedError: no intersection for CylinderParam yet`, the three
`TestMarchingInternals` tests with `ImportError: cannot import name ...`.

- [ ] **Step 3: Write the implementation**

In `intersect.py`:

1. Add `from collections import defaultdict` below `from __future__ import annotations`.
2. Add these constants below `_PARALLEL_EPS = 1e-9`:

```python
_DEFAULT_CELLS = 200
_MIN_CELLS = 8
_MAX_CELLS = 1000
```

3. In `intersect_surface_plane` replace

```python
    raise NotImplementedError(
        f"no intersection for {type(param).__name__} yet")
```

with

```python
    return _marching_cut(param, p, n, window, tol_m)
```

4. Append to the end of the module:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_geometry_intersect.py -q`
Expected: `20 passed`.

- [ ] **Step 5: Lint and commit**

Run: `uv run ruff check packages/ocx-geometry tests/test_geometry_intersect.py`
Expected: `All checks passed!`

```powershell
git add packages/ocx-geometry/src/ocx_geometry/intersect.py tests/test_geometry_intersect.py
git commit -m "feat(geometry): marching-squares surface/plane intersection" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: GeometryContext — grid-plane synthesis and `grid_ref_plane`

A grid ref plane belongs to the X, Y or Z list of a coordinate system;
`panel_surface` currently returns `rp.reference_plane`, which is `None` for
location-only planes (all of iter0). Synthesize an `IrPlane3D` in the
location's unit (same as ocx-render's `_plane_from_ref_plane`).

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/geometry_context.py`
- Test: `tests/test_rules_geometry_context_grid.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rules_geometry_context_grid.py`:

```python
"""GeometryContext: grid ref planes, GridRef planes and panel uv windows."""
from __future__ import annotations

import numpy as np
from ocx_model_core.model.ir import (
    IrCoordinateSystem,
    IrLimitedByRef,
    IrPanel,
    IrPlane3D,
    IrPoint3D,
    IrRefPlane,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    Quantity,
)
from ocx_rules.geometry_context import GeometryContext

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _vessel(planes: dict[str, tuple[str, float]],
            extra: dict[str, IrRefPlane] | None = None) -> IrVessel:
    """``planes``: ref-plane id -> (axis, location in mm)."""
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    ids = {a: [pid for pid, (ax, _) in planes.items() if ax == a]
           for a in "xyz"}
    v.coordinate_systems["cs"] = IrCoordinateSystem(
        id="cs", is_global=True, x_ref_plane_ids=ids["x"],
        y_ref_plane_ids=ids["y"], z_ref_plane_ids=ids["z"])
    for pid, (_, loc) in planes.items():
        v.ref_planes[pid] = IrRefPlane(id=pid, location=Quantity(loc, "Umm"))
    v.ref_planes.update(extra or {})
    return v


def _grid(name: str, offset_mm: float | None = None) -> IrLimitedByRef:
    offset = None if offset_mm is None else Quantity(offset_mm, "Umm")
    return IrLimitedByRef(ref_type="GridRef", local_ref=name, offset=offset)


class TestRefPlaneAxis:
    def test_axis_from_coordinate_system(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1.0), "fy1": ("y", 1.0)}))
        assert geo.ref_plane_axis("fy1") == "y"
        assert geo.ref_plane_axis("fx1") == "x"
        assert geo.ref_plane_axis("nowhere") is None


class TestPanelSurfaceSynthesis:
    def test_location_only_grid_plane_is_synthesized(self):
        geo = GeometryContext(_vessel({"fz0": ("z", 250.0)}))
        panel = IrPanel(id="p",
                        unbounded_geometry=IrUnboundedGeometry(grid_ref="fz0"))
        surface = geo.panel_surface(panel)
        assert isinstance(surface, IrPlane3D)
        param = geo.surface_param(surface)
        np.testing.assert_allclose(param.o, [0.0, 0.0, 0.25])
        np.testing.assert_allclose(param.n, [0.0, 0.0, 1.0])

    def test_ref_plane_outside_any_coordinate_system_gives_none(self):
        orphan = IrRefPlane(id="orphan", location=Quantity(1.0, "Umm"))
        geo = GeometryContext(_vessel({}, {"orphan": orphan}))
        panel = IrPanel(
            id="p", unbounded_geometry=IrUnboundedGeometry(grid_ref="orphan"))
        assert geo.panel_surface(panel) is None


class TestGridRefPlane:
    def test_synthesized_plane_in_metres(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1000.0)}))
        point, normal = geo.grid_ref_plane(_grid("fx1"))
        np.testing.assert_allclose(point, [1.0, 0.0, 0.0])
        np.testing.assert_allclose(normal, [1.0, 0.0, 0.0])

    def test_offset_moves_along_the_normal(self):
        geo = GeometryContext(_vessel({"fx1": ("x", 1000.0)}))
        point, _ = geo.grid_ref_plane(_grid("fx1", offset_mm=50.0))
        np.testing.assert_allclose(point, [1.05, 0.0, 0.0])
        point, _ = geo.grid_ref_plane(_grid("fx1", offset_mm=-50.0))
        np.testing.assert_allclose(point, [0.95, 0.0, 0.0])

    def test_explicit_reference_plane_wins(self):
        explicit = IrRefPlane(
            id="rp", location=Quantity(9999.0, "Umm"),
            reference_plane=IrPlane3D(point_on_surface=_pt(0, 0, 3000),
                                      normal=IrVector3D(0.0, 0.0, 2.0)))
        geo = GeometryContext(_vessel({}, {"rp": explicit}))
        point, normal = geo.grid_ref_plane(_grid("rp"))
        np.testing.assert_allclose(point, [0.0, 0.0, 3.0])
        np.testing.assert_allclose(normal, [0.0, 0.0, 1.0])

    def test_unknown_ref_plane_gives_none(self):
        geo = GeometryContext(_vessel({}))
        assert geo.grid_ref_plane(_grid("nowhere")) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_geometry_context_grid.py -q`
Expected: failures — `AttributeError: 'GeometryContext' object has no attribute 'ref_plane_axis'` / `'grid_ref_plane'`, and `test_location_only_grid_plane_is_synthesized` asserting on `None`.

- [ ] **Step 3: Write the implementation**

In `geometry_context.py`, extend the imports (after
`from ocx_geometry.curves import sample_curve`):

```python
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import offset_plane
```

and after `from ocx_geometry.surfaces import SurfaceParam, make_param`:

```python
from ocx_model_core.model.ir import IrPlane3D, IrPoint3D, IrVector3D
```

Add `IrRefPlane` to the `TYPE_CHECKING` import list (alphabetical, after
`IrPanel`).

In `panel_surface`, replace

```python
        if ug.grid_ref is not None:
            rp = v.ref_planes.get(ug.grid_ref)
            if rp is not None:
                return rp.reference_plane
        return None
```

with

```python
        if ug.grid_ref is not None:
            rp = v.ref_planes.get(ug.grid_ref)
            if rp is not None:
                return self._ref_plane_geometry(rp)
        return None

    def ref_plane_axis(self, ref_plane_id: str) -> str | None:
        """'x' | 'y' | 'z' — the coordinate-system list holding the plane."""
        for cs in self.vessel.coordinate_systems.values():
            if ref_plane_id in cs.x_ref_plane_ids:
                return "x"
            if ref_plane_id in cs.y_ref_plane_ids:
                return "y"
            if ref_plane_id in cs.z_ref_plane_ids:
                return "z"
        return None

    def _ref_plane_geometry(self, rp: "IrRefPlane") -> IrPlane3D | None:
        """Explicit plane, else one synthesized from axis + location."""
        if rp.reference_plane is not None:
            return rp.reference_plane
        if rp.location is None or rp.location.value is None:
            return None
        axis = self.ref_plane_axis(rp.id)
        if axis is None:
            return None
        point, normal = grid_plane(axis, float(rp.location.value))
        return IrPlane3D(
            id=rp.id,
            point_on_surface=IrPoint3D(*map(float, point),
                                       unit=rp.location.unit),
            normal=IrVector3D(*map(float, normal)))

    def grid_ref_plane(
            self, ref: "IrLimitedByRef",
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """``(point, unit normal)`` in metres of a GridRef's plane with its
        ``Offset`` applied (positive along the normal), or None."""
        rp = self.vessel.ref_planes.get(ref.local_ref)
        plane = self._ref_plane_geometry(rp) if rp is not None else None
        if plane is None or plane.point_on_surface is None \
                or plane.normal is None:
            return None
        n = plane.normal
        try:
            return offset_plane(self.length.point(plane.point_on_surface),
                                [n.x, n.y, n.z],
                                self.to_si(ref.offset) or 0.0)
        except ValueError as exc:
            logger.debug("grid ref plane {} failed: {}", ref.local_ref, exc)
            return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_geometry_context_grid.py tests/test_rules_geometry_context.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-rules/src/ocx_rules/geometry_context.py tests/test_rules_geometry_context_grid.py
git commit -m "feat(rules): synthesize grid ref planes; GridRef plane with offset" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: `GeometryContext.panel_uv_window`

uv bounding box of OuterContour samples, `point_on_surface` and
`extra_points` (explicit boundary samples), grown on each side by its extent
plus 1 m (`1/su`, `1/sv` in uv). Periodic u: span capped at 2π around the
centre. Clamped to `param.uv_domain()`. No data: a finite `uv_domain()`, else
`None`. Empty after clamping: `None`.

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/geometry_context.py`
- Test: `tests/test_rules_geometry_context_grid.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rules_geometry_context_grid.py` (add `import math`
and `import pytest` to the imports, `IrPolyLine3D` to the IR import list,
and `from ocx_geometry.surfaces import CylinderParam, ExtrudedParam, PlaneParam`):

```python
def _contour(*pts: IrPoint3D) -> IrPolyLine3D:
    return IrPolyLine3D(curve_length=None, vertices=list(pts), is_closed=True)


_XY_SQUARE = _contour(_pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000))
_Z = np.array([0.0, 0.0, 1.0])
_XY = PlaneParam(np.zeros(3), _Z, np.array([1.0, 0.0, 0.0]))  # u = x, v = y


class _BoxedPlane(PlaneParam):
    def uv_domain(self):
        return (0.0, 1.0, 0.0, 2.0)


class TestPanelUvWindow:
    def _geo(self) -> GeometryContext:
        return GeometryContext(_vessel({}))

    def test_contour_box_grown_by_extent_plus_one_metre(self):
        panel = IrPanel(id="p", outer_contours=[_XY_SQUARE])
        assert self._geo().panel_uv_window(panel, _XY) == pytest.approx(
            (-2.0, 3.0, -2.0, 3.0))

    def test_extra_points_extend_the_box(self):
        panel = IrPanel(id="p", outer_contours=[_XY_SQUARE])
        extra = [np.array([[2.0, 0.0, 0.0], [2.0, 1.0, 0.0]])]
        assert self._geo().panel_uv_window(panel, _XY, extra) == \
            pytest.approx((-3.0, 5.0, -2.0, 3.0))

    def test_point_on_surface_alone(self):
        panel = IrPanel(id="p", point_on_surface=_pt(500, 500))
        assert self._geo().panel_uv_window(panel, _XY) == pytest.approx(
            (-0.5, 1.5, -0.5, 1.5))

    def test_clamped_to_uv_domain(self):
        extruded = ExtrudedParam(np.array([[0.0, 0, 0], [4.0, 0, 0]]), _Z)
        panel = IrPanel(id="p", outer_contours=[_contour(
            _pt(0, 0, 0), _pt(1000, 0, 0), _pt(1000, 0, 1000),
            _pt(0, 0, 1000))])
        assert self._geo().panel_uv_window(panel, extruded) == pytest.approx(
            (0.0, 3.0, -2.0, 3.0))

    def test_no_data_falls_back_to_finite_domain(self):
        panel = IrPanel(id="p")
        boxed = _BoxedPlane(np.zeros(3), _Z)
        assert self._geo().panel_uv_window(panel, boxed) == (0.0, 1.0, 0.0, 2.0)
        assert self._geo().panel_uv_window(panel, _XY) is None

    def test_periodic_span_capped_at_two_pi(self):
        c = 1000.0 / math.sqrt(2.0)
        quarter = _contour(_pt(1000, 0, 0), _pt(c, c, 0), _pt(0, 1000, 0),
                           _pt(0, 1000, 1000), _pt(c, c, 1000),
                           _pt(1000, 0, 1000))
        panel = IrPanel(id="p", outer_contours=[quarter])
        u0, u1, v0, v1 = self._geo().panel_uv_window(
            panel, CylinderParam(np.zeros(3), _Z, 1.0))
        assert u1 - u0 == pytest.approx(2.0 * math.pi)
        assert (v0, v1) == pytest.approx((-2.0, 3.0))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_geometry_context_grid.py -q -k UvWindow`
Expected: 6 failed with `AttributeError: ... has no attribute 'panel_uv_window'`.

- [ ] **Step 3: Write the implementation**

In `geometry_context.py` add after `grid_ref_plane` (add `Iterable` via
`from collections.abc import Iterable` at the top-level imports):

```python
    def panel_uv_window(
            self, panel: "IrPanel", param: SurfaceParam,
            extra_points: Iterable[np.ndarray] = (),
    ) -> tuple[float, float, float, float] | None:
        """uv window ``(u0, u1, v0, v1)`` around a panel on ``param``.

        Bounding box (in uv) of the OuterContour samples, point_on_surface
        and ``extra_points``, grown on each side by its extent plus 1 m;
        periodic u is capped at one period; clamped to ``param.uv_domain()``.
        """
        chunks = [s for s in (self.sample(c) for c in panel.outer_contours)
                  if s is not None and len(s)]
        if panel.point_on_surface is not None:
            chunks.append(self.length.point(panel.point_on_surface)[None, :])
        chunks += [np.asarray(p, dtype=float).reshape(-1, 3)
                   for p in extra_points if len(p)]
        domain = param.uv_domain()
        if not chunks:
            if domain is not None and np.all(np.isfinite(domain)):
                return tuple(float(x) for x in domain)
            return None
        uv = param.inverse(np.vstack(chunks))
        lo, hi = uv.min(axis=0), uv.max(axis=0)
        su, sv = param.uv_scale()
        grow = (hi - lo) + np.array([1.0 / su, 1.0 / sv])
        lo, hi = lo - grow, hi + grow
        if param.periodic_u and hi[0] - lo[0] > 2.0 * np.pi:
            mid = 0.5 * (lo[0] + hi[0])
            lo[0], hi[0] = mid - np.pi, mid + np.pi
        if domain is not None:
            lo = np.maximum(lo, [domain[0], domain[2]])
            hi = np.minimum(hi, [domain[1], domain[3]])
        if np.any(hi <= lo):
            return None
        return (float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_geometry_context_grid.py -q`
Expected: all pass (13 tests).

- [ ] **Step 5: Lint and commit**

Run: `uv run ruff check packages/ocx-rules tests/test_rules_geometry_context_grid.py`
Expected: `All checks passed!`

```powershell
git add packages/ocx-rules/src/ocx_rules/geometry_context.py tests/test_rules_geometry_context_grid.py
git commit -m "feat(rules): GeometryContext.panel_uv_window" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Extract `boundary_reasons` into `limited_by_region.py`

Pure refactor so the grid path can reuse the reason formatter without a
circular import (`topology` will import `limited_by_region`, never the
reverse).

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/limited_by_region.py`
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py:41-78`

- [ ] **Step 1: Create the module**

```python
"""OCX-TOP-001 helpers: boundary-ref reason fragments and the arrangement
path for panels bounded by GridRefs."""
from __future__ import annotations

from collections import Counter


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
```

- [ ] **Step 2: Use it in `topology.py`**

Add the import after `from ocx_rules.model import CheckOutcome, Finding, OutcomeCollector`:

```python
from ocx_rules.packs.best_practice.checks.limited_by_region import (
    boundary_reasons,
)
```

In `_classified_boundary_samples`, replace everything from
`    def by_type(counts: Counter[str]) -> str:` through `    return samples, reasons`
with:

```python
    return samples, boundary_reasons(dangling, no_curve, unsampleable)
```

and change its docstring line
`    without an explicit curve (e.g. GridRef), and unsampleable curves.`
to
`    without an explicit curve (e.g. PanelRef), and unsampleable curves.`

- [ ] **Step 3: Run the existing TOP-001 tests (must stay green)**

Run: `uv run pytest tests/test_rules_checks_topology.py -q`
Expected: all pass (no behaviour change).

- [ ] **Step 4: Commit**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/limited_by_region.py packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py
git commit -m "refactor(rules): extract TOP-001 boundary reason formatter" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: TOP-001 arrangement path for GridRef panels

Steps for a panel with at least one GridRef (spec §3):
1. Classify refs; an unresolvable GridRef counts as dangling. Any reason → unchecked.
2. Surface param → `"no buildable panel surface"`; window → `"cannot determine panel extent"`.
3. Seed: `representative_point()` of the first OuterContour in uv, else `point_on_surface` → `"no seed point"`.
4. Intersect grid planes; explicit curves have open ends extended by the tolerance; everything mapped to uv (periodic u shifted into the window); `unary_union` + `polygonize`.
5. No face contains the seed → one finding `"Panel boundary is not closed: LimitedBy does not enclose the panel"`. Else, for the smallest containing face, every boundary whose min 3D distance to the face's ring exceeds the tolerance (or that has no intersection) → `"LimitedBy boundary <ref_type> <local_ref> does not bound the panel"`.
6. Any exception → unchecked `"boundary evaluation failed: <exc>"`.

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/limited_by_region.py`
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py` (`panel_limited_by_closed`)
- Modify: `tests/test_rules_checks_topology.py:117-127`
- Test: `tests/test_rules_limited_by_region.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rules_limited_by_region.py`:

```python
"""OCX-TOP-001 for panels bounded by GridRefs (checks/limited_by_region.py)."""
from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

from ocx_model_core.model.ir import (
    IrCoordinateSystem,
    IrCylinder3D,
    IrLimitedByRef,
    IrLine3D,
    IrPanel,
    IrPoint3D,
    IrPolyLine3D,
    IrRefPlane,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    Quantity,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.model import CheckOutcome, Unchecked
from ocx_rules.packs.best_practice.checks.topology import panel_limited_by_closed

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")
_PLANES = {"fx0": ("x", 0.0), "fx1": ("x", 1000.0), "fx2": ("x", 5000.0),
           "fy0": ("y", 0.0), "fy1": ("y", 1000.0),
           "fz0": ("z", 0.0), "fz1": ("z", 1000.0)}
_NOT_CLOSED = ("Panel boundary is not closed: LimitedBy does not enclose "
               "the panel")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _grid(name: str, offset_mm: float | None = None) -> IrLimitedByRef:
    offset = None if offset_mm is None else Quantity(offset_mm, "Umm")
    return IrLimitedByRef(ref_type="GridRef", local_ref=name, offset=offset)


def _fec(p0: IrPoint3D, p1: IrPoint3D) -> IrLimitedByRef:
    return IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="",
                          curve=IrLine3D(curve_length=None, start=p0, end=p1))


def _square() -> IrPolyLine3D:
    return IrPolyLine3D(curve_length=None, is_closed=True, vertices=[
        _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)])


def _flat_panel(refs: list[IrLimitedByRef], *, contour: bool = True,
                surface: bool = True) -> IrPanel:
    """Panel on grid plane fz0 (z = 0), OuterContour 0..1000 mm square."""
    return IrPanel(
        id="p1", guidref="g1", limited_by=refs,
        unbounded_geometry=(IrUnboundedGeometry(grid_ref="fz0")
                            if surface else None),
        outer_contours=[_square()] if contour else [])


def _run(panel: IrPanel) -> CheckOutcome:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    ids = {a: [p for p, (ax, _) in _PLANES.items() if ax == a] for a in "xyz"}
    v.coordinate_systems["cs"] = IrCoordinateSystem(
        id="cs", is_global=True, x_ref_plane_ids=ids["x"],
        y_ref_plane_ids=ids["y"], z_ref_plane_ids=ids["z"])
    for pid, (_, loc) in _PLANES.items():
        v.ref_planes[pid] = IrRefPlane(id=pid, location=Quantity(loc, "Umm"))
    v.panels["p1"] = panel
    ctx = SimpleNamespace(vessel=v, geometry=GeometryContext(v))
    return panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})


def _unchecked(reason: str) -> CheckOutcome:
    return CheckOutcome(unchecked=(Unchecked(reason, "p1", "g1"),))


_XXYY = ["fx0", "fx1", "fy0", "fy1"]


class TestGridRefPanels:
    def test_four_grid_planes_close(self):
        assert _run(_flat_panel([_grid(n) for n in _XXYY])) == CheckOutcome()

    def test_three_grid_planes_are_not_closed(self):
        outcome = _run(_flat_panel([_grid(n) for n in _XXYY[:3]]))
        (finding,) = outcome.findings
        assert finding.message == _NOT_CLOSED
        assert (finding.element_id, finding.guid) == ("p1", "g1")
        assert outcome.unchecked == ()

    def test_distant_parallel_plane_is_stray(self):
        outcome = _run(_flat_panel([_grid(n) for n in [*_XXYY, "fx2"]]))
        assert [f.message for f in outcome.findings] == [
            "LimitedBy boundary GridRef fx2 does not bound the panel"]

    def test_grid_and_free_edge_mix_closes(self):
        refs = [_grid("fx0"), _grid("fy0"), _grid("fy1"),
                _fec(_pt(1000, 0), _pt(1000, 1000))]
        assert _run(_flat_panel(refs)) == CheckOutcome()

    def test_offset_grid_ref_opens_the_boundary(self):
        refs = [_grid("fx0"), _grid("fy0"), _grid("fy1", offset_mm=50.0),
                _fec(_pt(1000, 0), _pt(1000, 1000))]
        (finding,) = _run(_flat_panel(refs)).findings
        assert finding.message == _NOT_CLOSED

    def test_curved_panel_closes(self):
        c = 1000.0 / math.sqrt(2.0)
        quarter = IrPolyLine3D(curve_length=None, is_closed=True, vertices=[
            _pt(1000, 0, 0), _pt(c, c, 0), _pt(0, 1000, 0),
            _pt(0, 1000, 1000), _pt(c, c, 1000), _pt(1000, 0, 1000)])
        cylinder = IrCylinder3D(origin=_pt(0, 0, 0),
                                axis=IrVector3D(0.0, 0.0, 1.0),
                                radius=Quantity(1000.0, "Umm"))
        panel = IrPanel(
            id="p1", guidref="g1",
            limited_by=[_grid(n) for n in ("fz0", "fz1", "fx0", "fy0")],
            unbounded_geometry=IrUnboundedGeometry(surface=cylinder),
            outer_contours=[quarter], point_on_surface=_pt(c, c, 500))
        assert _run(panel) == CheckOutcome()

    def test_unresolvable_grid_ref_is_dangling(self):
        refs = [_grid(n) for n in _XXYY[:3]] + [_grid("nowhere")]
        assert _run(_flat_panel(refs)) == _unchecked(
            "1 dangling boundary ref(s) (GridRef×1)")

    def test_curveless_ref_beside_grid_refs_unchecked(self):
        refs = [_grid(n) for n in _XXYY[:3]]
        refs.append(IrLimitedByRef(ref_type="PanelRef", local_ref="p9"))
        assert _run(_flat_panel(refs)) == _unchecked(
            "1 boundary ref(s) without explicit curve (PanelRef×1)")

    def test_no_panel_surface_unchecked(self):
        panel = _flat_panel([_grid(n) for n in _XXYY], surface=False)
        assert _run(panel) == _unchecked("no buildable panel surface")

    def test_no_panel_extent_unchecked(self):
        panel = _flat_panel([_grid(n) for n in _XXYY], contour=False)
        assert _run(panel) == _unchecked("cannot determine panel extent")

    def test_no_seed_point_unchecked(self):
        refs = [_grid("fx0"), _grid("fy0"), _grid("fy1"),
                _fec(_pt(1000, 0), _pt(1000, 1000))]
        assert _run(_flat_panel(refs, contour=False)) == _unchecked(
            "no seed point")

    def test_evaluation_error_unchecked(self):
        target = ("ocx_rules.packs.best_practice.checks.limited_by_region."
                  "intersect_surface_plane")
        with patch(target, side_effect=RuntimeError("boom")):
            outcome = _run(_flat_panel([_grid(n) for n in _XXYY]))
        assert outcome == _unchecked("boundary evaluation failed: boom")
```

In `tests/test_rules_checks_topology.py`, replace
`test_grid_and_dangling_refs_reported_separately` (≈ lines 117–127) with:

```python
    def test_unresolvable_grid_refs_count_as_dangling(self):
        sides = _square_sides()[:2]
        sides += [IrLimitedByRef(ref_type="GridRef", local_ref="fr10"),
                  IrLimitedByRef(ref_type="GridRef", local_ref="fr11"),
                  IrLimitedByRef(ref_type="SeamRef", local_ref="missing")]
        panel = IrPanel(id="p1", guidref="g1", limited_by=sides)
        ctx = _ctx(_vessel({"p1": panel}))
        (u,) = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}).unchecked
        assert u.reason == "3 dangling boundary ref(s) (GridRef×2, SeamRef×1)"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_limited_by_region.py tests/test_rules_checks_topology.py -q`
Expected: most new tests fail (unchecked "N boundary ref(s) without explicit curve (GridRef×N)" instead of the expected outcomes); `test_unresolvable_grid_refs_count_as_dangling` fails; `test_evaluation_error_unchecked` fails with `AttributeError: ... does not have the attribute 'intersect_surface_plane'`.

- [ ] **Step 3: Implement the arrangement path**

Replace `limited_by_region.py` with:

```python
"""OCX-TOP-001 helpers: boundary-ref reason fragments and the arrangement
path for panels bounded by GridRefs.

A GridRef names a plane, not a curve, and LimitedBy order is not cyclic,
so the boundary is found as a planar arrangement in the panel surface's uv
space: every boundary becomes uv linework, the linework is polygonized and
the face containing a seed point inside the OuterContour is the panel.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from ocx_geometry.intersect import intersect_surface_plane
from ocx_geometry.topology2d import points_polyline_distances
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

_SAMPLE_TOL_M = 0.001
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

    Exceptions propagate; the caller reports them as unchecked.
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

    param = geo.surface_param(geo.panel_surface(panel))
    if param is None:
        return "no buildable panel surface", []
    window = geo.panel_uv_window(panel, param, [p for _, p in explicit])
    if window is None:
        return "cannot determine panel extent", []
    seed = _seed(geo, panel, param, window)
    if seed is None:
        return "no seed point", []

    boundaries = [(label, [pts]) for label, pts in explicit]
    boundaries += [(label, intersect_surface_plane(param, p, n, window,
                                                   _SAMPLE_TOL_M))
                   for label, (p, n) in planes]
    lines = [LineString(_to_uv(param, pl, window))
             for _, pls in boundaries for pl in pls if len(pl) >= 2]
    faces = [f for f in polygonize(unary_union(lines)) if f.contains(seed)]
    if not faces:
        return None, [NOT_CLOSED]
    face = min(faces, key=lambda f: f.area)
    ring = param.evaluate(np.asarray(face.exterior.coords))
    messages = []
    for label, pls in boundaries:
        dist = min((float(points_polyline_distances(ring, pl).min())
                    for pl in pls), default=np.inf)
        if dist > tol_m:
            messages.append(f"LimitedBy boundary {label} does not bound "
                            f"the panel")
    return None, messages


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


def _seed(geo, panel, param, window) -> Point | None:
    """A uv point inside the panel: representative point of the first
    OuterContour (inside even when concave), else point_on_surface."""
    for contour in panel.outer_contours[:1]:
        pts = geo.sample(contour, _SAMPLE_TOL_M)
        if pts is not None and len(pts) >= 3:
            poly = Polygon(_to_uv(param, pts, window))
            if poly.is_valid and poly.area > 0:
                return poly.representative_point()
    if panel.point_on_surface is not None:
        uv = _to_uv(param, geo.length.point(panel.point_on_surface)[None, :],
                    window)
        return Point(uv[0])
    return None
```

- [ ] **Step 4: Route GridRef panels in `panel_limited_by_closed`**

In `topology.py`, extend the import added in Task 7:

```python
from ocx_rules.packs.best_practice.checks.limited_by_region import (
    boundary_reasons,
    grid_panel_outcome,
)
```

and in `panel_limited_by_closed`, directly after

```python
        if not panel.limited_by:
            continue
```

insert:

```python
        if any(ref.ref_type == "GridRef" for ref in panel.limited_by):
            try:
                reason, messages = grid_panel_outcome(
                    context.geometry, panel, tol_m)
            except Exception as exc:
                logger.debug("TOP-001 grid path failed for {}: {}", pid, exc)
                reason, messages = f"boundary evaluation failed: {exc}", []
            if reason:
                out.unchecked(reason, pid, panel.guidref)
            for message in messages:
                out.add(Finding(message=message, element_id=pid,
                                guid=panel.guidref))
            continue
```

- [ ] **Step 5: Add shapely as a direct ocx-rules dependency**

`limited_by_region.py` imports shapely directly. In
`packages/ocx-rules/pyproject.toml`, add to `dependencies` (after
`"ocx-geometry>=0.2,<0.3",`):

```toml
    "shapely>=2.2.0",
```

Run: `uv lock` — expected: lock updates without new packages (shapely is
already resolved via ocx-geometry).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_limited_by_region.py tests/test_rules_checks_topology.py -q`
Expected: all pass.

If `test_curved_panel_closes` fails, debug with
`superpowers:systematic-debugging` — print the uv linework and the faces
from `polygonize` before changing any code; do not loosen the tolerance.

- [ ] **Step 7: Full suite and lint**

Run: `uv run pytest -q` → expected: all pass (≈ 1215 tests).
Run: `uv run ruff check packages tests` → expected: `All checks passed!`

- [ ] **Step 8: Commit**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/limited_by_region.py packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py packages/ocx-rules/pyproject.toml uv.lock tests/test_rules_limited_by_region.py tests/test_rules_checks_topology.py
git commit -m "feat(rules): TOP-001 checks GridRef-bounded panels via a uv arrangement" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Changelogs, iter0 verification, PR

**Files:**
- Modify: `packages/ocx-geometry/CHANGELOG.md`
- Modify: `packages/ocx-rules/CHANGELOG.md`

- [ ] **Step 1: ocx-geometry changelog**

Insert directly below `# Changelog — ocx-geometry` (above `## 0.2.0 — 2026-11-08`):

```markdown
## Unreleased

### Added

- `grid.grid_plane(axis, location)`: axis-aligned grid plane (positive
  axis normal).
- `intersect.offset_plane` and `intersect.intersect_surface_plane`:
  surface ∩ plane as 3D polylines inside a uv window — analytic for
  planes, marching squares (saddle resolved by the cell centre) for every
  other surface.
- `SurfaceParam.uv_domain()`: parameter domain (NURBS knot domain;
  extruded `(0, base length, -inf, inf)`; `None` for analytic surfaces).

```

- [ ] **Step 2: ocx-rules changelog**

In `packages/ocx-rules/CHANGELOG.md`, append to the end of the
`## Unreleased` → `### Added` list (directly before the blank line that
precedes `### Fixed`):

```markdown
- `OCX-TOP-001` checks panels bounded by `GridRef`s instead of reporting
  them unchecked: grid planes (with `Offset`) are intersected with the
  panel surface, all boundaries are polygonized in the surface's uv space,
  and the face containing the panel's OuterContour must exist ("not
  closed" otherwise) and be bounded by every LimitedBy boundary (one
  "does not bound the panel" finding per stray boundary). Location-only
  grid ref planes are synthesized from their coordinate-system axis, also
  for `UnboundedGeometry/GridRef` panel surfaces. Unresolvable GridRefs
  are reported as dangling.
```

- [ ] **Step 3: Verify on iter0**

Run:

```powershell
@'
import warnings
from collections import Counter
from pathlib import Path
from loguru import logger
logger.remove(); warnings.filterwarnings("ignore")
from ocx_rules.context import ValidationContext
from ocx_rules.packs.best_practice.checks.topology import panel_limited_by_closed
import os
ctx = ValidationContext(Path(os.environ["TEMP"]) / "ucrun" / "iter0.3docx")
out = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})
print("findings", len(out.findings), "unchecked", len(out.unchecked))
print("gridref unchecked", sum("GridRef" in u.reason for u in out.unchecked))
print(Counter(u.reason for u in out.unchecked).most_common())
for f in out.findings:
    print(f.element_id, "|", f.message)
'@ | uv run python -
```

Expected: `gridref unchecked 0`; the 20 pre-existing gap findings remain
(messages "largest gap … mm exceeds 1.00 mm"). Any new "not closed" /
"does not bound the panel" findings and any remaining unchecked reasons
must be inspected one by one (render the panel or print its LimitedBy and
OuterContour) and explained in the PR description before merging; a
finding caused by our code (not the model) is a bug — fix it with a
failing test first.

- [ ] **Step 4: Full suite and lint again**

Run: `uv run pytest -q` and `uv run ruff check packages tests` — both clean.

- [ ] **Step 5: Commit, push, open the PR**

```powershell
git add packages/ocx-geometry/CHANGELOG.md packages/ocx-rules/CHANGELOG.md
git commit -m "docs: changelog for GridRef panel boundaries" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

Write the PR body to `$env:TEMP\pr-gridref.md` (summary, iter0 before/after
numbers from Step 3, explanation of any new findings, test commands) and run:

```powershell
gh pr create --base feat/unchecked-elements --head feat/gridref-boundaries --title "feat: TOP-001 evaluates GridRef-bounded panels" --body-file $env:TEMP\pr-gridref.md
```

Expected: PR URL printed.
