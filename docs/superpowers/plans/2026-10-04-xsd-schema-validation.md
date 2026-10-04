# XSD Schema Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `validator validate schema MODEL.3docx` — offline XSD validation against vendored OCX schemas, with rich terminal output plus fixed HTML and JSON sidecar files.

**Architecture:** XSDs for OCX 3.0.0/3.0.1/3.1.0/3.2.0 are vendored as package data under `ocx_model_validator/schemas/`. A new `validation/schema.py` module validates raw XML with `lxml.etree.XMLSchema` (a custom resolver remaps the remote UnitsML import to the local file) and returns a frozen `SchemaValidationResult`. A new report generator converts the result to the existing `Report` model for the rich/HTML renderers; JSON comes from `dataclasses.asdict`. A new `validate` typer sub-app wires it up with exit codes 0/1/2.

**Tech Stack:** Python 3.13, uv, lxml (existing dep), typer, loguru, pytest, existing `reporting` renderers, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-10-04-xsd-schema-validation-design.md`

**Conventions:** All commands run from the repo root. Use `uv run` for everything. All commits include the trailer:
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

---

### Task 1: Vendor the OCX XSDs as package data

The `ocx` PyPI package has no 3.1.0 XSD and its UnitsML import points at a
remote URL, so we vendor all four supported schema versions in this repo.
Hatchling (`[tool.hatch.build.targets.wheel] packages = ["ocx_model_validator"]`)
includes all files under the package dir automatically — no pyproject change
needed.

**Files:**
- Create: `ocx_model_validator/schemas/ocx_300/OCX_Schema.xsd` (+ unitsml)
- Create: `ocx_model_validator/schemas/ocx_301/OCX_Schema.xsd` (+ unitsml)
- Create: `ocx_model_validator/schemas/ocx_310/OCX_Schema.xsd` (+ unitsml)
- Create: `ocx_model_validator/schemas/ocx_320/OCX_Schema.xsd` (+ unitsml)

- [ ] **Step 1: Download the XSDs** (URLs verified working 2026-10-04)

```powershell
foreach ($pair in @(@('V300','ocx_300'), @('V301','ocx_301'), @('V310','ocx_310'), @('V320','ocx_320'))) {
    $v = $pair[0]; $dir = "ocx_model_validator\schemas\$($pair[1])"
    New-Item -ItemType Directory -Force $dir | Out-Null
    curl.exe -sf -o "$dir\OCX_Schema.xsd" "https://3docx.org/fileadmin//ocx_schema//$v//OCX_Schema.xsd"
    curl.exe -sf -o "$dir\unitsmlSchema_lite-0.9.18.xsd" "https://3docx.org/fileadmin/ocx_schema/unitsml/unitsmlSchema_lite-0.9.18.xsd"
}
```

- [ ] **Step 2: Verify all 8 files downloaded and are XML**

```powershell
Get-ChildItem ocx_model_validator\schemas -Recurse -File | ForEach-Object {
    $head = Get-Content $_.FullName -TotalCount 1
    "{0} {1} bytes starts: {2}" -f $_.FullName, $_.Length, $head.Substring(0, 30)
}
```

Expected: 8 files, each > 100 KB (OCX) or > 50 KB (unitsml), each starting with `<?xml`.

- [ ] **Step 3: Commit**

```bash
git add ocx_model_validator/schemas
git commit -m "feat: vendor OCX 3.0.0-3.2.0 XSDs as package data"
```

---

### Task 2: Shared schema-version detection helper

Extract the version-detection regexes (currently private in `cli.py`) into a
reusable module so both the report commands and the validator share one
implementation.

**Files:**
- Create: `ocx_model_validator/parsers/version.py`
- Modify: `ocx_model_validator/cli.py` (function `_detect_schema_version`, ~line 100)
- Test: `tests/test_version_detect.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_version_detect.py`:

```python
"""Tests for shared OCX schema-version detection."""
from ocx_model_validator.parsers.version import detect_schema_version


