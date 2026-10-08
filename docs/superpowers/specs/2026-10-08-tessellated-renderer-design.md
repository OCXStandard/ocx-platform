# Tessellated 3D Renderer — Design Spec

**Date:** 2026-10-08
**Status:** Approved
**Feature:** New advanced renderer that tessellates OCX geometry (via the schema-neutral IR) into a triangle mesh and exports it as GLB + a self-contained HTML viewer, displayable in any web browser.

## Goals

- Tessellate trimmed panel/plate surfaces and swept stiffener/pillar cross-sections from an `IrVessel`.
- Export glTF 2.0 binary (GLB) with one named node per part, per-part color, and part metadata in node `extras`.
- Write a self-contained HTML viewer (three.js) next to the GLB so a double-click displays the model.
- Pure-Python tessellation backend by default; backend isolated behind an interface so an OpenCASCADE (`cadquery-ocp`) backend can be added later without touching the writer or CLI.

## Non-goals (v1)

- Plate thickness as solid extrusion (plates render as single-sided shells with double-sided material).
- Brackets, reference planes, compartments, holes/penetration solids beyond `cut_by_contours`.
- Draco compression, texture mapping, server-based viewer.
- OCCT backend implementation (interface only).

## Decisions and rationale

| Decision | Choice | Rationale |
|---|---|---|
| Target viewer | Web browser (three.js) | User requirement |
| Output format | glTF 2.0 / GLB | Only format with node hierarchy + names, per-node `extras` metadata, per-material color, compact single binary, and ubiquitous viewers (three.js, Babylon, Windows 3D Viewer, Blender) |
| Tessellation backend | Pure-Python UV-domain tessellation behind an `ITessellator` interface | "Prefer light" dependency stance; `pythonocc-core` is not pip/uv-installable; `cadquery-ocp` adds ~150 MB (wheel + forced vtk) — kept as a possible later backend |
| 2D triangulator | `mapbox_earcut` (+ `shapely` cleanup) | Tiny ISC wheel; `triangle` (Shewchuk) rejected: license restricts commercial redistribution |
| NURBS evaluation | `geomdl` (NURBS-Python) | Pure Python, MIT, maps 1:1 onto `IrNurbsSurface`/`IrNurbs3D` fields |
| GLB writer | `trimesh.Scene` | Mature, MIT, handles node hierarchy, materials, extras |
| Scope v1 | Panels/plates (trimmed shells) + stiffeners/pillars (swept sections) | User choice |
| Delivery | CLI writes `.glb` + self-contained `.html` | User choice |

New runtime dependencies (all small, permissive licenses, Windows/Linux wheels): `geomdl`, `shapely`, `mapbox-earcut`, `trimesh`, `numpy`. Added with `uv add`.

## Architecture

New package `ocx_model_validator/render/`:

```
render/
├── __init__.py          # public API: render_model(vessel, options) → RenderResult
├── backend.py           # ITessellator ABC + TessellationOptions (tolerance, density)
├── mesh.py              # PartMesh dataclass: vertices, triangles, normals, part id/name/kind/color
├── uv_tessellator.py    # pure-Python ITessellator impl (default backend)
├── surfaces.py          # per-surface parametrization: eval(u,v), inverse(point)→(u,v), normals
├── curves.py            # curve sampling/stitching: IrCurve3D → 3D polyline (adaptive)
├── sweep.py             # stiffener/pillar section sweep along trace (IrInclination frames)
├── sections_2d.py       # IrSection → 2D profile polygon (flat bar, L, T, bulb, tube…)
├── gltf_writer.py       # list[PartMesh] → GLB via trimesh.Scene (names, colors, extras)
└── html_viewer.py       # GLB → self-contained viewer.html (three.js, CDN-pinned)
```

Data flow:

```
IrVessel → resolve panel surface + contours
        → ITessellator.tessellate_panel/plate / sweep stiffener
        → PartMesh*
        → gltf_writer → model.glb
        → html_viewer → model.html (GLB embedded base64, fully self-contained)
```

### Key types

- `TessellationOptions`: linear deflection tolerance (model units, default 50 mm), derived angular/curvature sampling parameters.
- `PartMesh` (frozen dataclass): `vertices: np.ndarray (N,3)` in metres, `triangles: np.ndarray (M,3)`, `normals: np.ndarray (N,3)`, `part_id`, `name`, `kind` (plate/stiffener/pillar/panel), `color: (r,g,b)`, `extras: dict`.
- `ITessellator` ABC: `tessellate_plate(...)`, `tessellate_panel(...)`, returning `PartMesh | None`. Backends swappable; future OCCT backend slots in here.
- `RenderResult`: list of `PartMesh`, skip log (part id → reason), counts.

### CLI

New subcommand reusing the existing parse→build pipeline:

```
validator render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]
```

Exit codes: 0 = rendered (skips allowed), 1 = nothing renderable, 2 = cannot parse/build.

