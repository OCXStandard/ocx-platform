# Changelog — ocx-render

## Unreleased

### Added

- Colour by plate thickness (new default, `--color-by thickness`):
  plates and brackets get one distinct colour per thickness from a
  20-colour palette (max-min separated in OKLab; grey when unknown),
  stiffeners and pillars one shade per section. Parts of one colour share
  a material: the VLCC hold model drops from 4314 to 46 materials and its
  GLB from 5.9 to 5.3 MB. `--color-by part` keeps per-part shades.
  `apply_color_scheme(meshes, scheme)` returns the legend, which
  `write_glb(..., legend=)` stores in the glTF scene `extras`.
- HTML viewer: thickness legend with plate counts; clicking an entry
  isolates that thickness (other parts turn translucent and unpickable).
- Parallel plate tessellation: `TessellationOptions.workers` (library
  default 1) and `--workers/-j` (CLI default: all cores). Panels are
  tessellated in worker processes, charted (multi-member) panels in
  chunks of 8 plates; results are merged in plate order, so output is
  byte-identical to a serial render. Worker log records are re-logged in
  the parent under its configuration. Diagnostics (`diag`) force serial
  mode; a failed task or broken pool falls back to serial rendering.
  VLCC hold model: render 13.3 s -> 6.8 s, CLI end-to-end 17.6 s -> ~11 s
  (parse/build, 3.5 s, stays serial).
- CLI `--panel/-p ID` (repeatable) renders only those panels' parts
  (`only_panels`); unknown ids are logged and ignored.
- Part metadata gains `thickness_mm` (plates, brackets) and `section`
  (stiffeners, pillars).
- Brackets are rendered as extruded solids using the plate thickness
  (`Offset` honoured, otherwise symmetric about the contour plane);
  brackets without a usable thickness render as flat sheets. Brackets
  were previously ignored by the renderer.
- HTML viewer: parts tree grouped by panel (rows built lazily on first
  open), a filter box matching name / id / guid / panel id / function
  type (first 500 hits), show/hide checkboxes on panels and parts, and
  click-to-select in the 3D view (drags still orbit; hidden parts are
  not pickable). Selecting from the 3D view reveals the part's tree row.
- `browser` pytest marker (deselected by default) for a headless-Chrome
  viewer test.

### Changed

- `TessellationOptions.only_panels` now restricts every part kind to the
  given panels: stiffeners are filtered too (previously always rendered),
  and parts not parented to a panel (e.g. vessel-level pillars, or plates
  that were skipped as "not parented to a panel") are left out silently.
  A single-panel `ocx-diagnose` render of the VLCC hold model drops from
  1.2 s / 4005 meshes to 0.4 s / 110 meshes.
- CutBy hole failures are reported in the new `RenderResult.hole_failures`
  instead of mixed into `RenderResult.skipped`, so `skipped` /
  `skipped_count` count only parts that did not render. The CLI summary
  and log line use these counts directly.
- Panel-level CutBy holes are resolved once per panel (previously
  re-sampled and re-placed for every plate of the panel), and their
  failures are reported once, keyed `<panel_id>/hole:<id>`, instead of
  once per plate under each plate id. Plate-level hole failures keep
  their `<plate_id>/hole:<id>` keys. `ocx-diagnose` includes the
  panel-keyed entries in the analysed panel's skip table.

### Fixed

- `render_model` now honours its "never raises per part" contract: an
  exception from any plate, stiffener, pillar, bracket, panel surface or
  LSCM chart is logged and recorded as `skipped[id] = "error: …"`
  (LSCM chart failures fall back to the best single member) instead of
  aborting the whole render.
- Plates that fail (triangulation failure or exception) now get a
  complete diagnostics record: `route`, `local_param`, `chart` and
  `seconds` are filled on every outcome, and the new `PlateDiag.failure`
  holds the skip reason (previously the record was left at its defaults
  for exactly the plates that most needed diagnosing).
- The CLI maps every failure to its documented exit code: an unexpected
  `render_model` failure exits 1 and any write/export error exits 3
  (previously only `OSError`; other errors printed a traceback).
- HTML viewer:
  - shows "needs network access" instead of a blank page when three.js
    cannot be loaded from the CDN; the README now states the dependency;
  - decodes the embedded GLB via a `data:` URL fetch instead of `atob`
    plus a per-byte copy (much faster and leaner on large models);
  - restores and disposes the highlight material on deselect (each
    selection previously leaked a material clone);
  - HTML-escapes the page title, and placeholder text in a file name is
    no longer substituted;
  - camera near/far planes follow the view distance instead of a fixed
    0.01–1e6 range that z-fought on ship-sized models.
- `--tolerance` must be greater than 0 (0 or negative is a usage error,
  exit 2, instead of an unusable render).
- `ocx_render.__version__` is read from the installed package metadata
  instead of a hard-coded string that could drift from `pyproject.toml`.
- `--destination` without a `.glb` suffix is written as GLB instead of
  failing with "unsupported export format".

- Slot contours (and other hole cut-outs crossing a plate edge) now cut
  the plate and remove material, rendering as open boundary notches —
  fixed upstream in `ocx-geometry` (`UvTessellator` boolean difference).
  Previously such slots left the plate uncut, and holes fully outside a
  plate could render as detached islands.
- Exported plate meshes no longer contain unwelded internal seams or
  T-junctions (drawn as skew lines by CAD viewers that show mesh free
  edges) — fixed upstream in `ocx-geometry` mesh trimming (tolerant weld
  + T-junction stitch in `MeshTrimmer`).
- Plates on multi-member panels no longer render as the whole panel side,
  as fragments, or empty — fixed upstream in `ocx-geometry` (mesh-trim
  side vote, uncut-face bridging, area guard, LSCM chart stitch fold and
  needle fan, holes that only touch a plate edge). On the tr05_tc18 ropax
  model this restores e.g. the superstructure sides (`nplcid8174`,
  `nplcid8568`), the side-shell plates along a patch seam (`nplcid2934`,
  `nplcid2938`, `nplcid4218`, `nplcid4222`), the plates beside the bow
  thrusters (`nplcid4252`, `nplcid2971`) and two DK8 deck plates. Of the
  558 trimmed ropax plates, 557 match their contour's vector area within
  1% and the last within 1.1%.
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
