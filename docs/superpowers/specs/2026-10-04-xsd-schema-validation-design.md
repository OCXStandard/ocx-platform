# XSD Schema Validation — Design

**Date:** 2026-10-04
**Status:** Approved
**Feature:** `validator validate schema MODEL.3docx`

## Purpose

Validate a `.3docx` model against the official OCX XSD for its declared
schema version, fully offline, with output for both humans (rich table,
HTML) and agents (JSON).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Schema source | Bundled XSD auto-selected from the model's `schemaVersion` (offline; no override flags) |
| Validation engine | `lxml.etree.XMLSchema` (existing dependency; fast; line/column in errors) |
| Output | Fixed: rich table to stdout + HTML sidecar + JSON sidecar (no `--format` flag) |
| Sidecar location | Beside the model: `model.validation.html`, `model.validation.json` |
| Terminal error cap | 50 by default; `--max-errors N` to change; sidecars always contain the full list |

## CLI

New typer sub-app `validate` on the existing `app` (room for future
subcommands such as `validate refs`):

```
validator validate schema MODEL.3docx [--max-errors N]
```

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Model is schema-valid |
| 1 | Validation errors found |
| 2 | Cannot validate: unreadable file, malformed XML, unknown/unsupported schema version |

Schema-version detection reuses the logic currently in
`cli._detect_schema_version` / `_load_vessel`, extracted into a shared
helper so both `report` and `validate` use one implementation.

## Schema vendoring & resolution

The `ocx` Python package bundles XSDs only for 2.8.6/3.0.0/3.0.1 (plus an
ad-hoc top-level 3.2.0), and its UnitsML `xs:import` points at a remote
URL. Therefore the XSDs are vendored in this repo as package data:

```
ocx_model_validator/schemas/
├── ocx_300/OCX_Schema.xsd + unitsmlSchema_lite-0.9.18.xsd
├── ocx_301/…
├── ocx_310/…
└── ocx_320/…
```

- Fetched once at development time from 3docx.org and committed.
- A registry maps `(major, minor, patch)` → schema directory. Unknown
  version → exit 2 with a message listing supported versions.
- A custom `lxml.etree.Resolver` remaps the remote UnitsML
  `schemaLocation` URL to the local vendored file so validation never
  touches the network.
- `packaging/validator.spec` adds a `datas` entry so the XSDs ship inside
  the PyInstaller one-dir bundle. Paths are resolved relative to the
  package (`importlib.resources` / `Path(__file__)`) so they work both
  from source and frozen.

## Validation module

New `ocx_model_validator/validation/schema.py` — independent of the IR
pipeline (validates raw XML; no parse/build):

```python
@dataclass(frozen=True)
class SchemaError:
    line: int
    column: int
    message: str
    domain: str          # lxml error domain/type name

@dataclass(frozen=True)
class SchemaValidationResult:
    model: str           # source file path
    schema_version: str
    valid: bool
    error_count: int
    errors: list[SchemaError]
    validated_at: str    # ISO timestamp

def validate_schema(model: Path) -> SchemaValidationResult
```

Implementation: `lxml.etree.parse(model)` → `XMLSchema.validate(tree)` →
map `schema.error_log` entries to `SchemaError`. Compiled `XMLSchema`
objects are cached per version in a module-level dict.

## Outputs

Every successful validation run (exit 0 or 1) emits all three:

1. **Rich table to stdout** — summary panel (model, schema version,
   VALID/INVALID, error count) + error table (line, column, message),
   capped at `--max-errors`.
2. **HTML sidecar** — `MODEL.validation.html` beside the model; full
   error list; rendered with the existing `HtmlRenderer` from a `Report`.
3. **JSON sidecar** — `MODEL.validation.json` beside the model;
   `dataclasses.asdict(result)`; stable schema for agentic consumers.

The result → `Report` conversion lives in
`reporting/generators/schema_validation.py`, consistent with the other
report generators.

## Error handling

- **Malformed XML** (not well-formed): exit 2 with the lxml parse error
  (line/col); no sidecars written.
- **Unknown/missing `schemaVersion`** or no vendored XSD: exit 2; message
  lists supported versions.
- **Sidecar write failure** (e.g. read-only directory): log the error,
  still print the terminal table, exit per validation result (0/1).
- All diagnostics via `loguru` (console at INFO, as configured in
  `cli.configure_logging`).

## Testing (TDD)

`tests/test_schema_validation.py`:

- Valid stub model (`tests/data/ocx_310_stubs/ocxxml.3docx`) →
  `valid=True`, `errors=[]`, exit 0.
- Deliberately broken model fixture (invalid attribute/element) →
  `valid=False`, errors carry line numbers, exit 1.
- Unknown schema version → exit 2.
- Malformed XML → exit 2.
- Sidecars written beside the model; JSON parsed and verified to contain
  the full error list.
- `--max-errors` caps the table but not the JSON.
- Registry test: every vendored schema directory compiles with
  `XMLSchema` (catches corrupt/incomplete vendored files).

CLI-level tests use typer's `CliRunner`, consistent with
`tests/test_cli_report.py`.

## Out of scope

- Semantic/reference validation (dangling refs etc.) — future
  `validate refs`.
- Schema-version override flags or user-supplied XSDs.
- Online schema fetching at runtime.
- The agentic consumer itself (only the JSON contract is provided now).
