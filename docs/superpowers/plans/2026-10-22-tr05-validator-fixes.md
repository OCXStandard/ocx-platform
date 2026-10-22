# TR05 Validator Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four validator issues confirmed by `docs/TR05_validation_mbrh.md` — order-dependent OCX-TOP-002, plates-only OCX-PROP-002, angle-threshold OCX-TOP-008, and unread `SlotContour` cut-outs.

**Architecture:** TOP-002 becomes order-invariant via a new greedy-chaining gap measure in `ocx_geometry.measure` (siblings `chain_polylines`/`ordered_junction_gaps` already live there). PROP-002 sums all panel children. TOP-008 replaces its angle threshold with a shared-edge handedness test. The builder maps `SlotContour` to the existing `IrHole2DContour` alongside `Hole2DContour`.

**Tech Stack:** Python 3.12, uv workspace, numpy, pytest, loguru. All commands run from the repo root `C:\PythonDev\ocx-platform`.

**Spec:** `docs/superpowers/specs/2026-10-22-tr05-validator-fixes-design.md`

**Conventions that matter here:**
- Run tests with `uv run pytest <path>` from the repo root.
- IR dataclasses are frozen; builders read raw OCX attributes only via `getattr(obj, "field", None)`.
- Tests against raw OCX objects use inline `types.SimpleNamespace` stubs, never the `ocx` bindings package.
- Logging is `from loguru import logger`; no prints.

---

### Task 1: `chained_junction_gaps` in `ocx_geometry.measure`

An order-invariant junction-gap measure: segments may attach at **either end** of the growing chain and may be reversed (the existing `chain_polylines` attaches only at the tail and appends a closure gap, which is wrong for open composite curves such as seams).

**Files:**
- Modify: `packages\ocx-geometry\src\ocx_geometry\measure.py` (add function after `ordered_junction_gaps`, which ends at line ~168)
- Test: `tests\test_measure_chain.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests\test_measure_chain.py` (import `chained_junction_gaps` in the existing `from ocx_geometry.measure import (...)` block; `_seg` and `_SQ` already exist at the top of the file):

```python
class TestChainedJunctionGaps:
    def test_out_of_order_scrambled_square_has_zero_gaps(self):
        gaps = chained_junction_gaps(_SQ)
        assert len(gaps) == 3           # junctions only, no closure gap
        assert max(gaps) < 1e-12

    def test_open_polyline_out_of_order(self):
        # L-shape declared middle-last: chainable only via both-end growth.
        segs = [_seg([1, 0, 0], [1, 1, 0]),
                _seg([1, 1, 0], [0, 1, 0]),
                _seg([0, 0, 0], [1, 0, 0])]
        gaps = chained_junction_gaps(segs)
        assert len(gaps) == 2 and max(gaps) < 1e-12

    def test_genuine_gap_reported(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1.057, 0, 0], [2, 0, 0])]
        gaps = chained_junction_gaps(segs)
        assert abs(gaps[0] - 0.057) < 1e-9

    def test_reversed_segment_chains(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([2, 0, 0], [1, 0, 0])]    # reversed
        gaps = chained_junction_gaps(segs)
        assert len(gaps) == 1 and gaps[0] < 1e-12

    def test_fewer_than_two_segments(self):
        assert chained_junction_gaps([]) == []
        assert chained_junction_gaps([_seg([0, 0, 0], [1, 0, 0])]) == []
        assert chained_junction_gaps([None]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_measure_chain.py::TestChainedJunctionGaps -v`
Expected: FAIL at import — `ImportError: cannot import name 'chained_junction_gaps'`

- [ ] **Step 3: Implement the function**

Add to `packages\ocx-geometry\src\ocx_geometry\measure.py`, directly after `ordered_junction_gaps`:

```python
def chained_junction_gaps(polylines: list[np.ndarray]) -> list[float]:
    """Junction gaps of the best greedy end-to-end chain of ``polylines``.

    Order-invariant: each segment may attach at either end of the growing
    chain and may be reversed — declared order carries no meaning.  Returns
    one gap per junction (no closure gap), or ``[]`` for fewer than two
    usable polylines.  Never raises.
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if len(parts) < 2:
        return []
    head, tail = parts[0][0], parts[0][-1]
    remaining = parts[1:]
    gaps: list[float] = []
    while remaining:
        # (gap, index, new_head, new_tail) of the best attachment
        best: tuple[float, int, np.ndarray, np.ndarray] | None = None
        for i, pts in enumerate(remaining):
            for p_join, p_far in ((pts[0], pts[-1]), (pts[-1], pts[0])):
                d_tail = float(np.linalg.norm(p_join - tail))
                if best is None or d_tail < best[0]:
                    best = (d_tail, i, head, p_far)
                d_head = float(np.linalg.norm(p_join - head))
                if d_head < best[0]:
                    best = (d_head, i, p_far, tail)
        gap, i, head, tail = best
        remaining.pop(i)
        gaps.append(gap)
    return gaps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_measure_chain.py -v`
Expected: all PASS (new class and the pre-existing tests)

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-geometry/src/ocx_geometry/measure.py tests/test_measure_chain.py
git commit -m "feat(geometry): order-invariant chained_junction_gaps"
```

---

### Task 2: OCX-TOP-002 uses the order-invariant measure

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py:9` (import) and `:121` (gap call)
- Modify: `packages\ocx-geometry\src\ocx_geometry\measure.py` (delete `ordered_junction_gaps`, lines ~139-168)
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\topology.toml` (OCX-TOP-002 description)
- Test: `tests\test_rules_checks_topology.py` (class `TestCompositeCurveContinuous`, ~line 137)
- Test: `tests\test_measure_chain.py` (delete `TestOrderedJunctionGaps` and its import)

- [ ] **Step 1: Write the failing test**

Add to `TestCompositeCurveContinuous` in `tests\test_rules_checks_topology.py` (helpers `_pt`, `_line`, `_ctx`, `_vessel` and `self._panel_with_composite` already exist):

```python
    def test_out_of_order_but_chainable_passes(self):
        # Three sides of a square declared out of order and one reversed:
        # continuous geometrically, discontinuous in declared order.
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(0, 1000), _pt(1000, 1000)),     # out of order
                _line(_pt(1000, 1000), _pt(1000, 0))]     # reversed
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_rules_checks_topology.py::TestCompositeCurveContinuous::test_out_of_order_but_chainable_passes" -v`
Expected: FAIL — a finding is produced because the declared-order gap is 1000 mm

- [ ] **Step 3: Switch the check to `chained_junction_gaps`**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py`, change line 9 from:

```python
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps
```

to:

```python
from ocx_geometry.measure import chain_polylines, chained_junction_gaps
```

and in `composite_curve_continuous` change:

```python
        gaps = ordered_junction_gaps(samples)
```

to:

```python
        gaps = chained_junction_gaps(samples)
```

- [ ] **Step 4: Delete `ordered_junction_gaps` and its tests**

- In `packages\ocx-geometry\src\ocx_geometry\measure.py`, delete the whole `ordered_junction_gaps` function (its only caller was TOP-002).
- In `tests\test_measure_chain.py`, delete the `TestOrderedJunctionGaps` class and remove `ordered_junction_gaps` from the import block.
- Confirm no other references: `grep -r ordered_junction_gaps packages tests` must return nothing.

- [ ] **Step 5: Update the rule description**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\topology.toml`, change the OCX-TOP-002 description from:

```toml
description = "CompositeCurve3D segments must be ordered end-to-end and continuous at every junction."
```

to:

```toml
description = "CompositeCurve3D segments must form one continuous chain: joinable end-to-end within tolerance, independent of declared order and orientation."
```

- [ ] **Step 6: Run the affected test files**

