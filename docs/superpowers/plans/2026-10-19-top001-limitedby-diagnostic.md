# TOP-001 LimitedBy Contour Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `ocx-diagnose top-001` CLI command that renders, per failing panel, an interactive plotly 3D HTML plot of the LimitedBy contour segments (document-order sequence labels, per-segment colors, ContourBounds markers, gap annotations, optional Panel OuterContour).

**Architecture:** Small additions to the core IR (`contour_start`/`contour_end` on `IrLimitedByRef`, `outer_contours` on `IrPanel`) and to `ocx-geometry` (`chain_gap_details` giving gap endpoints). `ocx-diagnose` gains a dependency on `ocx-rules` to reuse `GeometryContext` (which gets a per-ref resolution method), a new `top001.py` assembly module, a figure builder in `figures.py`, and a new CLI command. Spec: `docs/superpowers/specs/2026-10-19-top001-limitedby-diagnostic-design.md`.

**Tech Stack:** Python 3.12, uv workspace, typer, plotly (offline HTML), numpy, loguru, pytest. All commands run from the repo root. Package manager is **uv** — run tests with `uv run pytest`, never bare `pytest`.

**Conventions you must follow:**
- All IR dataclasses are frozen-or-plain dataclasses with every optional field defaulting to `None`/`[]`.
- All raw OCX attribute access in builders uses `getattr(obj, "field", None)` — never direct attribute access.
- Logging via `from loguru import logger` only; no `print()` in library code (CLI `typer.echo` is fine).
- Tests live in the shared root `tests/` directory. Builder tests use inline stub classes (see existing `tests/test_builders.py`), never imports from the `ocx` bindings package.
- Commit after every task with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

---

### Task 1: IR + builder — `contour_start` / `contour_end` on `IrLimitedByRef`

Both OCX 3.1.0 and 3.2.0 define `ContourBounds` (children `ContourStart`, `ContourEnd`, optional `ContourMidPoint`) on LimitedBy ref elements. The IR already stores `contour_mid_point`; add the other two points.

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py` (class `IrLimitedByRef`, ~line 267)
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (~line 1500, inside the `_LB_ATTRS` loop)
- Test: `tests/test_builders.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_builders.py`. House style: module-level `_Stub*` classes, direct `OcxV3Builder()` instantiation, plain test functions. The file already defines `_StubPoint3D(coordinates, unit="Um")` (the builder's `_pt` reads a `coordinates` list) and imports `OcxV3Builder`. `_build_panel` has signature `_build_panel(self, raw, ir: IrVessel, vessel_id: str)`; import `IrVessel` the same way other tests in the file import IR types (add the import if absent: `from ocx_model_core.model.ir.vessel import IrVessel`).

```python
class _StubContourBounds:
    def __init__(self):
        self.contour_start = _StubPoint3D([0.0, 0.0, 0.0])
        self.contour_end = _StubPoint3D([5.0, 0.0, 0.0])
        self.contour_mid_point = _StubPoint3D([2.5, 0.0, 0.0])


class _StubSeamRefWithBounds:
    def __init__(self, bounds):
        self.local_ref = "seam1"
        self.guidref = "g-seam1"
        self.ref_type = "ocx:SeamRef"
        self.contour_bounds = bounds


class _StubLimitedBy:
    def __init__(self, seam_refs):
        self.seam_ref = seam_refs


class _StubPanelWithBounds:
    def __init__(self, bounds):
        self.id = "p1"
        self.name = "P1"
        self.limited_by = _StubLimitedBy([_StubSeamRefWithBounds(bounds)])


def test_limited_by_contour_bounds_start_end_extracted():
    builder = OcxV3Builder()
    panel = builder._build_panel(
        _StubPanelWithBounds(_StubContourBounds()), IrVessel(), "V1")
    ref = panel.limited_by[0]
    assert ref.contour_start is not None and ref.contour_start.x == 0.0
    assert ref.contour_end is not None and ref.contour_end.x == 5.0
    assert ref.contour_mid_point is not None and ref.contour_mid_point.x == 2.5


def test_limited_by_contour_bounds_absent_degrades_to_none():
    builder = OcxV3Builder()
    panel = builder._build_panel(_StubPanelWithBounds(None), IrVessel(), "V1")
    ref = panel.limited_by[0]
    assert ref.contour_start is None and ref.contour_end is None
    assert ref.contour_mid_point is None
```

If `IrVessel()` requires constructor arguments, mirror how `conftest.py`'s `_build_session` or other tests construct one. The assertions are the contract.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_builders.py -k ContourBounds -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'contour_start'` or `AttributeError`/assertion on `contour_start`.

- [ ] **Step 3: Add the IR fields**

In `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py`, class `IrLimitedByRef`, immediately after the existing `contour_mid_point` field:

```python
    contour_mid_point: IrPoint3D | None = None
    contour_start: IrPoint3D | None = None   # ContourBounds/ContourStart
    contour_end: IrPoint3D | None = None     # ContourBounds/ContourEnd
```

Also update the class docstring's field list to mention that `contour_start`/`contour_end`/`contour_mid_point` come from the optional `ContourBounds` element.

- [ ] **Step 4: Extract the fields in the builder**

