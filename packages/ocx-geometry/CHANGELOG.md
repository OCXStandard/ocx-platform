# Changelog — ocx-geometry

## Unreleased

### Added

- `grid.grid_plane(axis, location)`: axis-aligned grid plane (positive
  axis normal).
- `intersect.offset_plane` and `intersect.intersect_surface_plane`:
  surface ∩ plane as 3D polylines inside a uv window — analytic for
  planes, marching squares (saddle resolved by the cell centre) for every
  other surface.
- `SurfaceParam.uv_domain()`: parameter domain (NURBS knot domain;
  extruded `(0, base length, -inf, inf)`; sphere `v ∈ [0, π]`; cone `v`
  bounded at the apex; `None` when no finite bounds are needed).

## 0.2.0 — 2026-11-08

### Removed

- The tessellation modules `lscm`, `mesh_trim`, `uv_tessellator`,
  `bracket`, `sweep`, `backend`, `mesh` and `diagnostics`, and the
  package-level exports `ITessellator`, `RenderResult`,
  `TessellationOptions` and `PartMesh`. Rendering is no longer part of
  the public platform. Dropped dependencies `trimesh`, `networkx` and
  `rtree`.
- `measure.ordered_junction_gaps` (declared-order junction gaps) —
  superseded by `chained_junction_gaps`.

### Added

- `measure.chained_junction_gaps`: order-invariant junction-gap measure —
  segments may attach at either end of the growing chain and may be
  reversed, so declared segment order carries no meaning.

### Fixed

- NURBS curve sampling (`curves._sample_nurbs`): the adaptive sampler now
  seeds its parameter set with every distinct interior knot, so C0 corners
  (full-multiplicity knots, as CAD exports use for plate-contour corners)
  are sampled exactly. Previously the uniform 33-point seed could straddle
  a corner and the sag refinement stop below tolerance, chamfering plate
  corners by up to ~tol (≈7 cm).

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
