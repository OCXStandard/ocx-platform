# OCX Rule Checks — Phase B (Geometry Rules) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real check logic for 10 geometry-dependent best-practice rules (OCX-TOP-001/002/003/004/005/008/009, OCX-PROP-001/002/003), leaving OCX-TOP-006/007 as stubs.

**Architecture:** Math lives in the `ocx-geometry` kernel (new `topology2d.py` + extensions to `measure.py` and `surfaces.py`); rule checks in `ocx_rules.packs.best_practice.checks` stay thin orchestration over the IR. `ocx-rules` gains a dependency on `ocx-geometry` and a lazily-built `GeometryContext`. **No meshing anywhere** — only curve sampling, analytic/B-spline surface evaluation and shapely 2-D polygon ops.

**Tech Stack:** Python 3.12, uv workspace, numpy, shapely 2.x, mapbox-earcut, scipy NdBSpline (analytic B-spline derivatives), lxml, loguru, pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-ocx-rule-checks-phase-b-design.md`

**Working conventions (read first):**
- Run everything from the repo root `C:\PythonDev\ocx-platform` with `uv run ...`.
- Branch: create `feat/rules-phase-b` off `master` before Task 1: `git checkout -b feat/rules-phase-b`.
- Ruff: line length 100, rules E4/E7/E9/F/I. Run `uv run ruff check <files> --fix` before each commit.
- Every commit message ends with the trailer line: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- Checks NEVER raise on bad model data — skip the element (optionally `logger.debug`) and continue. `RuleManager` crash-isolation is only a backstop.
- A check returns `list[Finding]`; empty list ⇒ PASSED. `Finding(message, element_id=None, guid=None, location=None)` is frozen.
- Loguru only (`from loguru import logger`); no print, no stdlib logging.
- Existing helpers you will reuse:
  - `ocx_geometry.measure.LengthResolver` — `to_m(value, unit_id)`, `point(IrPoint3D) -> np.ndarray (3,)`, `qty(Quantity|None) -> float|None` (metres).
  - `ocx_geometry.curves.sample_curve(curve, length, tol_m) -> np.ndarray(N,3)|None` — handles Line3D, PolyLine3D, CircumArc3D, Circle3D, Ellipse3D, NURBS3D, CompositeCurve3D.
  - `ocx_geometry.surfaces.make_param(surface, length, tol_m) -> SurfaceParam|None` — Plane/Cylinder/Cone/Sphere/Extruded/Nurbs params with `evaluate(uv)`, `inverse(pts)`, `normals(uv)`, `periodic_u`.
  - `ocx_geometry.holes.parametric_profile(IrParametricHole, length, tol) -> np.ndarray(N,2)|None` (closed local ring) and `place_hole(profile_2d, IrTransformation, length) -> np.ndarray(N,3)|None`.
  - `ocx_geometry.sections_2d.section_polygon(IrSection, length) -> np.ndarray(N,2)|None` (closed, CCW, no repeated last point).
- IR objects you will touch (all in `ocx_model_core.model.ir`): `IrVessel` (flat dicts `panels/plates/stiffeners/pillars/seams/materials/sections/surfaces/surface_collections/ref_planes`, `unit_registry: dict[str, IrUnit]`, `hole_shape_catalogue`), `IrPanel` (`limited_by: list[IrLimitedByRef]`, `seam_ids`, `plate_ids`, `unbounded_geometry`, `cut_by_holes`, `cut_by_contours`, `mass_properties`), `IrPlate` (`outer_contour`, `cut_by_holes`, `cut_by_contours`, `thickness`, `material_ref`, `mass_properties`), `IrStiffener`/`IrPillar` (`trace`, `inclinations: list[IrInclination(web_direction, flange_direction, position)]`), `IrSeam.trace_line`, `IrHole2D(contour, parametric)`, `IrMassProperties(moulded_dry_weight, physical_dry_weight, moulded_cog, physical_cog)`, `Quantity(value, unit)`, `IrUnit.to_si_factor`.
- Test helper patterns: `tests/rules_xml.py::context_for(body)` builds a `ValidationContext` with an inline XML tree; tests inject fakes with `ctx.__dict__["vessel"] = ...` / `ctx.__dict__["geometry"] = ...` (cached_property override). Geometry-check tests build small real IR objects — no XML needed.

---

### Task 0: Branch

- [ ] **Step 1:** `git checkout master && git pull && git checkout -b feat/rules-phase-b`

---

### Task 1: IR carries FreeEdgeCurve3D geometry (`IrLimitedByRef.curve`)

The IR builder currently drops the inline curve geometry inside a panel's
`LimitedBy/FreeEdgeCurve3D` elements, keeping only name/GUID. TOP-001 needs
that geometry. Add a `curve` field and populate it.

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py` (class `IrLimitedByRef`)
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (FreeEdgeCurve3D loop, around line 1515)
- Create: `tests/test_builder_limited_by_curve.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_builder_limited_by_curve.py`:

```python
"""FreeEdgeCurve3D boundary geometry must survive into IrLimitedByRef.curve."""
from __future__ import annotations

from pathlib import Path

import pytest
from ocx_model_core.model.ir.geometry import IrCurve3D

from tests.conftest import _build_session


@pytest.fixture()
def composedof_vessel(stub_dir_310: Path):
    return _build_session(stub_dir_310 / "composedof.3docx")


class TestFreeEdgeCurveGeometry:
    def test_free_edge_refs_carry_curves(self, composedof_vessel):
        panels = list(composedof_vessel.panels.values())
        assert panels, "stub model must contain at least one panel"
        fec_refs = [r for p in panels for r in p.limited_by
                    if r.ref_type == "FreeEdgeCurve3D"]
        assert fec_refs, "stub model must contain FreeEdgeCurve3D boundaries"
        for ref in fec_refs:
            assert isinstance(ref.curve, IrCurve3D), (
                f"FreeEdgeCurve3D ref {ref.guidref!r} lost its geometry")

    def test_named_refs_have_no_curve(self, composedof_vessel):
        other = [r for p in composedof_vessel.panels.values()
                 for r in p.limited_by if r.ref_type != "FreeEdgeCurve3D"]
        assert all(r.curve is None for r in other)
```

Note: `_build_session` and `stub_dir_310` already exist in `tests/conftest.py`.
If `_build_session` is not importable (it is module-private), copy its two-line
body instead: parse with `OcxParser().parse(str(path))`, then
`get_builder(root.schema_version).build(root)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_builder_limited_by_curve.py -q`
Expected: FAIL — `IrLimitedByRef` has no attribute `curve` (or curve is None).

- [ ] **Step 3: Implement**

In `structural.py`, add the field to `IrLimitedByRef` (after `contour_mid_point`):

```python
    contour_mid_point: IrPoint3D | None = None
    curve: "IrCurve3D | None" = None  # inline FreeEdgeCurve3D geometry only
```

`IrCurve3D` is already imported in `structural.py` via the
`ocx_model_core.model.ir.geometry` import block (check; add it to that import
list if absent).

In `v3_builder.py`, replace the FreeEdgeCurve3D loop body:

```python
            # FreeEdgeCurve3D is an inline geometry element (no local_ref).
            # Use guidref as identifier; fall back to name if guidref is absent.
            for fec in getattr(limited_by, "free_edge_curve3_d", []):
                guid = getattr(fec, "guidref", None)
                name_val = getattr(fec, "name", None)
                fec_curve = None
                for attr in self._CONTOUR_ATTRS:
                    raw_c = getattr(fec, attr, None)
                    if isinstance(raw_c, list):  # 2.8.6 list-typed fields
                        raw_c = raw_c[0] if raw_c else None
                    if raw_c is not None:
                        fec_curve = self._build_curve(raw_c)
                        break
                limited_by_refs.append(
                    IrLimitedByRef(
                        ref_type="FreeEdgeCurve3D",
                        local_ref=name_val or "",
                        guidref=guid,
                        curve=fec_curve,
                    )
                )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_builder_limited_by_curve.py tests/test_builders.py -q`
