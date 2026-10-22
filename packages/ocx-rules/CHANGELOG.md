# Changelog — ocx-rules

## Unreleased

### Fixed

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
