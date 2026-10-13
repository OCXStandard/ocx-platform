# Evaluation: `triangle` (Shewchuk CDT) for patched-surface meshing

**Date:** 2026-10-13
**Status:** Evaluation only — no implementation planned (explicit user decision)
**Library:** [drufat/triangle](https://github.com/drufat/triangle) — Python bindings
for Jonathan Shewchuk's *Triangle* (constrained Delaunay triangulation, quality
mesh refinement)

## Question

Would replacing our current 2-D meshers with Triangle's constrained Delaunay
triangulation (CDT) improve mesh quality or reduce failures at either of the two
meshing sites?

1. **Render site** — `ocx_geometry/uv_tessellator.py`: per-plate UV polygon →
   `mapbox_earcut` fan → `trimesh.remesh.subdivide_to_size` metric refinement.
2. **LSCM chart site** — `ocx_geometry/lscm.py::_facet_trimmed`: concave hull of
   member hint points → regular grid cells intersected via shapely → convex-piece
   fan triangulation; downstream weld/stitch/zip joins members into one chart.

## Method

Hands-on spike with real geometry: the 25-plate HULL panel of
`models/TR05/tr05_tc09_nast_hull.3docx` (3 planar + 4 NURBS bilge members, the
model used to debug the curved-shell rendering fixes in `870d372`). Throwaway
scripts ran via `uv run --python 3.12 --with triangle`; nothing merged.

- **Experiment 1 (render site):** for each plate, triangulate its UV contour
  polygon with (a) the current earcut + metric-subdivision pipeline and (b)
  `triangle.triangulate(..., "pq28a<area>")` in metric-scaled UV. Compare 3-D
  triangle quality (min angle, aspect ratio), degenerate-triangle counts,
  triangle counts, and chordal deviation sampled at edge midpoints.
- **Experiment 2 (LSCM site):** monkeypatch `_facet_trimmed` so trimmed (planar)
  members are meshed by CDT of the concave-hull outline instead of grid + fan,
  rebuild the chart, and re-run `param_for` over all 25 plates. Three flag
  variants: `pq28a` (quality + area), `pa` (area only), `pq28aYY` (no boundary
  Steiner points).

## Results

### Experiment 1 — render site: clear quality win

Aggregate over all 25 hull plates:

| Metric                       | earcut + subdivide | triangle `pq28a` |
| ---------------------------- | ------------------ | ---------------- |
| min angle, 5th pct / median  | 0.0° / 2.6°        | 16.0° / 36.9°    |
| aspect ratio, 95th pct       | 5 489              | 4.4              |
| degenerate triangles         | 2 679              | 1 063            |
| total triangles              | 26 175             | 20 441           |
| worst chordal deviation      | 1.84 m             | 1.84 m           |

Triangle produces near-isotropic meshes with ~20 % fewer triangles. The
remaining degenerates and the identical worst chordal deviation (plates
P14/P18/P21/P22) are **parameterization-limited, not mesh-limited** — they stem
from near-degenerate or fallback UV maps, which no 2-D triangulator can repair.
One outlier (P20) over-refined to 10 270 triangles under the metric area
constraint on a badly scaled UV map — area flags need per-plate guards.

Caveat: geometric *accuracy* of the rendered surface is already controlled by
the chordal-tolerance subdivision; Triangle's win is triangle *shape* (shading
normals, downstream robustness), plus fewer triangles for the same tolerance.

### Experiment 2 — LSCM chart site: clear loss

`param_for` success over 25 plates (baseline threshold: roundtrip ≤ 2·tol):

| Variant                       | Plates charted |
| ----------------------------- | -------------- |
| baseline (grid + fan)         | **24 / 25**    |
| CDT `pq28a` (quality + area)  | 18 / 25        |
| CDT `pa` (area only)          | 18 / 25        |
| CDT `pq28aYY` (no boundary Steiner) | 12 / 25  |

Every CDT variant regressed. The chart pipeline's weld/stitch/zip stages need
*conforming boundary vertex layouts* between neighbouring members at the seams;
CDT's irregular boundary sampling (with or without Steiner points) breaks seam
zipping. Interior triangle quality is irrelevant to the chart — LSCM/Tutte are
robust to grid-and-fan meshes, and the one remaining failure (P12) is a
tangent-seam *topology* problem (overlapping sheets, 0.6 m mid-seam gap) that
triangulation quality cannot address.

## Practical blockers

1. **No Python ≥ 3.13 support.** `triangle` 20230923 ships no wheels for
   CPython 3.13/3.14, and the sdist fails to compile on 3.14 (stale
   Cython-generated C referencing the removed `longintrepr.h`). This workspace
   runs Python 3.14. Adoption today would mean pinning Python ≤ 3.12 or
   vendoring/regenerating the bindings. Last upstream release: 2023.
2. **License.** The core Triangle C library is free for personal/research use
   only; commercial use requires arrangement with the author. Accepted as
   tolerable for this project, but it constrains redistribution.
3. **Extra native dependency** on all platforms (C extension).

## Verdict

| Site        | Fit  | Why                                                        |
| ----------- | ---- | ---------------------------------------------------------- |
| Render site | Good — *if* blockers solved | Large, measurable quality win; fewer triangles; same accuracy |
| LSCM site   | Poor — do not pursue        | Regresses chart success 24→18/25; the site needs seam conformity, not triangle quality |

If render-site mesh quality ever becomes a priority, the options in order of
preference are:

1. Same algorithm via a maintained package — e.g. `MeshPy` (wraps the same
   Triangle code; same license caveat).
2. Vendor/patch `triangle` bindings for Python 3.14.
3. Keep earcut and add a cheap quality post-pass (edge flips toward Delaunay)
   — smaller win, zero new dependencies.

No action is taken now; current rendering output is accuracy-correct, and the
skinny earcut triangles are a cosmetic/robustness concern, not a defect.

## Spike artifacts

Throwaway scripts `spike_triangle1.py` / `spike_triangle2.py` (deleted after
this evaluation; method fully described above for reproduction).
