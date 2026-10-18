# OCX Rule Checks — Phase B (Geometry Rules) Design

Date: 2026-10-18
Status: Approved
Predecessor: `2026-10-18-ocx-rule-checks-phase-a-design.md` (24 content rules, merged)

## Goal

Implement real check logic for 10 of the 12 geometry-dependent best-practice
rules that Phase A left as `NOT_IMPLEMENTED` stubs. The two compartment rules
(OCX-TOP-006 closed volume, OCX-TOP-007 disjoint) stay as stubs, deferred to a
later phase.

In scope:

- OCX-TOP-001 Panel LimitedBy closes
- OCX-TOP-002 Composite curves continuous
- OCX-TOP-003 Hole contours closed
- OCX-TOP-004 Holes do not split plates
- OCX-TOP-005 Seam topology valid
- OCX-TOP-008 Surface normals and boundaries consistent
- OCX-TOP-009 Stiffener inclinations consistent
- OCX-PROP plate weight consistent (`plate_weight_consistent`)
- OCX-PROP panel weight/CoG consistent (`panel_weight_cog_consistent`)
- OCX-PROP profile closed section (`profile_closed_section`)

Out of scope: OCX-TOP-006, OCX-TOP-007 (keep raising `CheckNotImplemented`);
any mesh/tessellation-based evaluation.

## Core constraint: no meshing

Geometry evaluation uses only:

1. **Curve sampling** to polylines (`ocx_geometry.curves.sample_curve` /
   `sample_contour`) at a tolerance.
2. **Analytic surface evaluation** — closed-form formulae for plane, cylinder,
   cone and sphere; **geomdl** evaluators for NURBS surfaces (points, partial
   derivatives, normals, first fundamental form).
3. **2-D polygon operations** with shapely in a plane or in a surface's UV
   domain.

No triangle meshes are built by any rule check. Meshing introduces an extra
layer of tolerances; the checks must not depend on it.

## Architecture

New dependency edge: `ocx-rules` depends on `ocx-geometry` (workspace source),
mirroring `ocx-render → ocx-geometry → ocx-model-core`. The resulting chain is
`ocx-model-validator → ocx-rules → ocx-geometry → ocx-model-core`.
`geomdl` and `shapely` are already dependencies of `ocx-geometry`; no new
third-party packages.

Math lives in the geometry kernel; rule checks stay thin orchestration.

### ocx-geometry additions

- `measure.py` (extend):
  - `contour_gaps(curves, length_resolver, tol_mm) -> list[Gap]` — sample each
    curve, chain segments end-to-end, return the junction/closure gaps (mm)
    with the offending curve ids. A contour is closed when every gap ≤ tol.
  - `surface_area(surface, boundary_uv) -> float` — area of a trimmed region:
    - plane: shapely polygon area;
    - cylinder/cone/sphere: closed-form patch formulae over the UV polygon;
    - NURBS: Gauss quadrature of `sqrt(EG − F²)` (first fundamental form via
      geomdl derivatives) over the trimmed UV polygon.
- `topology2d.py` (new, shapely-based):
  - `region_count(outer_ring, cut_rings) -> int` — number of connected regions
    after subtracting cuts/holes from the outer region;
  - `classify_point(point, contours, tol) -> Classification` — which contour
    (boundary / seam / hole) a point lies on, within tolerance;
  - `polygon_ok(ring) -> PolygonReport` — closed, simple (non-self-
    intersecting), non-zero area.

Each helper is pure (numpy/shapely in, plain results out) and unit-testable
without any OCX model.

### ocx-rules additions

- `ValidationContext.geometry` — new `cached_property` returning a
  `GeometryContext` that bundles the model's unit-aware `LengthResolver`,
  curve sampler and surface-param factory. Built lazily on first access, like
  `xml_tree` / `vessel` / `xml_index`.
- `RuleManager` treats the `"geometry"` requirement as satisfiable: it is
  satisfied when `context.geometry` builds (the IR must parse first, as for
  `"ir"`). If building fails the affected rules are SKIPPED with a reason, as
  for the other requirements.
- `packs/best_practice/checks/topology.py` — the seven TOP checks.
- `packs/best_practice/checks/properties.py` — the three property checks added
  alongside the existing PROP-004.
