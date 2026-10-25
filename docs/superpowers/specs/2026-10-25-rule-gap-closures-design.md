# Rule Implementation Gap Closures — Design

**Date:** 2026-10-25
**Status:** Approved
**Scope:** Close the three partial-implementation gaps found during the rule
wiki review: OCX-REF-002, OCX-GEO-005, OCX-TOP-005. The two compartment rules
(OCX-TOP-006/007) remain deferred stubs — explicitly out of scope.

## Background

All 36 best-practice rules are defined; 34 have real check implementations.
The wiki documentation pass flagged three rules whose implementation covers
only part of the documented rule:

| Rule | Gap |
|---|---|
| OCX-REF-002 | Counts `ComposedOf` wrapper children of `Panel`, not the `Plate` elements inside — an empty `<ocx:ComposedOf/>` passes. |
| OCX-GEO-005 | Title promises "planar **and centered**"; only planarity (Z = 0) is checked. |
| OCX-TOP-005 | Description includes "the seam pattern must subdivide the panel into closed plate contours"; only the seam-endpoint-on-hole aspect is checked. |

## Design decisions (user-approved)

- **Approach:** extend the existing check functions in place (no new rule
  IDs, no registry changes, one rule = one check preserved). Private helpers
  where a function would otherwise grow past ~40 lines.
- **TOP-005 scope:** plate-closure applies only to plates of panels that
  have seams (faithful to the rule text), not to every plate.
- **GEO-005 tolerance:** centering gets its own TOML parameter
  `center_tolerance_mm = 1.0` (bbox centres shift legitimately for
  asymmetric contours); planarity keeps `tolerance_mm = 0.1`.

## 1. OCX-REF-002 — Panel contains at least one Plate

**Change (TOML only):** in
`packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/references.toml`:

```toml
child = "ocx:ComposedOf/ocx:Plate"   # was: "ocx:ComposedOf"
```

The `cardinality` primitive evaluates `./{child}` as a relative XPath with
the shared nsmap, so nested paths work without touching the primitive. The
finding message renders the path verbatim ("has 0 `<ocx:ComposedOf/ocx:Plate>`
children") — mechanical but accurate. The `ocx:` prefix is bound to the
document's actual root namespace by `XmlIndex`, so the rule stays correct for
2.8.6 and 3.x models.

**Behavior change:** a Panel whose `ComposedOf` contains no `Plate` (including
an empty wrapper) now fails; a Panel with ≥1 nested `Plate` passes as before.

## 2. OCX-GEO-005 — Catalogue hole contours planar AND centered

**Change:** extend `catalogue_holes_planar` in
`packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/curves.py`.

Keep the existing point-level planarity loop unchanged. Add a second pass:

```
for hole in idx.xpath("//ocx:HoleShapeCatalogue//ocx:Hole2D"):
    pts = [unit-scaled (x_mm, y_mm) for each descendant element with a
           well-formed 3-float @coordinates attribute]
    if not pts:            # purely parametric shape (RectangularHole,
        continue           # SymmetricalHole, ParametricCircle, …) —
                           # centered by construction
    cx = (min_x + max_x) / 2 ;  cy = (min_y + max_y) / 2
    if max(|cx|, |cy|) > center_tolerance_mm:
        finding: "catalogue hole <id> contour bounding-box centre is
                  (cx, cy) mm; contours must be centered at the catalogue
                  origin (tolerance T mm)"   # element_id=hole id,
                                             # location=hole sourceline
```

One finding per off-centre `Hole2D` entry (not per point). Malformed
coordinate attributes are skipped in this pass (the planarity pass already
tolerates them the same way).

**TOML:** add `center_tolerance_mm = 1.0` to the OCX-GEO-005 block in
`rules/curves_surfaces.toml`. Severity stays `warning`; title/description
already promise centering — unchanged.

## 3. OCX-TOP-005 — Seam pattern subdivides panel into closed plate contours

**Change:** extend `seam_topology` in
`packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py`.

Add a private helper:

```
_plate_contours_closed(context, pid, panel, tol_m) -> list[Finding]:
    for plate_id in panel.plate_ids:
        plate = vessel.plates.get(plate_id)
        if plate is None or plate.outer_contour is None: continue
        pts = geo.sample(plate.outer_contour)
        if pts is None or len(pts) < 3:
            debug-log skip (lean-pass convention); continue
        gap = ||pts[0] - pts[-1]||
        if gap > tol_m:
            finding: "Plate outer contour is not closed: gap G mm exceeds
                      T mm"   # element_id=plate_id, guid=plate.guidref
```

Called from `seam_topology` for every panel that has ≥1 resolvable seam,
using the rule's existing `tolerance_mm` (5.0). **Ordering constraint:** the
current implementation does `if not hole_outlines: continue` before the
endpoint loop; the plate-closure pass must run before (or independent of)
that early-continue so panels without holes still get their plates checked.

Plates without an `outer_contour` or with unsampleable contours are skipped
silently (debug log), consistent with every other geometry check's
lean-pass convention.

## Error handling

No new failure modes: all three changes operate inside the existing
skip/lean-pass conventions. No CLI, renderer, exit-code, or RuleStatus
changes. No schema-support markers needed (all touched elements exist in
all supported schema families).

## Testing (strict TDD)

Follow the existing test-file layout for pack checks (locate the current
REF/GEO/TOP check tests and extend them in place):

- **REF-002:** inline XML stubs — Panel with empty `ComposedOf` → 1 finding;
  Panel with `ComposedOf/Plate` → no finding; Panel with no `ComposedOf`
  → 1 finding (unchanged behavior, regression guard).
- **GEO-005:** catalogue with an explicit contour centred at origin → no
  centering finding; same contour translated > 1 mm in X → 1 finding naming
  the Hole2D; purely parametric catalogue (existing stub shape) → no
  centering finding; existing planarity tests stay green.
- **TOP-005:** seamed panel whose plate outer contour closes within 5 mm →
  no new finding; same panel with an open plate contour (> 5 mm gap) →
  1 finding with the plate id; panel without seams and an open plate
  contour → no finding (scope guard); seamed panel with no holes and an
  open plate contour → 1 finding (early-continue regression guard).

Each test is written first and watched failing. Full `uv run pytest`
afterward (including the corpus tests) to confirm no regression on real
models.

## Documentation

Update the three wiki pages in
`C:\PythonDev\ocx-wiki\out\wiki-writer\rules\` (OCX-REF-002.md,
OCX-GEO-005.md, OCX-TOP-005.md): remove the ⚠ gap notes, extend the pseudo
code and mermaid flows to cover the new aspects, and update/extend the pass
and fail stub examples. The pages live outside this repo (gitignored store)
— no repo commit for them.
