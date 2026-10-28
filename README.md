# OCX Platform

[![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Python workspace for parsing and validating [OCX](https://3docx.org/) `.3docx` ship-model files.
It translates versioned OCX xsdata dataclasses into a **schema-neutral Intermediate Representation (IR)**,
making downstream tools independent of any particular OCX schema version.

---

## Features

- Parses `.3docx` XML files using [xsdata](https://xsdata.readthedocs.io/) with dynamic schema-version detection
- Builds a typed, frozen IR (`IrVessel`, `IrPanel`, `IrPlate`, `IrBracket`, `IrStiffener`, …)
- Supports OCX schema **3.0 / 3.1 / 3.2** out of the box
- Converts UnitsML unit definitions to SI factors via `build_unit_registry`
- CLI subcommands for model reports; xsdata test stubs are generated with the repo-internal script `python -m ocx_model_core.generate_stubs`
- Duplicate-id and dangling-ref integrity checks built into the builder
- **Frame table extraction** (`ocx_model_validator.frame_table`): derives frame
  labels, positions and spacings (mm) from the model's X reference planes
- **Model reports** (`validator report …`): frame table, compartments,
  catalogues and bill of materials, rendered rich to stdout or as Markdown
- **MCP server** `ocx-mcp` exposing model loading, info, frame table,
  compartments and scantling write-back to LLM clients
- **XSD schema validation** (`validator validate schema`): offline validation
  against vendored OCX 3.0.0–3.3.0 schemas with rich, HTML and JSON output
- **Rule-based validation** (`validator validate rules`): configurable
  best-practice rules beyond the XSD — 36 wiki-sourced rules in 6 categories
  (identity, document, references, curves/surfaces, topology, properties),
  defined declaratively in TOML, extensible via `ocx_rules.packs` entry-point
  plugins and tunable through a user config (disable rules, override
  severity/parameters). Rules may declare supported schema families
  (`schemas = ["3.2", "3.3"]`) and are skipped — not failed — on models of
  other versions. 34 of the 36 rules are fully implemented (24 content
  rules + 10 geometry-dependent rules backed by the analytic geometry
  kernel); the 2 compartment rules (OCX-TOP-006/007) are deferred
- **3-D rendering** (`ocx-render`): tessellates the model to a GLB plus a
  self-contained HTML viewer. Multi-member shell panels are built from one
  shared chart mesh that plates are trimmed out of (`ocx_geometry.mesh_trim`);
  `--log-level DEBUG` prints per-stage timings
- **Render diagnostics** (`ocx-diagnose`): runs the render with diagnostic
  hooks and writes an interactive HTML report (plotly.js embedded) plus optional
  JSON: per-plate route, mesh health, surface deviation, neighbour gaps/overlaps,
  chart distortion and a tolerance sweep. The report also contains ranked
  *Findings* per panel and a *Diagnosis* box per worst plate, each with
  evidence, likely cause, "Improve the meshing" steps and "Improve the OCX
  source" steps. Status `confirmed` means a probe proved it, `likely` means it
  was inferred from metrics. Findings are also written to the JSON output.

---

## Installation

```bash
# requires Python ≥ 3.12 and uv
uv sync
```

Install with development dependencies:

```bash
uv sync --dev
```

---

## Quick start

```python
from ocx_model_core.parsers.parser import OcxParser
from ocx_model_core.builders.factory import get_builder

parser = OcxParser()
root   = parser.parse("path/to/model.3docx")

builder = get_builder(root.schema_version)   # dispatches on "3.1.0" etc.
ir      = builder.build(root)                # → IrVessel

print(ir.name, len(ir.panels), "panels")
for plate in ir.plates.values():
    print(plate.id, plate.thickness)
```

### Frame table extraction

```python
from ocx_model_validator.frame_table import build_frame_table

frame_table = build_frame_table(ir)
print(len(frame_table.positions), "frame positions,",
      len(frame_table.entries), "spacing entries")

label, x_mm = frame_table.nearest_frame(161_000.0)   # e.g. midship
```

### MCP server

Run the `ocx-mcp` server over stdio:

```bash
uv run ocx-mcp
```

MCP client configuration (e.g. `mcp.json`):

```json
{
  "mcpServers": {
    "ocx": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\PythonDev\\ocx-platform", "ocx-mcp"]
    }
  }
}
```

| Tool | Purpose |
|---|---|
| `load_model` | Parse a `.3docx` file and build the IR (kept in session state) |
| `get_model_info` | Vessel name, schema version and entity counts |
| `get_frame_table` | Frame 0 offset, spacing entries and frame positions (mm) |
| `get_compartments` | Compartment names, tank types, COGs, volumes and extents |
| `apply_scantlings` | Apply an `nh-optimisation/1` report to a `.3docx`: plate thicknesses plus stiffener `BarSection`s, written to a new file |

---

## Project structure

A [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) with five packages:

```
ocx-platform/                      ← workspace root (virtual — no package here)
├── pyproject.toml                 ← [tool.uv.workspace], shared dev deps, ruff, pytest
├── uv.lock                        ← single lockfile for all members
├── packages/
│   ├── ocx-model-core/            ← parse .3docx → schema-neutral IR (no CLI)
│   │   └── src/ocx_model_core/
│   │       ├── parsers/           ← OcxParser, dynamic xsdata loader, serializer
│   │       ├── builders/          ← IOcxBuilder ABC, get_builder() registry, OcxV3Builder
│   │       ├── model/
│   │       │   ├── ir/            ← IR dataclasses (base, structural, sections, …)
│   │       │   └── units.py       ← UnitConverter, build_unit_registry, SI helpers
│   │       ├── validation/        ← offline XSD validation
│   │       ├── schemas/           ← vendored OCX + UnitsML XSDs (package data)
│   │       ├── writeback.py       ← apply scantling reports to .3docx files
│   │       ├── generate_stubs.py  ← xsdata stub generator (repo-internal)
│   │       ├── utils.py           ← MetaData helpers
│   │       └── exeptions.py       ← custom exception hierarchy
│   ├── ocx-geometry/              ← geometry evaluation kernel (numpy, no display)
│   │   └── src/ocx_geometry/
│   │       └── measure.py         ← length/area/closure measurements on the IR
│   ├── ocx-render/                ← tessellated GLB/HTML renderer (core + geometry)
│   │   └── src/ocx_render/
│   │       ├── render.py          ← render_model(vessel, options) → RenderResult
│   │       ├── gltf_writer.py     ← write meshes to a .glb file
│   │       ├── html_viewer.py     ← self-contained HTML viewer around the GLB
│   │       └── cli.py             ← ocx-render / ocx-diagnose entrypoints
│   ├── ocx-rules/                 ← configurable best-practice rule engine
│   │   └── src/ocx_rules/
│   │       ├── model.py           ← RuleSpec, RuleResult, Finding, Severity, RuleStatus
│   │       ├── context.py         ← ValidationContext (lazy lxml tree + lazy IrVessel)
│   │       ├── xml_index.py       ← XmlIndex: shared identity/reference scan of the document
│   │       ├── catalogue.py       ← TOML rule-catalogue loader (load-time validation)
│   │       ├── primitives/        ← parameterized check primitives (PRIMITIVE_REGISTRY)
│   │       ├── manager.py         ← RuleManager: entry-point discovery + execution
│   │       ├── config.py          ← user TOML config (disable/severity/params)
│   │       └── packs/best_practice/ ← built-in pack: rules/*.toml + checks/ package
│   └── ocx-model-validator/       ← validation, reports, CLI, MCP server
│       └── src/ocx_model_validator/
│           ├── cli.py             ← validator / ocx-validate CLI entrypoint
│           ├── frame_table.py     ← FrameTable, build_frame_table
│           ├── reporting/
│           │   ├── model.py       ← Report, ReportSection, ReportTable
│           │   ├── generators/    ← frame table, compartments, catalogues, BOM, …
│           │   └── renderers/     ← rich, markdown and html renderers
│           └── mcp/
│               ├── state.py       ← session state (loaded vessel)
│               └── server.py      ← FastMCP "ocx-mcp" server (5 tools)
└── tests/
    ├── conftest.py
    ├── stubs.py                   ← stub loaders for each OCX entity
    ├── object_stubs.py            ← duck-typed helpers for unit tests
    ├── data/
    │   ├── ocx_310_stubs/         ← generated XML stubs for 3.1.0
    │   ├── ocx_320rc8_stubs/      ← generated XML stubs for 3.2.0rc8
    │   └── unitsml_stubs/         ← generated UnitsML stubs
    └── test_*.py
```

Dependency direction: `ocx-model-validator` → `ocx-geometry` → `ocx-model-core`,
`ocx-render` → `ocx-geometry` → `ocx-model-core`, and
`ocx-model-validator` → `ocx-rules` → `ocx-model-core` (rule checks use
geometry lazily when installed).
A tessellation render/viewer can depend on core + geometry without ever being
deployed with the validator.

---

## CLI

```bash
# model reports (rich to stdout; markdown/html via --format or a .md/.html destination)
validator report frame-table  model.3docx
validator report compartments model.3docx
validator report catalogues   model.3docx --catalogue material
validator report bom          model.3docx
validator report panels       model.3docx
validator report plates       model.3docx
validator report stiffeners   model.3docx
validator report brackets     model.3docx
validator report pillars      model.3docx
validator report all          model.3docx --destination report.md

# validate the model against its OCX XSD (offline; writes
# model.validation.json + model.validation.html beside the model)
validator validate schema model.3docx
validator validate schema model.3docx --max-errors 100

# run configurable best-practice rules (exit 0 clean / 1 error findings / 2 cannot run;
# writes model.rules.json beside the model — agent-friendly JSON with every
# finding and its source provenance)
validator validate rules model.3docx
validator validate rules model.3docx --config ocx-rules.toml --category identity
validator validate rules model.3docx --rule OCX-ID-002 --destination rules.md

# a full model validation is both commands: schema AND rules. Downstream
# agents read the JSON sidecars (model.validation.json + model.rules.json)
# and summarize them into a single two-part <model>_validation.md beside the
# model: Part 1 — XSD errors grouped into root causes with proposed
# improvements; Part 2 — per-rule findings summary with proposed changes

# tessellate to GLB + HTML viewer (DEBUG log shows timing per stage)
ocx-render model.3docx --destination out.glb --log-level DEBUG [--tolerance MM] [--no-html]

# diagnose the render: HTML report (+ JSON), optional tolerance sweep in mm
ocx-diagnose model.3docx [--panel ID] [--tolerance 50] [--tolerance-sweep 25,50,100] \
    [--report out.html] [--json out.json] [--max-plates 12]

# generate xsdata stubs from .3docx models in ./models/ (repo-internal script)
uv run python -m ocx_model_core.generate_stubs

# wipe and regenerate all stubs
uv run python -m ocx_model_core.generate_stubs --force
```

---

## Standalone Windows executable

Build a standalone `ocx-validator.exe` that runs on Windows machines
without a Python installation:

```bash
uv run pyinstaller packaging/validator.spec --noconfirm
```

The build produces a one-dir bundle in `dist/ocx-validator/` (fast
startup — no self-extraction at launch). Distribute the whole folder
(or zip it); the executable inside exposes the full `validator` CLI:

```bash
dist\ocx-validator\ocx-validator.exe report all model.3docx --destination report.html
```

All versioned OCX data-binding modules are bundled (they are imported
dynamically at runtime), so every supported schema version works out of
the box.

### Installing on another machine

Zip the dist and run the installer script, which extracts to a folder of
your choice and adds it to the user `PATH`:

```powershell
# on the build machine
Compress-Archive -Path dist\ocx-validator\* -DestinationPath ocx-validator.zip

# on the target machine (prompts for install folder)
.\packaging\install.ps1 -ZipPath ocx-validator.zip
```

For machines where PowerShell script execution is restricted, use the
plain `cmd.exe` installer instead (requires Windows 10 1803+ for the
built-in `tar`):

```bat
packaging\install.bat ocx-validator.zip [install-folder]
```

Note: `install.bat` uses `setx`, which truncates a user `PATH` longer
than 1024 characters — prefer `install.ps1` when possible.

---

## Running tests

```bash
uv run pytest                  # unit tests (integration deselected by default)
uv run pytest -m integration   # end-to-end against a real .3docx model (slow)
```

The integration suite parses a full VLCC model and verifies frame table,
midship cross-section and document extraction against known values.

---

## Architecture

```
.3docx file
    │
    ▼
OcxParser.parse(xml_file)
    │  detects schemaVersion → loads versioned xsdata module at runtime
    │  → raw OCX root dataclass
    ▼
get_builder(schema_version)
    │  dispatches on (major, minor) → OcxV3Builder
    ▼
IOcxBuilder.build(root) → IrVessel   ← schema-neutral IR
    │
    ▼
frame_table.build_frame_table(vessel) → FrameTable      (X ref planes → frames)
reporting.generators → Report                           (frame table, compartments,
    │                                                    catalogues, BOM)
    ▼
validator CLI / ocx-mcp MCP server
```

---

## License

[MIT](LICENSE) © 2026 3docx.org
