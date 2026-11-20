# Changelog

Workspace-level summary; each package keeps its own `CHANGELOG.md` under
`packages/` with the details.

## 0.8.3 — 2026-11-20

### Release

- Completes the PyPI rollout under the `3docx.org` organisation: publishes
  `ocx-integrity` 0.3.0 and `ocx-model-validator` 0.7.0. All five workspace
  packages are now published on every tag (versions already on PyPI are
  skipped).

## 0.8.2 — 2026-11-20

### Fixed

- Publishing: PyPI allows only one pending trusted publisher per
  (repository, workflow, environment), so the three packages could not share
  the `pypi` environment and v0.8.1 was rejected (`invalid-publisher`). Each
  package now publishes from its own matrix job with environment
  `pypi-<package>`. Same packages and versions as 0.8.1.

## 0.8.1 — 2026-11-20

### Fixed

- CI: the integrity model tests read `models/TR02`, which is no longer
  tracked; their two TR02 models are now fixtures in `tests/data/integrity/`.
- Publishing: `uv build` at the virtual workspace root failed, so v0.6.0–
  v0.8.0 never reached PyPI. The workflow now builds the workspace members
  listed in `PUBLISH_PACKAGES` and skips versions already on PyPI.

### Release

- Staged PyPI rollout under the `3docx.org` organisation: this tag publishes
  `ocx-model-core` 0.6.1, `ocx-geometry` 0.3.1 and `ocx-rules` 0.1.0.
  `ocx-integrity` and `ocx-model-validator` follow in the next release.

## 0.8.0 — 2026-11-20

### Added

- IR: `IrPlate.offset` holds the plate's material `Offset` from its parent
  surface; integrity hashes it in the plate `geometry` aspect.

### Fixed

- OCX 2.8.6: point coordinates and vector directions are read (they came
  out as (0,0,0)); GUID-only panel `SurfaceRef`s resolve to the referenced
  surface or surface collection.

### Compatibility

- `ocx-integrity`: manifests built before this change for models whose
  plates carry `<Offset>` (including `0.0`) report a plate `geometry`
  change on `verify`/`diff`. The profile stays `ocx-hash/1`.

## 0.7.0 — 2026-11-17

### Removed (breaking)

- `ocx-model-validator`: the `ocx-mcp` MCP server moved to its own
  repository, [OCXStandard/ocx-mcp](https://github.com/OCXStandard/ocx-mcp).
  MCP client configs must launch it from that repository.

### Changed

- `ocx-model-validator`: `ocx_model_validator.compartments` is public.
- All packages require `ocx-model-core>=0.6,<0.7` (stale `<0.6` pins
  fixed); a test now guards inter-package pins.

## 0.6.0 — 2026-11-16

### Added

- IR: panel children (plates, brackets, stiffeners, pillars, edge
  reinforcements) carry the panel `functionType` when not overridden,
  flagged by `function_type_inherited`; integrity hashes the effective
  value.

### Dependencies

- certifi 2026.10.19, filelock 4.2.1, setuptools 84.1.0, virtualenv
  21.14.13 (lockfile).

## 0.5.0 — 2026-10-03

### Added

- HTML report renderer: `--format html` (auto-inferred from a `.html`
  destination), tabbed multi-section documents, in-document links from
  BOM groups and part rows to catalogue entries.
- New reports: `report panels`, `report plates`, `report stiffeners`,
  `report brackets`, `report pillars` — attributes, physical properties
  and unit-converted scantlings; geometry intentionally excluded.
  All included in `report all`.
- Compartments report: `Cargo type` column and a `Cargoes` table with
  cargo attributes and properties (density, carriage pressure, liquid
  state, stowage factor, permeability, angle of repose).
- Bill of material: groups are expandable rows with per-group totals
  (click-to-toggle in HTML; inline child rows in markdown/rich).
- Panel children (plates, stiffeners, pillars) inherit the panel
  `functionType`; inherited values shown in parentheses.
- IR: full `BracketParameters` on `IrBracket` (noses, free edge radius,
  reinforcement type, origin, U/V directions, `FeatureCope`,
  `FlangeEdgeReinforcement`); `IrPillar` trace, inclinations and
  penetrations.

### Changed

- Cross-section catalogue reports list unique bar sections only.
- BOM item rows show the part name (id as fallback) without the id.
- Group rows render in bold; missing values render as empty cells
  instead of `N/A`.
- `report bom --detailed` flag removed — superseded by expandable
  groups.

## 0.4.0 — 2026-10-01

### Removed (breaking)

- `validator section create/export/plot` CLI commands.
- `build_cross_section` and `save_cross_section` MCP tools (the `ocx-mcp`
  server now exposes 5 tools).
- Unused `numpy` runtime dependency and `xmlschema` dev dependency.

### Changed

- Generic helpers relocated into core:
  - `ocx_model_validator.frame_table` — `FrameTable`, `build_frame_table`,
    `frame_table_block`.
  - `ocx_model_validator.model.units` — `to_si`, `qty_mm`, `qty_m3`,
    `qty_kpa`, `point_mm`.
  - `ocx_model_validator.reporting.generators._compartment_data` —
    `build_compartments_block` and curve-point sampling helpers.
- `ocx` dependency pinned to the final `>=3.2.0` release.

## 0.3.0 and earlier

See the git history.
