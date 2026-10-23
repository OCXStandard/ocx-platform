# Bracket Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render OCX brackets — the only steel part the renderer ignores — as extruded solids (sheet fallback) in the GLB/HTML output.

**Architecture:** Three layers, one task each: (1) `IrBracket` gains `outer_contour` / `plane` / `offset` populated by `OcxV3Builder._build_bracket`; (2) a new planar tessellation kernel `ocx_geometry/bracket.py` turns sampled contour + plane + thickness into a prism (or sheet); (3) `ocx_render/render.py` gains a `_tessellate_brackets` loop mirroring `_sweep_part`. Spec: `docs/superpowers/specs/2026-10-23-bracket-rendering-design.md`.

**Tech Stack:** Python 3.12, uv workspace, numpy, mapbox_earcut (existing dependency), pytest. All commands run from the repo root. Tests: `uv run pytest`.

**Conventions that matter here:**
- IR dataclasses: every new field optional, defaulting to `None`.
- Builders: raw OCX attribute access ALWAYS via `getattr(obj, "field", None)`.
- Logging: `from loguru import logger` (never print/stdlib logging).
- The renderer never raises per part — failures go to `result.skipped[part_id] = reason`.
- Commits: surgical `git add` of named files only (never `git add -A` — the repo contains unrelated untracked files), and end every commit message with the trailer
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

---

### Task 1: IR fields + builder extraction

Brackets in OCX carry `OuterContour` (100% of repo models), their own
`UnboundedGeometry/Plane3D` (most exports), and sometimes `Offset`.
The IR currently drops all three.

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py` (class `IrBracket`, ~line 95)
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (`_build_bracket`, ~line 1294)
- Test: `tests/test_builders.py` (append new class at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_builders.py`:

```python
class TestBuildBracketGeometry:
    """_build_bracket extracts OuterContour, Plane3D and Offset."""

    @staticmethod
    def _raw_bracket():
        class Point3D:
            def __init__(self, *c):
                self.coordinates = list(c)
                self.unit = "Um"

        class Vector3D:
            def __init__(self, *d):
                self.direction = list(d)

        class Line3D:
            def __init__(self, a, b):
                self.start_point = a
                self.end_point = b

        class OuterContour:
            line3_d = [Line3D(Point3D(0, 0, 0), Point3D(1, 0, 0)),
                       Line3D(Point3D(1, 0, 0), Point3D(1, 1, 0)),
                       Line3D(Point3D(1, 1, 0), Point3D(0, 0, 0))]

        class Plane3D:
            point_on_surface = Point3D(0, 0, 0)
            normal = Vector3D(0, 0, 1)

        class UnboundedGeometry:
            plane3_d = Plane3D()

        class Offset:
            numericvalue = 0.005
            unit = "Um"

        class Bracket:
            id = "br1"
            name = "BR1"
            outer_contour = OuterContour()
            unbounded_geometry = UnboundedGeometry()
            offset = Offset()

        return Bracket()

    def test_bracket_geometry_fields_extracted(self):
        from ocx_model_core.model.ir.geometry import IrPlane3D

        b = OcxV3Builder()
        parent = ParentRef(kind=ParentKind.VESSEL, id="v1")
        ir = b._build_bracket(self._raw_bracket(), parent)
        assert ir is not None
        assert ir.outer_contour is not None
        assert isinstance(ir.plane, IrPlane3D)
        assert ir.plane.normal is not None
        assert ir.offset is not None

    def test_bracket_geometry_fields_default_none(self):
        class Bracket:
            id = "br2"

        b = OcxV3Builder()
        parent = ParentRef(kind=ParentKind.VESSEL, id="v1")
        ir = b._build_bracket(Bracket(), parent)
        assert ir.outer_contour is None
        assert ir.plane is None
        assert ir.offset is None
```

Note: `_qty` reads the raw element's numeric value and unit; if the
`Offset` stub above does not round-trip (inspect `_qty` at
`v3_builder.py:265` for the exact attribute names it reads, e.g.
`numericvalue`/`unit`), adjust the stub attribute names to match
`_qty` — not the other way around.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_builders.py::TestBuildBracketGeometry -v`
Expected: FAIL — `AttributeError: 'IrBracket' object has no attribute 'plane'` (or `outer_contour`).

- [ ] **Step 3: Add the IR fields**

In `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py`,
class `IrBracket`, append after `vdirection: IrVector3D | None = None`:

```python
    outer_contour: IrCurve3D | None = None
    plane: IrPlane3D | None = None
    offset: Quantity | None = None
