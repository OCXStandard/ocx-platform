# Changelog — ocx-geometry

## Unreleased

### Added

- `bracket.tessellate_bracket`: planar bracket tessellation — outer
  contour + plane (given or best-fit) extruded by the plate thickness
  into a closed prism (`Offset` honoured, else symmetric), or a flat
  sheet when thickness is unknown.
- `KIND_COLORS` gains a `"bracket"` entry (orange).

### Fixed

- Mesh trimming (`MeshTrimmer._cut`): each cut piece's inside/outside side
  is now read at the ring itself — probes just left and right of every
  ring segment's midpoint vote for the piece they fall in, weighted by
  segment length. Previously a piece took its side from the ring segment
  nearest its representative point, weighted by piece area; in coarse
  charts with long sliver faces that point could lie tens of metres from
  the ring, its nearest point a clipped segment end with an arbitrary
  cross-product sign, and one large mislabelled outside piece outvoted
  the rest. Both components then came out "inside" and unseeded plates
  rendered as the whole chart (e.g. the ropax superstructure sides
  `nplcid8174`/`nplcid8568` as 5143 m² instead of 20/38 m²).
- Mesh trimming (`MeshTrimmer._cut`): an uncut face no longer connects
  across an edge the ring crosses (one split between two or more cut
  pieces). On a manifold chart the face beyond a crossed edge is always
  cut too, but where member sheets overlap (the ring jumps to the other
  sheet, leaving a straddling face of the first uncut) or a folded sliver
  sits on a non-manifold edge, that uncut face bridged the inside and
  outside pieces into one component and unseeded plates rendered as the
  whole chart (ropax `nplcid5964` on `DK8_E_S`: 312 m² instead of 24 m²;
  `nplcid4241` on `SHELL_P`: 5171 m² instead of 12 m²).
- Mesh trimming (`MeshTrimmer.trim`): a cut whose kept vector area exceeds
  1.5 × the outer ring's is rejected (`trim_reject` records both areas), so
  the renderer falls back to its next route instead of keeping a leaked
  cut. A correct cut's vector area equals the ring's however curved the
  surface. Safety net for charts whose member sheets overlap rather than
  meet: where the ring jumps to an overlapping sheet and back, the stretch
  of the first sheet it skips is never cut and joins inside to outside
  (ropax `nplcid4222` on `SHELL_P` rendered as the whole 5163 m² side).
  The proper fix belongs in the chart construction.
- UV tessellation (`UvTessellator`): hole cut-outs are now removed with an
  explicit boolean difference (shell − holes) instead of constructing a
  holed polygon and repairing it with `make_valid`. Cut-outs crossing the
  plate exterior (e.g. slot contours open to a plate edge, as authored for
  stiffener penetrations) now cut proper boundary notches; previously the
  even-odd `make_valid` repair kept the overlap as spurious filled
  fragments, so slots did not remove material. Holes fully outside the
  plate are now dropped instead of rendered as detached islands.
- Mesh trimming (`MeshTrimmer._assemble`): after the exact-duplicate weld,
  the trimmed mesh is now welded at a tolerance tied to the cut-end border
  pull (3 mm = 2 × pull), remaining T-junctions on boundary edges are
  stitched by splitting the edge at the near-lying vertex, and the mesh is
  re-welded. Previously `_cut` pulled cut-segment ends onto a face border
  independently in each face's 2-D frame, so the same 3-D cut point could
  re-emerge up to a couple of millimetres apart in adjacent faces; the
  exact weld could not merge those, leaving unwelded internal seams along
  interior chart edges (e.g. the hull's flat-of-side tangent line) that
  CAD viewers draw as skew lines on shell plates.
- NURBS curve sampling (`curves._sample_nurbs`): the adaptive sampler now
  seeds its parameter set with every distinct interior knot, so C0 corners
  (full-multiplicity knots, as CAD exports use for plate-contour corners)
  are sampled exactly. Previously the uniform 33-point seed could straddle
  a corner and the sag refinement stop below tolerance, chamfering plate
  corners by up to ~tol (≈7 cm) and opening visible holes where plates meet.
- LSCM chart building (`make_lscm_chart` / `make_lscm`): hint points may
  now be passed as per-plate contour loops; each plane member's trim is
  then bounded by the union of the concave hull and the loop polygons.
  Previously the concave hull of sparse hints could tunnel into plate
  interiors (e.g. knuckled inner-skin panels, where the knuckle edge has
  hints only at plate corners), leaving slits in the chart mesh that made
  plates render with large missing regions or leak the whole chart.

### Added

- `measure.chained_junction_gaps`: order-invariant junction-gap measure —
  segments may attach at either end of the growing chain and may be
  reversed, so declared segment order carries no meaning.

### Removed

- `measure.ordered_junction_gaps` (declared-order junction gaps) —
  superseded by `chained_junction_gaps`.

## 0.1.0 — 2026-10-20

Initial release.

### Added

- Geometry evaluation kernel for the OCX IR, built on numpy with no
  display stack (depends only on `ocx-model-core`).
- `measure`: length, area and closure measurements on IR geometry,
  including `chain_polylines` and `chain_gap_details` (gap endpoint
  pairs for unclosed boundary chains).
- `curves`: sampling and evaluation of IR curves (lines, arcs, polylines,
  NURBS).
- `surfaces`: IR surface → parametric surface evaluation.
- `sweep`: profile sweeps along traces for stiffeners and pillars.
- `sections_2d`: 2-D section profile outlines.
- `uv_tessellator`: UV-domain triangulation of trimmed surfaces.
- `holes`: hole contour resolution and placement on surfaces.
- `mesh`: triangle-mesh containers and utilities.
- `backend`: numpy backend helpers for tessellation.