- `checks/geometry_stubs.py` shrinks to the two compartment stubs;
  `checks/__init__.py` facade re-exports unchanged names (`__all__` stays 31).

## Check logic per rule

| Rule | Logic |
|------|-------|
| TOP-001 | For each panel: resolve `LimitedBy` refs to curves via the IR, `contour_gaps` with `tolerance_mm`; any gap > tol → finding naming the panel and the gap size/location. |
| TOP-002 | For each `CompositeCurve3D`: sample segments in declared order; consecutive endpoint gap > `tolerance_mm` → finding per junction. |
| TOP-003 | Hole/opening contours: parametric hole profiles are closed by construction (verify the generated ring); curve-defined contours via `contour_gaps`. |
| TOP-004 | For each plate with holes: plate outline and placed hole outlines in the plate's plane/UV; `region_count(outline, holes)` > 1 → finding. Skips plates whose surface param cannot be built. |
| TOP-005 | For each panel: sample boundary, seams and hole contours; classify each seam endpoint (`classify_point`). A seam endpoint on a hole contour (boundary–hole, seam–hole, hole–hole connection) → finding. Then verify the seams + boundary partition the panel region into closed sub-regions (shapely split; every piece a valid polygon). |
| TOP-008 | For connected surface collections: evaluate analytic normals at samples along shared boundaries; adjacent-member normal deviation beyond `angle_tolerance_deg` → finding. Boundary loops checked closed via `contour_gaps`. |
| TOP-009 | From the IR inclination data per stiffener: duplicate positions (same parameter/point twice) and consecutive web or flange direction vectors with negative dot product (flip) → finding. Pure vector math, no sampling. |
| plate_weight | `surface_area` × thickness × material density vs declared mass; relative deviation > `rel_tolerance` (TOML param, default 0.05) → finding. Plates lacking mass, thickness, density or a buildable surface are skipped. |
| panel_weight_cog | Σ of child part masses vs panel declared mass (`rel_tolerance`, default 0.05); mass-weighted child CoG vs panel CoG (`cog_tolerance_mm`, default 50). Panels lacking declared values or whose children lack masses are skipped. |
| profile_closed_section | `section_polygon` from `sections_2d` for each section; `polygon_ok` must report closed, simple, non-zero area. |

All tolerances are TOML `[rule.check]` params, overridable through the user
config. TOML updates: the ten rules' `custom` targets move from stubs to the
new modules (paths stay `ocx_rules.packs.best_practice.checks:<name>`);
new tolerance params added where listed above.

## Error handling and uncertainty

- Checks never raise (`RuleManager` crash isolation remains the backstop).
- Per-element degradation: if geometry for one element cannot be built
  (unsupported surface type, missing refs, unresolved units), that element is
  skipped silently and the rule evaluates the rest. A rule with zero
  evaluable elements PASSES (vacuous), consistent with Phase A.
- Lean PASS: findings are reported only when the violation clearly exceeds
  the tolerance; borderline cases pass.
- Logging via loguru `debug` for skipped elements (diagnosability without
  noise).

## Testing

TDD per rule. Three layers:

1. **Kernel unit tests** — `contour_gaps`, `surface_area` (rectangle on a
   plane, cylinder patch, sphere lune, NURBS patch with known area),
   `topology2d` helpers. Pure numpy/shapely fixtures.
2. **Check unit tests** — synthetic IR/XML stubs per rule: a known-closed and
   a known-gapped contour, a hole that splits vs doesn't split, a flipped
   normal pair, a weight 10% off, etc. Reuse `tests/rules_xml.py` helpers and
   inline IR stubs.
3. **Corpus integration** — extend `tests/test_rules_corpus.py` to assert zero
   CRASHED and that the ten rules now report PASSED/FAILED (not
   NOT_IMPLEMENTED) across `models/**/*.3docx`.

Definition of done: full suite green, ruff clean (two accepted E402s),
corpus run zero crashes, smoke `validator validate rules` on
D-VLCC shows the geometry rules evaluated, docs touched up
(README + copilot-instructions: 34 implemented / 2 deferred).