```

`IrCurve3D` and `Quantity` are already imported in this module, but
`IrPlane3D` is NOT — add it to the existing
`from ocx_model_core.model.ir.geometry import (...)` block (line ~31),
alphabetically between `IrCurve3D` and `IrPoint3D`:

```python
from ocx_model_core.model.ir.geometry import (
    IrCoordinateSystem,
    IrCurve3D,
    IrPlane3D,
    IrPoint3D,
    ...
)
```

- [ ] **Step 4: Populate them in the builder**

In `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py`,
`_build_bracket` (~line 1294), add to the `IrBracket(...)` constructor
call, after `vdirection=...`:

```python
            outer_contour=self._build_contour(getattr(raw, "outer_contour", None)),
            plane=self._bracket_plane(getattr(raw, "unbounded_geometry", None)),
            offset=self._qty(getattr(raw, "offset", None)),
```

And add this helper method directly below `_build_bracket`:

```python
    def _bracket_plane(self, ug) -> IrPlane3D | None:
        """The bracket's own plane, when its UnboundedGeometry holds one."""
        built = self._build_unbounded(ug)
        if built is None or built.surface is None:
            return None
        return built.surface if isinstance(built.surface, IrPlane3D) else None
```

`IrPlane3D` is already imported in `v3_builder.py` (used by
`_build_surface`); verify, and add to the import if not.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_builders.py::TestBuildBracketGeometry -v`
Expected: 2 PASSED.

- [ ] **Step 6: Run the whole builder + IR test files**

Run: `uv run pytest tests/test_builders.py tests/test_ir.py -q`
Expected: all pass (frozen-dataclass or import regressions would show here).

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py tests/test_builders.py
git commit -m "feat(core): extract bracket OuterContour, Plane3D and Offset into the IR

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Geometry kernel — `tessellate_bracket`

Planar tessellation: contour points + optional plane + optional
thickness/offset → solid prism, or flat sheet when thickness is
unknown. No chart/LSCM/trim machinery.

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/bracket.py`
- Modify: `packages/ocx-geometry/src/ocx_geometry/mesh.py:11-17` (`KIND_COLORS`)
- Test: `tests/test_render_brackets.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_render_brackets.py`:

```python
"""Tests for ocx_geometry.bracket — planar bracket tessellation."""
from collections import Counter

import numpy as np
import pytest
from ocx_geometry.bracket import tessellate_bracket

# 4 x 2 rectangle in the XY plane
RECT = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0],
                 [4.0, 2.0, 0.0], [0.0, 2.0, 0.0]])
PLANE = (np.zeros(3), np.array([0.0, 0.0, 1.0]))
TOL = 0.005


def _welded(v, f, grid=1e-9):
    """Weld exact-duplicate vertices so edge adjacency is countable."""
    key = np.round(v / grid).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True,
                              return_inverse=True)
    return v[first], np.asarray(inv).ravel()[f]


