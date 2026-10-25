# Rule Implementation Gap Closures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three partial-implementation gaps in the best-practice rule pack: OCX-REF-002 (count Plates, not ComposedOf wrappers), OCX-GEO-005 (add catalogue-hole centering), OCX-TOP-005 (add closed-plate-contour check for seamed panels).

**Architecture:** Extend the existing check functions in place — no new rule IDs, no registry changes. REF-002 is a TOML-only change (the `cardinality` primitive already evaluates nested relative XPaths). GEO-005 gains a second per-`Hole2D` pass in `catalogue_holes_planar`. TOP-005 gains a private `_plate_contours_closed` helper called from `seam_topology` for every seamed panel, independent of the hole-outline early-continue.

**Tech Stack:** Python 3.11+, lxml, numpy, pytest, uv. All commands run from repo root `C:\PythonDev\ocx-platform`. Strict TDD: write each test, watch it fail, implement, watch it pass, commit with the Co-authored-by trailer.

**Spec:** `docs/superpowers/specs/2026-10-25-rule-gap-closures-design.md`

**Test conventions you'll reuse:**
- `tests/rules_xml.py` provides `context_for(body)` — wraps an XML fragment in a 3.1.0 `ocx:ocxXML` root and returns a `ValidationContext`.
- `tests/test_rules_checks_topology.py` builds IR fixtures directly: `_pt`, `_line`, `_square_sides`, `_square_outline`, `_Z_PLANE`, `_vessel`, `_ctx` (a `SimpleNamespace` with `vessel` + `geometry`), `_placement`, `_circle_hole`.
- `tests/test_rules_best_practice_pack.py` loads the pack via `from ocx_rules.packs.best_practice import load_pack`.

---

### Task 1: OCX-REF-002 — count Plates inside ComposedOf

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\references.toml` (OCX-REF-002 block, ~line 25)
- Test: `tests\test_rules_best_practice_pack.py`, `tests\test_rules_primitives.py`

- [ ] **Step 1: Write the failing pack test** — append to `TestBestPracticePack` in `tests\test_rules_best_practice_pack.py`:

```python
    def test_ref_002_counts_plates_inside_composed_of(self):
        pack = load_pack()
        by_id = {r.rule_id: r for r in pack.rules}
        assert by_id["OCX-REF-002"].params["child"] == "ocx:ComposedOf/ocx:Plate"
```

- [ ] **Step 2: Write the nested-path primitive tests** — append to `TestCardinality` in `tests\test_rules_primitives.py` (mechanism guard; these may pass immediately since lxml already supports relative paths — that is expected and fine):

```python
    def test_nested_child_path_counts_grandchildren(self):
        params = {"xpath": "//ocx:Panel", "child": "ocx:ComposedOf/ocx:Plate",
                  "min": 1}
        ctx = context_for(
            '<ocx:Panel id="p"><ocx:ComposedOf><ocx:Plate id="pl"/>'
            "</ocx:ComposedOf></ocx:Panel>")
        assert content.cardinality(ctx, params) == []

    def test_nested_child_path_empty_wrapper_fails(self):
        params = {"xpath": "//ocx:Panel", "child": "ocx:ComposedOf/ocx:Plate",
                  "min": 1}
        ctx = context_for('<ocx:Panel id="p"><ocx:ComposedOf/></ocx:Panel>')
        (finding,) = content.cardinality(ctx, params)
        assert "ocx:ComposedOf/ocx:Plate" in finding.message
```

- [ ] **Step 3: Run tests to verify RED/GREEN split**

Run: `uv run pytest tests/test_rules_best_practice_pack.py::TestBestPracticePack::test_ref_002_counts_plates_inside_composed_of "tests/test_rules_primitives.py::TestCardinality" -v`
Expected: the pack test FAILS with `AssertionError: assert 'ocx:ComposedOf' == 'ocx:ComposedOf/ocx:Plate'`; the two new primitive tests PASS (nested xpath already supported); existing cardinality tests PASS.

- [ ] **Step 4: Implement** — in `references.toml`, OCX-REF-002 block:

```toml
child     = "ocx:ComposedOf/ocx:Plate"
```

(replacing `child     = "ocx:ComposedOf"`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_primitives.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/references.toml tests/test_rules_best_practice_pack.py tests/test_rules_primitives.py
git commit -m "fix(ocx-rules): OCX-REF-002 counts Plates inside ComposedOf, not wrappers

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" --no-verify
```

