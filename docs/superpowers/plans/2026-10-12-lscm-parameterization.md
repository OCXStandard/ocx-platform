# LSCM Multi-Patch Parameterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the heuristic `CompositeParam` with an LSCM (Least Squares Conformal Maps) chart that parameterizes plates spanning multi-patch NURBS surface collections.

**Architecture:** All member surfaces of a panel's surface collection are faceted into one welded triangle mesh carrying per-vertex back-pointers `(member, local uv)`. The mesh is flattened into a single metric 2-D chart with LSCM (one scipy sparse solve). Queries route through the mesh: `inverse` = closest 3-D triangle → barycentric → chart UV; `evaluate` = chart-UV triangle → barycentric → source member local uv → **exact** member evaluation. The chart is built once per panel and cached. Spec: `docs/superpowers/specs/2026-10-12-lscm-parameterization-design.md`.

**Design deviation from spec (approved rationale):** unbounded members (`PlaneParam`, `CylinderParam`, …) have no intrinsic UV domain to facet. `make_lscm` therefore takes `hint_pts` — the concatenated sampled plate contours of the panel — and bounds unbounded members by the bbox of their on-surface hint points in member-local UV. `NurbsSurfaceParam` uses its intrinsic knot domain (`du`/`dv`). The chart is still per-panel and cached; Task 5 amends the spec.

**Tech Stack:** Python 3.12, uv workspace, numpy, scipy (new dep: sparse solve + cKDTree + connected_components), trimesh (3-D proximity, winding repair), shapely (STRtree UV lookup), pytest, loguru.

**Conventions:** run everything from the repo root with `uv run …`. Windows paths in commands. Every commit message ends with the trailer:

```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

---

## Background for the engineer

- `SurfaceParam` ABC (`packages/ocx-geometry/src/ocx_geometry/surfaces.py` top): `evaluate(uv)` (N,2)→(N,3) metres, `inverse(pts)` (N,3)→(N,2), `normals(uv)` (N,2)→(N,3) unit, `uv_scale()` → (su, sv) metres per uv unit, `max_edge_m(tol_m)` → max metric edge for chordal error ≤ tol, or `None` for flat directions.
- `NurbsSurfaceParam` has `self.du`, `self.dv` (uv domain tuples). `PlaneParam`/`CylinderParam`/`ConeParam`/`SphereParam`/`ExtrudedParam` have no domain attributes (unbounded).
- `_member_fit(member, pts)` in surfaces.py returns `(uv, roundtrip_pts, residuals)` or `None`.
- The consumer is `uv_tessellator.py`: it calls `param.inverse` on contour/hole points, `param.max_edge_m` + `param.uv_scale` for subdivision, `param.evaluate` and `param.normals` on final vertices. **No changes needed there.**
- `render.py::_tessellate_plates` currently builds `make_composite(candidates, contour) or _best_param(candidates, contour)` per plate when a panel has >1 candidate params.
- `CompositeParam`/`make_composite` live at `packages/ocx-geometry/src/ocx_geometry/surfaces.py:438-626` and are deleted in Task 5.
- Tests run from root: `uv run pytest tests/test_render_lscm.py -v`. Integration tests are deselected by default; run with `-m integration` (slow, ~5 min).

---

### Task 1: Add the scipy dependency

**Files:**
- Modify: `packages/ocx-geometry/pyproject.toml`

- [ ] **Step 1: Add scipy to ocx-geometry**

Run:
```bash
uv add --package ocx-geometry "scipy>=1.14"
```
Expected: `pyproject.toml` of ocx-geometry gains `"scipy>=1.14"` under `dependencies`, `uv.lock` updated, sync succeeds.

- [ ] **Step 2: Verify the import works**

Run: `uv run python -c "import scipy.sparse, scipy.spatial; print(scipy.__version__)"`
Expected: a version ≥ 1.14 printed, exit 0.

- [ ] **Step 3: Commit**

```bash
git add packages/ocx-geometry/pyproject.toml uv.lock
git commit -m "build: add scipy to ocx-geometry for the LSCM solver"
```

---

### Task 2: Chart mesh construction (facet + weld + stitch)

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/lscm.py`
- Create: `tests/test_render_lscm.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_lscm.py`:

```python
"""Tests for the LSCM multi-patch chart (ocx_geometry.lscm)."""
import numpy as np
import pytest
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import make_param
from ocx_model_core.model.ir.geometry import IrNurbsSurface, IrPoint3D

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def _grid_patch(pid, x0, y0, size=2.0):
    """Flat bilinear NURBS patch spanning [x0,x0+size] x [y0,y0+size], z=0."""
    return IrNurbsSurface(
        id=pid, u_degree=1, v_degree=1,
        u_knot_vector=[0, 0, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(x0, y0, 0), pt(x0, y0 + size, 0)],
                        [pt(x0 + size, y0, 0), pt(x0 + size, y0 + size, 0)]],
    )


def _grid_members():
    members = [make_param(_grid_patch(f"p{i}{j}", 2.0 * i, 2.0 * j), LR,
                          tol_m=0.01)
               for i in range(2) for j in range(2)]
    assert all(m is not None for m in members)
    return members


def _bilge_members_and_hints():
    """Flat bottom + quarter bilge cylinder + flat side, with plate-contour
    hint points (mirrors test_render_model's spanning-plate scenario)."""
    from ocx_geometry.surfaces import CylinderParam, PlaneParam
    bot = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
    cyl = CylinderParam(np.array([0.0, 1.0, 1.0]),
                        np.array([1.0, 0.0, 0.0]), 1.0)
    side = PlaneParam(np.array([0.0, 2.0, 0.0]), np.array([0.0, 1.0, 0.0]))

    def girth(x):
        rows = [[x, 0.0, 0.0]]
        for th in np.linspace(0.0, np.pi / 2, 9):
            rows.append([x, 1.0 + np.sin(th), 1.0 - np.cos(th)])
        rows.append([x, 2.0, 2.0])
        return rows

    xs = np.linspace(0.0, 4.0, 9)
    hints = np.array(
        girth(0.0) + girth(4.0)
        + [[x, 0.0, 0.0] for x in xs]      # bottom closing edge
        + [[x, 2.0, 2.0] for x in xs])     # top closing edge
    return [bot, cyl, side], hints


class TestBuildMesh:
    def test_grid_members_weld_into_one_connected_mesh(self):
        from ocx_geometry.lscm import _build_mesh
        cm = _build_mesh(_grid_members(), tol_m=0.01, hint_pts=None)
        assert cm is not None
        # 4 one-cell patches = 16 raw corners; welding shared corners
        # leaves the 3x3 lattice of 9 distinct vertices
        assert len(cm.V) == 9
        assert len(cm.F) == 8
        # every triangle knows its source member
        assert (cm.tri_member >= 0).all()

    def test_mismatched_seam_densities_are_stitched(self):
        """Plane edges sample 2 points where the cylinder edge samples many:
        the T-junctions must be split so no boundary edge passes through
        another boundary vertex."""
        from ocx_geometry.lscm import _boundary_edges, _build_mesh
        members, hints = _bilge_members_and_hints()
        cm = _build_mesh(members, tol_m=0.01, hint_pts=hints)
        assert cm is not None
        bnd = _boundary_edges(cm.F)
        bverts = np.unique(bnd)
        for a, b in bnd:
            d = cm.V[b] - cm.V[a]
            ll = float(d @ d)
            for w in bverts:
                if w in (a, b):
                    continue
                t = float((cm.V[w] - cm.V[a]) @ d) / ll
                if not 1e-6 < t < 1 - 1e-6:
                    continue
                gap = np.linalg.norm(cm.V[a] + t * d - cm.V[w])
                assert gap > 1e-4, f"T-junction left at vertex {w}"

    def test_disconnected_members_return_none(self):
        from ocx_geometry.lscm import _build_mesh
        a = make_param(_grid_patch("a", 0.0, 0.0), LR, tol_m=0.01)
        b = make_param(_grid_patch("b", 10.0, 0.0), LR, tol_m=0.01)
        assert _build_mesh([a, b], tol_m=0.01, hint_pts=None) is None

    def test_unbounded_members_without_hints_return_none(self):
        from ocx_geometry.lscm import _build_mesh
        from ocx_geometry.surfaces import PlaneParam
        p1 = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        p2 = PlaneParam(np.array([0.0, 2.0, 0.0]), np.array([0.0, 1.0, 0.0]))
        assert _build_mesh([p1, p2], tol_m=0.01, hint_pts=None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_lscm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_geometry.lscm'`

- [ ] **Step 3: Implement the mesh construction**

Create `packages/ocx-geometry/src/ocx_geometry/lscm.py`:

```python
"""LSCM chart over multi-patch surface collections.

Replaces the developed-chart ``CompositeParam``: all member surfaces are
faceted into one welded triangle mesh with per-vertex back-pointers to
``(member, local uv)``; the mesh is flattened with Least Squares Conformal
Maps into a single metric 2-D chart.  Queries route through the mesh:

- ``inverse``  — closest 3-D triangle -> barycentric -> chart UV
- ``evaluate`` — chart-UV triangle -> barycentric -> source member local uv
  -> exact member evaluation, so points stay on the true surface and
  curvature-driven subdivision refines onto real geometry.

Reference: GeniE ``LSCMParameterizedSurface.cpp`` (DNV, libigl-based).
"""
from __future__ import annotations

import math

import numpy as np
import shapely
import trimesh
from loguru import logger
from scipy.sparse import bmat, coo_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree
from shapely.strtree import STRtree

from ocx_geometry.surfaces import SurfaceParam, _member_fit

_MAX_GRID = 48            # max facet cells per axis per member
_MAX_SCALE_RATIO = 100.0  # reject charts with larger per-triangle scale spread
_MAX_FLIPPED = 0.005      # tolerated fraction of flipped UV triangles
_STITCH_PASSES = 8


class _ChartMesh:
    """Welded facet mesh of all members with per-vertex source params."""

    def __init__(self, V: np.ndarray, F: np.ndarray,
                 src: list[dict[int, tuple[float, float]]],
                 tri_member: np.ndarray) -> None:
        self.V = V                      # (n, 3) vertices, metres
        self.F = F                      # (m, 3) triangle vertex indices
        self.src = src                  # per vertex: {member index: local uv}
        self.tri_member = tri_member    # (m,) member per triangle, -1 = none


def _member_domain(member: SurfaceParam, hint_pts: np.ndarray | None,
                   on_tol: float):
    """Member UV sampling domain: intrinsic knot domain when available,
    else the bbox of on-surface hint points in member-local UV."""
    du, dv = getattr(member, "du", None), getattr(member, "dv", None)
    if du is not None and dv is not None:
        return (float(du[0]), float(du[1])), (float(dv[0]), float(dv[1]))
    if hint_pts is None or len(hint_pts) < 3:
        return None
    fit = _member_fit(member, hint_pts)
    if fit is None:
        return None
    uv, _, res = fit
    on = res <= on_tol
    if int(on.sum()) < 3:
        return None
    u0, u1 = float(uv[on, 0].min()), float(uv[on, 0].max())
    v0, v1 = float(uv[on, 1].min()), float(uv[on, 1].max())
    if u1 - u0 < 1e-9 or v1 - v0 < 1e-9:
        return None                     # degenerate: no 2-D extent
    return (u0, u1), (v0, v1)


def _facet_member(member: SurfaceParam, dom, tol_m: float):
    """Sample a member on a UV grid -> (pts (n,3), uvs (n,2), faces (m,3))."""
    (u0, u1), (v0, v1) = dom
    su, sv = member.uv_scale()
    edge = member.max_edge_m(tol_m)

    def n_cells(span_m: float) -> int:
        if edge is None or edge <= 0.0:
            return 1                    # flat direction: one cell suffices
        return int(np.clip(math.ceil(span_m / edge), 1, _MAX_GRID))

    nu, nv = n_cells((u1 - u0) * su), n_cells((v1 - v0) * sv)
    us = np.linspace(u0, u1, nu + 1)
    vs = np.linspace(v0, v1, nv + 1)
    uu, vv = np.meshgrid(us, vs, indexing="ij")
    uvs = np.column_stack([uu.ravel(), vv.ravel()])
    pts = np.asarray(member.evaluate(uvs), dtype=float)
    faces = []
    for i in range(nu):
        for j in range(nv):
            a = i * (nv + 1) + j
            b = (i + 1) * (nv + 1) + j
            faces.append((a, b, b + 1))
            faces.append((a, b + 1, a + 1))
    return pts, uvs, np.asarray(faces, dtype=int)


def _weld(V: np.ndarray, src: list[dict], weld_tol: float):
    """Merge vertices within weld_tol (union-find); src dicts are unioned."""
    pairs = cKDTree(V).query_pairs(weld_tol, output_type="ndarray")
    parent = np.arange(len(V))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in pairs:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    root = np.array([find(i) for i in range(len(V))])
    uniq, remap = np.unique(root, return_inverse=True)
    out_src: list[dict] = [{} for _ in uniq]
    for i, r in enumerate(remap):
        out_src[r].update(src[i])
    return V[uniq], out_src, remap


def _boundary_edges(F: np.ndarray) -> np.ndarray:
    """Directed edges that belong to exactly one triangle."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(e, axis=1)
    _, idx, cnt = np.unique(key, axis=0, return_index=True,
                            return_counts=True)
    return e[idx[cnt == 1]]


def _stitch(V: np.ndarray, F: np.ndarray, src: list[dict],
            snap_tol: float) -> np.ndarray:
    """Split triangles whose boundary edge passes through another boundary
    vertex — the T-junctions left where member seams were sampled at
    different densities.  The inserted vertex inherits an interpolated
    local-uv source for every member shared by the edge endpoints."""
    for _ in range(_STITCH_PASSES):
        bnd = _boundary_edges(F)
        if len(bnd) == 0:
            break
        bverts = np.unique(bnd)
        tree = cKDTree(V[bverts])
        splits: dict[tuple[int, int], tuple[int, float]] = {}
        for a, b in bnd:
            key = (min(a, b), max(a, b))
            d = V[b] - V[a]
            seg = float(np.linalg.norm(d))
            if seg < 1e-12:
                continue
            mid = 0.5 * (V[a] + V[b])
            best = None
            for ci in tree.query_ball_point(mid, 0.5 * seg + snap_tol):
                w = int(bverts[ci])
                if w == a or w == b:
                    continue
                t = float((V[w] - V[a]) @ d) / (seg * seg)
                if not 1e-6 < t < 1.0 - 1e-6:
                    continue
                gap = float(np.linalg.norm(V[a] + t * d - V[w]))
                if gap > snap_tol:
                    continue
                if best is None or gap < best[0]:
                    best = (gap, w, t)
            if best is not None:
                splits[key] = (best[1], best[2])
        if not splits:
            break
        out = []
        for f in F:
            fl = [int(f[0]), int(f[1]), int(f[2])]
            done = False
            for e in range(3):
                a, b = fl[e], fl[(e + 1) % 3]
                key = (min(a, b), max(a, b))
                if key not in splits:
                    continue
                w, t = splits[key]
                if (a, b) != (key[0], key[1]):
                    t = 1.0 - t          # edge stored in opposite direction
                c = fl[(e + 2) % 3]
                out.append((a, w, c))
                out.append((w, b, c))
                for k, lua in src[a].items():
                    if k in src[b] and k not in src[w]:
                        la = np.asarray(lua, dtype=float)
                        lb = np.asarray(src[b][k], dtype=float)
                        luv = la + t * (lb - la)
                        src[w][k] = (float(luv[0]), float(luv[1]))
                done = True
                break                    # one split per face per pass
            if not done:
                out.append(tuple(fl))
        F = np.asarray(out, dtype=int)
    return F


def _build_mesh(members: list[SurfaceParam], tol_m: float,
                hint_pts: np.ndarray | None) -> _ChartMesh | None:
    weld_tol = max(1e-6, 0.1 * tol_m)
    on_tol = max(10.0 * weld_tol, tol_m)
    pts_all, src_all, faces_all = [], [], []
    offset = 0
    for k, member in enumerate(members):
        dom = _member_domain(member, hint_pts, on_tol)
        if dom is None:
            continue
        try:
            pts, uvs, faces = _facet_member(member, dom, tol_m)
        except Exception:  # noqa: BLE001 — member disqualifies itself
            continue
        if not np.isfinite(pts).all():
            continue
        pts_all.append(pts)
        src_all.extend({k: (float(u), float(v))} for u, v in uvs)
        faces_all.append(faces + offset)
        offset += len(pts)
    if not pts_all:
        logger.debug("LSCM: no facetable members")
        return None
    V = np.vstack(pts_all)
    F = np.vstack(faces_all)
    V, src, remap = _weld(V, src_all, weld_tol)
    F = remap[F]
    F = _stitch(V, F, src, max(weld_tol, 0.5 * tol_m))
    # drop degenerate triangles
    F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 2] != F[:, 0])]
    if len(F):
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        F = F[np.linalg.norm(n, axis=1) > 1e-14]
    if len(F) == 0:
        logger.debug("LSCM: empty mesh")
        return None
    # the chart must be a single connected component
    used = np.unique(F)
    rows = np.concatenate([F[:, 0], F[:, 1], F[:, 2]])
    cols = np.concatenate([F[:, 1], F[:, 2], F[:, 0]])
    adj = coo_matrix((np.ones(len(rows)), (rows, cols)),
                     shape=(len(V), len(V)))
    _, labels = connected_components(adj, directed=False)
    if len(np.unique(labels[used])) > 1:
        logger.debug("LSCM: members do not form a connected mesh")
        return None
    # drop unused vertices and make the winding consistent
    remap2 = -np.ones(len(V), dtype=int)
    remap2[used] = np.arange(len(used))
    V, src = V[used], [src[i] for i in used]
    F = remap2[F]
    mesh = trimesh.Trimesh(V, F, process=False)
    trimesh.repair.fix_normals(mesh)
    F = np.asarray(mesh.faces, dtype=int)
    # per-triangle source member: one present at all three corners
    tri_member = np.full(len(F), -1, dtype=int)
    for i, f in enumerate(F):
        common = set(src[f[0]]) & set(src[f[1]]) & set(src[f[2]])
        if common:
            tri_member[i] = min(common)
    return _ChartMesh(V, F, src, tri_member)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_lscm.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-geometry/src/ocx_geometry/lscm.py tests/test_render_lscm.py
git commit -m "feat: welded multi-member chart mesh for LSCM parameterization"
```