def test_detects_schema_version_attribute():
    xml = '<ocx:ocxXML xmlns:ocx="https://3docx.org/x" schemaVersion="3.1.0">'
    assert detect_schema_version(xml) == "3.1.0"


def test_detects_version_from_namespace():
    xml = ('<ocx:Panel xmlns:ocx='
           '"https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd"/>')
    assert detect_schema_version(xml) == "3.2.0"


def test_attribute_wins_over_namespace():
    xml = ('<ocx:ocxXML xmlns:ocx='
           '"https://3docx.org/fileadmin//ocx_schema//V310//OCX_Schema.xsd" '
           'schemaVersion="3.1.0">')
    assert detect_schema_version(xml) == "3.1.0"


def test_returns_none_when_undetectable():
    assert detect_schema_version("<foo/>") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_version_detect.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ocx_model_validator.parsers.version'`

- [ ] **Step 3: Implement the helper**

Create `ocx_model_validator/parsers/version.py`:

```python
"""Shared OCX schema-version detection from raw XML text."""
from __future__ import annotations

import re

_SCHEMA_VERSION_RE = re.compile(r'\bschemaVersion="([^"]+)"')
_NAMESPACE_RE = re.compile(r"//V(\d)(\d)(\d)//OCX_Schema\.xsd")


def detect_schema_version(xml_text: str) -> str | None:
    """Return the OCX schema version declared in *xml_text*, or ``None``.

    Checks the ``schemaVersion`` attribute first, then falls back to the
    version encoded in the OCX namespace URI (``//V310//OCX_Schema.xsd``).
    """
    match = _SCHEMA_VERSION_RE.search(xml_text)
    if match:
        return match.group(1)
    match = _NAMESPACE_RE.search(xml_text)
    if match:
        return ".".join(match.groups())
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_version_detect.py -q`
Expected: 4 passed

- [ ] **Step 5: Refactor cli.py to use the shared helper**

In `ocx_model_validator/cli.py`, replace the body of `_detect_schema_version`
(keep its existing inverted semantics: it returns `None` when the file has a
`schemaVersion` attribute — meaning "OcxParser can handle it directly" — and
a namespace-derived version only for bare fragments):

```python
def _detect_schema_version(model: Path) -> str | None:
    from ocx_model_validator.parsers.version import detect_schema_version

    xml = model.read_text(encoding="utf-8")
    if re.search(r'\bschemaVersion="', xml):
        return None
    return detect_schema_version(xml)
```

- [ ] **Step 6: Run the CLI tests to verify no regression**

Run: `uv run pytest tests/test_cli_report.py tests/test_model_summary.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add ocx_model_validator/parsers/version.py ocx_model_validator/cli.py tests/test_version_detect.py
git commit -m "feat: extract shared schema-version detection helper"
```

---

### Task 3: Validation core — `validation/schema.py`

**Files:**
- Modify: `ocx_model_validator/exeptions.py` (add one exception)
- Create: `ocx_model_validator/validation/__init__.py`
- Create: `ocx_model_validator/validation/schema.py`
- Test: `tests/test_schema_validation.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_validation.py`:

