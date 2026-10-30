# Changelog — ocx-diagnose

## Unreleased

### Changed

- The analysed panel's skip table now includes CutBy hole failures
  (`RenderResult.hole_failures`, split out of `skipped` by `ocx-render`),
  including panel-level failures keyed `<panel_id>/hole:<id>`, which
  `ocx-render` now reports once per panel instead of once per plate.
- Single-panel renders also include the panel's stiffeners
  (`only_panels` now filters every part kind); plate statistics are
  unaffected, since they use plate meshes only.

## 0.1.0 — 2026-10-20

Initial release.

### Added

- `ocx-diagnose diagnose model.3docx`: render-pipeline tolerance-sweep
  diagnostics (`sweep` / `analyse` / `checks` / `probes` / `advice`) with
  a self-contained HTML report and plotly chart visuals.
- `ocx-diagnose top-001 model.3docx [--panel ID]... [--tolerance MM]
  [--report out.html]`: TOP-001 LimitedBy closure diagnostics —
  per-panel diagnosis (`diagnose_panel`, `select_panels`), plotly 3D
  figures of closure failures, and an HTML report. Selects a superset of
  the validator's TOP-001 findings. Exit codes: 0 (all plotted panels
  close), 1 (at least one does not), 2 (cannot parse/build/diagnose,
  incl. unknown `--panel` ids), 3 (cannot write output).
