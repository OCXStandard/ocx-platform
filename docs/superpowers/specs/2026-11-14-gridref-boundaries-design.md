# GridRef panel boundaries — design

**Status:** approved 2026-11-14
**Packages:** ocx-geometry, ocx-rules
**Rule affected:** OCX-TOP-001 (Panel LimitedBy closes)

## Problem

OCX-TOP-001 resolves each `LimitedBy` ref to an explicit 3D curve
(FreeEdgeCurve3D, SeamRef → seam trace, StiffenerRef → stiffener trace).
A `GridRef` names a reference *plane*, not a curve, so any panel with a
GridRef boundary is reported as *unchecked* ("boundary ref(s) without
explicit curve (GridRef×N)") and gets no closure check.

On the iter0 model this affects 107 of 127 panels:

- 386 GridRefs; every one resolves to an `IrRefPlane` that has only a
  `location` (e.g. `X173.4`) and no explicit `reference_plane` geometry;
  none carries `ContourBounds`; one carries an `Offset`.
- 82 panels are bounded only by GridRefs, 25 by GridRefs plus
  FreeEdgeCurve3D.
- 105 panels lie on a grid plane themselves (`UnboundedGeometry/GridRef`);
  `GeometryContext.panel_surface` returns `None` for them because the ref
  plane has no explicit geometry.
- LimitedBy order is **not** cyclic: refs come in parallel pairs
  (`zzxx`, `xxyy`), so a boundary cannot be trimmed against "the next ref".
- All 107 panels have an `OuterContour`.

## Goal

Every GridRef boundary is resolved geometrically by intersecting the
panel's support surface with the (optionally offset) grid plane, and
OCX-TOP-001 checks closure of panels with GridRef boundaries instead of
reporting them unchecked.

Out of scope: switching ocx-render to the new ocx-geometry helpers
(follow-up); other curveless ref types (PanelRef, SurfaceRef,
EdgeCurveRef, EdgeReinforcementRef) remain unchecked as today.

## Schema facts

- `GridRef_T` extends `BoundedRef_T` with an optional `Offset`
  (`Quantity_T`); it has no `OffsetDirection`.
- `Offset`: "A positive offset value is in the direction of the surface
  normal vector."
- A grid ref plane belongs to the X, Y or Z ref-plane list of a
  coordinate system; its synthesized plane has the positive axis as
  normal (same convention as ocx-render's `_plane_from_ref_plane`).

## Section 1 — ocx-geometry

### `ocx_geometry/grid.py` (new)

- `grid_plane(axis: str, location_m: float) -> tuple[np.ndarray, np.ndarray]`
  returns `(point, unit_normal)` for `axis in {"x", "y", "z"}`; the
  normal is the positive axis, the point is `location_m` along it.
  Raises `ValueError` for any other axis.

### `ocx_geometry/intersect.py` (new)

IR-independent, all values in metres.

- `offset_plane(point, normal, offset_m) -> tuple[np.ndarray, np.ndarray]`
  normalizes `normal` and returns `(point + offset_m * n, n)`.
- `intersect_surface_plane(param: SurfaceParam, point, normal,
  uv_window: tuple[float, float, float, float], tol_m: float)
  -> list[np.ndarray]` returns the intersection as 3D polylines
  (each `(N, 3)`, `N >= 2`) restricted to
  `uv_window = (u0, u1, v0, v1)`.
  - `PlaneParam`: analytic. Direction `n1 × n2`; parallel planes
    (`|n1 × n2| < 1e-9`) return `[]`. The infinite line is mapped to uv
    and clipped to the window rectangle (Liang–Barsky); a line that
    misses the window returns `[]`. Result is one 2-point polyline.
  - Every other `SurfaceParam`: numerical. Evaluate the signed distance
    `d(u, v) = n · (S(u, v) − p)` on a regular uv grid over the window;
    grid step from `param.max_edge_m(tol_m)` converted with
    `param.uv_scale()` (fallback: 200 cells per axis), clamped to 8…1000
    cells per axis. A built-in marching-squares routine extracts the
    zero contour (linear interpolation on cell edges; the ambiguous
    saddle case is resolved by the cell-centre value), segments are
    linked into polylines, and points are evaluated back to 3D.
    No new dependency.

## Section 2 — GeometryContext (ocx-rules)

1. `panel_surface(panel)`: when `UnboundedGeometry/GridRef` names a ref
   plane without `reference_plane`, synthesize an `IrPlane3D` from the
   ref plane's `location` and its axis (looked up in
   `vessel.coordinate_systems`) via `grid_plane`. Unknown axis or no
   location → `None` (unchanged behaviour).
2. `grid_ref_plane(ref: IrLimitedByRef) -> tuple[point, normal] | None`:
   resolve `ref.local_ref` in `vessel.ref_planes`; use the explicit
   `reference_plane` (point + normal, converted to metres) or the
   synthesized grid plane; then apply `ref.offset` (converted with
   `to_si`) with `offset_plane`. Missing ref plane or unknown axis →
   `None`.
3. `panel_uv_window(panel, param) -> tuple[u0, u1, v0, v1] | None`: uv
   bounding box (via `param.inverse`) of the panel's OuterContour
   samples, `point_on_surface` and all explicit boundary-curve samples,
   enlarged on each side by 100 % of its extent plus 1 m (converted to
   uv with `uv_scale`), then clamped to `param.uv_domain()`. If none of
   these exist, fall back to a finite `param.uv_domain()`; otherwise
   `None`. `SurfaceParam.uv_domain()` is a new method (default `None`;
   NURBS: knot domain; extruded: `(0, base length, -inf, inf)`), needed
   because `bounds()` is a 3D box and NURBS/extruded `evaluate` clamp uv.

## Section 3 — OCX-TOP-001

Panels **without** any GridRef keep the current code path
(`_classified_boundary_samples` + `chain_polylines`), unchanged.

Panels **with** at least one GridRef use the arrangement path,
implemented in a new module `checks/limited_by_region.py` and called
from `panel_limited_by_closed`:

1. Classify the LimitedBy refs first (dangling / no curve / unsampleable,
   with unresolvable GridRefs counted as dangling); any reason fragment →
   unchecked. No OuterContour → unchecked "cannot determine panel
   extent" (the uv window would be too small to hold the GridRef cuts).
2. `param = surface_param(panel_surface(panel))`; `None` → unchecked
   "no buildable panel surface". Then `window = panel_uv_window(panel,
   param)`; `None` → unchecked "cannot determine panel extent".
3. Resolve each LimitedBy ref to 3D polylines:
   - GridRef → `grid_ref_plane` then `intersect_surface_plane`; a
     GridRef whose ref plane cannot be resolved counts as dangling
     (reason fragment "dangling boundary ref(s) (GridRef×n)"). Each plane
     is cut across the whole window, so a non-convex panel's own planes
     split it into several faces (handled in step 6).
   - FreeEdgeCurve3D / SeamRef / StiffenerRef → sampled curve as today;
     each open end is extended by `tolerance_mm` along its end tangent.
   - Dangling SeamRef/StiffenerRef, other curveless types, unsampleable
     curves → same reason fragments as today.
   If any ref yields a reason fragment, the whole panel is reported
   unchecked with the joined reasons and skipped (same as today).
4. Map all polylines to uv with `param.inverse`. Add the window edges
   that coincide with a finite `param.uv_domain()` bound (real surface
   edges, e.g. the ends of an extruded base curve or NURBS patch edges;
   edges that only come from window growth are not added): beyond the
   domain the plane function is constant, so a plane lying on such an
   edge yields no marching-squares cut. `unary_union` the linestrings
   and `polygonize`.
5. `contour` = the first OuterContour mapped to uv; it must be a valid
   polygon with area > 0, else unchecked "unusable OuterContour".
6. Panel region `U` = union of the polygonized faces whose
   `representative_point()` lies inside `contour`. Findings (rule
   severity, error):
   - `U` empty, or `area(U △ contour) > 1 % · area(contour)` (absorbs
     sampling/marching discretisation) → "Panel boundary is not closed:
     LimitedBy does not enclose the panel".
   - Otherwise the boundary rings of `U` (exteriors and interiors) are
     evaluated to 3D. A GridRef boundary bounds the panel when the
     analytic plane distance `min |n·(x − p)|` over those ring points is
     ≤ `tolerance_mm` (so planes on surface edges, which have no cut,
     still count); an explicit curve bounds it when its minimum 3D
     distance to the ring points is ≤ `tolerance_mm`. Every other
     boundary → "LimitedBy boundary <ref_type> <local_ref> does not bound
     the panel" (one finding per boundary).

## Error handling

- Exceptions inside the arrangement path for one panel are caught and
  reported as unchecked "boundary evaluation failed: <exc>", consistent
  with other geometry checks; the rule continues with the next panel.
- No change to rule status semantics: unchecked never changes
  PASSED/FAILED.

## Testing (TDD)

ocx-geometry (`tests/test_geometry_intersect.py`, known answers):
plane∩plane gives the expected line; parallel planes → `[]`; offset
shifts the line by the offset along the normal; cylinder cut by a plane
through its axis → 2 lines; cylinder cut by a plane perpendicular to its
axis → one closed polyline with radius within `tol_m`; result clipped to
the window; `grid_plane` for x/y/z and invalid axis.

ocx-rules (`tests/test_rules_checks_topology.py` or a new
`tests/test_rules_limited_by_region.py`):
rectangle of 4 grid planes on a grid-plane panel passes; 3 grid planes →
"not closed"; a 5th distant parallel plane → stray-boundary finding; an
offset GridRef that moves an edge away from a FreeEdgeCurve3D end →
finding, without offset → pass; GridRef + FreeEdgeCurve3D mix closes;
curved (cylinder) panel bounded by 4 planes closes; location-only ref
plane panel surface is synthesized (`panel_surface` test).

## Success criteria

- On iter0: TOP-001 has 0 unchecked entries mentioning GridRef; the
  20 existing findings remain; any new findings are inspected and
  explained before merge.
- Full suite (`uv run pytest -q`) and `uv run ruff check packages tests`
  pass.
- `packages/ocx-rules/CHANGELOG.md` and `packages/ocx-geometry/CHANGELOG.md`
  updated.