```python
"""Tests for XSD schema validation (ocx_model_validator.validation.schema)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_model_validator.exeptions import SchemaVersionError, XmlParserError

STUB_MODEL = Path(__file__).parent / "data" / "ocx_310_stubs" / "ocxxml.3docx"


@pytest.fixture()
def valid_model(tmp_path: Path) -> Path:
    """Copy of the full 3.1.0 stub model in a writable directory."""
    target = tmp_path / "model.3docx"
    target.write_text(STUB_MODEL.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture()
def invalid_model(tmp_path: Path) -> Path:
    """Valid stub with a bogus element injected into the Vessel."""
    text = STUB_MODEL.read_text(encoding="utf-8")
    assert "</ocx:Vessel>" in text
    text = text.replace("</ocx:Vessel>",
                        "<ocx:NotARealElement/></ocx:Vessel>", 1)
    target = tmp_path / "broken.3docx"
    target.write_text(text, encoding="utf-8")
    return target


class TestValidateSchema:
    def test_valid_model(self, valid_model: Path):
        from ocx_model_validator.validation.schema import validate_schema

        result = validate_schema(valid_model)
        assert result.valid is True
        assert result.errors == []
        assert result.error_count == 0
        assert result.schema_version == "3.1.0"
        assert result.model == str(valid_model)
        assert result.validated_at  # ISO timestamp set

    def test_invalid_model_reports_errors_with_lines(self, invalid_model: Path):
        from ocx_model_validator.validation.schema import validate_schema

        result = validate_schema(invalid_model)
        assert result.valid is False
        assert result.error_count == len(result.errors) > 0
        first = result.errors[0]
        assert first.line > 0
        assert "NotARealElement" in first.message

    def test_unknown_schema_version_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "odd.3docx"
        model.write_text('<ocx:ocxXML xmlns:ocx="https://3docx.org/x" '
                         'schemaVersion="9.9.9"/>', encoding="utf-8")
        with pytest.raises(SchemaVersionError) as exc_info:
            validate_schema(model)
        assert "3.1.0" in str(exc_info.value)  # lists supported versions

    def test_missing_schema_version_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "noversion.3docx"
        model.write_text("<foo/>", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            validate_schema(model)

    def test_malformed_xml_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "malformed.3docx"
        model.write_text('<ocx:ocxXML schemaVersion="3.1.0"><unclosed>',
                         encoding="utf-8")
        with pytest.raises(XmlParserError):
            validate_schema(model)


class TestSchemaRegistry:
    def test_all_vendored_schemas_compile(self):
        """Every vendored schema dir must compile (catches corrupt files)."""
        from ocx_model_validator.validation.schema import (SUPPORTED_VERSIONS,
                                                           load_schema)

        for version in SUPPORTED_VERSIONS:
            assert load_schema(version) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schema_validation.py -q`
Expected: FAIL — first with `ImportError: cannot import name 'SchemaVersionError'`

- [ ] **Step 3: Add the exception**

Append to `ocx_model_validator/exeptions.py`:

```python
class SchemaVersionError(ValueError):
    """Unknown, missing or unsupported OCX schema version."""
```

- [ ] **Step 4: Implement the validation module**

Create empty `ocx_model_validator/validation/__init__.py`:

```python
"""Model validation (XSD schema validation and future semantic checks)."""
```

Create `ocx_model_validator/validation/schema.py`:

```python
"""XSD validation of .3docx models against vendored OCX schemas.

Independent of the IR pipeline: validates raw XML with lxml, fully
offline. The vendored XSDs live in ``ocx_model_validator/schemas/``;
a custom resolver remaps the remote UnitsML ``xs:import`` URL to the
local copy so no network access ever occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import lxml.etree as etree
from loguru import logger

from ocx_model_validator.exeptions import (SchemaVersionError, SourceError,
                                           XmlParserError)
from ocx_model_validator.parsers.version import detect_schema_version

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_UNITSML_FILE = "unitsmlSchema_lite-0.9.18.xsd"

#: OCX schema version -> vendored schema directory name
SUPPORTED_VERSIONS: dict[str, str] = {
    "3.0.0": "ocx_300",
    "3.0.1": "ocx_301",
    "3.1.0": "ocx_310",
    "3.2.0": "ocx_320",
}


@dataclass(frozen=True)
class SchemaError:
    """One XSD validation error."""
    line: int
    column: int
    message: str
    domain: str  # lxml error type name, e.g. 'SCHEMAV_ELEMENT_CONTENT'


@dataclass(frozen=True)
class SchemaValidationResult:
    """Outcome of validating one model file against its OCX XSD."""
    model: str
    schema_version: str
    valid: bool
    error_count: int
    errors: list[SchemaError]
    validated_at: str  # ISO 8601 UTC


class _LocalUnitsmlResolver(etree.Resolver):
    """Remap the remote UnitsML schemaLocation to the vendored local file."""

    def __init__(self, schema_dir: Path) -> None:
        super().__init__()
        self._schema_dir = schema_dir

    def resolve(self, url, pubid, context):  # noqa: ANN001 — lxml signature
        if url and "unitsmlSchema_lite" in url:
            return self.resolve_filename(
                str(self._schema_dir / _UNITSML_FILE), context)
        return None


_schema_cache: dict[str, etree.XMLSchema] = {}


def load_schema(version: str) -> etree.XMLSchema:
    """Return the compiled XMLSchema for *version* (cached per process)."""
    if version in _schema_cache:
        return _schema_cache[version]
    folder = SUPPORTED_VERSIONS.get(version)
    if folder is None:
        raise SchemaVersionError(
            f"No bundled XSD for schema version {version!r}; supported "
            f"versions: {', '.join(sorted(SUPPORTED_VERSIONS))}")
    schema_dir = _SCHEMAS_DIR / folder
    parser = etree.XMLParser()
    parser.resolvers.add(_LocalUnitsmlResolver(schema_dir))
    doc = etree.parse(str(schema_dir / "OCX_Schema.xsd"), parser)
    schema = etree.XMLSchema(doc)
    _schema_cache[version] = schema
    return schema


def validate_schema(model: Path) -> SchemaValidationResult:
    """Validate *model* against the bundled XSD for its declared version.

    Raises:
        SourceError: the file cannot be read.
        SchemaVersionError: no version declared, or no bundled XSD for it.
        XmlParserError: the file is not well-formed XML.
    """
    try:
        xml_bytes = model.read_bytes()
    except OSError as exc:
        raise SourceError(f"Cannot read {model}: {exc}") from exc

    version = detect_schema_version(xml_bytes.decode("utf-8", errors="replace"))
    if version is None:
        raise SchemaVersionError(
            f"{model} declares no OCX schema version; supported versions: "
            f"{', '.join(sorted(SUPPORTED_VERSIONS))}")
    schema = load_schema(version)

    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise XmlParserError(f"{model} is not well-formed XML: {exc}") from exc

    valid = schema.validate(doc)
    errors = [
        SchemaError(line=e.line, column=e.column, message=e.message,
                    domain=e.type_name)
        for e in schema.error_log
    ]
    logger.info("Schema validation of {}: {} ({} error(s), schema {})",
                model, "VALID" if valid else "INVALID", len(errors), version)
    return SchemaValidationResult(
        model=str(model),
        schema_version=version,
        valid=valid,
        error_count=len(errors),
        errors=errors,
        validated_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_schema_validation.py -q`
Expected: 7 passed (schema compilation takes a few seconds on first run)

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/exeptions.py ocx_model_validator/validation tests/test_schema_validation.py
git commit -m "feat: add offline XSD schema validation core"
```

---

### Task 4: Report generator — result → `Report`

Converts a `SchemaValidationResult` into the neutral `Report` model consumed
by the existing rich/HTML renderers. `max_errors=None` means "all errors"
(used for the HTML sidecar); the CLI passes the cap for the terminal table.

**Files:**
- Create: `ocx_model_validator/reporting/generators/schema_validation.py`
- Test: `tests/test_schema_validation_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_schema_validation_report.py`:

```python
"""Tests for the schema-validation report generator."""
from __future__ import annotations

from ocx_model_validator.validation.schema import (SchemaError,
                                                   SchemaValidationResult)


def _result(n_errors: int) -> SchemaValidationResult:
    errors = [SchemaError(line=i + 1, column=0, message=f"error {i}",
                          domain="SCHEMAV_TEST") for i in range(n_errors)]
    return SchemaValidationResult(
        model="m.3docx", schema_version="3.1.0", valid=n_errors == 0,
        error_count=n_errors, errors=errors,
        validated_at="2026-10-04T00:00:00+00:00")