## Panel/plate tessellation pipeline

Per part:

1. **Resolve surface** — from the parent panel's `IrUnboundedGeometry`: inline `IrSurface3D`, `surface_ref` (lookup in `IrVessel` surface collections), or `grid_ref` (ref-plane → `IrPlane3D`).
2. **Sample boundary** — flatten `outer_contour` (`IrCompositeCurve3D` → stitched segments; arcs/circles/ellipses sampled by sagitta tolerance; NURBS via `geomdl`) into a closed 3D polyline. Segment gaps smaller than tolerance are snapped shut; larger gaps → part skipped with logged warning.
3. **Map to UV** — closed-form inverse for plane/cylinder/cone/sphere/extruded surfaces; Newton point-inversion (with `geomdl` derivatives) for NURBS. Periodic-u seam handling (cylinder/cone, closed NURBS): unwrap angles continuously along the polyline instead of wrapping to [0, 2π). Sphere poles: clamp parameters and filter degenerate triangles.
4. **Clean & triangulate in UV** — `shapely` validates/repairs the polygon (dedupe, orientation, self-touch); `cut_by_contours` holes subtracted; `mapbox_earcut` triangulates. Irreparable polygon → skip + warn. For curved surfaces, interior Steiner points from a curvature-sized UV grid are overlaid before earcut so triangles do not cut across curvature.
5. **Lift to 3D** — evaluate surface at each UV vertex; normals from analytic partials (closed-form surfaces) or `geomdl` derivatives. Plates render as single-sided shells; glTF material is double-sided.

Density control: the single `--tolerance` (linear deflection) drives both boundary sampling and interior refinement.

## Stiffener/pillar sweep

1. **Profile** — `sections_2d.py` turns the resolved section (`section_ref` → vessel section catalogue) into a closed 2D polygon in (web, flange) coordinates: flat bar, L/angle, T, bulb flat (parametric polygon approximation), tube (polygonized circle), U, I. Unknown type → flat-bar proxy sized from section height/width, logged.
2. **Trace** — sampled to a 3D polyline with the same sagitta tolerance.
3. **Frames** — orthonormal frame at each sample: web direction interpolated from `IrInclination` hints when present; else parent panel surface normal at the trace point; else rotation-minimizing frame. Never a naive Frenet frame (flips at inflections/straights).
4. **Sweep** — place profile at each frame, connect consecutive rings into triangles, cap both ends → one watertight `PartMesh` per stiffener/pillar. Pillars use the identical path.

## GLB output

- `trimesh.Scene`, one named node per part (`name` = part name or id), grouped: `Panels/<panel>` with its plates and stiffeners as children; `Pillars` as a sibling group.
- Node `extras`: `{id, guid, kind, functionType}`.
- Colors deterministic per kind — plates steel-grey, stiffeners blue, pillars green, panels-without-plates tan — with per-part hue jitter. Flat PBR (metallic 0.1, roughness 0.8), double-sided.
- All vertices converted to metres via the existing `UnitConverter` (glTF mandates metres).

## HTML viewer

`html_viewer.py` writes `<stem>.html` next to the GLB:

- Single self-contained file: three.js + GLTFLoader + OrbitControls from a pinned CDN version; the GLB embedded as base64 so `file://` opening always works (the standalone `.glb` is still written as its own artifact).
- Part-tree sidebar generated from node names; click-to-highlight with the node's `extras` displayed.

## Error handling

- Per-part failures never abort the render: skip, log via `loguru`, count in a render summary (`N parts rendered, M skipped: reasons`).
- Hard failures only for unreadable/unbuildable models (existing exception hierarchy).
- Panels with no resolvable geometry (common in minimal models) are skipped and counted.

## Testing

Unit tests per module:

- `surfaces`: eval∘inverse round-trips per surface type, including a seam-crossing cylinder contour and sphere-pole cases.
- `curves`: composite-curve stitching with small gaps; arc/NURBS sampling respects sagitta tolerance.
- `uv_tessellator`: earcut on L-shaped and holed UV polygons; degenerate-triangle filtering.
- `sweep`: frame continuity along curved traces (no flips); watertight ring/cap topology.
- `sections_2d`: closed polygons for every section type; flat-bar fallback.
- `gltf_writer`/integration: build a GLB from existing `tests/data` stubs (plus a `models/` 3docx when present); reload with `trimesh` and assert node names exist, triangle counts > 0, no NaN vertices.

## Risks

- **NURBS point-inversion convergence** near degenerate parametrizations — mitigated by seeded Newton with bisection fallback and per-part skip on failure; the `ITessellator` interface keeps an OCCT backend as an escape hatch.
- **Messy real-world contours** (gaps, overlaps from authoring tools) — shapely repair + tolerance snapping; otherwise skip-and-report rather than fail.
- **Large models / file size** — flat per-kind materials and binary GLB keep size reasonable; Draco compression is a possible later addition.
