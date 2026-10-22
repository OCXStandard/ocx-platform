# TR05 validator fixes — design

Date: 2026-10-22
Source: `docs/TR05_validation_mbrh.md` (third-party validation of OCX Platform
Validator 0.5.0 against the TR05 mbrh models). The report confirms four issues
in the validator itself. All four are fixed in this project.

## Background

Running `validator validate rules` on `tr05_tc04a/tc09/tc14a_mbrh.3docx`
produced 126 error/warning findings. Re-checking every finding against the
files showed only 15 are real export issues (all in tc09, OCX-PROP-001). The
rest are validator artefacts:

| # | Rule | Findings | Cause (confirmed in code) |
|---|------|----------|---------------------------|
| 1 | OCX-TOP-002 | 48 | `composite_curve_continuous` measures junction gaps in IR segment order, but the builder collects `CompositeCurve3D` segments **by type** (`_build_curve`/`_build_contour` iterate per-type list fields of the xsdata bindings), so order is not end-to-end |
| 2 | OCX-PROP-002 | 60 | `panel_weight_cog_consistent` sums **child plates only**; mbrh declares the complete panel (plates + stiffeners + edge reinforcements + brackets) and reconciles to 0.001 % |
| 3 | OCX-TOP-008 | 3 | Fixed 90° normal-angle threshold flags a sharp bow stem (148° between outboard-pointing normals); the test cannot distinguish a knuckle from a flipped face |
| 4 | OCX-PROP-001 | (latent) | `PlateCutBy.slot_contour` is never read — `_build_hole2d_contours` only iterates `hole2_dcontour` — so slots are never subtracted from plate area |

## Fix 1 — OCX-TOP-002: order-invariant continuity check

Continuity must mean "the segments *can* be chained end-to-end", independent
of IR or declared order (exporters are not required to emit segments
end-to-end even in declared order).

`ocx_geometry.curves._sample_composite` already chains sampled segments
greedily with reversal. Extract that logic:

- New public function in `ocx_geometry.curves`:
  `chained_junction_gaps(samples: list[np.ndarray]) -> list[float]` —
  runs the same greedy chain-with-reversal and returns the per-junction gap
  of the best chain (it does not abort at a snap tolerance).
- `_sample_composite` becomes a thin wrapper sharing the chaining core, with
  behaviour unchanged (stitches, snaps, fails above `snap_tol_m`).
- `composite_curve_continuous` (OCX-TOP-002, `checks/topology.py`) calls
  `chained_junction_gaps` instead of `ordered_junction_gaps`; a finding is
  raised only when the best chain still has a gap above `tolerance_mm`.
- `ordered_junction_gaps` is removed if no other caller remains.
- The builder (`_build_curve`/`_build_contour`) is **unchanged**: IR segment
  order stays type-grouped; no consumer depends on order once TOP-002 is
  order-invariant (sampling already chains).

Tests: mixed-type composite declared out of order but chainable → no finding;
composite with a genuine 57 mm gap → finding; reversal needed to chain → no
finding; single-segment composites unaffected.

## Fix 2 — OCX-PROP-002: panel mass covers the complete panel

Convention (fixed, not configurable): **a panel's declared mass/CoG covers
all children parented to it** — plates, stiffeners, edge reinforcements,
brackets and pillars.

- `panel_weight_cog_consistent` (`checks/properties.py`) collects children
  from `vessel.plates`, `vessel.stiffeners`, `vessel.edge_reinforcements`,
  `vessel.brackets` and `vessel.pillars` whose `parent_ref` is the panel,
  using the existing `_declared_weight_kg` / `_declared_cog` helpers for each.
- Weight and CoG comparison logic and tolerances are unchanged; only the
  summation set grows.
- `rules/properties.toml` OCX-PROP-002 description states the convention
  explicitly. Finding and skip messages say "children", not "plates".

Tests: panel reconciling only when a stiffener's mass is included → no
finding; total still deviating → finding; CoG weighted across mixed child
kinds.

## Fix 3 — OCX-TOP-008: orientation (handedness) test, not an angle

Replace the pass/fail angle threshold with a shared-edge orientation test; a
consistently oriented pair passes at any dihedral angle.

At each shared-boundary sample `p` of an adjacent pair (A, B):

- `t` — shared-edge tangent: direction of the nearest boundary-polyline
  segment at `p`.
- `d_X` — in-plane probe into face X: vector from `p` toward X's boundary
  centroid, projected onto X's tangent plane at `p`, normalised.
- Handedness `s_X = sign((t × d_X) · n_X)`.

Consistent orientation ⇔ `s_A · s_B < 0` (the faces lie on opposite sides of
the edge). `s_A · s_B > 0` → flipped face → finding. Verdict by strict
majority of the up-to-5 evaluable shared samples (ties pass — no finding);
degenerate samples (tiny `|d|`, `|t|` or
`|t × d|`) are skipped, as unevaluable samples are today.

- Finding message reports the verdict plus the normal angle for
  diagnosability: "face orientation reverses across the shared boundary with
  member … (normals 148.3° apart)".
- `angle_tolerance_deg` is removed from `rules/topology.toml` (no longer a
  criterion); the rule description is updated.
- Adjacency detection (AABB prefilter, symmetric point-to-segment proximity,
  `_ADJACENCY_TOL_M`, `_MAX_SHARED_SAMPLES`) is unchanged.

Tests: two coplanar faces, one flipped → finding; knife-edge pair (~150°
between normals) consistently oriented → no finding; collections that pass
today still pass.

## Fix 4 — OCX-PROP-001: read `SlotContour` into plate cut-outs

- `_build_hole2d_contours` (`v3_builder.py`) iterates **both**
  `hole2_dcontour` and `slot_contour` children of a `CutBy`/`PlateCutBy`
  wrapper. The bindings give both the identical shape (`id`, `name`,
  `guidref`, `hole_ref`, `transformation`), so both map to
  `IrHole2DContour` and land in the same `cut_by_holes` list. No IR change;
  nothing downstream distinguishes slots from holes.
- The fix flows automatically to every consumer of `cut_by_holes`:
  OCX-PROP-001 area, OCX-TOP-004 region split, OCX-TOP-005 seam endpoints and
  the renderer's hole placement.
- Known, intended consequence: on files that notch slots into the exported
  contour *and* declare `SlotContour` (tc09 transverse-girder webs), the slot
  is now subtracted twice and the PROP-001 deviation grows — surfacing
  exactly the mbrh inconsistency the report describes.

Tests: builder test — `PlateCutBy` stub with one `Hole2DContour` and two
`SlotContour` → 3 `cut_by_holes`; existing hole tests unchanged.

## Verification

- Unit tests per fix; full suite (`uv run pytest`) green.
- End-to-end acceptance against the local TR05 models
  (`models/TR05/tr05_tc04a_mbrh.3docx`, `tr05_tc09_mbrh.3docx`,
  `tr05_tc14a_mbrh.3docx`), comparing to the report's baseline:
  - OCX-TOP-002: 48 findings → 0.
  - OCX-PROP-002: 60 findings → 0.
  - OCX-TOP-008: 3 findings → 0.
  - OCX-PROP-001: the 15 genuine tc09 findings remain (reported values may
    shift now that slots are placed).

## Rollout

Each fix is independent and lands as its own commit, in the order
1 (TOP-002), 4 (slots), 2 (PROP-002), 3 (TOP-008) — geometry-helper work
first, smallest surface next, rule-behaviour changes last.