Run: `uv run pytest tests/test_rules_checks_topology.py tests/test_measure_chain.py -v`
Expected: all PASS (including the pre-existing `test_junction_gap_fails` — a real 2 mm gap is still flagged)

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/topology.toml packages/ocx-geometry/src/ocx_geometry/measure.py tests/test_rules_checks_topology.py tests/test_measure_chain.py
git commit -m "fix(rules): OCX-TOP-002 continuity is order-invariant"
```

---

### Task 3: Builder reads `SlotContour` into plate cut-outs

**Files:**
- Modify: `packages\ocx-model-core\src\ocx_model_core\builders\v3_builder.py:550-571` (`_build_hole2d_contours`)
- Test: `tests\test_builder_cutby.py` (class `TestCutByParsing`)

- [ ] **Step 1: Write the failing test**

Add to `TestCutByParsing` in `tests\test_builder_cutby.py` (the `_hole2d_contour` helper already exists in the file; `NS` is `types.SimpleNamespace`):

```python
    def test_cut_by_slot_contours_are_read(self):
        """SlotContour entries have the same shape as Hole2DContour and
        must land in cut_by_holes alongside them."""
        raw = NS(id="pan1", name="P", guidref=None, function_type=None,
                 tightness=None, point_on_surface=None,
                 composed_of=None, stiffened_by=None, limited_by=None,
                 unbounded_geometry=None,
                 cut_by=NS(hole2_dcontour=[_hole2d_contour("hc1", "H1")],
                           slot_contour=[_hole2d_contour("sc1", "H2"),
                                         _hole2d_contour("sc2", "H3")],
                           inner_contour=[]))
        ir = IrVessel(id="v1")
        panel = _b()._build_panel(raw, ir, "v1")
        assert len(panel.cut_by_holes) == 3
        assert {h.id for h in panel.cut_by_holes} == {"hc1", "sc1", "sc2"}
        assert panel.cut_by_holes[1].hole_ref.local_ref == "H2"
        assert panel.cut_by_holes[1].transformation is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_builder_cutby.py::TestCutByParsing::test_cut_by_slot_contours_are_read" -v`
Expected: FAIL — `assert 1 == 3` (only the Hole2DContour is read)

- [ ] **Step 3: Read `slot_contour` in `_build_hole2d_contours`**

In `packages\ocx-model-core\src\ocx_model_core\builders\v3_builder.py`, change the loop header in `_build_hole2d_contours` from:

```python
        for hc in _children(getattr(cut_by, "hole2_dcontour", None)):
```

to:

```python
        # SlotContour has the identical shape (hole_ref + transformation)
        # and is a cut-out exactly like Hole2DContour.
        for hc in (*_children(getattr(cut_by, "hole2_dcontour", None)),
                   *_children(getattr(cut_by, "slot_contour", None))):
```

- [ ] **Step 4: Run the builder test files**

Run: `uv run pytest tests/test_builder_cutby.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py tests/test_builder_cutby.py
git commit -m "fix(core): read PlateCutBy/CutBy SlotContour into cut_by_holes"
```

---

### Task 4: OCX-PROP-002 sums all panel children

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\properties.py:120-180` (`panel_weight_cog_consistent`)
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\properties.toml` (OCX-PROP-002 description)
- Test: `tests\test_rules_checks_properties.py` (class `TestPanelWeightCogConsistent`)

- [ ] **Step 1: Write the failing tests**

In `tests\test_rules_checks_properties.py`, add `IrStiffener` to the existing `from ocx_model_core.model.ir import (...)` block, then add to `TestPanelWeightCogConsistent`:

```python
    def test_mass_including_stiffener_children_passes(self):
        # Panel declares the complete panel: 78.5 kg plate + 78.5 kg
        # stiffener. Plates-only summation would flag this.
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=157.0),
            [_mass_props(weight_kg=78.5)])
        ctx.vessel.stiffeners["st1"] = IrStiffener(
            id="st1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            mass_properties=_mass_props(weight_kg=78.5))
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []

    def test_cog_weighted_across_child_kinds(self):
        # plate at x=250, stiffener at x=750, equal masses -> CoG x=500.
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=157.0, cog_mm=(500, 500, 0)),
            [_mass_props(weight_kg=78.5, cog_mm=(250, 500, 0))])
        ctx.vessel.stiffeners["st1"] = IrStiffener(
            id="st1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            mass_properties=_mass_props(weight_kg=78.5, cog_mm=(750, 500, 0)))
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == []

    def test_total_including_children_still_deviating_fails(self):
        ctx = self._ctx_with_panel(
            _mass_props(weight_kg=300.0),
            [_mass_props(weight_kg=78.5)])
        ctx.vessel.stiffeners["st1"] = IrStiffener(
            id="st1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            mass_properties=_mass_props(weight_kg=78.5))
        (finding,) = panel_weight_cog_consistent(ctx, self.PARAMS)
        assert finding.element_id == "pan1"
        assert "300.00" in finding.message
        assert "157.00" in finding.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_properties.py::TestPanelWeightCogConsistent -v`
