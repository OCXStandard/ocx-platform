# Exporter plausibility rules — design

Date: 2026-11-13
Package: `ocx-rules` (best_practice pack)
Branch: `feat/exporter-plausibility-rules` (based on
`fix/multi-surface-unbounded-geometry`, which adds `IrUnboundedGeometry.surfaces`)

## Problem

`iter0.3docx` exposed exporter bugs that no existing rule catches:

- All 156 shell stiffeners on panel `nplcid34586` carry one inclination with
  the same `Position` (195.404, 24.0821, 2.96424), up to 25 m off their traces.
- Their `WebDirection` is copied too: e.g. `nplcid34858` has web ≈ [0,0,1]
  while the bilge shell normal is ≈ (0.05, 0.62, -0.78) — 37° off; six webs lie
  in the plate plane (90°).
- The part `MouldedCOG` equals the same point, outside the part.

`OCX-TOP-009` only checks series of ≥ 2 inclinations (duplicates, flips);
`OCX-PROP-002` only reconciles panel totals. Neither looks at single-entry
inclinations or per-part COG plausibility.

## Rules

Severity is per rule (`Finding` has none), so the tiered web check is two rules.

| ID | Severity | Title | Parameters |
|---|---|---|---|
| OCX-TOP-010 | error | Inclination position on trace | `position_tolerance_mm = 50` |
| OCX-TOP-011 | error | Web direction not in plate plane | `max_angle_deg = 80` |
| OCX-TOP-012 | warning | Web direction close to surface normal | `warn_angle_deg = 30`, `max_angle_deg = 80` |
| OCX-PROP-005 | warning | Part COG within part geometry | `margin_mm = 500` |
| OCX-PROP-006 | warning | Position/COG not shared across parts | `tolerance_mm = 1`, `min_parts = 3` |

All require `["ir", "geometry"]`. TOP rules go in `rules/topology.toml`, PROP
rules in `rules/properties.toml`. Check functions live in a new module
`packs/best_practice/checks/plausibility.py`, exported via `checks/__init__.py`.

## Computation

### OCX-TOP-010 — inclination position on trace

For every stiffener and pillar, for every inclination with a `Position`:
sample the trace (`GeometryContext.sample`), compute the exact point-to-polyline
distance. Finding when distance > `position_tolerance_mm`. Message names the
entry index and the distance in metres.

### OCX-TOP-011 / OCX-TOP-012 — web direction vs panel surface normal

Stiffeners only (pillars have no panel surface). For each inclination with a
non-zero `WebDirection`:

1. Evaluation point: the trace polyline point nearest the inclination position
   (trace start when the position is missing). An off-trace position is still
   evaluated here; TOP-010 reports the position itself.
2. Surface: the panel's surfaces are `UnboundedGeometry.surfaces`, falling back
   to `surface` and then the referenced surface. Pick the member whose
   inverse/evaluate distance to the point is smallest.
3. Skip (no finding) when the stiffener has no panel, no surface resolves, or
   the nearest surface is > 50 mm from the point (free-standing member).
4. `angle = degrees(arccos(|w · n|))` with unit `w`, `n` — the normal's sign is
   arbitrary.
5. TOP-011: finding when `angle >= max_angle_deg`.
   TOP-012: finding when `warn_angle_deg < angle < max_angle_deg`.

Both rules share one helper that yields `(stiffener, entry index, angle)`.

### OCX-PROP-005 — part COG within part geometry

Parts: plates (outer contour) and stiffeners/pillars (trace). Brackets and edge
reinforcements are out of scope. Finding when `mass_properties.moulded_cog`
lies outside the axis-aligned bounding box of the sampled geometry inflated by
`margin_mm`. Parts without mass properties or geometry are skipped. Message
gives the COG and its distance to the box.

### OCX-PROP-006 — values shared across parts

Two independent pools: inclination positions (stiffeners, pillars) and
`MouldedCOG`s (plates, stiffeners, pillars). Values are keyed by rounding to a
`tolerance_mm` grid. A part contributing the same key more than once counts
once. For every key held by ≥ `min_parts` distinct parts, emit one finding per
part, e.g. `Inclination position (195.404, 24.082, 2.964) is shared by 156
parts`.

### Error handling

Each part is evaluated in its own `try`; an exception skips that part with a
debug log (pattern of `_inclination_positions`). Unparseable quantities are
skipped. Rules never raise for bad model data.

## Testing

Unit tests in `packages/ocx-rules/tests`, test-first, on a small synthetic
`IrVessel` (flat plane panel, one plate, straight-trace stiffeners):

- TOP-010: position on trace → none; 1 m off → finding.
- TOP-011/012: web along normal → none; 45° → TOP-012 only; in-plane → TOP-011
  only; stiffener without panel surface → skipped.
- PROP-005: COG inside box → none; 5 m outside → finding.
- PROP-006: 3 parts sharing a value → 3 findings; 2 parts → none; one part
  repeating its own value → counted once.

Update any catalogue/rule-count assertions. Manual check on
`ocx-render/example-models/iter0.3docx`: expect PROP-006 on the 156 shared
positions, TOP-010 on the off-trace positions, TOP-011 on the six in-plane
webs, TOP-012 on the 6 between 30° and 80° (21 exceed 10°, 12 exceed 30°,
6 of those are ≥ 80° and belong to TOP-011).

## Docs

`ocx-rules` CHANGELOG entry; extend the rule list where one is maintained.

## Out of scope

Correcting the data in the renderer; brackets and edge reinforcements in
PROP-005; flange-direction plausibility.
