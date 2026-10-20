# Changelog — ocx-diagnose

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
