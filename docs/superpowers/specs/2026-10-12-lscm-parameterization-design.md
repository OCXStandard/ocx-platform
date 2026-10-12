# LSCM Multi-Patch Surface Parameterization — Design

**Date:** 2026-10-12
**Status:** Approved
**Scope:** Replace `CompositeParam` in `ocx-geometry` with an LSCM-based chart.

## Problem

Outer-shell panels resolve to large multi-patch NURBS collections (TR04 hull:
108 members — 4 planes + NURBS patches in a 2-D grid). Each patch has its own
parameterization; plates span multiple patches, and their contours and seams
must be parameterized across all of them in one chart.

The current `CompositeParam` builds a developed (girth, spine) chart with
per-member affine fits. It was recently patched to handle 2-D grids, but
remains heuristic-laden (girth-sign choice, per-member affine fits requiring
≥3 contour samples, member-selection scoring) and is rebuilt per plate.

## Reference solution

GeniE's `LSCMParameterizedSurface.cpp`
(`GeniE.Source/src/components/Reparameterization/`, DNV Azure DevOps) solves
the same problem: facet all member surfaces into one welded triangle mesh with
per-triangle back-pointers `(source surface, local UV per corner)`, flatten it
with Least Squares Conformal Maps (libigl `igl::lscm`, two pinned boundary
vertices), and answer queries through two AABB trees — 3-D point → triangle →
barycentric → global UV, and global UV → triangle → barycentric → *source
surface local UV* → exact surface evaluation. Evaluation stays on the true
NURBS; the mesh only carries the correspondence.

Evaluation verdict: a direct fit. It removes every topology/heuristic
assumption that broke `CompositeParam`.

## Decisions

| Decision | Choice |
|---|---|
| Integration scope | **Replace** `CompositeParam` entirely |
| Solver dependency | **scipy** (own ~100-line LSCM; no libigl binding) |
| Chart granularity | **Per panel**, cached — not per plate |
| Evaluation fidelity | Exact: map back to source member NURBS |

## Architecture

New module `packages/ocx-geometry/src/ocx_geometry/lscm.py`:

- `LscmParam(SurfaceParam)` — implements `evaluate(uv)`, `inverse(pts)`,
  `normals(uv)`, `u_range`/`v_range`. `uv_tessellator` needs zero changes.
- `make_lscm(members: list[SurfaceParam], tol_m: float) -> LscmParam | None` —
  factory; `None` on any failure, logged at DEBUG.
- Private helpers: member faceting, tolerance welding, scipy LSCM solve,
  barycentric utilities.

Changes elsewhere:

- `surfaces.py`: delete `CompositeParam` and `make_composite` (~200 lines).
  `_member_fit` stays while `_best_param` uses it.
- `render.py` `_tessellate_plates`: per-panel lazy cache
  `dict[str, LscmParam | None]`; fallback chain per plate is
  `lscm_param or _best_param(candidates, contour)`.
  **Amendment (implementation):** `make_lscm(members, tol_m, hint_pts)` takes
  the panel's concatenated sampled plate contours as *hint points*: members
  without an intrinsic UV domain (planes, cylinders — only
  `NurbsSurfaceParam` carries knot-domain bounds) are bounded by the bbox of
  their on-surface hint points in member-local UV. `_tessellate_plates` runs
  two passes — contour sampling first, then chart build + tessellation — so
  the per-panel chart and cache remain sound.
- `ocx-geometry/pyproject.toml`: add `scipy>=1.14`.

Dependency direction unchanged: lscm.py uses numpy/scipy/trimesh/shapely —
all within ocx-geometry.

## Chart construction (build-time)

`make_lscm(members, tol_m)`:

1. **Facet members.** Sample each member param on its own UV grid; density per
   axis `n = clamp(ceil(span / chord_edge(curvature, tol_m)), 2, 48)` reusing
   the existing chord-tolerance logic; planes get 2×2. Members without an
   intrinsic domain use the hint-point bbox (see Architecture amendment);
   members with no on-surface hints or no 2-D extent are excluded from the
   mesh. T-junctions left by density mismatches along member seams are
   stitched by splitting the hosting boundary triangle at the junction
   vertex. Each cell → 2
   triangles. Every vertex keeps a back-pointer `(member_index, local_uv)`.
2. **Weld seams.** `scipy.spatial.cKDTree` pairs vertices within
   `weld_tol = max(1e-6, tol_m * 0.1)` m; union-find merges them. A merged
   vertex keeps a *list* of back-pointers (one per patch meeting at the seam).
   Drop degenerate triangles. Require a single connected component, else
   return `None`.