Expected: all PASS. Also run `uv run pytest tests -q -k "builder"` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py tests/test_builder_limited_by_curve.py
git commit -m "feat(ocx-model-core): keep FreeEdgeCurve3D geometry on IrLimitedByRef"
```

---

### Task 2: Kernel — contour chaining and gap measurement (`chain_polylines`, `ordered_junction_gaps`)

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/measure.py`
- Create: `tests/test_measure_chain.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_measure_chain.py`:

```python
"""Tests for polyline chaining / gap measurement in ocx_geometry.measure."""
from __future__ import annotations

import numpy as np

from ocx_geometry.measure import chain_polylines, ordered_junction_gaps


def _seg(a, b):
    return np.array([a, b], dtype=float)


# Four sides of the unit square in scrambled order and orientation.
_SQ = [
    _seg([0, 0, 0], [1, 0, 0]),
    _seg([1, 1, 0], [1, 0, 0]),   # reversed
    _seg([0, 1, 0], [1, 1, 0]),
    _seg([0, 0, 0], [0, 1, 0]),   # reversed
]


class TestChainPolylines:
    def test_closed_square_has_zero_gaps(self):
        ring, gaps = chain_polylines(_SQ)
        assert ring is not None and len(ring) >= 4
        assert len(gaps) == 4          # 3 junctions + closure
        assert max(gaps) < 1e-12

    def test_open_square_reports_closure_gap(self):
        open_sq = [s.copy() for s in _SQ]
        open_sq[3][0] = [0.005, 0.0, 0.0]   # pull one corner 5 mm away
        ring, gaps = chain_polylines(open_sq)
        assert ring is not None
        assert abs(max(gaps) - 0.005) < 1e-9

    def test_single_closed_polyline(self):
        ring = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]],
                        dtype=float)
        chained, gaps = chain_polylines([ring])
        assert chained is not None
        assert max(gaps) < 1e-12

    def test_empty_input_returns_none(self):
        ring, gaps = chain_polylines([])
        assert ring is None and gaps == []


class TestOrderedJunctionGaps:
    def test_continuous_in_declared_order(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1, 0, 0], [1, 1, 0]),
                _seg([1, 1, 0], [0, 1, 0])]
        gaps = ordered_junction_gaps(segs)
        assert len(gaps) == 2 and max(gaps) < 1e-12

    def test_reversed_segment_still_continuous(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1, 1, 0], [1, 0, 0])]     # reversed second segment
        gaps = ordered_junction_gaps(segs)
        assert len(gaps) == 1 and gaps[0] < 1e-12

    def test_gap_reported(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1.002, 0, 0], [2, 0, 0])]
        gaps = ordered_junction_gaps(segs)
        assert abs(gaps[0] - 0.002) < 1e-9

    def test_fewer_than_two_segments(self):
        assert ordered_junction_gaps([_seg([0, 0, 0], [1, 0, 0])]) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_measure_chain.py -q`
Expected: FAIL — ImportError (`chain_polylines` not defined).

- [ ] **Step 3: Implement**

Append to `packages/ocx-geometry/src/ocx_geometry/measure.py`:

```python
def chain_polylines(
    polylines: list[np.ndarray],
) -> tuple[np.ndarray | None, list[float]]:
    """Greedily chain 3-D polylines end-to-end into one loop.

    Unlike ``curves._sample_composite`` this never fails on a gap: segments
    are always attached at their nearest endpoints and every junction gap is
    recorded. Returns ``(ring, gaps)`` where ``ring`` is the (N, 3) chained
    polyline (not explicitly closed) and ``gaps`` has one entry per junction
    plus a final entry for the closure gap ring-end -> ring-start.
    Returns ``(None, [])`` when no usable polylines are given.
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if not parts:
        return None, []
    out = parts[0]
    remaining = parts[1:]
    gaps: list[float] = []
    while remaining:
        tail = out[-1]
        best_i, best_d, best_rev = 0, np.inf, False
        for i, pts in enumerate(remaining):
            d0 = float(np.linalg.norm(pts[0] - tail))
            d1 = float(np.linalg.norm(pts[-1] - tail))
            if d0 < best_d:
                best_i, best_d, best_rev = i, d0, False
            if d1 < best_d:
                best_i, best_d, best_rev = i, d1, True
        pts = remaining.pop(best_i)
        if best_rev:
            pts = pts[::-1]
        gaps.append(best_d)
        out = np.vstack([out, pts])
    gaps.append(float(np.linalg.norm(out[-1] - out[0])))
    return out, gaps


def ordered_junction_gaps(polylines: list[np.ndarray]) -> list[float]:
    """Junction gaps between consecutive polylines in their declared order.

    Each segment may be used reversed; the orientation minimising the gap to
    the current chain end is chosen. Returns one gap per junction (no closure
    gap). Segments that are None/too short are ignored by the caller.
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if len(parts) < 2:
        return []
    gaps: list[float] = []
    tail = parts[0][-1]
    # orient the first segment so its far end is closest to segment 2
    d_fwd = float(np.linalg.norm(parts[0][-1] - parts[1][0]))
    d_rev = float(np.linalg.norm(parts[0][0] - parts[1][0]))
    if min(float(np.linalg.norm(parts[0][0] - parts[1][-1])), d_rev) < \
            min(float(np.linalg.norm(parts[0][-1] - parts[1][-1])), d_fwd):
        tail = parts[0][0]
    for pts in parts[1:]:
        d0 = float(np.linalg.norm(pts[0] - tail))
        d1 = float(np.linalg.norm(pts[-1] - tail))
        if d1 < d0:
            gaps.append(d1)
            tail = pts[0]
        else:
            gaps.append(d0)
            tail = pts[-1]
    return gaps
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_measure_chain.py -q` — all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-geometry tests/test_measure_chain.py --fix
git add packages/ocx-geometry/src/ocx_geometry/measure.py tests/test_measure_chain.py
git commit -m "feat(ocx-geometry): polyline chaining with junction gap measurement"
```

---

### Task 3: Kernel — trimmed surface area without meshing (`surface_area`)

Area of a trimmed region given a surface parametrization and the trim polygon
in UV: triangulate the **UV polygon** (exact polygon decomposition with
earcut — not a tolerance-bearing 3-D mesh), then Gauss-quadrature the metric
`sqrt(EG − F²)` over each UV triangle. First derivatives come from a new
`SurfaceParam.first_derivs` method: analytic for planes and B-splines
(scipy `NdBSpline` partial derivatives — the same spline geomdl defines),
central differences otherwise.

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/surfaces.py` (`SurfaceParam`, `PlaneParam`, `NurbsSurfaceParam`)
- Modify: `packages/ocx-geometry/src/ocx_geometry/measure.py` (add `surface_area`)
- Create: `tests/test_measure_area.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_measure_area.py`:

```python
"""Tests for quadrature-based trimmed surface area."""
from __future__ import annotations

import math

import numpy as np

from ocx_geometry.measure import surface_area
from ocx_geometry.surfaces import CylinderParam, PlaneParam


def _plane():
    return PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]),
                      np.array([1.0, 0.0, 0.0]))


class TestPlaneArea:
    def test_unit_square(self):
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        assert abs(surface_area(_plane(), uv) - 1.0) < 1e-9

    def test_square_with_hole(self):
        outer = np.array([[0, 0], [2, 0], [2, 2], [0, 2]], dtype=float)
        hole = np.array([[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]],
                        dtype=float)
        a = surface_area(_plane(), outer, holes_uv=[hole])
        assert abs(a - (4.0 - 0.25)) < 1e-9

    def test_concave_polygon(self):
        # L-shape, area 3
        uv = np.array([[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]],
                      dtype=float)
        assert abs(surface_area(_plane(), uv) - 3.0) < 1e-9

    def test_degenerate_returns_zero(self):
        uv = np.array([[0, 0], [1, 0]], dtype=float)
        assert surface_area(_plane(), uv) == 0.0


class TestCylinderArea:
    def test_quarter_patch(self):
        # r=2; u is the angle, v metres along the axis (CylinderParam
        # evaluate: o + r*(cos u * x + sin u * y) + v * a).
        r, h = 2.0, 3.0
        param = CylinderParam(np.zeros(3), np.array([0.0, 0.0, 1.0]), r)
        uv = np.array([[0, 0], [math.pi / 2, 0], [math.pi / 2, h], [0, h]],
                      dtype=float)
        expected = r * (math.pi / 2) * h
        assert abs(surface_area(param, uv) - expected) / expected < 1e-3
```

