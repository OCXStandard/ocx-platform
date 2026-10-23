# Changelog — ocx-render

## Unreleased

### Added

- Brackets are rendered as extruded solids using the plate thickness
  (`Offset` honoured, otherwise symmetric about the contour plane);
  brackets without a usable thickness render as flat sheets. Brackets
  were previously ignored by the renderer.

### Fixed

- Slot contours (and other hole cut-outs crossing a plate edge) now cut
  the plate and remove material, rendering as open boundary notches —
  fixed upstream in `ocx-geometry` (`UvTessellator` boolean difference).
  Previously such slots left the plate uncut, and holes fully outside a
  plate could render as detached islands.
- Exported plate meshes no longer contain unwelded internal seams or
  T-junctions (drawn as skew lines by CAD viewers that show mesh free
  edges) — fixed upstream in `ocx-geometry` mesh trimming (tolerant weld
  + T-junction stitch in `MeshTrimmer`).
- Plate-contour corners are sampled exactly (upstream `ocx-geometry`
  NURBS fix), closing corner gaps between adjacent plates.
- Pass per-plate contour loops (not a stacked point array) to
  `make_lscm_chart`, so plane trims on multi-member panels are bounded by
  the plate polygons — fixes inner-skin plates rendering with missing
  halves ("bowtie") or blown-up whole-chart geometry on knuckled panels.

## 0.1.0 — 2026-10-20

Initial release.

### Added

- `render_model(vessel, options) → RenderResult`: tessellates an IR model
  (plates, stiffeners, brackets, pillars) via `ocx-geometry`.
- GLB writer (`gltf_writer`): writes tessellated meshes to a `.glb` file.
- Self-contained HTML viewer (`html_viewer`) wrapping the GLB.
- `ocx-render` CLI: `ocx-render model.3docx [--destination out.glb]
  [--tolerance MM] [--no-html]` with exit codes 0 (rendered),
  1 (nothing renderable), 2 (cannot parse), 3 (cannot write output).