---

### Task 3: LSCM solve, metric rescale, and the LscmParam chart

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/lscm.py` (append)
- Modify: `tests/test_render_lscm.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_lscm.py`:

```python
class TestLscmFlat:
    def test_single_patch_chart_is_metric_and_exact(self):
        from ocx_geometry.lscm import make_lscm
        m = make_param(_grid_patch("p", 0.0, 0.0, 4.0), LR, tol_m=0.01)
        chart = make_lscm([m], tol_m=0.01)
        assert chart is not None
        pts = np.array([[0.0, 0, 0], [4.0, 0, 0], [4.0, 4, 0],
                        [0.0, 4, 0], [2.0, 2, 0]])
        uv = chart.inverse(pts)
        # metric chart: UV distances match 3-D distances
        assert np.linalg.norm(uv[1] - uv[0]) == pytest.approx(4.0, rel=0.05)
        np.testing.assert_allclose(chart.evaluate(uv), pts, atol=1e-6)

    def test_normals_are_unit_and_perpendicular(self):
        from ocx_geometry.lscm import make_lscm
        chart = make_lscm(_grid_members(), tol_m=0.01)
        assert chart is not None
        uv = chart.inverse(np.array([[1.0, 1.0, 0.0], [3.0, 3.0, 0.0]]))
        n = chart.normals(uv)
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0, atol=1e-9)
        np.testing.assert_allclose(np.abs(n[:, 2]), 1.0, atol=1e-9)


