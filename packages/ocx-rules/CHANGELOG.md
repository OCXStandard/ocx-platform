# Changelog — ocx-rules

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
