# Tessellation Cutout (CutBy) Support — Design Spec

**Date:** 2026-10-12
**Status:** Approved
**Feature:** Port the tessellated renderer into the uv-workspace layout and add support for OCX `CutBy` openings (catalogue hole shapes placed by transformation) so plates render with their holes cut.

## Context

- The renderer currently lives only on `feature/tessellated-renderer` (pre-workspace-split flat layout, `ocx_model_validator/render/`). The workspace-split layout (`packages/ocx-model-core`, `packages/ocx-geometry`, `packages/ocx-model-validator`) has no render code.
- The UV tessellator already supports holes end-to-end (`hole_pts` → UV inversion → periodic-u shift → shapely clean → earcut-with-holes), but is only fed from `IrPlate.cut_by_contours`, which the builder fills solely from inline `PlateCutBy` contours.
- Reference model `models/TR04/tr04_tc13_nast.3docx` (OCX 3.2.0rc8, NAPA Steel) attaches `CutBy` at **panel** level. Each `CutBy` child is a `Hole2DContour`: a `HoleRef` into the vessel `HoleShapeCatalogue` plus a placement `Transformation` (`Origin`, `PrimaryAxis`, `SecondaryAxis`). The catalogue contains one contour-based `Hole2D` and parametric variants: `SymmetricalHole`, `ParametricCircle`, `RectangularHole` (with and without fillet), `RectangularMickeyMouseEars`, `Ellipse`. The model defines 9 openings on one panel (curved surface + flat region).

### Gaps closed by this design

1. `IrHole2D.parametric` stores only the variant name — no dimensions.
2. No IR representation of `Hole2DContour` (hole ref + transformation); panel/plate `CutBy` is not parsed.
3. The renderer cannot resolve catalogue holes, generate parametric 2D profiles, place them in 3D, or project them onto plate UV.

## Decisions

| Decision | Choice |
|---|---|
| Base branch | Port the renderer into the workspace-split layout first, then add cutouts there |
| Package split | Tessellation math → `ocx-geometry`; writers + orchestration → new `packages/ocx-render`; **separate CLI entrypoint** `ocx-render` (no `validator render` subcommand) |
| Hole-shape coverage | All catalogue variants, including `SuperElliptical` (not in the test model) |
| Cutting approach | **A — faithful IR + resolve-and-project in the renderer.** IR keeps ref + transformation; the renderer resolves shapes, places them in 3D, and inverse-maps onto surface UV, feeding the existing hole pipeline. Rejected: baking 3D contours in the builder (leaks evaluation into the parser, loses IR fidelity); mesh booleans (plates are open shells; fragile/heavy) |

## Section 1 — Port & package layout

Content port (not a git merge — the branch predates the split):

**`packages/ocx-geometry/src/ocx_geometry/`** gains (from branch `ocx_model_validator/render/`):
`surfaces.py`, `curves.py`, `sweep.py`, `sections_2d.py`, `uv_tessellator.py`, `backend.py` (`ITessellator`, `TessellationOptions`), `mesh.py` (`PartMesh`); `length.py` folded into the existing `measure.py`.
New dependencies: `geomdl`, `shapely`, `mapbox-earcut`, `numpy` (added with `uv add`).

**New `packages/ocx-render/src/ocx_render/`** (depends on `ocx-model-core` + `ocx-geometry`; dependency `trimesh`):
- `render.py` — `render_model(vessel, options) → RenderResult` orchestration (branch `render/__init__.py`)
- `gltf_writer.py`, `html_viewer.py`
- `cli.py` — entrypoint `ocx-render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]`; exit codes 0 = rendered (skips allowed), 1 = nothing renderable, 2 = cannot parse/build.

Branch `test_render_*.py` tests move to the shared root `tests/` with imports updated. Root `pyproject.toml` workspace members updated; `uv sync --dev`.

## Section 2 — IR & builder changes (ocx-model-core)