3. **LSCM solve.** Sparse system from cotangent Laplacian (`L_flat`) and
   vector-area matrix (`A`): minimize with `(L_flat − 2A)`; pin two far-apart
   boundary vertices (first boundary-loop vertex and the one half-way around
   the loop); `scipy.sparse.linalg.spsolve` on the reduced system. Reject
   non-finite results or collapsed UV (area ≈ 0).
4. **Metric rescale.** Scale UV by `sqrt(median(area3D_i / areaUV_i))` so
   chart units ≈ metres. Reject if per-triangle scale ratio max/min > 100
   (flattening too distorted).

Stored state: `V (n×3)`, `F (m×3)`, `V_uv (n×2)`, per-vertex back-pointer
lists, a `trimesh.Trimesh` for 3-D proximity, a shapely `STRtree` of UV
triangles, and a precomputed per-triangle source member.

## Query-time behaviour

- **`inverse(pts)`**: `trimesh.proximity.closest_point` → nearest triangle +
  point; barycentric in 3-D; interpolate corner `V_uv`. Slightly off-surface
  points land on the closest triangle — no clamping surprises.
- **`evaluate(uv)`** (exact): STRtree finds the containing (or nearest) UV
  triangle; barycentric in UV; pick the triangle's source member; interpolate
  the corners' *local* uv of that member; call `member.evaluate(local_uv)`.
  Points land exactly on the true NURBS, so curvature subdivision refines
  onto real geometry.
  - Triangle's member = the member present in all three corners' back-pointer
    lists (interior triangles have exactly one; seam vertices several).
    Precomputed at build time.
  - Queries outside the UV mesh snap to the nearest triangle edge.
- **`normals(uv)`**: same triangle → member → local uv route, then
  `member.normals`. Member orientation made consistent at build time by
  flipping members whose faceted normals disagree with mesh winding.
- **`u_range`/`v_range`**: bounding box of `V_uv`.
- All queries vectorised (batched STRtree query, single `closest_point`
  call). Build cost: one solve per panel (~20k vertices for the 108-patch
  shell — within `spsolve` range).

## Error handling & fallback

1. `make_lscm` fails (disconnected after weld, singular solve, scale ratio
   > 100, < 2 boundary vertices) → DEBUG log with reason → `_best_param` per
   plate (today's behaviour for flat plates).
2. `_best_param` finds no acceptable member → plate skipped with
   "triangulation failed", as today.
3. Per-query failures cannot occur by construction (closest-triangle always
   answers); non-finite member evaluations fall back to barycentric 3-D
   interpolation of `V` for those points (logged once).

`CompositeParam`, `make_composite`, and their unit tests (including
`TestComposite2DGrid`) are deleted — replaced, not kept alongside.

## Testing

Unit tests (new `tests/test_render_lscm.py`, synthetic geometry, fast):

1. Single plane (2×2 flat grid): roundtrip `inverse∘evaluate` ≈ identity,
   chart ≈ isometric (scale ≈ 1).
2. 2×2 NURBS patch grid (reuse `_grid_patch` helper): welding across 4
   patches, single chart, roundtrip on contour + interior points < 1e-6 m.
   Replaces `TestComposite2DGrid` coverage.
3. Quarter-cylinder from 2 patches: curved development; exact evaluation
   stays on the analytic cylinder (< 1e-9 m).
4. Seam member selection: evaluating at a seam point returns a finite exact
   position (no wrong-member metre-scale errors).
5. Failure paths: disconnected members (gap > weld tol) → `None`; degenerate
   (collinear) input → `None`.

Integration (existing, unchanged assertions):
`test_tr04_tc14a_outer_shell_renders_all_plates` — 24/24 plates, 0 skipped,
every contour point < 0.1 m from mesh vertices. Run with `-m integration`.

Manual: `ocx-render models\TR04\tr04_tc14a_outer_shell.3docx` and the full
`tr04_tc14a_nast.3docx`; visual HTML check. The two previously-coarse plates
(`nplcid925`, `nplcid935`) may also improve as chart distortion shrinks.

## Success criteria

- Full test suite passes with `CompositeParam` removed.
- New LSCM unit tests pass.
- TR04 outer-shell integration test passes.
- No plate regressions on the full nast model (same or fewer skips).
- ruff clean.
