# Changelog — ocx-model-core

## 0.5.0 — 2026-10-20

Initial release as a standalone workspace package, split out of the former
monolithic `ocx-model-validator`. For the pre-split history see the
workspace-root `CHANGELOG.md`.

### Added

- `OcxParser`: parses `.3docx` files by detecting the `schemaVersion` and
  dynamically loading the matching versioned `ocx` data-binding module via
  `DynamicLoader` / `DeclarationOfOcxImport` (no static binding imports).
- Builder layer: `get_builder(version)` factory with `_BUILDER_REGISTRY`
  dispatch and major-version fallback.
  - `OcxV3Builder` handles all OCX 3.x models (reads 3.2.0 element names
    first, falling back to 3.1.0 names).
  - `Ocx286Builder` handles the legacy 2.8.6 namespace, normalising
    list-vs-scalar field differences before delegating to the v3 logic.
- Schema-neutral IR: frozen dataclasses rooted at `IrVessel`, with all
  structural parts (panels, plates, stiffeners, brackets, pillars,
  materials, sections, compartments) in flat dicts keyed by `id`;
  children carry `ParentRef` back-references. Panel `OuterContour` curves
  are built into `IrPanel.outer_contours`.
- Units: `UnitConverter` and `build_unit_registry` resolve raw OCX unit id
  strings (e.g. `"Umm"`) to SI.
- Offline XSD validation (`validation/schema.py`) against vendored OCX and
  UnitsML schemas (3.1.0, 3.2.0, and 2.8.6 with its single XSD-1.1
  `xs:assert` stripped for lxml compatibility).
- `writeback`: apply scantling reports back onto `.3docx` files.
- `generate_stubs`: repo-internal script generating XML test stubs from
  models in `./models/`.
- Exception hierarchy in `exeptions.py`: `XmlParserError`, `SourceError`,
  `DynamicLoaderError`, `ConverterError` / `ConverterWarning`.