In `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py`, inside `_build_panel`'s `_LB_ATTRS` loop (~line 1495), hoist the `contour_bounds` lookup and pass the two new fields:

```python
            for attr, ref_type in _LB_ATTRS:
                for ref_raw in getattr(limited_by, attr, []):
                    local = getattr(ref_raw, "local_ref", None) or ""
                    guid  = getattr(ref_raw, "guidref", None)
                    # ref_type attr on the OCX element itself (e.g. "ocx:PanelRef")
                    ocx_rt = getattr(ref_raw, "ref_type", None)
                    bounds = getattr(ref_raw, "contour_bounds", None)
                    limited_by_refs.append(
                        IrLimitedByRef(
                            ref_type=ref_type,
                            local_ref=local,
                            guidref=guid,
                            ocx_ref_type=ocx_rt,
                            offset=self._qty(getattr(ref_raw, "offset", None)),
                            offset_direction=self._vec(getattr(ref_raw, "offset_direction", None)),
                            contour_mid_point=self._pt(
                                getattr(bounds, "contour_mid_point", None)),
                            contour_start=self._pt(
                                getattr(bounds, "contour_start", None)),
                            contour_end=self._pt(
                                getattr(bounds, "contour_end", None)),
                        )
                    )
```

(This replaces the existing nested `getattr(getattr(ref_raw, "contour_bounds", None), "contour_mid_point", None)` expression — same behavior, single lookup.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_builders.py -v`
Expected: all PASS (new tests plus no regressions in the file).

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py tests/test_builders.py
git commit -m "feat(core): extract ContourBounds start/end into IrLimitedByRef

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: IR + builder — `outer_contours` on `IrPanel`

`Panel_T` allows `OuterContour` 0..unbounded (3.1.0 and 3.2.0). Store the built curves on the panel.

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py` (class `IrPanel`, ~line 321)
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (the `return IrPanel(...)` at the end of `_build_panel`, ~line 1535)
- Test: `tests/test_builders.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_builders.py`. The builder's `_build_contour(container)` reads curve children from its `_CONTOUR_ATTRS` (e.g. `line3_d`); the file already defines a `_Line3D` stub (~line 208) — reuse it, and note `raw.outer_contour` is a **list** on Panel (maxOccurs unbounded):

```python
class _StubOuterContour:
    def __init__(self):
        # reuse the existing _Line3D stub from this file; check its
        # constructor arguments (~line 208) and pass what it requires
        self.line3_d = _Line3D(
            _StubPoint3D([0.0, 0.0, 0.0]), _StubPoint3D([1.0, 0.0, 0.0]))


def test_panel_outer_contours_built():
    builder = OcxV3Builder()
    raw = _StubPanelWithBounds(None)   # from Task 1's tests
    raw.outer_contour = [_StubOuterContour()]
    panel = builder._build_panel(raw, IrVessel(), "V1")
    assert len(panel.outer_contours) == 1


def test_panel_without_outer_contour_is_empty_list():
    builder = OcxV3Builder()
    panel = builder._build_panel(_StubPanelWithBounds(None), IrVessel(), "V1")
    assert panel.outer_contours == []
```

Check `_Line3D`'s actual constructor in the file and the `_CONTOUR_ATTRS` tuple in `v3_builder.py` (the attribute must be one the builder scans, e.g. `line3_d`); adjust the stub accordingly. The assertions are the contract.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_builders.py -k OuterContour -v`
Expected: the new tests FAIL (`AttributeError: 'IrPanel' object has no attribute 'outer_contours'` or `TypeError` on the constructor).

- [ ] **Step 3: Add the IR field**

In `IrPanel` (structural.py), after `unbounded_geometry`:

```python
    unbounded_geometry: IrUnboundedGeometry | None = None
    outer_contours: list[IrCurve3D] = field(default_factory=list)
```

- [ ] **Step 4: Build the contours**

In `_build_panel`'s `return IrPanel(...)` call, add:

```python
            unbounded_geometry=self._build_unbounded(getattr(raw, "unbounded_geometry", None)),
            outer_contours=[
                c for c in (self._build_contour(oc)
                            for oc in getattr(raw, "outer_contour", []) or [])
                if c is not None
            ],
```

Note: in the 3.x bindings `outer_contour` on Panel is a list (maxOccurs unbounded); the `or []` guards builds where a normalisation pass left a scalar `None`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_builders.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py tests/test_builders.py
git commit -m "feat(core): build Panel OuterContour curves into IrPanel.outer_contours

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: `ocx-geometry` — `chain_gap_details` (gap endpoints)

`chain_polylines` returns only gap distances. The diagnostic needs the two endpoint coordinates of each gap to draw connectors. Add a sibling function that mirrors the same greedy walk and records endpoints.

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/measure.py` (after `chain_polylines`, ~line 98)
- Test: `tests/test_measure_chain.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_measure_chain.py`:

```python
import numpy as np

from ocx_geometry.measure import chain_gap_details


class TestChainGapDetails:
    def test_square_with_one_gap(self):
        # Three sides of a unit square + a short fourth side leaving a gap.
        a = np.array([[0, 0, 0], [1, 0, 0]], float)
        b = np.array([[1, 0, 0], [1, 1, 0]], float)
        c = np.array([[1, 1, 0], [0, 1, 0]], float)
        d = np.array([[0, 1, 0], [0, 0.4, 0]], float)  # stops 0.4 short
        details = chain_gap_details([a, b, c, d])
        # 3 junctions + 1 closure entry
        assert len(details) == 4
        gaps = [g for _, _, g in details]
        assert max(gaps[:3]) < 1e-12          # junctions touch exactly
        assert abs(gaps[3] - 0.4) < 1e-12     # closure gap
        pa, pb, _ = details[3]
        np.testing.assert_allclose(pa, [0, 0.4, 0])
        np.testing.assert_allclose(pb, [0, 0, 0])

    def test_empty_and_single(self):
        assert chain_gap_details([]) == []
        one = np.array([[0, 0, 0], [1, 0, 0]], float)
        details = chain_gap_details([one])
        assert len(details) == 1              # closure gap only
        assert abs(details[0][2] - 1.0) < 1e-12
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_measure_chain.py -k GapDetails -v`
Expected: FAIL with `ImportError: cannot import name 'chain_gap_details'`.

- [ ] **Step 3: Implement**

Add to `packages/ocx-geometry/src/ocx_geometry/measure.py` directly after `chain_polylines`:

```python
def chain_gap_details(
    polylines: list[np.ndarray],
) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """Gap endpoints for the same greedy chaining as :func:`chain_polylines`.

    Returns one ``(point_a, point_b, gap)`` tuple per junction in attachment
    order plus a final tuple for the closure gap chain-end -> chain-start.
    ``point_a`` is the current chain tail, ``point_b`` the attached segment's
    chosen endpoint. Returns ``[]`` when no usable polylines are given.
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if not parts:
        return []
    out = parts[0]
    remaining = parts[1:]
    details: list[tuple[np.ndarray, np.ndarray, float]] = []
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
        details.append((tail.copy(), pts[0].copy(), best_d))
        out = np.vstack([out, pts])
    details.append((out[-1].copy(), out[0].copy(),
                    float(np.linalg.norm(out[-1] - out[0]))))
    return details
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_measure_chain.py -v`
Expected: all PASS (the gap *distances* must equal what `chain_polylines` reports for the same input — the two functions share the walk logic by construction).

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-geometry/src/ocx_geometry/measure.py tests/test_measure_chain.py
git commit -m "feat(geometry): chain_gap_details returns gap endpoint pairs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: `ocx-rules` — per-ref boundary curve resolution on `GeometryContext`

`GeometryContext.boundary_curves(panel)` resolves all refs at once. The diagnostic needs per-ref resolution in document order. Extract the per-ref logic into a public method and delegate.

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/geometry_context.py` (method `boundary_curves`, ~line 97)
- Test: `tests/test_geometry_context_refs.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_geometry_context_refs.py`:

```python
"""GeometryContext.boundary_curve_for_ref resolution per LimitedBy ref type."""
from ocx_model_core.model.ir.base import ParentKind, ParentRef
from ocx_model_core.model.ir.structural import IrLimitedByRef, IrPanel, IrSeam
from ocx_model_core.model.ir.vessel import IrVessel
from ocx_rules.geometry_context import GeometryContext


def _vessel_with_seam():
    v = IrVessel()
    v.seams["s1"] = IrSeam(
        id="s1", parent_ref=ParentRef(kind=ParentKind.PANEL, id="p1"),
        trace_line="SENTINEL-CURVE")  # geometry object identity is all we need
    return v


def test_seam_ref_resolves_to_trace_line():
    geo = GeometryContext(_vessel_with_seam())
    ref = IrLimitedByRef(ref_type="SeamRef", local_ref="s1")
    assert geo.boundary_curve_for_ref(ref) == "SENTINEL-CURVE"


def test_free_edge_curve_returns_inline_curve():
    geo = GeometryContext(IrVessel())
    ref = IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="",
                         curve="INLINE-CURVE")
    assert geo.boundary_curve_for_ref(ref) == "INLINE-CURVE"


def test_unresolvable_ref_types_return_none():
    geo = GeometryContext(IrVessel())
    assert geo.boundary_curve_for_ref(
        IrLimitedByRef(ref_type="GridRef", local_ref="g1")) is None
    assert geo.boundary_curve_for_ref(
        IrLimitedByRef(ref_type="SeamRef", local_ref="missing")) is None


def test_boundary_curves_unchanged():
    v = _vessel_with_seam()
    panel = IrPanel(id="p1", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref="s1"),
        IrLimitedByRef(ref_type="GridRef", local_ref="g1"),
    ])
    curves, unresolved = GeometryContext(v).boundary_curves(panel)
    assert curves == ["SENTINEL-CURVE"] and unresolved == 1
```

**Important:** check the real constructor signatures first (`IrVessel`, `IrSeam` — field names/required args in `packages/ocx-model-core/src/ocx_model_core/model/ir/`). `trace_line` is typed `IrCurve3D | None` but the method only passes it through, so a string sentinel works; if `IrSeam` is a frozen dataclass with other required fields, supply them. Adjust imports to the actual module layout (check `ocx_model_core/model/ir/__init__.py` re-exports).

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_geometry_context_refs.py -v`
Expected: FAIL with `AttributeError: 'GeometryContext' object has no attribute 'boundary_curve_for_ref'`.

- [ ] **Step 3: Implement — extract per-ref logic**

Replace `boundary_curves` in `packages/ocx-rules/src/ocx_rules/geometry_context.py` with:

```python
    def boundary_curve_for_ref(self, ref) -> "IrCurve3D | None":
        """Resolve one LimitedBy ref to an explicit boundary curve, or None.

        FreeEdgeCurve3D -> inline curve; SeamRef -> seam trace_line;
        StiffenerRef -> stiffener trace. Other ref types carry no explicit
        curve.
        """
        v = self.vessel
        if ref.ref_type == "FreeEdgeCurve3D":
            return ref.curve
        if ref.ref_type == "SeamRef":
            seam = v.seams.get(ref.local_ref)
            return seam.trace_line if seam else None
        if ref.ref_type == "StiffenerRef":
            stf = v.stiffeners.get(ref.local_ref)
            return stf.trace if stf else None
        return None

    def boundary_curves(self, panel: "IrPanel") -> tuple[list, int]:
        """Explicit boundary curves of a panel + count of unresolvable refs."""
        curves = []
        unresolved = 0
        for ref in panel.limited_by:
            curve = self.boundary_curve_for_ref(ref)
            if curve is not None:
                curves.append(curve)
            else:
                unresolved += 1
        return curves, unresolved
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_geometry_context_refs.py tests/test_rules_checks_topology.py -v`
Expected: all PASS (topology checks consume `boundary_curves` — behavior must be identical).

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/geometry_context.py tests/test_geometry_context_refs.py
git commit -m "refactor(rules): expose per-ref boundary curve resolution on GeometryContext

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: `ocx-diagnose` — dependency on `ocx-rules` + diagnosis assembly module

**Files:**
- Modify: `packages/ocx-diagnose/pyproject.toml`
- Create: `packages/ocx-diagnose/src/ocx_diagnose/top001.py`
- Test: `tests/test_top001_diagnose.py` (create)

- [ ] **Step 1: Add the workspace dependency**

In `packages/ocx-diagnose/pyproject.toml` add to `dependencies`:

```toml
    "ocx-rules>=0.1,<0.2",
```

(check the actual version in `packages/ocx-rules/pyproject.toml` and match the range style of the other entries) and to `[tool.uv.sources]`:

```toml
ocx-rules = { workspace = true }
```

Then run: `uv sync --dev` — expected: resolves and installs with no errors.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_top001_diagnose.py`:

```python
"""TOP-001 diagnosis assembly (ocx_diagnose.top001)."""
import numpy as np

from ocx_model_core.model.ir.base import ParentKind, ParentRef
from ocx_model_core.model.ir.geometry import IrLine3D, IrPoint3D
from ocx_model_core.model.ir.structural import IrLimitedByRef, IrPanel, IrSeam
from ocx_model_core.model.ir.vessel import IrVessel
from ocx_diagnose.top001 import diagnose_panel, select_panels
from ocx_rules.geometry_context import GeometryContext

# NOTE: check the real IrLine3D field names in
# packages/ocx-model-core/src/ocx_model_core/model/ir/geometry.py before
# writing — this assumes IrLine3D(start_point=IrPoint3D, end_point=IrPoint3D).

M = "Um"  # metres unit id — check the registry fallback in measure.py
          # (_FALLBACK_TO_M) accepts it; otherwise use the id it accepts.


def _pt(x, y, z):
    return IrPoint3D(x=x, y=y, z=z, unit=M)


def _line(a, b):
    return IrLine3D(start_point=_pt(*a), end_point=_pt(*b))


def _seam(vid, sid, a, b):
    vid.seams[sid] = IrSeam(
        id=sid, parent_ref=ParentRef(kind=ParentKind.PANEL, id="p1"),
        trace_line=_line(a, b))


def _open_square_panel():
    """Panel whose LimitedBy traces three sides of a unit square (1 m gap)."""
    v = IrVessel()
    _seam(v, "s1", (0, 0, 0), (1, 0, 0))
    _seam(v, "s2", (1, 0, 0), (1, 1, 0))
    _seam(v, "s3", (1, 1, 0), (0, 1, 0))
    panel = IrPanel(id="p1", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref="s1"),
        IrLimitedByRef(ref_type="SeamRef", local_ref="s2"),
        IrLimitedByRef(ref_type="SeamRef", local_ref="s3",
                       contour_start=_pt(1, 1, 0), contour_end=_pt(0, 1, 0)),
        IrLimitedByRef(ref_type="GridRef", local_ref="missing",
                       contour_start=_pt(0, 1, 0), contour_end=_pt(0, 0, 0)),
    ])
    v.panels["p1"] = panel
    return v, panel


def test_segments_in_document_order_with_bounds():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    assert [s.seq for s in diag.segments] == [1, 2, 3, 4]
    assert diag.segments[0].ref_type == "SeamRef"
    assert diag.segments[0].polyline is not None
    np.testing.assert_allclose(diag.segments[2].start, [1, 1, 0])
    np.testing.assert_allclose(diag.segments[2].end, [0, 1, 0])


def test_unresolvable_segment_flagged():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    assert diag.segments[3].polyline is None
    assert diag.unresolved_count == 1
    np.testing.assert_allclose(diag.segments[3].start, [0, 1, 0])


def test_gap_detected_above_tolerance():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    # three chained sides leave one closure gap of 1 m
    assert diag.worst_gap_m > 0.9
    assert len(diag.gaps) == 1
    assert abs(diag.gaps[0].distance_m - 1.0) < 1e-9


def test_closed_panel_has_no_gaps():
    v, panel = _open_square_panel()
    _seam(v, "s4", (0, 1, 0), (0, 0, 0))
    closed = IrPanel(id="p2", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref=s)
        for s in ("s1", "s2", "s3", "s4")])
    v.panels["p2"] = closed
    diag = diagnose_panel(GeometryContext(v), closed, tol_m=0.001)
    assert diag.gaps == [] and diag.worst_gap_m <= 0.001


def test_select_panels_failing_by_default():
    v, _ = _open_square_panel()
    geo = GeometryContext(v)
    selected = select_panels(geo, panel_ids=None, tol_m=0.001)
    assert [p.panel_id for p in selected] == ["p1"]
    forced = select_panels(geo, panel_ids=["p1"], tol_m=0.001)
    assert [p.panel_id for p in forced] == ["p1"]
```

**Important:** verify the real names/shapes first: `IrLine3D` fields, `IrSeam` required fields, `IrVessel()` default-constructibility, the metre unit id the `LengthResolver` fallback accepts (`_FALLBACK_TO_M` in `ocx_geometry/measure.py`), and whether `sample_curve` supports `IrLine3D` (check `ocx_geometry/curves.py`). Use whichever simple curve type the sampler supports; the tests' *assertions* are the contract.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_top001_diagnose.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocx_diagnose.top001'`.

- [ ] **Step 4: Implement the assembly module**

Create `packages/ocx-diagnose/src/ocx_diagnose/top001.py`:

```python
"""OCX-TOP-001 diagnosis: assemble per-panel LimitedBy contour data.

Coordinates are SI metres throughout (GeometryContext convention).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from loguru import logger
from ocx_geometry.measure import chain_gap_details

_SAMPLE_TOL_M = 0.001


@dataclass
class SegmentDiag:
    """One LimitedBy child in document order."""
    seq: int                       # 1-based document position
    ref_type: str                  # e.g. "SeamRef"
    target: str                    # local_ref or guidref ("" when absent)
    polyline: np.ndarray | None    # (N, 3) metres; None when unresolvable
    start: np.ndarray | None = None  # ContourBounds points, metres
    mid: np.ndarray | None = None
    end: np.ndarray | None = None


@dataclass
class GapDiag:
    """A junction/closure gap above tolerance."""
    point_a: np.ndarray            # (3,) metres
    point_b: np.ndarray
    distance_m: float


@dataclass
class PanelTop001Diagnosis:
    panel_id: str
    segments: list[SegmentDiag] = field(default_factory=list)
    gaps: list[GapDiag] = field(default_factory=list)
    outer_contours: list[np.ndarray] = field(default_factory=list)
    worst_gap_m: float = 0.0
    unresolved_count: int = 0


def _bound_point(geo, pt) -> np.ndarray | None:
    """IrPoint3D -> (3,) metres, or None (lean: never raises)."""
    if pt is None:
        return None
    try:
        return np.asarray(geo.length.point(pt), dtype=float)
    except Exception as exc:  # noqa: BLE001 — lean per point
        logger.debug("TOP-001 diag: unparseable ContourBounds point: {}", exc)
        return None


def diagnose_panel(geo, panel, tol_m: float) -> PanelTop001Diagnosis:
    """Assemble the TOP-001 diagnosis for one panel."""
    segments: list[SegmentDiag] = []
    for seq, ref in enumerate(panel.limited_by, start=1):
        curve = geo.boundary_curve_for_ref(ref)
        pts = geo.sample(curve, _SAMPLE_TOL_M) if curve is not None else None
        if pts is not None and len(pts) < 2:
            pts = None
        segments.append(SegmentDiag(
            seq=seq,
            ref_type=ref.ref_type,
            target=ref.local_ref or ref.guidref or "",
            polyline=pts,
            start=_bound_point(geo, ref.contour_start),
            mid=_bound_point(geo, ref.contour_mid_point),
            end=_bound_point(geo, ref.contour_end),
        ))

    samples = [s.polyline for s in segments if s.polyline is not None]
    gaps: list[GapDiag] = []
    worst = 0.0
    if samples:
        for pa, pb, d in chain_gap_details(samples):
            worst = max(worst, d)
            if d > tol_m:
                gaps.append(GapDiag(point_a=pa, point_b=pb, distance_m=d))

    outers: list[np.ndarray] = []
    for oc in getattr(panel, "outer_contours", []):
        opts = geo.sample(oc, _SAMPLE_TOL_M)
        if opts is not None and len(opts) >= 2:
            outers.append(opts)

    return PanelTop001Diagnosis(
        panel_id=panel.id,
        segments=segments,
        gaps=gaps,
        outer_contours=outers,
        worst_gap_m=worst,
        unresolved_count=sum(1 for s in segments if s.polyline is None),
    )


def select_panels(geo, panel_ids: list[str] | None,
                  tol_m: float) -> list[PanelTop001Diagnosis]:
    """Diagnose panels: the given ids, or all panels failing TOP-001.

    A panel "fails" when its worst gap exceeds *tol_m* or it has
    unresolvable LimitedBy refs. Panels without LimitedBy are skipped.
    """
    vessel = geo.vessel
    out: list[PanelTop001Diagnosis] = []
    if panel_ids:
        for pid in panel_ids:
            panel = vessel.panels.get(pid)
            if panel is None:
                logger.warning("TOP-001 diag: panel id {} not found", pid)
                continue
            out.append(diagnose_panel(geo, panel, tol_m))
        return out
    for panel in vessel.panels.values():
        if not panel.limited_by:
            continue
        diag = diagnose_panel(geo, panel, tol_m)
        if diag.worst_gap_m > tol_m or diag.unresolved_count:
            out.append(diag)
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_top001_diagnose.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-diagnose/pyproject.toml uv.lock packages/ocx-diagnose/src/ocx_diagnose/top001.py tests/test_top001_diagnose.py
git commit -m "feat(diagnose): TOP-001 per-panel LimitedBy diagnosis assembly

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: `ocx-diagnose` — plotly 3D figure builder

**Files:**
- Modify: `packages/ocx-diagnose/src/ocx_diagnose/figures.py` (append)
- Test: `tests/test_top001_diagnose.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_top001_diagnose.py`:

```python
from ocx_diagnose.figures import limitedby_fig


def test_limitedby_fig_traces():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    fig = limitedby_fig(diag)
    names = [t.name for t in fig.data if t.name]
    # one solid trace per resolvable segment, labelled with sequence + ref
    assert any(n.startswith("1: SeamRef") for n in names)
    assert any(n.startswith("3: SeamRef") for n in names)
    # the unresolvable segment appears as a dashed ContourBounds trace
    assert any(n.startswith("4: GridRef") and "unresolved" in n for n in names)
    # one gap connector
    assert any(n.startswith("gap ") for n in names)
    # equal aspect
    assert fig.layout.scene.aspectmode == "data"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_top001_diagnose.py::test_limitedby_fig_traces -v`
Expected: FAIL with `ImportError: cannot import name 'limitedby_fig'`.

- [ ] **Step 3: Implement**

Open `packages/ocx-diagnose/src/ocx_diagnose/figures.py` first and match its import style (it already imports plotly — reuse the same module aliases). Append:

```python
_TOP001_PALETTE = (
    "#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756",
    "#72b7b2", "#ff9da6", "#9d755d", "#eeca3b", "#bab0ac",
)

# plotly Scatter3d has no triangle symbol; use diamond/circle/square.
_BOUND_MARKS = (("start", "diamond"), ("mid", "circle"), ("end", "square"))


def _seg_marker_trace(seg, colour):
    """ContourBounds markers of one segment as a single Scatter3d, or None."""
    import plotly.graph_objects as go
    pts, syms, labels = [], [], []
    for attr, sym in _BOUND_MARKS:
        p = getattr(seg, attr)
        if p is not None:
            pts.append(p)
            syms.append(sym)
            labels.append(f"Contour{attr.capitalize()} seg {seg.seq}")
    if not pts:
        return None
    arr = np.asarray(pts)
    return go.Scatter3d(
        x=arr[:, 0], y=arr[:, 1], z=arr[:, 2], mode="markers",
        marker=dict(size=5, symbol=syms, color=colour),
        text=labels, hoverinfo="text", showlegend=False)


def limitedby_fig(diag):
    """TOP-001 figure: LimitedBy segments, bounds markers, gaps, OuterContour."""
    import plotly.graph_objects as go
    fig = go.Figure()
    for seg in diag.segments:
        colour = _TOP001_PALETTE[(seg.seq - 1) % len(_TOP001_PALETTE)]
        label = f"{seg.seq}: {seg.ref_type} {seg.target}".rstrip()
        if seg.polyline is not None:
            p = seg.polyline
            fig.add_trace(go.Scatter3d(
                x=p[:, 0], y=p[:, 1], z=p[:, 2], mode="lines",
                line=dict(color=colour, width=5), name=label))
            m = p[len(p) // 2]
            fig.add_trace(go.Scatter3d(
                x=[m[0]], y=[m[1]], z=[m[2]], mode="text",
                text=[str(seg.seq)], textfont=dict(size=14, color=colour),
                showlegend=False, hoverinfo="skip"))
        else:
            # dashed grey polyline through the declared bounds
            chain = [p for p in (seg.start, seg.mid, seg.end) if p is not None]
            if len(chain) >= 2:
                c = np.asarray(chain)
                fig.add_trace(go.Scatter3d(
                    x=c[:, 0], y=c[:, 1], z=c[:, 2], mode="lines+text",
                    line=dict(color="#888888", width=3, dash="dash"),
                    text=[str(seg.seq)] + [""] * (len(c) - 1),
                    name=f"{label} (unresolved)"))
            elif len(chain) == 1:
                c = chain[0]
                fig.add_trace(go.Scatter3d(
                    x=[c[0]], y=[c[1]], z=[c[2]], mode="markers+text",
                    marker=dict(size=5, color="#888888"),
                    text=[str(seg.seq)],
                    name=f"{label} (unresolved)"))
        marks = _seg_marker_trace(seg, colour)
        if marks is not None:
            fig.add_trace(marks)
    for i, oc in enumerate(diag.outer_contours):
        fig.add_trace(go.Scatter3d(
            x=oc[:, 0], y=oc[:, 1], z=oc[:, 2], mode="lines",
            line=dict(color="rgba(0,0,0,0.45)", width=2),
            name="OuterContour" if i == 0 else f"OuterContour {i + 1}",
            showlegend=i == 0))
    for gap in diag.gaps:
        g = np.asarray([gap.point_a, gap.point_b])
        mm = gap.distance_m * 1000.0
        fig.add_trace(go.Scatter3d(
            x=g[:, 0], y=g[:, 1], z=g[:, 2], mode="lines+text",
            line=dict(color="red", width=4, dash="dash"),
            text=[f"gap {mm:.1f} mm", ""],
            textfont=dict(color="red"),
            name=f"gap {mm:.1f} mm"))
    fig.update_layout(
        title=f"{diag.panel_id} — LimitedBy closure "
              f"(worst gap {diag.worst_gap_m * 1000:.1f} mm, "
              f"{diag.unresolved_count} unresolved)",
        scene=dict(aspectmode="data",
                   xaxis_title="x [m]", yaxis_title="y [m]",
                   zaxis_title="z [m]"),
        legend=dict(itemsizing="constant"),
        margin=dict(l=0, r=0, t=40, b=0))
    return fig
```

(If `figures.py` imports `plotly.graph_objects as go` and `numpy as np` at module level, drop the local imports and use the module-level ones — follow the file's style.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_top001_diagnose.py -v`
Expected: all PASS. If plotly rejects per-point `symbol` lists on `Scatter3d.marker`, split `_seg_marker_trace` into one trace per bound point (keep `showlegend=False`).

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/figures.py tests/test_top001_diagnose.py
git commit -m "feat(diagnose): plotly 3D figure for TOP-001 LimitedBy diagnosis

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: `ocx-diagnose` — HTML report writer

A lightweight standalone page (summary table + one figure per panel). Do not reuse the heavyweight lazy-WebGL report in `report.py` — a TOP-001 report has few figures.

**Files:**
- Modify: `packages/ocx-diagnose/src/ocx_diagnose/top001.py` (append)
- Test: `tests/test_top001_diagnose.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_top001_diagnose.py`:

```python
from ocx_diagnose.top001 import write_top001_report


def test_write_top001_report(tmp_path):
    v, panel = _open_square_panel()
    diags = select_panels(GeometryContext(v), None, tol_m=0.001)
    out = tmp_path / "r.html"
    write_top001_report(diags, out, title="model.3docx")
    text = out.read_text(encoding="utf-8")
    assert "p1" in text and "LimitedBy closure" in text
    assert "plotly" in text.lower()


def test_write_top001_report_empty(tmp_path):
    out = tmp_path / "r.html"
    write_top001_report([], out, title="model.3docx")
    assert "No panels" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_top001_diagnose.py -k report -v`
Expected: FAIL with `ImportError: cannot import name 'write_top001_report'`.

- [ ] **Step 3: Implement**

Append to `packages/ocx-diagnose/src/ocx_diagnose/top001.py`:

```python
def write_top001_report(diags: list[PanelTop001Diagnosis], path,
                        title: str) -> None:
    """Write one self-contained HTML report (plotly.js embedded once)."""
    import html as _html
    from pathlib import Path

    import plotly.offline

    from ocx_diagnose.figures import limitedby_fig

    rows = "".join(
        f"<tr><td>{_html.escape(d.panel_id)}</td><td>{len(d.segments)}</td>"
        f"<td>{d.unresolved_count}</td><td>{d.worst_gap_m * 1000:.2f}</td>"
        f"<td>{'no' if d.gaps or d.unresolved_count else 'yes'}</td></tr>"
        for d in diags)
    summary = ("<table border='1' cellpadding='4' cellspacing='0'>"
               "<tr><th>panel</th><th>segments</th><th>unresolved</th>"
               "<th>worst gap mm</th><th>closed</th></tr>"
               f"{rows}</table>") if diags else "<p>No panels to diagnose.</p>"
    figs = "".join(
        limitedby_fig(d).to_html(full_html=False, include_plotlyjs=False,
                                 default_height="650px")
        for d in diags)
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(title)} — TOP-001</title>"
            f"<script>{plotly.offline.get_plotlyjs()}</script></head><body>"
            f"<h1>TOP-001 LimitedBy diagnosis — {_html.escape(title)}</h1>"
            f"{summary}{figs}</body></html>")
    Path(path).write_text(page, encoding="utf-8")
    logger.info("Wrote TOP-001 report {} ({:.1f} MB)", path, len(page) / 1e6)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_top001_diagnose.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/top001.py tests/test_top001_diagnose.py
git commit -m "feat(diagnose): self-contained HTML report for TOP-001 diagnosis

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: `ocx-diagnose` — CLI command

**Breaking change to accept:** today `ocx-diagnose` has a single typer command, so it runs without a subcommand (`ocx-diagnose model.3docx`). Adding a second command makes typer require subcommand names: `ocx-diagnose diagnose model.3docx` and `ocx-diagnose top-001 model.3docx`. Update the README accordingly.

**Files:**
- Modify: `packages/ocx-diagnose/src/ocx_diagnose/cli.py`
- Modify: `packages/ocx-diagnose/README.md` (invocation examples)
- Test: manual CLI verification (CLI wiring only; logic is covered by Task 5–7 tests)

- [ ] **Step 1: Add the command**

In `packages/ocx-diagnose/src/ocx_diagnose/cli.py`, change the existing decorator `@app.command()` to `@app.command("diagnose")`, and append after the `diagnose` function:

```python
@app.command("top-001")
def top001(
    model: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False,
                                 help="Path to the .3docx model."),
    panel: list[str] = typer.Option(
        [], "--panel",
        help="Panel id to plot (repeatable; default: panels failing TOP-001)."),
    tolerance_mm: float = typer.Option(
        1.0, "--tolerance", help="Closure tolerance in millimetres."),
    report: Path | None = typer.Option(
        None, "--report", help="Output HTML report (default: <model>.top001.html)."),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level."),
) -> None:
    """Diagnose OCX-TOP-001 (panel LimitedBy closure) with 3D contour plots.

    Exit codes: 0 all plotted panels close, 1 at least one does not,
    2 cannot parse/build the model, 3 cannot write the output.
    """
    configure_logging(log_level.upper())
    try:
        vessel = _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        logger.error("Cannot parse/build {}: {}", model, exc)
        raise typer.Exit(code=2) from exc

    from ocx_rules.geometry_context import GeometryContext

    from ocx_diagnose.top001 import select_panels, write_top001_report

    tol_m = tolerance_mm / 1000.0
    geo = GeometryContext(vessel)
    diags = select_panels(geo, list(panel) or None, tol_m)
    out = report if report is not None else model.with_suffix(".top001.html")
    try:
        write_top001_report(diags, out, title=model.name)
    except OSError as exc:
        logger.error("Cannot write output for {}: {}", model, exc)
        raise typer.Exit(code=3) from exc
    typer.echo(f"Report written to {out} ({len(diags)} panel(s))")
    if any(d.gaps or d.unresolved_count for d in diags):
        raise typer.Exit(code=1)
```

- [ ] **Step 2: Update the README**

In `packages/ocx-diagnose/README.md`, update every invocation example from `ocx-diagnose MODEL …` to `ocx-diagnose diagnose MODEL …` and add a section:

```markdown
## TOP-001 LimitedBy diagnosis

Plot the unresolved LimitedBy contours of panels failing the OCX-TOP-001
best-practice rule (panel boundary must close):

    ocx-diagnose top-001 model.3docx [--panel ID]... [--tolerance MM] [--report out.html]

Each failing panel gets an interactive 3D figure: LimitedBy segments in
document order (coloured, sequence-labelled), ContourBounds markers
(Start ◆ / Mid ● / End ■), red dashed gap connectors annotated in mm, and
the Panel OuterContour (when present) as a grey reference curve.
Exit codes: 0 all plotted panels close, 1 at least one does not close,
2 cannot parse/build, 3 cannot write output.
```

- [ ] **Step 3: Verify the CLI manually**

```bash
uv run ocx-diagnose top-001 models/tr05/tr05_tc14a_cadhu.3docx
```

Expected: exit code 1; `models/tr05/tr05_tc14a_cadhu.top001.html` written containing figures for `_hullgroup2_layer-02_0panel` and `_hullgroup2_layer-02_1panel` (the two known TOP-001 failures with 4 939 mm / 2 663 mm gaps). Open the HTML and spot-check: coloured sequence-labelled segments, red gap connector with an mm annotation close to the rule's reported values. Also verify the old command still works as `uv run ocx-diagnose diagnose models/tr05/tr05_tc14a_nast.3docx --help` (help renders without error).

Then run: `uv run pytest` (full suite)
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/cli.py packages/ocx-diagnose/README.md
git commit -m "feat(diagnose): top-001 CLI command plotting LimitedBy closure failures

The diagnose command now requires its explicit subcommand name:
ocx-diagnose diagnose MODEL (was: ocx-diagnose MODEL).

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Documentation + final verification

**Files:**
- Modify: `.github/copilot-instructions.md` — in the repo-layout tree, extend the `ocx-diagnose` entry (or add it if the tree lacks one) to mention `top001.py` and the two subcommands; update the CLI section with the `ocx-diagnose top-001` invocation and exit codes. Keep edits minimal and in the file's existing style.

- [ ] **Step 1: Update the instructions file** (as described above).

- [ ] **Step 2: Full-suite + lint verification**

```bash
uv run pytest
uv run ruff check packages/ tests/
```

Expected: all tests pass; ruff clean (fix any findings in files this plan touched — leave pre-existing findings elsewhere alone).

- [ ] **Step 3: Commit**

```bash
git add .github/copilot-instructions.md
git commit -m "docs: document ocx-diagnose top-001 command

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
