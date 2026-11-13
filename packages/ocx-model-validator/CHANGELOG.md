# Changelog — ocx-model-validator

## Unreleased

### Changed

- **Breaking:** the rules report is one table with an expandable row per
  rule category, holding its rules and all their findings and unchecked
  elements (no cap). Severities are colour-coded badges (error red,
  warning yellow, info green). `validate rules --max-findings` is removed.

### Added

- Report cells can be coloured `Badge` labels (HTML and rich renderers).
- Rule reports show unchecked elements: the JSON sidecar gains a per-result
  `unchecked` list and `summary.unchecked_elements`; the rules report shows
  them per rule. The exit code is unchanged.

## 0.5.0 — 2026-10-20

Initial release as a workspace package: parsing, IR, units and schema
validation were split out into `ocx-model-core`; this package keeps the
reporting, CLI and MCP layers. For the pre-split history (0.5.0 features
and earlier) see the workspace-root `CHANGELOG.md`.

### Added

- CLI with two equivalent entrypoints (`validator` / `ocx-validate`):
  - `report frame-table | compartments | panels | plates | stiffeners |
    brackets | pillars | all` — rich to stdout, markdown or HTML via
    `--destination` / `--format`.
  - `validate schema` — offline validation against the bundled OCX XSD
    (exit 0 valid / 1 errors / 2 cannot validate).
  - `validate rules` — configurable best-practice rules via `ocx-rules`
    (exit 0 clean / 1 error findings / 2 cannot run), with `--config`,
    `--category` and `--rule` filters.
- Reporting: generators plus rich, markdown and HTML renderers.
- `frame_table`: `FrameTable`, `build_frame_table`, `frame_table_block`.
- FastMCP `ocx-mcp` server with session state.
- Back-compat: `ocx_model_validator.__init__` re-exports the
  `ocx-model-core` public API.