---

### Task 2: OCX-GEO-005 — catalogue hole contours centered at origin

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\curves.py` (`catalogue_holes_planar`, ~line 169)
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\curves_surfaces.toml` (OCX-GEO-005 block, ~line 49)
- Test: `tests\test_rules_checks_curves.py`, `tests\test_rules_best_practice_pack.py`

- [ ] **Step 1: Write the failing check tests** — append to `tests\test_rules_checks_curves.py`:

```python
class TestCatalogueHolesCentered:
    PARAMS = {"tolerance_mm": 0.1, "center_tolerance_mm": 1.0}

    def _catalogue(self, coords: list[str]) -> str:
        pts = "".join(f'<ocx:Point3D coordinates="{c}"/>' for c in coords)
        return (f'<ocx:HoleShapeCatalogue><ocx:Hole2D id="h1">{pts}'
                "</ocx:Hole2D></ocx:HoleShapeCatalogue>")

    def test_centered_contour_passes(self):
        ctx = context_for(self._catalogue(
            ["-50 -50 0", "50 -50 0", "50 50 0", "-50 50 0"]))
        assert catalogue_holes_planar(ctx, self.PARAMS) == []

    def test_off_centre_contour_fails(self):
        # bbox centre = (5, 0) mm -> exceeds 1 mm tolerance
        ctx = context_for(self._catalogue(
            ["-45 -50 0", "55 -50 0", "55 50 0", "-45 50 0"]))
        (finding,) = catalogue_holes_planar(ctx, self.PARAMS)
        assert finding.element_id == "h1"
        assert "center" in finding.message.lower()

    def test_parametric_hole_without_coordinates_passes(self):
        ctx = context_for(
            '<ocx:HoleShapeCatalogue><ocx:Hole2D id="h1">'
            '<ocx:RectangularHole id="h1s"><ocx:Height numericvalue="2.0" unit="Um"/>'
            '<ocx:Width numericvalue="1.8" unit="Um"/></ocx:RectangularHole>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        assert catalogue_holes_planar(ctx, self.PARAMS) == []

    def test_one_finding_per_hole_not_per_point(self):
        two = (self._catalogue(["90 -50 0", "110 -50 0", "110 50 0", "90 50 0"])
               .replace("</ocx:HoleShapeCatalogue>", "")
               + '<ocx:Hole2D id="h2"><ocx:Point3D coordinates="-50 -50 0"/>'
                 '<ocx:Point3D coordinates="50 50 0"/></ocx:Hole2D>'
                 "</ocx:HoleShapeCatalogue>")
        (finding,) = catalogue_holes_planar(context_for(two), self.PARAMS)
        assert finding.element_id == "h1"
```