Expected: the three new tests FAIL (stiffener mass not summed); the existing ones PASS

- [ ] **Step 3: Sum all children in the check**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\properties.py`, inside `panel_weight_cog_consistent`, replace the child-collection loop:

```python
        children: list[tuple[float, Any]] = []
        for plate in vessel.plates.values():
            pr = plate.parent_ref
            if pr is None or pr.kind != ParentKind.PANEL or pr.id != pid:
                continue
            mass = _declared_weight_kg(geo, plate.mass_properties)
            if mass is None:
                continue
            children.append((mass, _declared_cog(plate.mass_properties)))
        if not children:
            logger.debug("PROP-002: panel {} skipped (no child plates with "
                         "declared mass)", pid)
            continue
```

with:

```python
        # A panel's declared mass covers the complete panel: all children
        # parented to it (plates, stiffeners, edge reinforcements,
        # brackets, pillars).
        children: list[tuple[float, Any]] = []
        for part in (*vessel.plates.values(), *vessel.stiffeners.values(),
                     *vessel.edge_reinforcements.values(),
                     *vessel.brackets.values(), *vessel.pillars.values()):
            pr = part.parent_ref
            if pr is None or pr.kind != ParentKind.PANEL or pr.id != pid:
                continue
            mass = _declared_weight_kg(geo, part.mass_properties)
            if mass is None:
                continue
            children.append((mass, _declared_cog(part.mass_properties)))
        if not children:
            logger.debug("PROP-002: panel {} skipped (no children with "
                         "declared mass)", pid)
            continue
```

Then update the two finding messages in the same function:
- `"deviates from the sum of its plate weights "` → `"deviates from the sum of its child part weights "`
- `"mass-weighted plate centre of gravity by "` → `"mass-weighted child centre of gravity by "`

Also update the docstring: `"""OCX-PROP-002: panel weight/CoG consistent with its child plates."""` → `"""OCX-PROP-002: panel weight/CoG consistent with all its children."""`

- [ ] **Step 4: State the convention in the rule TOML**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\properties.toml`, change the OCX-PROP-002 description to:

```toml
description = "Panel declared weight and centre of gravity cover the complete panel and must reconcile with the sum of all children parented to it: plates, stiffeners, edge reinforcements, brackets and pillars."
```

- [ ] **Step 5: Run the test file**

Run: `uv run pytest tests/test_rules_checks_properties.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml tests/test_rules_checks_properties.py
git commit -m "fix(rules): OCX-PROP-002 sums all panel children, not only plates"
```

---

### Task 5: OCX-TOP-008 handedness test

Replace the pass/fail normal-angle threshold with a shared-edge orientation test. At a shared-boundary point `p` with shared-edge tangent `t`, each face gets an in-plane probe `d` toward its own boundary centroid; handedness is `s = sign((t × d) · n)`. A consistently oriented pair has opposite handedness (`s_a · s_b < 0`) at **any** dihedral angle, so sharp knuckles pass while flipped faces fail.

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py:336-425` (`_normal_at` area + `surface_normals_and_boundaries`)
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\topology.toml` (OCX-TOP-008 entry)
- Test: `tests\test_rules_checks_topology.py` (class `TestSurfaceNormalsAndBoundaries`, ~line 353)

- [ ] **Step 1: Update and extend the tests**

In `tests\test_rules_checks_topology.py`, class `TestSurfaceNormalsAndBoundaries` (helpers `_coll_member` / `_coll_ctx` already exist above the class):

1. Change `PARAMS = {"angle_tolerance_deg": 90.0}` to `PARAMS: dict = {}`.
2. In `test_opposed_normals_fail` and `test_t_configuration_without_shared_corners_fails`, change the message assertion `assert "normals deviate" in finding.message` to `assert "orientation reverses" in finding.message` (the T-configuration test only asserts `"sb" in finding.message` — leave that).
3. Add a knife-edge test:

```python
    def test_sharp_knuckle_consistently_oriented_passes(self):
        # Face A in z=0; face B folds up steeply from the shared edge
        # x=1000: normals ~143 deg apart, but orientation is consistent
        # (both probes obey the opposite-handedness relation).
        boundary_b = IrPolyLine3D(curve_length=None, vertices=[
            _pt(1000, 0, 0), _pt(200, 0, 600), _pt(200, 1000, 600),
            _pt(1000, 1000, 0), _pt(1000, 0, 0)], is_closed=True)
        geom_b = IrExtrudedSurface(
            base_curve=_line(_pt(1000, 0, 0), _pt(200, 0, 600)),
            sweep=IrVector3D(0.0, 1.0, 0.0),
            face_boundary_curve=boundary_b)
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        IrSurface(id="sb", geometry=geom_b))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `uv run pytest tests/test_rules_checks_topology.py::TestSurfaceNormalsAndBoundaries -v`
Expected: `test_sharp_knuckle_consistently_oriented_passes` FAILS (normals ~143° > 90° are flagged today); `test_opposed_normals_fail` also fails on the changed message assertion. The others pass.

- [ ] **Step 3: Implement the handedness test**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py`, add two helpers directly after `_normal_at` (~line 346):

```python
def _tangent_at(bnd: np.ndarray, p: np.ndarray) -> np.ndarray | None:
    """Unit direction of the boundary-polyline stretch nearest ``p``."""
    j = int(np.argmin(np.linalg.norm(bnd - p, axis=1)))
    t = bnd[min(j + 1, len(bnd) - 1)] - bnd[max(j - 1, 0)]
    norm = float(np.linalg.norm(t))
    if not np.isfinite(norm) or norm < 1e-12:
        return None
    return t / norm


def _probe_into(p: np.ndarray, centroid: np.ndarray,
                normal: np.ndarray) -> np.ndarray | None:
    """Unit in-plane direction at ``p`` toward the face interior."""
    d = centroid - p
    d = d - (d @ normal) * normal
    norm = float(np.linalg.norm(d))
    if not np.isfinite(norm) or norm < 1e-9:
        return None
    return d / norm
```

Then rewrite `surface_normals_and_boundaries`:

1. Delete the first line `tol_deg = float(params.get("angle_tolerance_deg", 90.0))`.
2. Extend each member tuple with its boundary centroid — change

```python
            members.append((surf, param, bnd,
                            bnd.min(axis=0), bnd.max(axis=0)))
```

to

```python
            members.append((surf, param, bnd, bnd.mean(axis=0),
                            bnd.min(axis=0), bnd.max(axis=0)))
```

and the two unpacking lines to:

```python
            surf_a, param_a, bnd_a, cen_a, lo_a, hi_a = members[i]
            for surf_b, param_b, bnd_b, cen_b, lo_b, hi_b in members[i + 1:]:
```

3. Replace the sampling loop and verdict (from `angles = []` down to the `findings.append(...)` block) with:

```python
                votes: list[bool] = []
                angles: list[float] = []
                for _, p in close[:_MAX_SHARED_SAMPLES]:
                    try:
                        na = _normal_at(param_a, p)
                        nb = _normal_at(param_b, p)
                    except Exception as exc:  # noqa: BLE001 — skip sample
                        logger.debug("TOP-008: normal evaluation failed for "
                                     "{}/{}: {}", surf_a.id, surf_b.id, exc)
                        continue
                    if na is None or nb is None:
                        continue
                    t = _tangent_at(bnd_a, p)
                    da = _probe_into(p, cen_a, na)
                    db = _probe_into(p, cen_b, nb)
                    if t is None or da is None or db is None:
                        continue
                    sa = float(np.cross(t, da) @ na)
                    sb = float(np.cross(t, db) @ nb)
                    if abs(sa) < 1e-9 or abs(sb) < 1e-9:
                        continue  # degenerate handedness sample
                    votes.append(sa * sb > 0.0)
                    dot = float(np.clip(na @ nb, -1.0, 1.0))
                    angles.append(np.degrees(np.arccos(dot)))
                if not votes:
                    logger.debug("TOP-008: pair {}/{} skipped (no evaluable "
                                 "shared boundary samples)", surf_a.id,
                                 surf_b.id)
                    continue
                flipped = sum(votes)
                # strict majority of flipped samples; ties pass
                if flipped > len(votes) - flipped:
                    angle = float(np.median(angles))
                    findings.append(Finding(
                        message=(f"Surface orientation reverses across the "
                                 f"shared boundary with member {surf_b.id} "
                                 f"in collection {cid} (normals "
                                 f"{angle:.1f} deg apart)"),
                        element_id=surf_a.id, guid=surf_a.guidref))
```