**New frozen IR types** (`model/ir/`):
- `IrTransformation` — `origin: IrPoint3D`, `primary_axis: IrVector3D`, `secondary_axis: IrVector3D`.
- `IrHole2DContour` — `id`, `name`, `guidref`, `hole_ref: Ref`, `transformation: IrTransformation | None`.
- `IrParametricHole` — replaces the `{"variant": ...}` dict on `IrHole2D.parametric`: `variant: str` plus optional `Quantity` fields `height`, `width`, `radius`, `fillet_radius`, `diameter`, `major_diameter`, `minor_diameter`, `displacement`. Quantities keep raw OCX unit-id strings per IR convention.

**New IR fields:** `IrPanel.cut_by_holes: list[IrHole2DContour]` and `IrPlate.cut_by_holes` (the schema allows `CutBy` on both; the test model uses panel level). Existing `IrPlate.cut_by_contours` (inline 3D contours) is unchanged.

**Builder (`OcxV3Builder`):**
- Parse `getattr(raw, "cut_by", None)` on panels and plates → `Hole2DContour` children → `hole_ref` + `transformation`, using existing `_ref` / `_pt` / `_vec` helpers with `getattr`-safe access. A `Hole2DContour` carrying an inline contour instead of a ref falls back into the existing `cut_by_contours` list.
- Extend `_build_hole_catalogue` to read each parametric variant's dimensions via `_qty` into `IrParametricHole`.

## Section 3 — Hole resolution & cutting (ocx-geometry / ocx-render)

**New `ocx_geometry/holes.py`:**
- `parametric_profile(hole: IrParametricHole, tol) -> np.ndarray (N,2)` — closed 2D polygon per variant: circle and ellipse polygonized by sagitta tolerance; rectangular with optional fillet arcs; symmetrical hole as a stadium (rectangle + semicircular ends); super-elliptical; mickey-mouse ears (rectangle + corner lobes). Exact dimension semantics are verified against the OCX schema annotations in the xsdata stubs during implementation. Shapes are centred on the local origin.
- `contour_profile(contour: IrCurve3D, tol) -> np.ndarray (N,2)` — sample the 2D composite curve (reusing `curves.py` sampling), taking x, y.
- `place_hole(profile_2d, transformation: IrTransformation) -> np.ndarray (N,3)` — `origin + x·P̂ + y·Ŝ` with normalized axes. All quantities converted to metres via the existing `UnitConverter`, consistent with current contour sampling.

**In `render_model` (ocx-render):** per plate, the hole polylines are:
1. inline `plate.cut_by_contours`, sampled as today, plus
2. resolved `plate.cut_by_holes` and the parent `panel.cut_by_holes`: `hole_ref` → `vessel.hole_shape_catalogue.holes` → profile → placed 3D polyline.

These feed the **existing** `hole_pts` pipeline unchanged: inverse-map to UV, periodic-u shift, shapely clean (holes outside or straddling the plate region are clipped or dropped automatically), earcut. Panel-level holes are offered to every plate of the panel; the shapely intersection decides which plates are actually cut.

**Skip-and-log (never abort a render):** unresolvable `HoleRef`, unknown parametric variant, missing/degenerate transformation axes, non-finite UV after inversion — each logged via `loguru` with the hole id and counted in the render summary.

## Section 4 — Testing & success criteria

**Unit tests:**
- `holes.py`: every parametric generator returns a closed, non-self-intersecting polygon with the expected bounding box (e.g. circle Ø0.5 → bbox 0.5×0.5); `place_hole` maps the unit square onto an arbitrary frame correctly.
- Builder: inline stub classes (per `test_builders.py` convention) for `CutBy`/`Hole2DContour`/`Transformation` and catalogue variants with dimensions → assert `IrParametricHole` quantities and `cut_by_holes` refs/transforms.
- Port regression: all existing `test_render_*` tests pass with updated module paths.

**Integration test** (skipped when the model file is absent): render `models/TR04/tr04_tc13_nast.3docx` → build succeeds, plate meshes produced, zero hole-skip entries, and the mesh surface area is measurably smaller than the same render with holes ignored.

**Success criteria:**
1. `uv run pytest` green from the repo root.
2. `ocx-render models/TR04/tr04_tc13_nast.3docx` writes GLB + HTML; the viewer shows the panel with all 9 openings.
