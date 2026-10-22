# Changelog — ocx-geometry

## Unreleased

### Fixed

- LSCM chart building (`make_lscm_chart` / `make_lscm`): hint points may
  now be passed as per-plate contour loops; each plane member's trim is
  then bounded by the union of the concave hull and the loop polygons.
  Previously the concave hull of sparse hints could tunnel into plate
  interiors (e.g. knuckled inner-skin panels, where the knuckle edge has
  hints only at plate corners), leaving slits in the chart mesh that made
  plates render with large missing regions or leak the whole chart.

### Added

- `measure.chained_junction_gaps`: order-invariant junction-gap measure —
  segments may attach at either end of the growing chain and may be
  reversed, so declared segment order carries no meaning.

### Removed

- `measure.ordered_junction_gaps` (declared-order junction gaps) —
  superseded by `chained_junction_gaps`.

## 0.1.0 — 2026-10-20

Initial release.

### Added

- Geometry evaluation kernel for the OCX IR, built on numpy with no
  display stack (depends only on `ocx-model-core`).
- `measure`: length, area and closure measurements on IR geometry,
  including `chain_polylines` and `chain_gap_details` (gap endpoint
  pairs for unclosed boundary chains).
- `curves`: sampling and evaluation of IR curves (lines, arcs, polylines,
  NURBS).
- `surfaces`: IR surface → parametric surface evaluation.
- `sweep`: profile sweeps along traces for stiffeners and pillars.
- `sections_2d`: 2-D section profile outlines.
- `uv_tessellator`: UV-domain triangulation of trimmed surfaces.
- `holes`: hole contour resolution and placement on surfaces.
- `mesh`: triangle-mesh containers and utilities.
- `backend`: numpy backend helpers for tessellation.