(`context_for` and `catalogue_holes_planar` are already imported at the top of this file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_curves.py::TestCatalogueHolesCentered -v`
Expected: `test_off_centre_contour_fails` and `test_one_finding_per_hole_not_per_point` FAIL with `ValueError: not enough values to unpack` (no finding produced); the two pass-cases PASS. The failing tests are the behavior being added.

- [ ] **Step 3: Implement** — in `checks/curves.py`, replace the body of `catalogue_holes_planar` with the planarity loop plus a per-hole centering pass:

```python
def catalogue_holes_planar(context, params: dict) -> list[Finding]:
    """OCX-GEO-005 (warning): catalogue hole contours are planar (Z = 0)
    and centered on the catalogue origin."""
    idx = context.xml_index
    tol = float(params.get("tolerance_mm", 0.1))
    center_tol = float(params.get("center_tolerance_mm", 1.0))
    scales = _unit_scales_mm(idx)
    findings = []
    for point in idx.xpath("//ocx:HoleShapeCatalogue//*[@coordinates]"):
        coords = _floats_of(point.get("coordinates"))
        if coords is None or len(coords) != 3:
            continue
        z_mm = coords[2] * scales.get(point.get("unit"), 1.0)
        if abs(z_mm) > tol:
            findings.append(Finding(
                message=(f"catalogue hole point at line {point.sourceline} has "
                         f"Z = {z_mm:.3f} mm; contours must be planar (Z = 0)"),
                location=point.sourceline))
    for hole in idx.xpath("//ocx:HoleShapeCatalogue//ocx:Hole2D"):
        xs, ys = [], []
        for point in hole.xpath(".//*[@coordinates]", namespaces=idx.nsmap):
            coords = _floats_of(point.get("coordinates"))
            if coords is None or len(coords) != 3:
                continue
            scale = scales.get(point.get("unit"), 1.0)
            xs.append(coords[0] * scale)
            ys.append(coords[1] * scale)
        if not xs:
            continue  # purely parametric shape — centered by construction
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        if max(abs(cx), abs(cy)) > center_tol:
            findings.append(Finding(
                message=(f"catalogue hole contour bounding-box center is "
                         f"({cx:.2f}, {cy:.2f}) mm; contours must be centered "
                         f"at the catalogue origin "
                         f"(tolerance {center_tol:.2f} mm)"),
                element_id=hole.get("id"), location=hole.sourceline))
    return findings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_curves.py -v`
Expected: all PASS (new class + existing `TestCatalogueHolesPlanar`).

- [ ] **Step 5: Write the failing TOML-param test** — append to `TestBestPracticePack` in `tests\test_rules_best_practice_pack.py`:

```python
    def test_geo_005_declares_center_tolerance(self):
        pack = load_pack()
        by_id = {r.rule_id: r for r in pack.rules}
        assert by_id["OCX-GEO-005"].params["center_tolerance_mm"] == 1.0
```

Run: `uv run pytest tests/test_rules_best_practice_pack.py::TestBestPracticePack::test_geo_005_declares_center_tolerance -v`
Expected: FAIL with `KeyError: 'center_tolerance_mm'`.

- [ ] **Step 6: Add the param** — in `curves_surfaces.toml`, OCX-GEO-005 `[rule.check]` block, after `tolerance_mm = 0.1`:

```toml
center_tolerance_mm = 1.0
```

Run: `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_checks_curves.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/curves.py packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/curves_surfaces.toml tests/test_rules_checks_curves.py tests/test_rules_best_practice_pack.py
git commit -m "feat(ocx-rules): OCX-GEO-005 verifies catalogue hole contours are centered

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" --no-verify
```

---

### Task 3: OCX-TOP-005 — seamed panels have closed plate contours

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py` (`seam_topology`, ~line 284)
- Test: `tests\test_rules_checks_topology.py`

- [ ] **Step 1: Write the failing tests** — append to `TestSeamTopology` in `tests\test_rules_checks_topology.py`. First a helper and an "open square" contour builder inside the class:

```python
    def _ctx_with_seam_and_plate(self, closed_plate: bool,
                                 with_seam: bool = True,
                                 hole_at: tuple[float, float] | None = None
                                 ) -> SimpleNamespace:
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        segs = [_line(a, b), _line(b, c), _line(c, d)]
        if closed_plate:
            segs.append(_line(d, a))
        outline = IrCompositeCurve3D(curve_length=None, segments=segs)
        cut_by = []
        cat = None
        if hole_at is not None:
            cat = IrHoleShapeCatalogue(id="cat",
                                       holes={"h1": _circle_hole(100.0)})
            cut_by = [IrHole2DContour(
                id="hc1", hole_ref=Ref(local_ref="h1"),
                transformation=_placement(*hole_at))]
        panel = IrPanel(
            id="pan1", plate_ids=["pl1"],
            seam_ids=(["s1"] if with_seam else []),
            limited_by=_square_sides(),
            unbounded_geometry=IrUnboundedGeometry(surface=_Z_PLANE),
            cut_by_holes=cut_by)
        plate = IrPlate(
            id="pl1", guidref="gpl1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            outer_contour=outline)
        vessel = _vessel({"pan1": panel}, catalogue=cat)
        vessel.plates["pl1"] = plate
        if with_seam:
            vessel.seams["s1"] = IrSeam(
                id="s1", trace_line=_line(_pt(0, 500), _pt(1000, 500)))
        return _ctx(vessel)

    def test_seamed_panel_closed_plate_contour_passes(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=True)
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_seamed_panel_open_plate_contour_fails(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False)
        (finding,) = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert finding.element_id == "pl1"
        assert finding.guid == "gpl1"
        assert "closed" in finding.message

    def test_unseamed_panel_open_plate_contour_ignored(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False, with_seam=False)
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_open_plate_contour_reported_even_with_holes_present(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False,
                                            hole_at=(500.0, 100.0))
        (finding,) = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert finding.element_id == "pl1"
```

(All names used — `IrCompositeCurve3D`, `IrSeam`, `IrPlate`, `ParentRef`, `ParentKind`, `Ref`, `IrUnboundedGeometry`, `IrHoleShapeCatalogue`, `IrHole2DContour` — are already imported at the top of this test file.)

Note the no-hole fail case exercises the current `if not hole_outlines: continue` early-continue: without the fix, the plate check never runs for hole-free panels.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest "tests/test_rules_checks_topology.py::TestSeamTopology" -v`
Expected: `test_seamed_panel_open_plate_contour_fails` and `test_open_plate_contour_reported_even_with_holes_present` FAIL with `ValueError: not enough values to unpack (expected 1, got 0)`; the other two new tests PASS (scope guards); all existing seam tests PASS.

- [ ] **Step 3: Implement** — in `checks/topology.py`:

Add a private helper directly above `seam_topology`:

```python
def _plate_contours_closed(context, panel, tol_m: float) -> list[Finding]:
    """OCX-TOP-005 aspect: plates of a seamed panel have closed outer contours."""
    geo = context.geometry
    vessel = context.vessel
    findings: list[Finding] = []
    for plate_id in panel.plate_ids:
        plate = vessel.plates.get(plate_id)
        if plate is None or plate.outer_contour is None:
            continue
        pts = geo.sample(plate.outer_contour)
        if pts is None or len(pts) < 3:
            logger.debug("TOP-005: plate {} skipped (unsampleable outer "
                         "contour)", plate_id)
            continue
        gap = float(np.linalg.norm(pts[0] - pts[-1]))
        if gap > tol_m:
            findings.append(Finding(
                message=(f"Plate outer contour is not closed: gap "
                         f"{gap * 1000:.2f} mm exceeds "
                         f"{tol_m * 1000:.2f} mm"),
                element_id=plate_id, guid=plate.guidref))
    return findings
```

Then in `seam_topology`, insert the call immediately after the `if not seams: continue` guard (before boundary/hole work, so the hole early-continue cannot skip it):

```python
        if not seams:
            continue
        findings += _plate_contours_closed(context, panel, tol_m)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_topology.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py tests/test_rules_checks_topology.py
git commit -m "feat(ocx-rules): OCX-TOP-005 verifies seamed panels have closed plate contours

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" --no-verify
```

---

### Task 4: Full verification + corpus

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass (~1090 passed, ~41 skipped).

- [ ] **Step 2: Run the corpus integration tests** (real models; asserts no rule crashes)

Run: `uv run pytest tests/test_rules_corpus.py -m integration -q`
Expected: all pass — new findings on reference models are fine, CRASHED is not.

---

### Task 5: Wiki page updates (external store, no repo commit)

**Files:**
- Modify: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-REF-002.md`
- Modify: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-GEO-005.md`
- Modify: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-TOP-005.md`

These pages live in a gitignored store — edit in place, no commit. For each page, read it first, then:

- [ ] **Step 1: OCX-REF-002.md** — delete the `> ⚠ note:` block (the wrapper-counting gap is fixed); update the pseudo code / params table to show `child = "ocx:ComposedOf/ocx:Plate"`; update the fail example so an empty `<ocx:ComposedOf/>` is shown as FAILING (it previously passed).

- [ ] **Step 2: OCX-GEO-005.md** — delete the `> ⚠ note:` block about centering being unchecked; extend the pseudo code with the per-Hole2D bbox-centre pass (collect XY of all descendant coordinate points, skip parametric-only entries, flag `max(|cx|,|cy|) > center_tolerance_mm`); add `center_tolerance_mm = 1.0` to the parameter table; extend the mermaid flow with the centering branch; add a fail example with an off-centre explicit contour.

- [ ] **Step 3: OCX-TOP-005.md** — replace the sentence noting the "closed plate contours" aspect is not separately checked; extend the pseudo code with `_plate_contours_closed` (per plate of a seamed panel: sample outer contour, gap = ‖first − last‖, flag > tolerance_mm); extend the mermaid flow; add a fail example with an open plate contour.

- [ ] **Step 4: Verify** — confirm no `⚠` remains on the three pages:

Run: `Select-String -Path C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-REF-002.md,C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-GEO-005.md,C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-TOP-005.md -Pattern '⚠'`
Expected: no output.