class TestLscm2DGrid:
    """Chart over a 2-D patch grid — the TR04 hull patch-layout regression
    (replaces TestComposite2DGrid)."""

    def _chart(self):
        from ocx_geometry.lscm import make_lscm
        chart = make_lscm(_grid_members(), tol_m=0.01)
        assert chart is not None, "LSCM chart failed to build"
        return chart

    def _contour(self):
        t = np.arange(0.0, 4.0, 0.25)
        z = np.zeros_like(t)
        return np.concatenate([
            np.column_stack([t, z, z]),
            np.column_stack([np.full_like(t, 4.0), t, z]),
            np.column_stack([4.0 - t, np.full_like(t, 4.0), z]),
            np.column_stack([z, 4.0 - t, z]),
        ])

    def test_roundtrip_on_contour(self):
        chart = self._chart()
        contour = self._contour()
        out = chart.evaluate(chart.inverse(contour))
        err = np.linalg.norm(out - contour, axis=1)
        assert err.max() < 1e-6, f"max round-trip error {err.max():.2e} m"

    def test_roundtrip_on_interior_points(self):
        chart = self._chart()
        xs = np.linspace(0.2, 3.8, 7)            # includes the seam at 2.0
        pts = np.array([[x, y, 0.0] for x in xs for y in xs])
        out = chart.evaluate(chart.inverse(pts))
        err = np.linalg.norm(out - pts, axis=1)
        assert err.max() < 1e-6, f"max round-trip error {err.max():.2e} m"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_lscm.py -v -k "Flat or 2DGrid"`
Expected: FAIL — `ImportError: cannot import name 'make_lscm'`

- [ ] **Step 3: Implement the solve and the chart**

Append to `packages/ocx-geometry/src/ocx_geometry/lscm.py`:

```python
def _longest_boundary_loop(bnd: np.ndarray) -> list[int] | None:
    """Longest closed loop among the directed boundary edges."""
    nxt = {int(a): int(b) for a, b in bnd}
    seen: set[int] = set()
    best: list[int] | None = None
    for start in list(nxt):
        if start in seen:
            continue
        loop, v = [], start
        while v in nxt and v not in seen:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if v != start:
            continue                     # open chain, not a loop
        if best is None or len(loop) > len(best):
            best = loop
    return best


def _lscm_uv(V: np.ndarray, F: np.ndarray) -> np.ndarray | None:
    """Flatten the mesh with LSCM: minimize conformal energy
    x' (L_flat - 2A) x with two pinned boundary vertices.
    x = [u_0..u_{n-1}, v_0..v_{n-1}]."""
    n = len(V)
    i0, i1, i2 = F[:, 0], F[:, 1], F[:, 2]

    def cot(a, b):
        cr = np.linalg.norm(np.cross(a, b), axis=1)
        return (a * b).sum(axis=1) / np.maximum(cr, 1e-15)

    e0, e1, e2 = V[i2] - V[i1], V[i0] - V[i2], V[i1] - V[i0]
    c0, c1, c2 = cot(e2, -e1), cot(e0, -e2), cot(e1, -e0)
    rows = np.concatenate([i1, i2, i2, i0, i0, i1])
    cols = np.concatenate([i2, i1, i0, i2, i1, i0])
    vals = 0.5 * np.concatenate([c0, c0, c1, c1, c2, c2])
    W = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    L = diags(np.asarray(W.sum(axis=1)).ravel()) - W

    bnd = _boundary_edges(F)
    if len(bnd) < 2:
        return None
    ar, ac, av = [], [], []
    for a, b in bnd:                     # x'Ax = sum 0.5 (u_a v_b - u_b v_a)
        ar += [a, n + b, b, n + a]
        ac += [n + b, a, n + a, b]
        av += [0.25, 0.25, -0.25, -0.25]
    A = coo_matrix((av, (ar, ac)), shape=(2 * n, 2 * n)).tocsr()
    Q = (bmat([[L, None], [None, L]]) - 2.0 * A).tocsr()

    loop = _longest_boundary_loop(bnd)
    if loop is None or len(loop) < 2:
        return None
    p0, p1 = loop[0], loop[len(loop) // 2]
    fixed = np.array([p0, p1, n + p0, n + p1])
    xb = np.array([0.0, 1.0, 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * n), fixed)
    rhs = -Q[free][:, fixed] @ xb
    xf = spsolve(Q[free][:, free].tocsc(), rhs)
    x = np.empty(2 * n)
    x[fixed], x[free] = xb, xf
    if not np.isfinite(x).all():
        return None
    return np.column_stack([x[:n], x[n:]])


class LscmParam(SurfaceParam):
    """Metric LSCM chart over a welded multi-member facet mesh."""

    def __init__(self, members: list[SurfaceParam], cm: _ChartMesh,
                 uv: np.ndarray) -> None:
        self.members = members
        self._V, self._F = cm.V, cm.F
        self._src, self._tri_member = cm.src, cm.tri_member
        self._uv = uv
        self._mesh = trimesh.Trimesh(self._V, self._F, process=False)
        self._tree = STRtree([shapely.Polygon(t) for t in uv[self._F]])

    def _locate_uv(self, uv):
        uv = np.atleast_2d(np.asarray(uv, dtype=float))
        tid = np.asarray(self._tree.nearest(
            [shapely.Point(p) for p in uv]), dtype=int)
        tri2 = self._uv[self._F[tid]]

        def pad(a):
            return np.concatenate(
                [a, np.zeros(a.shape[:-1] + (1,))], axis=-1)

        bary = trimesh.triangles.points_to_barycentric(pad(tri2), pad(uv))
        bary = np.clip(bary, 0.0, None)   # outside points snap to the tri
        bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-300)
        return tid, bary

    def _source_eval(self, tid, bary, fn, fallback):
        """fn(member, local_uv) per point grouped by source member;
        rows stay on ``fallback`` where no source exists or fn fails."""
        corners = self._F[tid]
        ks = self._tri_member[tid]
        out = np.array(fallback, dtype=float, copy=True)
        for k in np.unique(ks[ks >= 0]):
            sel = np.nonzero(ks == k)[0]
            luv = np.array([[self._src[c][k] for c in corners[i]]
                            for i in sel])
            local = np.einsum("ij,ijk->ik", bary[sel], luv)
            try:
                val = np.asarray(fn(self.members[k], local), dtype=float)
            except Exception:  # noqa: BLE001 — keep the mesh fallback
                continue
            good = np.isfinite(val).all(axis=1)
            out[sel[good]] = val[good]
        return out

    def evaluate(self, uv):
        tid, bary = self._locate_uv(uv)
        fallback = np.einsum("ij,ijk->ik", bary, self._V[self._F[tid]])
        return self._source_eval(tid, bary,
                                 lambda m, luv: m.evaluate(luv), fallback)

    def inverse(self, pts):
        pts = np.atleast_2d(np.asarray(pts, dtype=float))
        closest, _, tid = trimesh.proximity.closest_point(self._mesh, pts)
        bary = trimesh.triangles.points_to_barycentric(
            self._V[self._F[tid]], np.asarray(closest, dtype=float))
        bary = np.clip(bary, 0.0, None)
        bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-300)
        return np.einsum("ij,ijk->ik", bary, self._uv[self._F[tid]])

    def normals(self, uv):
        tid, bary = self._locate_uv(uv)
        fallback = np.asarray(self._mesh.face_normals)[tid]
        n = self._source_eval(tid, bary,
                              lambda m, luv: m.normals(luv), fallback)
        flip = (n * fallback).sum(axis=1) < 0.0   # orient with mesh winding
        n[flip] *= -1.0
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True),
                              1e-15)

    def max_edge_m(self, tol_m):
        edges = [e for e in (m.max_edge_m(tol_m) for m in self.members)
                 if e is not None]
        return min(edges) if edges else None