def test_valid_result_has_no_error_table():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(0))
    assert report.metadata["Result"] == "VALID"
    assert report.sections[0].tables == []


def test_invalid_result_lists_errors():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(3))
    assert report.metadata["Result"] == "INVALID"
    table = report.sections[0].tables[0]
    assert len(table.rows) == 3
    assert table.rows[0][1] == 1  # line number of first error


def test_max_errors_caps_rows_and_adds_note():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(10), max_errors=4)
    table = report.sections[0].tables[0]
    assert len(table.rows) == 4
    assert any("first 4 of 10" in n for n in report.sections[0].notes)


def test_max_errors_above_count_adds_no_note():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(2), max_errors=50)
    assert len(report.sections[0].tables[0].rows) == 2
    assert report.sections[0].notes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schema_validation_report.py -q`
Expected: FAIL with `ImportError: cannot import name 'schema_validation'`

- [ ] **Step 3: Implement the generator**

Create `ocx_model_validator/reporting/generators/schema_validation.py`:

```python
"""Schema validation report generator — SchemaValidationResult → Report."""
from __future__ import annotations

from ocx_model_validator.reporting.model import (Report, ReportSection,
                                                 ReportTable)
from ocx_model_validator.validation.schema import SchemaValidationResult

_TITLE = "Schema validation report"


def build(result: SchemaValidationResult,
          max_errors: int | None = None) -> Report:
    """Build a Report; *max_errors* caps the table (None = all errors)."""
    shown = result.errors if max_errors is None else result.errors[:max_errors]
    tables = []
    if shown:
        tables.append(ReportTable(
            title="Validation errors",
            columns=["#", "Line", "Column", "Message"],
            rows=[[i + 1, e.line, e.column, e.message]
                  for i, e in enumerate(shown)],
        ))
    notes: list[str] = []
    if max_errors is not None and result.error_count > max_errors:
        notes.append(
            f"Showing first {max_errors} of {result.error_count} errors; "
            "the full list is in the JSON and HTML sidecar files.")
    verdict = "VALID" if result.valid else "INVALID"
    section = ReportSection(
        title=f"Result: {verdict}",
        intro=f"{result.error_count} schema error(s).",
        tables=tables,
        notes=notes,
    )
    metadata = {
        "Source file": result.model,
        "Schema version": result.schema_version,
        "Validated at": result.validated_at,
        "Result": verdict,
    }
    return Report(title=_TITLE, metadata=metadata, sections=[section])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schema_validation_report.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/reporting/generators/schema_validation.py tests/test_schema_validation_report.py
