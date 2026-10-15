# ocx-diagnose — render pipeline diagnostics (design)

## Goal

A diagnostic tool for trimmed NURBS patch tessellation. It lets a user check
tolerance and internal settings of the render pipeline and see *why* a panel
renders wrongly, via an interactive HTML report.

## Decision

New uv workspace member `packages/ocx-diagnose` (CLI `ocx-diagnose`), depending
on `ocx-render` and `ocx-geometry`. Plotly is a dependency of this package only,
so `ocx-render` stays light and its CLI (`ocx-render model.3docx`) is unchanged.

Rejected: an `ocx-render diagnose` subcommand (pulls plotly into the renderer and
breaks the single-command CLI); loose scripts (not installable, untested).

## Command

```
ocx-diagnose MODEL [--panel ID ...] [--tolerance-sweep 10,25,50,100]
                   [--report out.html] [--json out.json] [--log-level LEVEL]
```

- No `--panel`: whole-model summary table plus one tab per panel.
- `--panel` (repeatable): restrict to the listed panels.
- `--tolerance-sweep`: tolerances in mm; default is the renderer's current value only.
- `--json`: machine-readable stats for regression checks.
- Exit codes: 0 ok, 2 cannot parse/build model, 3 cannot write output.

## Per-panel checks

1. **Tolerance sweep** — per tolerance: triangle count, build and tessellation
   time, and mean/max deviation of the mesh from the exact surface. Deviation is
   found by projecting mesh points back onto each patch with the existing Newton
   inversion. Reported against the target tolerance.
2. **Chart quality** — flipped-triangle area fraction, per-triangle LSCM
   scale spread, counts of welded vertices, pinch splits, T-junctions stitched,
   seams zipped, and whether the Tutte fallback was used.
3. **Trim fidelity** — mesh-trim accepted/rejected with reason, ring snap-distance
   distribution versus `max_snap`, and which route was used (mesh-trim or LSCM).
4. **Geometry sanity** — boundary and non-manifold edge counts, gaps/overlaps
   between neighbouring patches (nearest distance across shared boundaries),
   bounding box versus the panel's declared extents.

## Visuals (self-contained plotly HTML, one tab per panel)

- 3-D chart mesh coloured by distortion; flipped triangles in red.
- 2-D UV chart layout with seams and pinned vertices marked.
- Contour rings with snap vectors at the mesh-trim cut positions.
- 3-D deviation heatmap on the final mesh; boundary and non-manifold edges highlighted.
- Tolerance-sweep curve (error vs triangle count, target line).

## Code changes in existing packages

- `ocx_geometry.lscm` and `ocx_geometry.mesh_trim` return optional frozen
  `stats` dataclasses (counts, snap distances, reject reason) alongside their
  results. No behaviour change; existing callers ignore them.
- `ocx_render.render` exposes a per-panel entry point that accepts a tolerance
  and returns mesh plus stats, so the sweep does not re-render the whole model.

## Testing

- Unit tests on small stub panels: stats are populated, deviation of a plane is
  ~0, a deliberately coarse tolerance exceeds target, JSON schema is stable.
- Regression: tessellation output is bit-identical with and without stats collection.
- Slow-marked smoke test on `models/tr04/tr04_tc14A_outer_shell.3docx` producing a report.

## Out of scope

OCX IR inspection, GLB overlay output, automatic parameter tuning.