def make_lscm(members: list[SurfaceParam], tol_m: float,
              hint_pts: np.ndarray | None = None) -> LscmParam | None:
    """LSCM chart over collection members, or None if not buildable."""
    try:
        cm = _build_mesh(members, tol_m, hint_pts)
        if cm is None:
            return None
        uv = _lscm_uv(cm.V, cm.F)
        if uv is None:
            logger.debug("LSCM: flattening failed")
            return None
        tri3 = cm.V[cm.F]
        a3 = 0.5 * np.linalg.norm(
            np.cross(tri3[:, 1] - tri3[:, 0], tri3[:, 2] - tri3[:, 0]),
            axis=1)
        t2 = uv[cm.F]
        a2s = 0.5 * ((t2[:, 1, 0] - t2[:, 0, 0])
                     * (t2[:, 2, 1] - t2[:, 0, 1])
                     - (t2[:, 2, 0] - t2[:, 0, 0])
                     * (t2[:, 1, 1] - t2[:, 0, 1]))
        ok = (np.abs(a2s) > 1e-18) & (a3 > 1e-18)
        if not ok.any():
            logger.debug("LSCM: chart collapsed")
            return None
        maj = 1.0 if a2s[ok].sum() >= 0.0 else -1.0
        flipped = float((np.sign(a2s[ok]) != maj).mean())
        if flipped > _MAX_FLIPPED:
            logger.debug("LSCM: {:.2%} flipped UV triangles", flipped)
            return None
        ratio = a3[ok] / np.abs(a2s[ok])
        if float(ratio.max() / ratio.min()) > _MAX_SCALE_RATIO:
            logger.debug("LSCM: per-triangle scale spread too large")
            return None
        uv = uv * math.sqrt(float(np.median(ratio)))
        return LscmParam(members, cm, uv)
    except Exception as exc:  # noqa: BLE001 — chart disqualifies itself
        logger.debug("LSCM chart failed: {}", exc)
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_lscm.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-geometry/src/ocx_geometry/lscm.py tests/test_render_lscm.py
git commit -m "feat: LSCM solve and LscmParam chart with exact source evaluation"
```

---

### Task 4: Curved-geometry and failure-path tests

**Files:**
- Modify: `tests/test_render_lscm.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_lscm.py`:

```python
class TestLscmCurved:
    def test_evaluation_stays_exactly_on_member_surfaces(self):
        """Bottom plane + bilge cylinder + side plane: every evaluated point
        must lie exactly on one of the true member surfaces (not on the
        chart facets), and round-trip near the original."""
        from ocx_geometry.lscm import make_lscm
        members, hints = _bilge_members_and_hints()
        chart = make_lscm(members, tol_m=0.01, hint_pts=hints)
        assert chart is not None
        out = chart.evaluate(chart.inverse(hints))
        d_bot = np.abs(out[:, 2])
        d_side = np.abs(out[:, 1] - 2.0)
        d_cyl = np.abs(
            np.linalg.norm(out[:, 1:] - [1.0, 1.0], axis=1) - 1.0)
        d = np.minimum(np.minimum(d_bot, d_side), d_cyl)
        assert d.max() < 1e-9, f"off-surface by {d.max():.2e} m"
        err = np.linalg.norm(out - hints, axis=1)
        assert err.max() < 0.05, f"round-trip error {err.max():.3f} m"


