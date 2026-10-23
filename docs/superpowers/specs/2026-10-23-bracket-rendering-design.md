# Bracket rendering — design

**Date:** 2026-10-23
**Status:** approved

## Problem

Brackets are the only steel part the renderer ignores: `render_model`
tessellates plates, stiffeners and pillars, but `IrBracket` carries no
geometry and `ocx-render` has no bracket path. Models such as
`TR02_TC08_*` (88–136 brackets each) render without them.

Survey of all repo models containing brackets (TR02/TR04 TC08, TR05
TC09): every bracket has an `OuterContour`; most carry their own
`UnboundedGeometry/Plane3D` (ai3dx and mbrh exports do not); none has
`CutBy` holes; some exports carry an `Offset` element.

## Decisions

- Brackets render as **extruded solids** using the plate thickness.
- Thickness placement: **honour `Offset` when present, otherwise
  symmetric** (half thickness each side of the contour plane).
- Missing thickness → render as a **flat sheet** (never lose the part).
- Planar-only pipeline (Approach A). No chart/LSCM/trim machinery; no
  hole support (no model needs it — YAGNI).

## 1. IR & builder (`ocx-model-core`)

`IrBracket` gains optional fields, defaulting to `None`:

| field | source |
|---|---|
| `outer_contour: IrCurve3D \| None` | `Bracket/OuterContour` |
| `plane: IrPlane3D \| None` | `Bracket/UnboundedGeometry/Plane3D` (plane only; other surface types ignored) |
| `offset: Quantity \| None` | `Bracket/Offset` |

`OcxV3Builder._build_bracket` populates them via the existing
`_build_curve` / `_build_surface` / `_qty` helpers with `getattr`-safe
access, mirroring `_build_plate`. OCX 2.8.6 inherits through
`Ocx286Builder`'s normalisation pass unchanged.

## 2. Geometry kernel (`ocx-geometry/src/ocx_geometry/bracket.py`)

```python
def tessellate_bracket(contour_pts: np.ndarray,
                       plane: tuple[np.ndarray, np.ndarray] | None,
                       thickness_m: float | None,
                       offset_m: float | None,
                       tol: float) -> tuple[V, F, N] | None
```

1. **Plane**: use the given (point, normal) when available; otherwise
   best-fit via SVD on centred contour points. Return `None` when the
   contour deviates from the plane by more than a tolerance-scaled
   bound (caller records the skip reason).
2. **Projection + triangulation**: project the contour into the plane's
   2-D frame and triangulate the single outer ring with
   `mapbox_earcut` (already a dependency).
3. **Solid** (thickness known): prism with bottom cap at
   `base = offset_m` (when given) else `-thickness_m / 2` along the
   plane normal, top cap at `base + thickness_m`, and side quads
   (two triangles each) along the contour. Flat per-face normals:
   caps get ±n̂, walls get outward edge normals.
4. **Sheet** (no thickness): single cap at the contour plane.
5. Degenerate contours (< 3 distinct points or ~zero area) → `None`.

Contour sampling reuses `sample_curve`/`sample_contour` from
`curves.py`, so NURBS corner-exactness comes for free.

## 3. Renderer (`ocx-render/render.py`)

`_tessellate_brackets(vessel, length, options, result)` runs after
plates, mirroring the `_sweep_part` loop:

- resolve contour points via `sample_contour`, thickness and offset to
  metres via `LengthResolver`;
- call `tessellate_bracket`; emit `PartMesh` named
  `B:<name or id>/<panel name>`;
- honour `options.only_panels` (via the bracket's parent panel;
  vessel-parented brackets render only when `only_panels` is `None`).

## Error handling

Never raises per-part. Failure paths record
`result.skipped[bracket.id] = reason`:

- "no outer contour"
- "contour not planar"
- "degenerate contour"

Missing thickness is not a failure — the bracket renders as a sheet.

## Testing (TDD)

`tests/test_render_brackets.py`:

- rectangular contour + plane + thickness → closed prism: watertight
  (every edge shared by exactly two faces), volume ≈ area × t;
- `Offset` honoured vs symmetric placement;
- sheet fallback when thickness is missing;
- best-fit plane when the IR plane is absent;
- non-planar contour → `None`;
- integration: `render_model` over inline-stub IR with brackets
  produces bracket parts (conftest stub pattern).

Manual verification (not a committed test): render
`models/TR02/TR02_TC08_cadhu.3docx` and confirm bracket count and
visual placement.

## Changelogs

- `ocx-geometry`: Added — planar bracket tessellation
  (`tessellate_bracket`).
- `ocx-render`: Added — brackets rendered as extruded solids (sheet
  fallback without thickness).