def _edge_counts(f):
    e = np.sort(f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    return Counter(map(tuple, e))


def _volume(v, f):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


class TestSolid:
    def test_prism_is_watertight(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert all(c == 2 for c in _edge_counts(wf).values())

    def test_prism_volume_matches_area_times_thickness(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert abs(_volume(wv, wf)) == pytest.approx(4 * 2 * 0.02, rel=0.01)

    def test_symmetric_placement_without_offset(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        assert v[:, 2].min() == pytest.approx(-0.01, abs=1e-9)
        assert v[:, 2].max() == pytest.approx(+0.01, abs=1e-9)

    def test_offset_places_base_face(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, 0.005, TOL)
        assert v[:, 2].min() == pytest.approx(0.005, abs=1e-9)
        assert v[:, 2].max() == pytest.approx(0.025, abs=1e-9)

    def test_normals_aligned_with_vertices(self):
        v, f, n = tessellate_bracket(RECT, PLANE, 0.02, None, TOL)
        assert n.shape == v.shape
        np.testing.assert_allclose(np.linalg.norm(n, axis=1), 1.0,
                                   atol=1e-9)


class TestSheetFallback:
    def test_no_thickness_gives_flat_sheet(self):
        v, f, n = tessellate_bracket(RECT, PLANE, None, None, TOL)
        assert np.allclose(v[:, 2], 0.0)
        # area of the triangulation == rectangle area
        a = v[f[:, 1]] - v[f[:, 0]]
        b = v[f[:, 2]] - v[f[:, 0]]
        area = float(np.linalg.norm(np.cross(a, b), axis=1).sum() / 2)
        assert area == pytest.approx(8.0, rel=1e-6)


class TestPlaneHandling:
    def test_best_fit_plane_when_none_given(self):
        # same rectangle, tilted 30 deg about x — no plane passed in
        ang = np.radians(30.0)
        rot = np.array([[1, 0, 0],
                        [0, np.cos(ang), -np.sin(ang)],
                        [0, np.sin(ang), np.cos(ang)]])
        pts = RECT @ rot.T
        v, f, n = tessellate_bracket(pts, None, 0.02, None, TOL)
        wv, wf = _welded(v, f)
        assert abs(_volume(wv, wf)) == pytest.approx(4 * 2 * 0.02, rel=0.01)

    def test_non_planar_contour_returns_none(self):
        pts = RECT.copy()
        pts[2, 2] = 1.0  # one corner lifted 1 m out of plane
        assert tessellate_bracket(pts, PLANE, 0.02, None, TOL) is None

    def test_degenerate_contour_returns_none(self):
        line = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0]])
        assert tessellate_bracket(line, PLANE, 0.02, None, TOL) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_brackets.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'ocx_geometry.bracket'`.

- [ ] **Step 3: Implement the kernel**

Create `packages/ocx-geometry/src/ocx_geometry/bracket.py`:

```python
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

    # 2-D frame in the contour plane
    tmp = np.array([1.0, 0.0, 0.0])
    if abs(normal[0]) > 0.9:
        tmp = np.array([0.0, 1.0, 0.0])
    e1 = np.cross(normal, tmp)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    rel = pts - base_origin
    xy = np.column_stack([rel @ e1, rel @ e2])

    # enforce CCW winding about the normal (walls face outward below)
    area2 = float(np.cross(xy, np.roll(xy, -1, axis=0)).sum())
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
```

Note on wall orientation: the ring is CCW about ``normal``; for a CCW
polygon the outward direction of edge ``d`` is ``d × n̂`` (e.g. in the
XY plane with ``n̂ = +ẑ``, the bottom edge ``+x̂`` gives outward
``−ŷ``). The quad `[bot_i, bot_j, top_j, top_i]` wound as two
triangles `(0,1,2)/(0,2,3)` then faces outward. If the watertight or
volume test shows negative volume, the caps/walls disagree — flip the
bottom-cap reversal, not the walls.

- [ ] **Step 4: Add the bracket color**

In `packages/ocx-geometry/src/ocx_geometry/mesh.py`, extend
`KIND_COLORS` (and the `kind` comment on `PartMesh`):

```python
KIND_COLORS: dict[str, tuple[int, int, int]] = {
    "plate": (140, 145, 150),      # steel grey
    "stiffener": (70, 110, 200),   # blue
    "pillar": (80, 170, 110),      # green
    "bracket": (200, 140, 60),     # orange
    "panel": (205, 170, 125),      # tan (reserved; panels are not tessellated in v1)
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_brackets.py -v`
Expected: 9 PASSED. If `test_prism_volume...` fails with a negative
volume, see the orientation note in Step 3.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-geometry/src/ocx_geometry/bracket.py packages/ocx-geometry/src/ocx_geometry/mesh.py tests/test_render_brackets.py
git commit -m "feat(geometry): planar bracket tessellation (solid prism or sheet)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Renderer integration

**Files:**
- Modify: `packages/ocx-render/src/ocx_render/render.py` (new function after `_sweep_part` ~line 311; call in `render_model` ~line 373)
- Test: `tests/test_render_brackets.py` (append)

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_render_brackets.py`:

```python
class TestRenderModelBrackets:
    @staticmethod
    def _vessel():
        from ocx_model_core.model.ir.base import (IrVector3D, ParentKind,
                                                  ParentRef, Quantity)
        from ocx_model_core.model.ir.geometry import (IrLine3D,
                                                      IrCompositeCurve3D,
                                                      IrPlane3D, IrPoint3D)
        from ocx_model_core.model.ir.structural import IrBracket, IrVessel

        def pt(x, y, z):
            return IrPoint3D(x, y, z, "Um")

        contour = IrCompositeCurve3D(curve_length=None, segments=[
            IrLine3D(curve_length=None, start=pt(0, 0, 0), end=pt(1, 0, 0)),
            IrLine3D(curve_length=None, start=pt(1, 0, 0), end=pt(1, 1, 0)),
            IrLine3D(curve_length=None, start=pt(1, 1, 0), end=pt(0, 0, 0)),
        ])
        plane = IrPlane3D(point_on_surface=pt(0, 0, 0),
                          normal=IrVector3D(0, 0, 1))
        parent = ParentRef(kind=ParentKind.VESSEL, id="v1")
        v = IrVessel(id="v1", name="V")
        v.brackets["br1"] = IrBracket(
            id="br1", parent_ref=parent, name="BR1",
            thickness=Quantity(0.01, "Um"),
            outer_contour=contour, plane=plane)
        v.brackets["br2"] = IrBracket(id="br2", parent_ref=parent)
        return v

    def test_bracket_rendered_as_solid(self):
        from ocx_render.render import render_model

        result = render_model(self._vessel())
        brackets = [m for m in result.meshes if m.kind == "bracket"]
        assert len(brackets) == 1
        pm = brackets[0]
        assert pm.part_id == "br1"
        # solid: both sides of the plane present
        assert pm.vertices[:, 2].min() == pytest.approx(-0.005, abs=1e-9)
        assert pm.vertices[:, 2].max() == pytest.approx(+0.005, abs=1e-9)
        assert pm.normals is not None

    def test_bracket_without_contour_is_skipped_with_reason(self):
        from ocx_render.render import render_model

        result = render_model(self._vessel())
        assert result.skipped.get("br2") == "no outer contour"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_render_brackets.py::TestRenderModelBrackets -v`
Expected: FAIL — `len(brackets) == 1` is 0 and/or `skipped.get("br2")` is `None` (renderer ignores brackets today).

- [ ] **Step 3: Implement `_tessellate_brackets`**

In `packages/ocx-render/src/ocx_render/render.py`:

(a) Add to the ocx_geometry import block at the top:

```python
from ocx_geometry.bracket import tessellate_bracket
```

(b) Add after `_sweep_part` (~line 350):

```python
def _tessellate_brackets(vessel: IrVessel, length: LengthResolver,
                         options: TessellationOptions,
                         result: RenderResult) -> None:
    for br in vessel.brackets.values():
        panel_id = (br.parent_ref.id
                    if br.parent_ref.kind == ParentKind.PANEL else None)
        if options.only_panels is not None and panel_id not in options.only_panels:
            continue
        if br.outer_contour is None:
            result.skipped[br.id] = "no outer contour"
            continue
        pts = sample_contour(br.outer_contour, length, options.tolerance_m,
                             options.snap_tolerance_m)
        if pts is None or len(pts) < 3:
            result.skipped[br.id] = "contour unsampleable or open"
            continue
        plane = None
        if (br.plane is not None and br.plane.normal is not None
                and br.plane.point_on_surface is not None):
            plane = (length.point(br.plane.point_on_surface),
                     np.array([br.plane.normal.x, br.plane.normal.y,
                               br.plane.normal.z], dtype=np.float64))
        thickness = length.qty(br.thickness)
        offset = length.qty(br.offset)
        out = tessellate_bracket(pts, plane, thickness, offset,
                                 options.tolerance_m)
        if out is None:
            result.skipped[br.id] = "degenerate or non-planar contour"
            continue
        verts, faces, normals = out
        pm = PartMesh(part_id=br.id, name=br.name or br.id, kind="bracket",
                      vertices=verts, triangles=faces, normals=normals,
                      extras={"id": br.id, "guid": br.guidref,
                              "kind": "bracket", "panel_id": panel_id})
        result.meshes.append(pm)
```

(c) Call it in `render_model`, after the pillars loop and before the
"render_model total" timing log (~line 384), so the existing
plate/stiffener timing deltas stay correct:

```python
    t_pillars = time.perf_counter()
    _tessellate_brackets(vessel, length, options, result)
    logger.debug("Timing: {} brackets in {:.2f}s", len(vessel.brackets),
                 time.perf_counter() - t_pillars)
```

(The pillars loop currently logs its timing with an inline
`time.perf_counter() - t_stiff`; place `t_pillars = ...` right after
that `logger.debug` line.)

- [ ] **Step 4: Run the integration tests**

Run: `uv run pytest tests/test_render_brackets.py -v`
Expected: all PASS (9 kernel + 2 integration).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: everything passes (baseline before this feature: 1051 passed, 41 skipped).

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-render/src/ocx_render/render.py tests/test_render_brackets.py
git commit -m "feat(render): tessellate brackets as extruded solids

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Changelogs

**Files:**
- Modify: `packages/ocx-geometry/CHANGELOG.md` (Unreleased → Added)
- Modify: `packages/ocx-render/CHANGELOG.md` (Unreleased → Added)

- [ ] **Step 1: ocx-geometry entry**

In `packages/ocx-geometry/CHANGELOG.md`, under `## Unreleased` →
`### Added`, add as the first bullet:

```markdown
- `bracket.tessellate_bracket`: planar bracket tessellation — outer
  contour + plane (given or best-fit) extruded by the plate thickness
  into a closed prism (`Offset` honoured, else symmetric), or a flat
  sheet when thickness is unknown.
```

- [ ] **Step 2: ocx-render entry**

In `packages/ocx-render/CHANGELOG.md`, under `## Unreleased`, add an
`### Added` section above `### Fixed` (if not present):

```markdown
### Added

- Brackets are rendered as extruded solids using the plate thickness
  (`Offset` honoured, otherwise symmetric about the contour plane);
  brackets without a usable thickness render as flat sheets. Brackets
  were previously ignored by the renderer.
```

Also mention bracket geometry in
`packages/ocx-model-core/CHANGELOG.md` under `## Unreleased` →
`### Added` (create the section if needed):

```markdown
- `IrBracket` gains `outer_contour`, `plane` and `offset`, populated
  from the bracket's `OuterContour`, `UnboundedGeometry/Plane3D` and
  `Offset` elements.
```

- [ ] **Step 3: Commit**

```bash
git add packages/ocx-geometry/CHANGELOG.md packages/ocx-render/CHANGELOG.md packages/ocx-model-core/CHANGELOG.md
git commit -m "docs: changelog entries for bracket rendering

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Real-model verification + deployment

Manual verification (no committed test — `models/` is not test data).

- [ ] **Step 1: Render a bracket-rich model from the workspace**

```powershell
uv run ocx-render .\models\TR02\TR02_TC08_cadhu.3docx --destination .\examples\TR02_TC08_cadhu.glb
```

Expected: exit 0; the log's "parts tessellated" count exceeds the
plate+stiffener count by up to 136 (this model has 136 brackets, all
with OuterContour + Plane3D). Inspect skips:
`result` logs any skipped bracket ids at DEBUG.

- [ ] **Step 2: Verify bracket meshes inside the GLB**

```powershell
@'
import numpy as np, trimesh
sc = trimesh.load(r"examples/TR02_TC08_cadhu.glb")
bk = {k: g for k, g in sc.geometry.items() if k.startswith("B:")}
print("bracket meshes:", len(bk))
closed = sum(1 for g in bk.values()
             if trimesh.Trimesh(np.asarray(g.vertices),
                                np.asarray(g.faces), process=True).is_watertight)
print("watertight:", closed)
'@ | uv run python - 2>&1 | Select-String -NotMatch 'DEBUG|INFO '
```

Expected: `bracket meshes:` close to 136 (minus any legitimately
skipped), `watertight:` equal to the mesh count. (Node names follow
the existing scheme — kind initial + name/panel; confirm the actual
prefix in `gltf_writer.py` if `B:` matches nothing.)

- [ ] **Step 3: Push and reinstall the tools system-wide**

```powershell
git push origin master
uv tool install --force --reinstall ocx-model-validator --from .\packages\ocx-model-validator
uv tool install --force --reinstall ocx-render --from .\packages\ocx-render
uv tool install --force --reinstall ocx-diagnose --from .\packages\ocx-diagnose
```

Expected: push succeeds; each install reports its executables.

- [ ] **Step 4: Clean up the verification artifact**

```powershell
Remove-Item .\examples\TR02_TC08_cadhu.glb, .\examples\TR02_TC08_cadhu.html -ErrorAction SilentlyContinue
```

(Keep them instead if the user wants the example committed — ask.)