class TestLscmFailure:
    def test_make_lscm_disconnected_returns_none(self):
        from ocx_geometry.lscm import make_lscm
        a = make_param(_grid_patch("a", 0.0, 0.0), LR, tol_m=0.01)
        b = make_param(_grid_patch("b", 10.0, 0.0), LR, tol_m=0.01)
        assert make_lscm([a, b], tol_m=0.01) is None

    def test_make_lscm_never_raises(self):
        from ocx_geometry.lscm import make_lscm
        from ocx_geometry.surfaces import PlaneParam
        p = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
        # unbounded member, no hints -> None, no exception
        assert make_lscm([p, p], tol_m=0.01, hint_pts=None) is None
        # degenerate hints (collinear) -> None, no exception
        hints = np.array([[x, 0.0, 0.0] for x in np.linspace(0, 1, 5)])
        assert make_lscm([p, p], tol_m=0.01, hint_pts=hints) is None
```

- [ ] **Step 2: Run tests to verify current state**

Run: `uv run pytest tests/test_render_lscm.py -v`
Expected: all pass (the implementation from Tasks 2–3 already covers these paths). If any FAIL, fix the implementation — these are acceptance tests for the curved/failure behaviour, and the bilge test exercises `_stitch` (plane seams sampled at 2 points vs ~15 on the cylinder).

- [ ] **Step 3: Commit**

```bash
git add tests/test_render_lscm.py
git commit -m "test: curved-surface exactness and failure paths for LSCM chart"
```

---

### Task 5: Replace CompositeParam in the render pipeline

**Files:**
- Modify: `packages/ocx-render/src/ocx_render/render.py` (imports ~line 21-25; `_tessellate_plates` ~line 175-220)
- Modify: `packages/ocx-geometry/src/ocx_geometry/surfaces.py` (delete lines 438-626: `CompositeParam` + `make_composite`)
- Modify: `tests/test_render_surfaces_ext.py` (delete `TestComposite2DGrid`, keep `_grid_patch` if other tests use it — they don't; delete it too)
- Modify: `tests/test_render_integration.py` (docstring only)
- Modify: `docs/superpowers/specs/2026-10-12-lscm-parameterization-design.md` (hint_pts amendment)

- [ ] **Step 1: Update render.py imports**

In `packages/ocx-render/src/ocx_render/render.py`, replace:

```python
from ocx_geometry.surfaces import (
    SurfaceParam,
    make_composite,
    make_param,
)
```

with:

```python
from ocx_geometry.lscm import make_lscm
from ocx_geometry.surfaces import (
    SurfaceParam,
    make_param,
)
```

- [ ] **Step 2: Rewrite `_tessellate_plates` as two passes**

Replace the whole `_tessellate_plates` function body with:

```python
def _tessellate_plates(vessel: IrVessel,
                       params: dict[str, list[SurfaceParam]],
                       tess: ITessellator, length: LengthResolver,
                       options: TessellationOptions, result: RenderResult) -> None:
    # Pass 1: sample contours; collect them per panel as hints that bound
    # otherwise-unbounded chart members (planes, cylinders).
    prepared = []
    hints: dict[str, list[np.ndarray]] = {}
    for plate in vessel.plates.values():
        panel_id = (plate.parent_ref.id
                    if plate.parent_ref.kind == ParentKind.PANEL else None)
        if panel_id is None:
            result.skipped[plate.id] = "not parented to a panel"
            continue
        candidates = params.get(panel_id) or []
        if not candidates:
            result.skipped[plate.id] = "no resolvable panel surface"
            continue
        if plate.outer_contour is None:
            result.skipped[plate.id] = "no outer contour"
            continue
        contour = sample_contour(plate.outer_contour, length,
                                 options.tolerance_m, options.snap_tolerance_m)
        if contour is None:
            result.skipped[plate.id] = "contour unsampleable or open"
            continue
        prepared.append((plate, panel_id, candidates, contour))
        hints.setdefault(panel_id, []).append(contour)

    # Pass 2: one LSCM chart per multi-member panel, shared by its plates.
    lscm_cache: dict[str, SurfaceParam | None] = {}
    for plate, panel_id, candidates, contour in prepared:
        if len(candidates) > 1:
            if panel_id not in lscm_cache:
                lscm_cache[panel_id] = make_lscm(
                    candidates, options.tolerance_m,
                    np.vstack(hints[panel_id]))
            param = lscm_cache[panel_id] or _best_param(candidates, contour)
        else:
            param = candidates[0]
        panel = vessel.panels.get(panel_id)
        holes, hole_failures = _hole_polylines(plate, panel, vessel, length,
                                               options)
        for key, reason in hole_failures.items():
            logger.warning("CutBy hole not applied to {} — {} ({})",
                           plate.id, reason, key)
        result.skipped.update(hole_failures)
        pm = tess.tessellate_trimmed_surface(
            plate.id, plate.name or plate.id, "plate", contour, holes,
            param, options)
        if pm is None:
            result.skipped[plate.id] = "triangulation failed"
            continue
        pm.extras.update({"id": plate.id, "guid": plate.guidref,
                          "kind": "plate", "functionType": plate.function_type,
                          "panel_id": panel_id})
        result.meshes.append(pm)
