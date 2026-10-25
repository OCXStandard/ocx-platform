# Changelog — ocx-rules

## Unreleased

### Added

- Per-rule schema-support markers: rules may declare
  `schemas = ["3.2", "3.3"]` in their TOML definition; the
  `RuleManager` skips rules not applicable to the loaded model's
  schema family (`ValidationContext.schema_version`), reporting them
  as `SKIPPED` with the reason. Rules without the marker run on all
  versions. `OCX-PROP-004` (TraceLine on stiffeners) is the first
  rule restricted this way (3.2/3.3 only).
- `OCX-GEO-005`: in addition to planarity, catalogue hole contours
  are now verified to be **centered** at the catalogue origin — XY
  bounding-box centre within the new `center_tolerance_mm` parameter
  (default 1.0 mm), one finding per `Hole2D`. Purely parametric
  shapes are centered by construction and skipped.
- `OCX-TOP-005`: seamed panels are now also verified to have
  **closed plate outer contours** — the gap between the first and
  last sample of each plate's `OuterContour` must not exceed
  `tolerance_mm`, closing the "pattern must subdivide the panel into
  closed plate contours" aspect of the rule.

### Fixed

- `OCX-REF-002`: the cardinality check now counts `Plate` elements
  inside `ComposedOf` (`ocx:ComposedOf/ocx:Plate`) instead of the
  wrapper elements — an empty `<ocx:ComposedOf/>` no longer
  satisfies the rule.

- `OCX-TOP-002`: composite-curve continuity is now order-invariant —
  junction gaps are measured on the best end-to-end chain
  (`chained_junction_gaps`) instead of declared segment order, which
  false-flagged exporters emitting segments out of order.
- `OCX-PROP-002`: panel weight/CoG reconciliation now sums **all**
  children parented to the panel (plates, stiffeners, edge
  reinforcements, brackets, pillars) instead of plates only.
- `OCX-TOP-008`: the fixed 90° normal-angle threshold is replaced by a
  shared-edge handedness test (`sign((t × d) · n)` with strict-majority
  voting; ties pass), so consistently oriented sharp knuckles no longer
  produce findings while flipped faces still do. The
  `angle_tolerance_deg` parameter is removed; the median normal angle is
  kept in the finding message for diagnosability. Shared-edge sampling
  hardened for curved seams (nearest-neighbour point chaining, evenly
  spread sample stations, bounded dedup).

## 0.1.0 — 2026-10-20

Initial release.

### Added

- Rule model: `RuleSpec`, `RuleResult`, `Finding`, `Severity`,
  `RuleStatus`.
- `ValidationContext` with lazy lxml tree and lazy `IrVessel` build, plus
  `XmlIndex` — a shared single-pass identity/reference document scan.
- TOML rule catalogues with load-time validation (`catalogue.py`) and
  parameterized check primitives (`PRIMITIVE_REGISTRY`).
- `RuleManager`: entry-point pack discovery and rule execution.
- User TOML configuration: disable rules, override severities and
  parameters (`config.py`).
- `GeometryContext`: geometry services for checks, loading `ocx-geometry`
  lazily when installed (including per-ref boundary curve resolution).
- Built-in `best_practice` pack: 34 of 36 rules implemented (24 content +
  10 geometry); compartment rules OCX-TOP-006/007 are deferred stubs.