4. Update the function docstring to: `"""OCX-TOP-008: face orientation must not reverse across shared boundaries."""`

- [ ] **Step 4: Update the rule TOML**

In `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\topology.toml`, OCX-TOP-008 entry: delete the `angle_tolerance_deg = 90.0` line and change the description to:

```toml
description = "Face orientation (normal handedness relative to the shared boundary) must be consistent across a connected surface collection; sharp knuckles are permitted."
```

- [ ] **Step 5: Run the test file**

Run: `uv run pytest tests/test_rules_checks_topology.py -v`
Expected: all PASS — flipped coplanar and flipped T-configuration still flagged, knife-edge passes

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/topology.toml tests/test_rules_checks_topology.py
git commit -m "fix(rules): OCX-TOP-008 handedness test replaces normal-angle threshold"
```

---

### Task 6: Full suite + TR05 acceptance

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: all pass (baseline before this work: 1039 passed, 41 skipped). Fix any regression before continuing.

- [ ] **Step 2: Acceptance run on the TR05 mbrh models**

Run each (from the repo root; exit code 0 = no error findings, 1 = error findings — PROP rules are warnings and never set exit 1, so read the printed findings):

```bash
uv run validator validate rules models/TR05/tr05_tc04a_mbrh.3docx --rule OCX-TOP-002
uv run validator validate rules models/TR05/tr05_tc09_mbrh.3docx  --rule OCX-TOP-002
uv run validator validate rules models/TR05/tr05_tc14a_mbrh.3docx --rule OCX-TOP-002
uv run validator validate rules models/TR05/tr05_tc04a_mbrh.3docx --rule OCX-PROP-002
uv run validator validate rules models/TR05/tr05_tc09_mbrh.3docx  --rule OCX-PROP-002
uv run validator validate rules models/TR05/tr05_tc14a_mbrh.3docx --rule OCX-PROP-002
uv run validator validate rules models/TR05/tr05_tc14a_mbrh.3docx --rule OCX-TOP-008
uv run validator validate rules models/TR05/tr05_tc09_mbrh.3docx  --rule OCX-PROP-001
```

Expected against the report baseline (`docs/TR05_validation_mbrh.md`):
- OCX-TOP-002: **0 findings** on all three models (was 2 / 33 / 13).
- OCX-PROP-002: **0 findings** on all three models (was 2 / 57 / 1).
- OCX-TOP-008: **0 findings** on tc14a (was 3).
- OCX-PROP-001 on tc09: findings **remain** for the genuine export issues (was 15; count may shift slightly now that slots are subtracted — the transverse-girder webs deviate further, which is correct).

- [ ] **Step 3: Record the acceptance result**

If any expectation fails, debug with the superpowers:systematic-debugging skill before claiming completion. When all pass, note the final per-rule counts in the final summary to the user (no new doc file needed).

---

## Self-review notes

- Spec coverage: Fix 1 → Tasks 1-2, Fix 4 → Task 3, Fix 2 → Task 4, Fix 3 → Task 5, Verification → Task 6. Rollout order matches the spec (TOP-002, slots, PROP-002, TOP-008).
- Deviation from spec, intentional: `chained_junction_gaps` lives in `ocx_geometry.measure` (not `curves`) beside its siblings `chain_polylines`/`chain_gap_details`, and `_sample_composite` in `curves.py` is left untouched — it already chains correctly; extracting it would change two call sites for no behavioural gain. Spec's intent (order-invariant TOP-002, shared greedy chaining semantics) is preserved.
- `ordered_junction_gaps` removal verified single-caller via grep (only `topology.py:9/121` and its own tests).