```

(The hole/tessellate/extras block is byte-identical to the current one — only the surrounding loop structure and param selection change.)

- [ ] **Step 3: Delete `CompositeParam` and `make_composite` from surfaces.py**

In `packages/ocx-geometry/src/ocx_geometry/surfaces.py`, delete the entire `class CompositeParam(SurfaceParam):` block and the `def make_composite(...)` function (lines 438–626; everything from `class CompositeParam` to the end of `make_composite`'s body). Keep `_member_fit` — `lscm.py` and `_best_param` use it.

- [ ] **Step 4: Delete the composite tests**

In `tests/test_render_surfaces_ext.py`, delete the `_grid_patch` function and the whole `TestComposite2DGrid` class (lines ~81–132). Their coverage now lives in `tests/test_render_lscm.py`.

- [ ] **Step 5: Update the integration-test docstring**

In `tests/test_render_integration.py` (~line 67), the outer-shell test docstring mentions "composite charts". Reword that sentence to reference the LSCM chart, e.g.:

```python
    Regression for distorted/missing shell plates: the LSCM chart over
```

(keep the rest of the docstring as-is).

- [ ] **Step 6: Verify nothing still references the deleted names**

Run: `uv run python -c "import subprocess,sys; sys.exit(0)"` then search:
```bash
git grep -n "make_composite\|CompositeParam" -- "*.py"
```
Expected: no matches.

- [ ] **Step 7: Amend the spec with the hint_pts deviation**

In `docs/superpowers/specs/2026-10-12-lscm-parameterization-design.md`, in the **Architecture** section, replace the sentence fragment "fallback chain per plate is `lscm_param or _best_param(candidates, contour)`. The chart is contour-independent, which makes per-panel caching sound." with:

```markdown
  fallback chain per plate is `lscm_param or _best_param(candidates, contour)`.
  **Amendment (implementation):** `make_lscm(members, tol_m, hint_pts)` takes
  the panel's concatenated sampled plate contours as *hint points*: members
  without an intrinsic UV domain (planes, cylinders — only
  `NurbsSurfaceParam` carries knot-domain bounds) are bounded by the bbox of
  their on-surface hint points in member-local UV. `_tessellate_plates` runs
  two passes — contour sampling first, then chart build + tessellation — so
  the per-panel chart and cache remain sound.
```

Also in **Chart construction**, step 1, append after the first sentence: "Members without an intrinsic domain use the hint-point bbox (see Architecture amendment); members with no on-surface hints or no 2-D extent are excluded from the mesh. T-junctions left by density mismatches along member seams are stitched by splitting the hosting boundary triangle at the junction vertex."

- [ ] **Step 8: Run the fast test suite and ruff**

Run: `uv run pytest` (expect: all pass, ~679 minus the 2 deleted composite tests plus the 11 new LSCM tests) and `uv run ruff check .`
Expected: 0 failures, ruff clean. Watch specifically `tests/test_render_model.py::TestRenderModel::test_plate_spanning_collection_members_projects_onto_each` and `test_collection_picks_member_matching_plate_contour` — they now exercise the LSCM path end-to-end.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat!: replace CompositeParam with per-panel LSCM chart

Multi-patch panels are now parameterized with a welded-mesh LSCM chart
(exact source-surface evaluation), built once per panel from the plates'
contour hints. The developed girth/spine CompositeParam and its
heuristics are removed."
```

---

### Task 6: Integration verification

**Files:**
- No source changes expected (fixes only if the gate fails).

- [ ] **Step 1: Run the integration suite**

Run (slow, ~5 min): `uv run pytest -m integration -v`
Expected: all pass, including `test_tr04_tc14a_outer_shell_renders_all_plates` (24/24 plates, 0 skipped, every contour point < 0.1 m from mesh vertices).

- [ ] **Step 2: Manual render checks**

```bash
uv run ocx-render models\TR04\tr04_tc14a_outer_shell.3docx
uv run ocx-render models\TR04\tr04_tc14a_nast.3docx
```
Expected: outer-shell model renders 24/24 parts, 0 skipped. The full nast model must report the same or fewer skipped parts than before the change (baseline: check the log). Open the generated HTML viewers and visually confirm the outer shell is smooth and complete. Outputs (.glb/.html) are gitignored.

- [ ] **Step 3: Full suite once more**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 4: Commit any verification fixes**

If Steps 1–3 required fixes, commit them with a descriptive message. If not, nothing to commit.

---

## Self-review checklist (done at planning time)

- Spec coverage: architecture (T2/T3/T5), construction steps 1–4 (T2/T3), query behaviour (T3), error ladder (T3/T4/T5), removal of CompositeParam (T5), all five unit-test scenarios (T2/T3/T4), integration gate (T6), scipy dep (T1), spec amendment (T5.7).
- The cylinder/bilge test replaces the spec's "quarter-cylinder from 2 NURBS patches" — geomdl B-splines are non-rational and cannot represent circles exactly, so the analytic `CylinderParam` is used instead; it additionally exercises T-junction stitching and hint-based domains.
- Known limitation (acceptable, documented in code): periodic members' hint inversion uses `np.unwrap` over the concatenated hint sequence; multi-loop hint sets on near-full cylinders could mis-wrap. Falls back via `make_lscm → None → _best_param`.