git commit -m "feat: add schema-validation report generator"
```

---

### Task 5: CLI command `validate schema` with sidecars and exit codes

**Files:**
- Modify: `ocx_model_validator/cli.py` (new sub-app after `report_app` setup, ~line 45; module docstring)
- Test: `tests/test_cli_validate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_validate.py`:

```python
"""CLI tests for `validator validate schema` (typer CliRunner)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ocx_model_validator.cli import app

runner = CliRunner()

STUB_MODEL = Path(__file__).parent / "data" / "ocx_310_stubs" / "ocxxml.3docx"


@pytest.fixture()
def valid_model(tmp_path: Path) -> Path:
    target = tmp_path / "model.3docx"
    target.write_text(STUB_MODEL.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture()
def invalid_model(tmp_path: Path) -> Path:
    text = STUB_MODEL.read_text(encoding="utf-8").replace(
        "</ocx:Vessel>", "<ocx:NotARealElement/></ocx:Vessel>", 1)
    target = tmp_path / "broken.3docx"
    target.write_text(text, encoding="utf-8")
    return target


def test_valid_model_exit_0_and_sidecars(valid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(valid_model)])
    assert result.exit_code == 0
    assert "VALID" in result.output
    json_path = valid_model.with_suffix(".validation.json")
    html_path = valid_model.with_suffix(".validation.html")
    assert json_path.exists() and html_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["valid"] is True
    assert data["schema_version"] == "3.1.0"
    assert data["errors"] == []


def test_invalid_model_exit_1_with_full_json(invalid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(invalid_model)])
    assert result.exit_code == 1
    assert "INVALID" in result.output
    data = json.loads(invalid_model.with_suffix(".validation.json")
                      .read_text(encoding="utf-8"))
    assert data["valid"] is False
    assert data["error_count"] == len(data["errors"]) > 0
    assert data["errors"][0]["line"] > 0


def test_max_errors_caps_table_not_json(invalid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(invalid_model),
                                 "--max-errors", "1"])
    assert result.exit_code == 1
    data = json.loads(invalid_model.with_suffix(".validation.json")
                      .read_text(encoding="utf-8"))
    # JSON always carries the full list even when the table is capped
    assert len(data["errors"]) == data["error_count"]


def test_unknown_schema_version_exit_2(tmp_path: Path):
    model = tmp_path / "odd.3docx"
    model.write_text('<ocx:ocxXML xmlns:ocx="https://3docx.org/x" '
                     'schemaVersion="9.9.9"/>', encoding="utf-8")
    result = runner.invoke(app, ["validate", "schema", str(model)])
    assert result.exit_code == 2
    assert not model.with_suffix(".validation.json").exists()


def test_malformed_xml_exit_2(tmp_path: Path):
    model = tmp_path / "malformed.3docx"
    model.write_text('<ocx:ocxXML schemaVersion="3.1.0"><unclosed>',
                     encoding="utf-8")
    result = runner.invoke(app, ["validate", "schema", str(model)])
    assert result.exit_code == 2
    assert not model.with_suffix(".validation.json").exists()


def test_missing_file_nonzero_exit():
    result = runner.invoke(app, ["validate", "schema", "no_such.3docx"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_validate.py -q`
Expected: FAIL — typer reports `No such command 'validate'` (exit code 2 from
usage error on every test; the valid-model test fails on the missing sidecar
assertion / "VALID" not in output)

Note: `test_unknown_schema_version_exit_2` and `test_malformed_xml_exit_2`
may pass incidentally (usage error also exits 2) — that is acceptable; the
command-existence tests are the gate.

- [ ] **Step 3: Implement the sub-app**

In `ocx_model_validator/cli.py`, after `app.add_typer(report_app, name="report")` add:

```python
validate_app = typer.Typer(help="Validate models.", no_args_is_help=True)
app.add_typer(validate_app, name="validate")
```

At the end of the file (before `def entrypoint`), add the command:

```python
@validate_app.command("schema")
def validate_schema_cmd(
    model: Path = _MODEL_ARG,
    max_errors: int = typer.Option(
        50, "--max-errors", min=1,
        help="Maximum number of errors shown in the terminal table "
             "(sidecar files always contain the full list)."),
) -> None:
    """Validate the model against its bundled OCX XSD (offline).

    Exit codes: 0 = valid, 1 = validation errors, 2 = cannot validate.
    Always writes MODEL.validation.json and MODEL.validation.html beside
    the model file.
    """
    import json
    from dataclasses import asdict

    from ocx_model_validator.exeptions import (SchemaVersionError,
                                               SourceError, XmlParserError)
    from ocx_model_validator.reporting.generators import schema_validation
    from ocx_model_validator.validation.schema import validate_schema

    try:
        result = validate_schema(model)
    except (SchemaVersionError, SourceError, XmlParserError) as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc

    RichRenderer().render_to_console(
        schema_validation.build(result, max_errors=max_errors), Console())

    json_path = model.with_suffix(".validation.json")
    html_path = model.with_suffix(".validation.html")
    try:
        json_path.write_text(json.dumps(asdict(result), indent=2),
                             encoding="utf-8")
        html_path.write_text(
            get_renderer("html").render(schema_validation.build(result)),
            encoding="utf-8")
        typer.echo(f"Sidecars written: {json_path}, {html_path}")
    except OSError as exc:
        logger.error("Cannot write sidecar files: {}", exc)

    raise typer.Exit(code=0 if result.valid else 1)
```

Also update the module docstring usage block at the top of `cli.py` — add
this line after the `validator report all ...` line:

```
    validator validate schema MODEL.3docx [--max-errors N]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_validate.py -q`
Expected: 6 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (previously 494 passed, 25 skipped + new tests)

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/cli.py tests/test_cli_validate.py
git commit -m "feat(cli): add validate schema command with HTML/JSON sidecars"
```

---

### Task 6: Packaging and docs

**Files:**
- Modify: `packaging/validator.spec` (`datas=[]` in the `Analysis` block)
- Modify: `README.md` (CLI section)
- Modify: `.github/copilot-instructions.md` (CLI section)

- [ ] **Step 1: Bundle the XSDs in the exe**

In `packaging/validator.spec`, change the `datas` line in `Analysis`:

```python
    datas=[("../ocx_model_validator/schemas", "ocx_model_validator/schemas")],
```

(Paths are relative to the spec file. In the one-dir bundle the XSDs land in
`_internal/ocx_model_validator/schemas/`, which matches the
`Path(__file__).parent.parent / "schemas"` lookup in `validation/schema.py`.)

- [ ] **Step 2: Rebuild and smoke-test the exe**

```powershell
uv run pyinstaller packaging/validator.spec --noconfirm
Copy-Item tests\data\ocx_310_stubs\ocxxml.3docx $env:TEMP\smoke.3docx
dist\ocx-validator\ocx-validator.exe validate schema $env:TEMP\smoke.3docx
echo "exit: $LASTEXITCODE"
Remove-Item $env:TEMP\smoke.3docx, $env:TEMP\smoke.validation.json, $env:TEMP\smoke.validation.html
```

Expected: rich summary with `Result: VALID`, `Sidecars written: ...`, `exit: 0`.

- [ ] **Step 3: Update README.md**

In the CLI examples block (after the `validator report all` lines), add:

```
# validate the model against its OCX XSD (offline; writes
# model.validation.json + model.validation.html beside the model)
validator validate schema model.3docx
validator validate schema model.3docx --max-errors 100
```

In the features bullet list near the top, add:

```
- **XSD schema validation** (`validator validate schema`): offline validation
  against vendored OCX 3.0.0–3.2.0 schemas with rich, HTML and JSON output
```

- [ ] **Step 4: Update .github/copilot-instructions.md**

In the CLI section, add after the report examples:

```
# Validate against the bundled OCX XSD (exit 0 valid / 1 errors / 2 cannot validate)
validator validate schema model.3docx [--max-errors N]
```

Add to the project-layout tree (after the `parsers/` entry):

```
│   ├── validation/
│   │   └── schema.py           ← offline XSD validation (lxml + vendored schemas/)
│   ├── schemas/                 ← vendored OCX + UnitsML XSDs (package data)
```

- [ ] **Step 5: Commit**

```bash
git add packaging/validator.spec README.md .github/copilot-instructions.md
git commit -m "feat: bundle XSDs in exe and document validate schema command"
```

---

## Verification checklist (end of plan)

- [ ] `uv run pytest -q` — full suite green
- [ ] `uv run validator validate schema tests/data/ocx_310_stubs/ocxxml.3docx` → exit 0 (note: writes sidecars beside the stub — delete `tests/data/ocx_310_stubs/ocxxml.validation.*` afterwards and do not commit them)
- [ ] Exe smoke test from Task 6 passed
- [ ] No sidecar files committed to git (`git status` clean of `*.validation.*`)