Note: before writing the cylinder test, open `surfaces.py::CylinderParam.evaluate`
and confirm the (u, v) convention; adjust the expected formula if u is not the
plain angle (if `evaluate` uses `u / r` or similar, scale accordingly).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_measure_area.py -q`
Expected: FAIL — ImportError (`surface_area` not defined).

- [ ] **Step 3: Add `first_derivs` to the surface params**

In `surfaces.py`, inside `class SurfaceParam`, after `normals`:

```python
    def first_derivs(self, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(dS/du, dS/dv) at each uv — numeric central differences by default."""
        uv = np.asarray(uv, dtype=float)
        span = max(float(np.ptp(uv[:, 0])), float(np.ptp(uv[:, 1])), 1.0)
        eps = 1e-5 * span
        du = (self.evaluate(uv + [eps, 0.0]) - self.evaluate(uv - [eps, 0.0])) / (2 * eps)
        dv = (self.evaluate(uv + [0.0, eps]) - self.evaluate(uv - [0.0, eps])) / (2 * eps)
        return du, dv
```

In `PlaneParam` (exact, constant):

```python
    def first_derivs(self, uv):
        n = len(np.asarray(uv))
        return np.tile(self.u, (n, 1)), np.tile(self.v, (n, 1))
```

In `NurbsSurfaceParam` (analytic B-spline partials via the vectorised
evaluator; clip uv to the domain like `evaluate` does):

```python
    def first_derivs(self, uv):
        uv = self._clip_uv(np.asarray(uv, dtype=float).reshape(-1, 2))
        return self._spl(uv, nu=(1, 0)), self._spl(uv, nu=(0, 1))
```

- [ ] **Step 4: Add `surface_area` to `measure.py`**

Append to `measure.py` (new imports at top of file: `import mapbox_earcut`
— numpy is already imported):

```python
# 3-point Gauss rule on the reference triangle (degree-2 exact); barycentric.
_TRI_GAUSS = np.array([[2 / 3, 1 / 6, 1 / 6],
                       [1 / 6, 2 / 3, 1 / 6],
                       [1 / 6, 1 / 6, 2 / 3]])


def _triangulate_uv(outer: np.ndarray,
                    holes: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    rings = [np.asarray(outer, dtype=float)[:, :2]]
    rings += [np.asarray(h, dtype=float)[:, :2] for h in holes]
    verts = np.vstack(rings)
    ends = np.cumsum([len(r) for r in rings])
    tris = np.asarray(
        mapbox_earcut.triangulate_float64(verts, ends), dtype=np.int64
    ).reshape(-1, 3)
    return verts, tris


def surface_area(param, outer_uv: np.ndarray,
                 holes_uv: list[np.ndarray] | None = None,
                 refine: int = 2) -> float:
    """Area in m² of the trimmed UV region on *param* — quadrature, no mesh.

    ``outer_uv``/``holes_uv`` are closed (N, 2) rings without a repeated last
    point. The UV polygon is earcut-decomposed exactly, each UV triangle is
    uniformly refined ``refine`` times (4**refine subtriangles) and the metric
    sqrt(EG - F²) is integrated with a 3-point Gauss rule. Returns 0.0 for
    degenerate input.
    """
    outer_uv = np.asarray(outer_uv, dtype=float)
    if len(outer_uv) < 3:
        return 0.0
    verts, tris = _triangulate_uv(outer_uv, holes_uv or [])
    if len(tris) == 0:
        return 0.0
    corners = verts[tris]                      # (T, 3, 2)
    for _ in range(refine):                    # 1-to-4 uniform split
        a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        corners = np.concatenate([
            np.stack([a, ab, ca], axis=1), np.stack([ab, b, bc], axis=1),
            np.stack([ca, bc, c], axis=1), np.stack([ab, bc, ca], axis=1)])
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    area2d = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                          - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    total = 0.0
    for bary in _TRI_GAUSS:
        uv = bary[0] * a + bary[1] * b + bary[2] * c   # (T, 2)
        du, dv = param.first_derivs(uv)
        e = np.einsum("ij,ij->i", du, du)
        f = np.einsum("ij,ij->i", du, dv)
        g = np.einsum("ij,ij->i", dv, dv)
        metric = np.sqrt(np.maximum(e * g - f * f, 0.0))
        total += float(np.sum(metric * area2d)) / len(_TRI_GAUSS)
    return total
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_measure_area.py tests/test_measure_chain.py -q` — all PASS.
Also `uv run pytest tests -q -k "surface or geometry"` — no regressions.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check packages/ocx-geometry tests/test_measure_area.py --fix
git add packages/ocx-geometry/src/ocx_geometry/surfaces.py packages/ocx-geometry/src/ocx_geometry/measure.py tests/test_measure_area.py
git commit -m "feat(ocx-geometry): quadrature trimmed-surface area and analytic first derivatives"
```

---

### Task 4: Kernel — 2-D polygon topology helpers (`topology2d.py`)

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/topology2d.py`
- Create: `tests/test_topology2d.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_topology2d.py`:

```python
"""Tests for shapely-based 2-D topology helpers."""
from __future__ import annotations

import numpy as np

from ocx_geometry.topology2d import (
    point_polyline_distance,
    polygon_ok,
    region_count,
)

_SQ = np.array([[0, 0], [4, 0], [4, 4], [0, 4]], dtype=float)


class TestPolygonOk:
    def test_valid_square(self):
        assert polygon_ok(_SQ) is None

    def test_self_intersecting_bowtie(self):
        bowtie = np.array([[0, 0], [2, 2], [2, 0], [0, 2]], dtype=float)
        assert polygon_ok(bowtie) is not None

    def test_degenerate(self):
        assert polygon_ok(np.array([[0, 0], [1, 1]], dtype=float)) is not None


class TestRegionCount:
    def test_no_cuts_is_one_region(self):
        assert region_count(_SQ, []) == 1

    def test_full_cut_splits_in_two(self):
        cut = np.array([[2, -1], [2, 5]], dtype=float)
        assert region_count(_SQ, [cut]) == 2

    def test_partial_cut_does_not_split(self):
        cut = np.array([[2, 1], [2, 3]], dtype=float)
        assert region_count(_SQ, [cut]) == 1

    def test_two_crossing_cuts_make_four(self):
        cuts = [np.array([[2, -1], [2, 5]], dtype=float),
                np.array([[-1, 2], [5, 2]], dtype=float)]
        assert region_count(_SQ, cuts) == 4

    def test_invalid_outer_returns_one(self):
        bowtie = np.array([[0, 0], [2, 2], [2, 0], [0, 2]], dtype=float)
        assert region_count(bowtie, []) == 1


class TestPointPolylineDistance:
    def test_on_segment(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        assert point_polyline_distance(np.array([5.0, 0, 0]), pl) < 1e-12

    def test_off_segment(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        d = point_polyline_distance(np.array([5.0, 3.0, 0]), pl)
        assert abs(d - 3.0) < 1e-12

    def test_beyond_endpoint(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        d = point_polyline_distance(np.array([13.0, 4.0, 0]), pl)
        assert abs(d - 5.0) < 1e-12
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_topology2d.py -q` fails with ImportError.

- [ ] **Step 3: Implement**

Create `packages/ocx-geometry/src/ocx_geometry/topology2d.py`:

```python
"""Shapely-based 2-D polygon topology helpers (no meshing).

All polygons are (N, 2) float arrays without a repeated last point; cuts are
open (N, 2) polylines. 3-D point/polyline distance works on (N, 3) arrays.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union


def polygon_ok(ring: np.ndarray | None) -> str | None:
    """None if *ring* is a valid simple polygon, else a short reason."""
    if ring is None or len(ring) < 3:
        return "fewer than 3 vertices"
    poly = Polygon(np.asarray(ring, dtype=float))
    if poly.is_valid and poly.area > 0.0:
        return None
    from shapely.validation import explain_validity

    return explain_validity(poly)


def region_count(outer: np.ndarray, cuts: list[np.ndarray]) -> int:
    """Number of regions the *cuts* partition *outer* into.

    Invalid/degenerate inputs degrade to 1 (lean-pass: cannot prove a split).
    """
    if polygon_ok(outer) is not None:
        return 1
    poly = Polygon(np.asarray(outer, dtype=float))
    lines = [LineString(np.asarray(c, dtype=float)[:, :2]) for c in cuts
             if c is not None and len(c) >= 2]
    if not lines:
        return 1
    try:
        pieces = split(poly, unary_union(lines))
        return max(1, sum(1 for g in pieces.geoms if g.area > 1e-12))
    except Exception:  # shapely GEOS edge cases degrade to "no split proven"
        return 1


def point_polyline_distance(point: np.ndarray, polyline: np.ndarray) -> float:
    """Min distance from a 3-D point to a 3-D polyline (exact per segment)."""
    p = np.asarray(point, dtype=float)
    pts = np.asarray(polyline, dtype=float)
    if len(pts) == 1:
        return float(np.linalg.norm(p - pts[0]))
    a, b = pts[:-1], pts[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    t = np.zeros(len(a))
    nz = denom > 0
    t[nz] = np.einsum("ij,ij->i", (p - a)[nz], ab[nz]) / denom[nz]
    t = np.clip(t, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return float(np.min(np.linalg.norm(closest - p, axis=1)))
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_topology2d.py -q` all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-geometry tests/test_topology2d.py --fix
git add packages/ocx-geometry/src/ocx_geometry/topology2d.py tests/test_topology2d.py
git commit -m "feat(ocx-geometry): 2-D topology helpers (polygon validity, region count, point distance)"
```

---

### Task 5: `ocx-rules` → `ocx-geometry` dependency + `GeometryContext`

**Files:**
- Modify: `packages/ocx-rules/pyproject.toml`
- Create: `packages/ocx-rules/src/ocx_rules/geometry_context.py`
- Modify: `packages/ocx-rules/src/ocx_rules/context.py`
- Create: `tests/test_rules_geometry_context.py`

- [ ] **Step 1: Add the dependency**

In `packages/ocx-rules/pyproject.toml` add `"ocx-geometry"` to
`[project] dependencies` and mirror the existing `ocx-model-core` entry in
`[tool.uv.sources]` with `ocx-geometry = { workspace = true }`. Then run
`uv sync --dev` and confirm it succeeds.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_rules_geometry_context.py`:

```python
"""Tests for ocx_rules.geometry_context.GeometryContext."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ocx_rules.context import ValidationContext
from ocx_rules.geometry_context import GeometryContext

from tests.conftest import _build_session


@pytest.fixture()
def gctx(stub_dir_310: Path) -> GeometryContext:
    vessel = _build_session(stub_dir_310 / "composedof.3docx")
    return GeometryContext(vessel)


class TestGeometryContext:
    def test_length_resolver_converts_mm(self, gctx):
        # Umm is in every stub's unit registry
        assert abs(gctx.length.to_m(1000.0, "Umm") - 1.0) < 1e-12

    def test_to_si_handles_none(self, gctx):
        assert gctx.to_si(None) is None

    def test_sample_returns_points_or_none(self, gctx):
        for panel in gctx.vessel.panels.values():
            curves, unresolved = gctx.boundary_curves(panel)
            for c in curves:
                pts = gctx.sample(c, tol_m=0.005)
                assert pts is None or (
                    isinstance(pts, np.ndarray) and pts.shape[1] == 3)

    def test_boundary_curves_counts_unresolvable(self, gctx):
        panel = next(iter(gctx.vessel.panels.values()))
        curves, unresolved = gctx.boundary_curves(panel)
        assert len(curves) + unresolved == len(panel.limited_by)


class TestValidationContextWiring:
    def test_geometry_is_cached_property(self, stub_dir_310: Path):
        ctx = ValidationContext(model_path=stub_dir_310 / "composedof.3docx")
        g1 = ctx.geometry
        assert isinstance(g1, GeometryContext)
        assert ctx.geometry is g1
```

- [ ] **Step 3: Run to verify failure** — ImportError on `ocx_rules.geometry_context`.

- [ ] **Step 4: Implement `GeometryContext`**

Create `packages/ocx-rules/src/ocx_rules/geometry_context.py`:

```python
"""Lazily-built geometry facade over an IrVessel for rule checks.

All methods degrade to None/empty instead of raising, matching the checks'
lean-pass policy. Units: everything returned is SI metres / kg.
"""
from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from ocx_geometry.curves import sample_curve
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import SurfaceParam, make_param

if TYPE_CHECKING:
    from ocx_model_core.model.ir import (
        IrCurve3D,
        IrPanel,
        IrSurface3D,
        IrVessel,
        Quantity,
    )


class GeometryContext:
    """Shared geometry services for geometry-dependent rule checks."""

    def __init__(self, vessel: "IrVessel") -> None:
        self.vessel = vessel

    @cached_property
    def length(self) -> LengthResolver:
        return LengthResolver(self.vessel.unit_registry)

    def to_si(self, q: "Quantity | None") -> float | None:
        """Any Quantity → SI float via the model's unit registry."""
        if q is None or q.value is None:
            return None
        unit = self.vessel.unit_registry.get(q.unit) if q.unit else None
        if unit is not None and unit.to_si_factor is not None:
            return float(q.value) * float(unit.to_si_factor)
        if q.unit:
            logger.debug("Unknown unit {!r}; treating value as SI", q.unit)
        return float(q.value)

    def sample(self, curve: "IrCurve3D | None",
               tol_m: float = 0.001) -> np.ndarray | None:
        if curve is None:
            return None
        try:
            return sample_curve(curve, self.length, tol_m)
        except Exception as exc:
            logger.debug("curve sampling failed: {}", exc)
            return None

    def surface_param(self, surface: "IrSurface3D | None",
                      tol_m: float = 0.001) -> SurfaceParam | None:
        if surface is None:
            return None
        try:
            return make_param(surface, self.length, tol_m)
        except Exception as exc:
            logger.debug("surface param failed: {}", exc)
            return None

    def panel_surface(self, panel: "IrPanel") -> "IrSurface3D | None":
        """Resolve a panel's support surface geometry, or None."""
        ug = panel.unbounded_geometry
        if ug is None:
            return None
        if ug.surface is not None:
            return ug.surface
        v = self.vessel
        if ug.surface_ref is not None:
            s = v.surfaces.get(ug.surface_ref)
            if s is not None:
                return s.geometry
            coll = v.surface_collections.get(ug.surface_ref)
            if coll is not None and len(coll.surfaces) == 1:
                return coll.surfaces[0].geometry
        if ug.grid_ref is not None:
            rp = v.ref_planes.get(ug.grid_ref)
            if rp is not None:
                return rp.reference_plane
        return None

    def boundary_curves(
        self, panel: "IrPanel"
    ) -> tuple[list["IrCurve3D"], int]:
        """Explicit boundary curves of a panel + count of unresolvable refs.

        FreeEdgeCurve3D -> inline curve; SeamRef -> seam trace_line;
        StiffenerRef -> stiffener trace. Panel/Grid/Surface/EdgeCurve/
        EdgeReinforcement refs carry no explicit curve -> unresolvable.
        """
        v = self.vessel
        curves: list[IrCurve3D] = []
        unresolved = 0
        for ref in panel.limited_by:
            curve = None
            if ref.ref_type == "FreeEdgeCurve3D":
                curve = ref.curve
            elif ref.ref_type == "SeamRef":
                seam = v.seams.get(ref.local_ref)
                curve = seam.trace_line if seam else None
            elif ref.ref_type == "StiffenerRef":
                stf = v.stiffeners.get(ref.local_ref)
                curve = stf.trace if stf else None
            if curve is not None:
                curves.append(curve)
            else:
                unresolved += 1
        return curves, unresolved
```

Note: check the real IR attribute names before finalising — `IrSurface.geometry`,
`IrSurfaceCollection.surfaces`, `IrRefPlane.reference_plane`,
`IrUnboundedGeometry.surface/surface_ref/grid_ref` are the names confirmed at
plan time; adapt if the IR differs.

- [ ] **Step 5: Wire into `ValidationContext`**

In `packages/ocx-rules/src/ocx_rules/context.py` add alongside `vessel`:

```python
    @cached_property
    def geometry(self) -> "GeometryContext":
        from ocx_rules.geometry_context import GeometryContext

        return GeometryContext(self.vessel)
```

(Local import keeps `ocx_rules.context` importable even if geometry extras
were missing; mirrors the `requires=["geometry"]` gate in the manager.)

- [ ] **Step 6: Run tests**

`uv run pytest tests/test_rules_geometry_context.py tests/test_rules_context.py -q` — all PASS.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests/test_rules_geometry_context.py --fix
git add packages/ocx-rules/pyproject.toml uv.lock packages/ocx-rules/src/ocx_rules/geometry_context.py packages/ocx-rules/src/ocx_rules/context.py tests/test_rules_geometry_context.py
git commit -m "feat(ocx-rules): GeometryContext facade and ocx-geometry dependency"
```

---

### Task 6: Checks — TOP-001 (closed contour), TOP-002 (boundary continuity), TOP-003 (seam continuity)

All checks share the lean-pass policy: elements whose geometry cannot be
resolved/sampled are skipped with `logger.debug`; zero evaluable elements ⇒
vacuous PASS (empty findings).

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py`
- Create: `tests/test_rules_checks_topology.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rules_checks_topology.py` with real small IR objects
(frozen dataclasses from `ocx_model_core.model.ir`) — build a unit-square
panel with four `FreeEdgeCurve3D` line boundaries (`IrLine3D` with
`IrPoint3D` ends in `Umm`), a minimal `IrVessel` with a `unit_registry`
containing `Umm` (`IrUnit(id="Umm", to_si_factor=0.001)`; copy the exact
constructor from `tests/test_rules_checks_properties.py` / IR source), and a
`SimpleNamespace(vessel=..., geometry=GeometryContext(vessel), params={...})`
context stand-in. Cover at minimum:

```python
class TestPanelClosedContour:          # TOP-001
    def test_closed_square_panel_passes(self): ...
    def test_open_contour_fails_with_gap_in_message(self): ...
        # move one line endpoint 5 mm off; params {"tolerance_mm": 1.0}
    def test_unresolvable_ref_skips_panel(self): ...
        # limited_by containing only a PanelRef -> no findings (lean pass)
    def test_no_panels_passes(self): ...

class TestBoundaryContinuity:          # TOP-002
    def test_continuous_declared_order_passes(self): ...
    def test_junction_gap_fails(self): ...   # 2 mm gap vs tolerance_mm 0.1

class TestSeamContinuity:              # TOP-003
    def test_seam_on_panel_passes(self): ...
    def test_detached_seam_fails(self): ...
        # seam trace 10 mm away from every panel boundary sample
```

Check functions under test: `panel_closed_contour`, `boundary_continuity`,
`seam_continuity` from `ocx_rules.packs.best_practice.checks.topology`.
Call signature identical to Phase A checks: `check(context, params) -> list[Finding]`.

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

Create `checks/topology.py`:

```python
"""Geometry topology checks (OCX-TOP-001/002/003/004/005/008/009)."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps
from ocx_geometry.topology2d import point_polyline_distance

from ocx_rules.models import Finding

_SAMPLE_TOL_M = 0.001


def _panel_boundary_samples(context, panel, tol_m=_SAMPLE_TOL_M):
    """-> (list of sampled (N,3) arrays, n_skipped_refs) in metres."""
    geo = context.geometry
    curves, unresolved = geo.boundary_curves(panel)
    samples = []
    for c in curves:
        pts = geo.sample(c, tol_m)
        if pts is None or len(pts) < 2:
            unresolved += 1
        else:
            samples.append(pts)
    return samples, unresolved


def panel_closed_contour(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-001: panel LimitedBy must form a closed contour."""
    tol_m = float(params.get("tolerance_mm", 1.0)) / 1000.0
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if not panel.limited_by:
            continue
        samples, skipped = _panel_boundary_samples(context, panel)
        if skipped or len(samples) < 2:
            logger.debug("TOP-001: panel {} skipped ({} unresolved refs)",
                         pid, skipped)
            continue
        ring, gaps = chain_polylines(samples)
        if ring is None:
            continue
        worst = max(gaps)
        if worst > tol_m:
            findings.append(Finding(
                message=(f"Panel boundary is not closed: largest gap "
                         f"{worst * 1000:.2f} mm exceeds "
                         f"{tol_m * 1000:.2f} mm"),
                element_id=pid, guid=panel.guidref))
    return findings


def boundary_continuity(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-002: consecutive LimitedBy curves must join end-to-end."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if len(panel.limited_by) < 2:
            continue
        samples, skipped = _panel_boundary_samples(context, panel)
        if skipped or len(samples) < 2:
            continue
        gaps = ordered_junction_gaps(samples)
        bad = [g for g in gaps if g > tol_m]
        if bad:
            findings.append(Finding(
                message=(f"{len(bad)} boundary junction(s) exceed "
                         f"{tol_m * 1000:.2f} mm (worst "
                         f"{max(bad) * 1000:.2f} mm)"),
                element_id=pid, guid=panel.guidref))
    return findings


def seam_continuity(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-003: a panel's seams must lie on the panel (within tol)."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    geo = context.geometry
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if not panel.seam_ids:
            continue
        boundary, skipped = _panel_boundary_samples(context, panel)
        surface = geo.surface_param(geo.panel_surface(panel))
        for sid in panel.seam_ids:
            seam = context.vessel.seams.get(sid)
            pts = geo.sample(seam.trace_line) if seam else None
            if pts is None:
                logger.debug("TOP-003: seam {} on panel {} skipped", sid, pid)
                continue
            if surface is not None:
                uv = surface.inverse(pts)
                dist = float(np.max(
                    np.linalg.norm(surface.evaluate(uv) - pts, axis=1)))
            elif boundary and not skipped:
                dist = max(
                    min(point_polyline_distance(p, b) for b in boundary)
                    for p in (pts[0], pts[-1]))
            else:
                continue
            if dist > tol_m:
                findings.append(Finding(
                    message=(f"Seam {sid} deviates {dist * 1000:.2f} mm from "
                             f"panel (tolerance {tol_m * 1000:.2f} mm)"),
                    element_id=pid, guid=panel.guidref))
    return findings
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_rules_checks_topology.py -q` all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests/test_rules_checks_topology.py --fix
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py tests/test_rules_checks_topology.py
git commit -m "feat(ocx-rules): TOP-001/002/003 topology checks"
```

---

### Task 7: Checks — TOP-004 (holes inside panel) and TOP-005 (plates partition panel)

Both operate in the panel surface's UV domain. Panels whose surface param is
unavailable or `periodic_u` (cylinders — UV polygon arithmetic is unsafe
across the seam) are skipped.

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py`
- Modify: `tests/test_rules_checks_topology.py`

- [ ] **Step 1: Write failing tests** — planar panel with a closed square
boundary; TOP-004: one hole fully inside (pass) vs. one hole centred on the
boundary edge (fail); periodic surface skipped (inject a fake param with
`periodic_u = True`). TOP-005: plates whose outer contours tile the panel
exactly (pass) vs. one plate missing (fail: uncovered area); plate without
`outer_contour` ⇒ panel skipped.

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** — append to `checks/topology.py`:

```python
def _uv_ring(geo, param, curve, tol_m=_SAMPLE_TOL_M):
    pts = geo.sample(curve, tol_m)
    if pts is None or len(pts) < 3:
        return None
    uv = param.inverse(pts)
    # drop a repeated closing point if present
    if np.linalg.norm(uv[0] - uv[-1]) < 1e-12:
        uv = uv[:-1]
    return uv if len(uv) >= 3 else None


def _panel_uv_outer(context, panel):
    """-> (param, outer_uv_ring) or (None, None) when unresolvable."""
    geo = context.geometry
    param = geo.surface_param(geo.panel_surface(panel))
    if param is None or getattr(param, "periodic_u", False):
        return None, None
    samples, skipped = _panel_boundary_samples(context, panel)
    if skipped or not samples:
        return None, None
    ring3d, gaps = chain_polylines(samples)
    if ring3d is None or max(gaps) > 0.01:   # not a usable closed loop
        return None, None
    uv = param.inverse(ring3d)
    if polygon_ok(uv) is not None:
        return None, None
    return param, uv


def holes_inside_panel(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-004: hole contours must lie strictly inside their panel."""
    from shapely.geometry import Polygon

    geo = context.geometry
    findings: list[Finding] = []
    catalogue = getattr(context.vessel.hole_shape_catalogue, "holes", {}) or {}
    for pid, panel in context.vessel.panels.items():
        if not panel.cut_by_holes:
            continue
        param, outer_uv = _panel_uv_outer(context, panel)
        if param is None:
            logger.debug("TOP-004: panel {} skipped (no UV domain)", pid)
            continue
        outer = Polygon(outer_uv)
        for hole_ref in panel.cut_by_holes:
            hole = catalogue.get(hole_ref.hole_ref)
            if hole is None:
                continue
            profile = parametric_profile(hole.parametric, geo.length,
                                         _SAMPLE_TOL_M)
            pts3d = (place_hole(profile, hole_ref.transformation, geo.length)
                     if profile is not None else
                     geo.sample(hole.contour))
            if pts3d is None or len(pts3d) < 3:
                continue
            hole_uv = param.inverse(pts3d)
            if polygon_ok(hole_uv) is not None:
                continue
            if not outer.contains(Polygon(hole_uv)):
                findings.append(Finding(
                    message=(f"Hole {hole_ref.hole_ref} is not fully inside "
                             f"the panel boundary"),
                    element_id=pid, guid=panel.guidref))
    return findings


def plates_partition_panel(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-005: a panel's plates must cover it without gaps/overlaps."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    rel_tol = float(params.get("relative_tolerance", 0.02))
    geo = context.geometry
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if len(panel.plate_ids) < 1:
            continue
        param, outer_uv = _panel_uv_outer(context, panel)
        if param is None:
            continue
        plate_polys = []
        skipped = False
        for plate_id in panel.plate_ids:
            plate = context.vessel.plates.get(plate_id)
            ring = (_uv_ring(geo, param, plate.outer_contour)
                    if plate is not None and plate.outer_contour is not None
                    else None)
            if ring is None or polygon_ok(ring) is not None:
                skipped = True
                break
            plate_polys.append(Polygon(ring))
        if skipped:
            logger.debug("TOP-005: panel {} skipped (plate contour)", pid)
            continue
        panel_poly = Polygon(outer_uv)
        union = unary_union(plate_polys)
        uncovered = panel_poly.difference(union).area
        overlap = sum(p.area for p in plate_polys) - union.area
        if panel_poly.area <= 0:
            continue
        if uncovered / panel_poly.area > rel_tol:
            findings.append(Finding(
                message=(f"Plates leave {uncovered / panel_poly.area:.1%} of "
                         f"the panel uncovered (tolerance {rel_tol:.0%})"),
                element_id=pid, guid=panel.guidref))
        elif overlap / panel_poly.area > rel_tol:
            findings.append(Finding(
                message=(f"Plates overlap by {overlap / panel_poly.area:.1%} "
                         f"of the panel area (tolerance {rel_tol:.0%})"),
                element_id=pid, guid=panel.guidref))
    return findings
```

Add the imports at the top of `topology.py`:
`from ocx_geometry.holes import parametric_profile, place_hole` and
`from ocx_geometry.topology2d import point_polyline_distance, polygon_ok`.
Check the actual `rules/topology.toml` param names for TOP-005 (if the TOML
has no `relative_tolerance`, add `relative_tolerance = 0.02` to its
`[rules.params]`).

Note: `IrHole2DContour.transformation` and `IrHole2D.parametric/contour` are
the plan-time names; verify against `ocx_model_core.model.ir` before coding.

- [ ] **Step 4: Run tests** — all topology tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests/test_rules_checks_topology.py --fix
git add -A packages/ocx-rules tests/test_rules_checks_topology.py
git commit -m "feat(ocx-rules): TOP-004/005 UV-domain containment and partition checks"
```

---

### Task 8: Checks — TOP-008 (stiffener web angle at attachment) and TOP-009 (inclination sanity)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py`
- Modify: `tests/test_rules_checks_topology.py`

- [ ] **Step 1: Write failing tests** — TOP-008: planar panel + stiffener with
trace on the panel and web_direction parallel to the panel normal (pass, 0°)
vs. web_direction in the panel plane (fail, 90° ≥ default
`angle_tolerance_deg` 90 ⇒ use e.g. 95° off? No — tolerance is a max
allowed deviation; test fail case with param `angle_tolerance_deg: 30` and a
45° web). Stiffener without inclinations ⇒ skipped. TOP-009: duplicate
inclination positions (fail), consecutive web flip dot<0 (fail), clean
monotone inclinations (pass), zero/absent vectors skipped.

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** — append to `topology.py`:

```python
def _unit(vec) -> np.ndarray | None:
    if vec is None:
        return None
    v = np.array([vec.x, vec.y, vec.z], dtype=float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else None


def stiffener_web_angle(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-008: stiffener web should not fold onto its support panel."""
    max_dev_deg = float(params.get("angle_tolerance_deg", 90.0))
    geo = context.geometry
    findings: list[Finding] = []
    for sid, stf in context.vessel.stiffeners.items():
        if not stf.inclinations:
            continue
        parent = getattr(stf.parent, "ref", None) if stf.parent else None
        panel = context.vessel.panels.get(parent) if parent else None
        param = (geo.surface_param(geo.panel_surface(panel))
                 if panel is not None else None)
        if param is None:
            logger.debug("TOP-008: stiffener {} skipped (no panel surface)",
                         sid)
            continue
        for inc in stf.inclinations:
            web = _unit(inc.web_direction)
            pos = inc.position
            if web is None or pos is None:
                continue
            pt = geo.length.point(pos).reshape(1, 3)
            uv = param.inverse(pt)
            normal = param.normals(uv)[0]
            cosang = abs(float(np.dot(web, normal)))
            dev = float(np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0))))
            if dev > max_dev_deg:
                findings.append(Finding(
                    message=(f"Web direction deviates {dev:.1f} deg from the "
                             f"panel normal (max {max_dev_deg:.0f} deg)"),
                    element_id=sid, guid=stf.guidref))
                break
    return findings


def _inclination_findings(kind: str, elem_id, guid, inclinations, length,
                          findings: list[Finding]) -> None:
    pts, webs = [], []
    for inc in inclinations:
        if inc.position is not None:
            pts.append(length.point(inc.position))
        w = _unit(inc.web_direction)
        if w is not None:
            webs.append(w)
    for a, b in zip(pts, pts[1:]):
        if float(np.linalg.norm(a - b)) < 1e-6:
            findings.append(Finding(
                message=f"{kind} has duplicate inclination positions",
                element_id=elem_id, guid=guid))
            break
    for wa, wb in zip(webs, webs[1:]):
        if float(np.dot(wa, wb)) < 0.0:
            findings.append(Finding(
                message=f"{kind} web direction flips between inclinations",
                element_id=elem_id, guid=guid))
            break


def inclination_sanity(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-009: inclination series must be duplicate-free and smooth."""
    length = context.geometry.length
    findings: list[Finding] = []
    for sid, stf in context.vessel.stiffeners.items():
        if len(stf.inclinations) >= 2:
            _inclination_findings("Stiffener", sid, stf.guidref,
                                  stf.inclinations, length, findings)
    for pid, pillar in context.vessel.pillars.items():
        if len(pillar.inclinations) >= 2:
            _inclination_findings("Pillar", pid, pillar.guidref,
                                  pillar.inclinations, length, findings)
    return findings
```

Verify at coding time: `IrStiffener.parent` is a `ParentRef(kind, ref)`;
`IrInclination.position` is an `IrPoint3D`; `guidref` attribute name on
stiffener/pillar (Phase A checks already use it — copy from there).

- [ ] **Step 4: Run tests** — all topology tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests/test_rules_checks_topology.py --fix
git add -A packages/ocx-rules tests/test_rules_checks_topology.py
git commit -m "feat(ocx-rules): TOP-008/009 stiffener web-angle and inclination checks"
```

---

### Task 9: Checks — PROP-001 (plate weight), PROP-002 (panel weight/CoG), PROP-003 (profile section closed)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py`
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml` (add `cog_tolerance_mm = 50.0` to OCX-PROP-002 params)
- Modify: `tests/test_rules_checks_properties.py` (extend)

- [ ] **Step 1: Write failing tests** — real IR objects again:
  - PROP-001 `plate_weight_consistency`: planar plate (square outer contour,
    thickness 10 mm, steel density 7850 kg/m³, declared
    `mass_properties.moulded_dry_weight`) — declared == computed within
    `relative_tolerance` 0.02 (pass); declared 20 % off (fail); plate without
    outer_contour/material/thickness skipped; periodic surface skipped.
  - PROP-002 `panel_weight_cog`: panel mass = Σ plate declared masses within
    rel tol (pass/fail); CoG deviation beyond `cog_tolerance_mm` (fail);
    panel without mass_properties skipped.
  - PROP-003 `profile_section_closed`: `section_polygon` yields a valid
    simple polygon (pass); a bar section forced degenerate (monkeypatch
    `section_polygon` to return a 2-point array) ⇒ finding; section without
    geometry skipped.

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** — append to `checks/properties.py`
(imports: `surface_area`, `polygon_ok`, `section_polygon`, plus the
`_uv_ring`/`_panel_uv_outer`-style helpers — import `_uv_ring` from
`.topology` rather than duplicating):

```python
def _plate_computed_mass(context, plate) -> float | None:
    """kg from area x thickness x density, or None when not computable."""
    geo = context.geometry
    panel = (context.vessel.panels.get(plate.parent.ref)
             if plate.parent and plate.parent.kind.name == "PANEL" else None)
    param = (geo.surface_param(geo.panel_surface(panel))
             if panel is not None else None)
    if param is None or getattr(param, "periodic_u", False):
        return None
    outer = _uv_ring(geo, param, plate.outer_contour)
    if outer is None or polygon_ok(outer) is not None:
        return None
    holes = []
    catalogue = getattr(context.vessel.hole_shape_catalogue, "holes", {}) or {}
    for hole_ref in plate.cut_by_holes:
        hole = catalogue.get(hole_ref.hole_ref)
        profile = (parametric_profile(hole.parametric, geo.length, 0.001)
                   if hole is not None else None)
        pts3d = (place_hole(profile, hole_ref.transformation, geo.length)
                 if profile is not None else None)
        if pts3d is None:
            return None            # unresolvable hole -> skip whole plate
        ring = param.inverse(pts3d)
        if polygon_ok(ring) is not None:
            return None
        holes.append(ring)
    area = surface_area(param, outer, holes_uv=holes)
    thickness = geo.to_si(plate.thickness)
    material = context.vessel.materials.get(plate.material_ref)
    density = geo.to_si(material.density) if material is not None else None
    if not area or not thickness or not density:
        return None
    return area * thickness * density


def plate_weight_consistency(context, params) -> list[Finding]:
    """OCX-PROP-001: declared plate dry weight vs area x t x rho."""
    rel_tol = float(params.get("relative_tolerance", 0.02))
    findings: list[Finding] = []
    for pid, plate in context.vessel.plates.items():
        mp = plate.mass_properties
        declared = context.geometry.to_si(
            mp.moulded_dry_weight if mp else None)
        if declared is None or declared <= 0:
            continue
        computed = _plate_computed_mass(context, plate)
        if computed is None:
            logger.debug("PROP-001: plate {} skipped", pid)
            continue
        dev = abs(computed - declared) / declared
        if dev > rel_tol:
            findings.append(Finding(
                message=(f"Declared weight {declared:.1f} kg deviates "
                         f"{dev:.1%} from computed {computed:.1f} kg "
                         f"(tolerance {rel_tol:.0%})"),
                element_id=pid, guid=plate.guidref))
    return findings


def panel_weight_cog(context, params) -> list[Finding]:
    """OCX-PROP-002: panel dry weight/CoG vs the sum of its plates."""
    rel_tol = float(params.get("relative_tolerance", 0.02))
    cog_tol_m = float(params.get("cog_tolerance_mm", 50.0)) / 1000.0
    geo = context.geometry
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        mp = panel.mass_properties
        declared = geo.to_si(mp.moulded_dry_weight if mp else None)
        if declared is None or declared <= 0 or not panel.plate_ids:
            continue
        masses, moments, ok = [], [], True
        for plate_id in panel.plate_ids:
            plate = context.vessel.plates.get(plate_id)
            pmp = plate.mass_properties if plate else None
            m = geo.to_si(pmp.moulded_dry_weight if pmp else None)
            cog = pmp.moulded_cog if pmp else None
            if m is None:
                ok = False
                break
            masses.append(m)
            if cog is not None:
                moments.append(m * np.array([
                    geo.length.to_m(cog.x, cog.unit),
                    geo.length.to_m(cog.y, cog.unit),
                    geo.length.to_m(cog.z, cog.unit)]))
        if not ok or not masses:
            logger.debug("PROP-002: panel {} skipped", pid)
            continue
        total = sum(masses)
        dev = abs(total - declared) / declared
        if dev > rel_tol:
            findings.append(Finding(
                message=(f"Panel weight {declared:.1f} kg deviates {dev:.1%} "
                         f"from plate sum {total:.1f} kg "
                         f"(tolerance {rel_tol:.0%})"),
                element_id=pid, guid=panel.guidref))
            continue
        pcog = mp.moulded_cog if mp else None
        if pcog is not None and len(moments) == len(masses):
            computed_cog = np.sum(moments, axis=0) / total
            declared_cog = np.array([
                geo.length.to_m(pcog.x, pcog.unit),
                geo.length.to_m(pcog.y, pcog.unit),
                geo.length.to_m(pcog.z, pcog.unit)])
            d = float(np.linalg.norm(computed_cog - declared_cog))
            if d > cog_tol_m:
                findings.append(Finding(
                    message=(f"Panel CoG deviates {d * 1000:.0f} mm from the "
                             f"plate aggregate (tolerance "
                             f"{cog_tol_m * 1000:.0f} mm)"),
                    element_id=pid, guid=panel.guidref))
    return findings


def profile_section_closed(context, params) -> list[Finding]:
    """OCX-PROP-003: bar section outlines must be valid closed polygons."""
    geo = context.geometry
    findings: list[Finding] = []
    for sid, section in context.vessel.sections.items():
        try:
            poly = section_polygon(section, geo.length)
        except Exception as exc:
            logger.debug("PROP-003: section {} skipped: {}", sid, exc)
            continue
        if poly is None:
            continue
        reason = polygon_ok(poly)
        if reason is not None:
            findings.append(Finding(
                message=f"Section outline is not a closed simple polygon: "
                        f"{reason}",
                element_id=sid, guid=getattr(section, "guidref", None)))
    return findings
```

Check `IrCog` field names (`x/y/z/unit`) and whether `to_m` accepts them;
adjust to `geo.length.point(...)` if `IrCog` is actually an `IrPoint3D`.

- [ ] **Step 4: TOML** — in `rules/properties.toml`, under the OCX-PROP-002
rule's `[.params]` table, add `cog_tolerance_mm = 50.0`.

- [ ] **Step 5: Run tests** — `uv run pytest tests/test_rules_checks_properties.py -q` all PASS; also run the TOML-loading tests (`uv run pytest tests -q -k "pack or manager"`).

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests/test_rules_checks_properties.py --fix
git add -A packages/ocx-rules tests/test_rules_checks_properties.py
git commit -m "feat(ocx-rules): PROP-001/002/003 weight, CoG and section checks"
```

---

### Task 10: Facade switch — wire the 10 real checks in, shrink the stubs

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/__init__.py`
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/geometry_stubs.py`
- Modify: `tests/test_rules_corpus.py`

- [ ] **Step 1: Update the facade** — in `checks/__init__.py`, change the 10
imports (TOP-001/002/003/004/005/008/009, PROP-001/002/003 check names) to
come from `.topology` / `.properties` instead of `.geometry_stubs`. Keep
`__all__` byte-for-byte identical. Only `compartment_closure` and
`compartments_disjoint` still import from `.geometry_stubs`.

- [ ] **Step 2: Shrink `geometry_stubs.py`** — delete the 10 implemented stub
functions; keep module docstring + the two compartment stubs raising
`CheckNotImplemented`.

- [ ] **Step 3: Update corpus test** — in `tests/test_rules_corpus.py`,
tighten the NOT_IMPLEMENTED assertion: the set of rules reporting
NOT_IMPLEMENTED must now be a subset of `{"OCX-TOP-006", "OCX-TOP-007"}`.
Update any stub-count assertions elsewhere
(`grep -rn "NOT_IMPLEMENTED\|geometry_stubs" tests/` to find them).

- [ ] **Step 4: Run** — `uv run pytest tests -q` (full suite, integration
deselected) — all PASS. Then the corpus:
`uv run pytest tests/test_rules_corpus.py -m integration -q` — all 89 models,
zero crashes; geometry rules report PASSED/FAILED/SKIPPED, never crash.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check packages/ocx-rules tests --fix
git add -A packages/ocx-rules tests
git commit -m "feat(ocx-rules): activate 10 geometry rule checks; stubs remain for TOP-006/007"
```

---

### Task 11: Final verification and docs

- [ ] **Step 1: Full suite** — `uv run pytest -q` → all pass (expect ~940+ passed, 41 skipped).
- [ ] **Step 2: Ruff** — `uv run ruff check .` → clean (the 2 known E402s in `tests/test_diag_hooks.py` are accepted).
- [ ] **Step 3: Integration corpus** — `uv run pytest tests/test_rules_corpus.py -m integration -q` → pass.
- [ ] **Step 4: Smoke run** — `uv run validator validate rules models/D-VLCC.3docx` (exact filename: pick the D-VLCC model present in `models/`); confirm geometry rules appear with real verdicts and exit code is 0/1 (not a crash).
- [ ] **Step 5: Docs** — update `README.md` and `.github/copilot-instructions.md`: 34 of 36 best-practice rules implemented (TOP-006/007 compartment rules deferred — would require meshing); mention `ocx_geometry.topology2d`, `measure.surface_area`, `ocx_rules.geometry_context` in the layout trees; note `ocx-rules` now depends on `ocx-geometry`.
- [ ] **Step 6: Commit**

```bash
git add README.md .github/copilot-instructions.md
git commit -m "docs: Phase B geometry rule checks implemented"
```

- [ ] **Step 7:** Final whole-branch code review, then finishing-a-development-branch (merge to master, full suite on master, delete branch, push).

---

## Verification checklist (whole plan)

- [ ] `uv run pytest -q` green
- [ ] `uv run ruff check .` clean
- [ ] Corpus integration test green (89 models, no crashes)
- [ ] Smoke CLI run shows TOP/PROP geometry rules with real verdicts
- [ ] Only OCX-TOP-006/OCX-TOP-007 report NOT_IMPLEMENTED
- [ ] No meshing code paths introduced (earcut used only for exact UV polygon decomposition)










---

## PLAN CORRECTION — spec realignment (supersedes Tasks 6-9 sketches above)

The sketches above for Tasks 6-9 drifted from the approved spec
(`docs/superpowers/specs/2026-10-18-ocx-rule-checks-phase-b-design.md`) and the
committed rule TOMLs. The authoritative semantics, function names (must equal
the existing `geometry_stubs` names so the Task 10 facade switch is a pure
import change) and params are:

| Rule | Check function | Semantics (spec) | Params |
|------|----------------|------------------|--------|
| TOP-001 | `panel_limited_by_closed` | Panel LimitedBy resolves to one closed contour (chain + gaps vs `tolerance_mm` 1.0) | tolerance_mm |
| TOP-002 | `composite_curve_continuous` | Every `IrCompositeCurve3D` in the model (panel boundary curves, seam traces, stiffener/pillar traces, plate outer contours, hole contours): sample segments in declared order; junction gap > `tolerance_mm` 0.1 → finding per curve | tolerance_mm |
| TOP-003 | `hole_contours_closed` | Hole/opening contours in `hole_shape_catalogue`: parametric profiles → generated ring must be a valid closed polygon; curve contours → sampled closure gap ≤ `tolerance_mm` 0.1 | tolerance_mm |
| TOP-004 | `hole_not_splitting_plate` | For each plate with holes: plate outline + placed hole outlines in the panel surface UV; `region_count(outline, holes)` > 1 → finding. Skip plates without buildable surface/outline. | — |
| TOP-005 | `seam_topology` | For each panel: sample boundary, seams, hole contours; classify seam endpoints by nearest contour (boundary/seam/hole, within tol) — endpoint on a hole contour → finding; optional: seams+boundary partition panel into valid regions. | tolerance_mm (endpoint classification tol, default 5.0) |
| TOP-008 | `surface_normals_and_boundaries` | For each `IrSurfaceCollection`: adjacent members (shared boundary proximity via face boundary curves); analytic normals sampled near the shared boundary; deviation > `angle_tolerance_deg` 90 → finding. Members lacking params/boundaries skipped. | angle_tolerance_deg |
| TOP-009 | `stiffener_inclinations` | Per stiffener/pillar inclination series: duplicate positions (<1e-6 m apart) or consecutive web/flange vectors with negative dot → finding. Pure IR vector math. | — |
| PROP-001 | `plate_weight_consistent` | surface_area x thickness x density vs declared moulded dry weight; rel deviation > `relative_tolerance` 0.02 → finding | relative_tolerance |
| PROP-002 | `panel_weight_cog_consistent` | Σ child plate masses vs panel declared (rel tol 0.02); mass-weighted child CoG vs panel CoG > `cog_tolerance_mm` 50 → finding (param added to TOML) | relative_tolerance, cog_tolerance_mm |
| PROP-003 | `profile_closed_section` | `section_polygon` per section; `polygon_ok` must pass → else finding | — |

Corrective actions during execution: Task 6 was first implemented with drifted
semantics (`panel_closed_contour`/`boundary_continuity`/`seam_continuity`);
a follow-up commit realigns it to the table above. Tasks 7-9 are dispatched
directly from this table.
