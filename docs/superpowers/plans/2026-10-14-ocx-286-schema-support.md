# OCX 2.8.6 Schema Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate and report on legacy OCX 2.8.6 customer models — XSD validation, parsing, and IR building — through the existing pipeline.

**Architecture:** Vendor the official v2.8.6 XSD (with its single XSD-1.1 `xs:assert` stripped for lxml/XSD-1.0 compatibility) and register it in `SUPPORTED_VERSIONS`. Add a thin `Ocx286Builder(OcxV3Builder)`: the 2.8.6 element names are close enough to 3.1.0 that the v3 getattr-fallback logic reads them directly, but the 2.8.6 xsdata bindings declare ~60 fields as `List[...]` where 3.x has scalars (`OcxXml.vessel`, `Plate.plate_material`, `Material.density`, …). The new builder runs one generic in-place normalisation pass — unwrap any field that is a list in the 2.8.6 bindings but a scalar in the 3.1.0 bindings — then delegates to the inherited v3 build. The only named structural override is `FrameTables` (2.8.6 nests `XRefPlanes`/`YRefPlanes`/`ZRefPlanes` inside a `FrameTables` wrapper on `CoordinateSystem`).

**Tech Stack:** Python 3.12, uv workspace, lxml, xsdata `ocx` bindings (already ship `ocx_286`), pytest.

**Verified during planning** (all code below was executed against the real 2.8.6 bindings on 2026-10-14):
- `DynamicLoader` resolves `"2.8.6"` → `ocx.ocx_286.ocx_286` with no changes.
- The v2.8.6 XSD from the `OCXStandard/OCX_Schema` repo tag `v2.8.6` compiles under lxml **after removing its single `<xs:assert …/>`** (XSD 1.1). Do NOT use the `v2.8.6_fix` tag — it pins `schemaVersion="2.8.6_fix"`, which real customer models don't declare.
- The `unitsmlSchema_lite-0.9.18.xsd` shipped inside the installed `ocx` package's `ocx_286/` folder is **corrupt** (it is actually a copy of the OCX 3.0.1 schema). Use the repo's own vendored copy from `schemas/ocx_310/`.
- 2.8.6 namespace is `http://data.dnvgl.com/Schemas/ocxXMLSchema`; models declare `schemaVersion="2.8.6"` as a root attribute, which `detect_schema_version` already picks up.
- `OcxVersion.get_version` in `parser.py` has a pre-existing bug our test XML trips: when `schemaVersion="…"` is the **last** attribute before `>`, it returns `2.8.6"` (trailing quote). Task 2 fixes it by delegating to the shared `detect_schema_version`.
- The complete `Ocx286Builder` below was run end-to-end against a parsed 2.8.6 test document and produced: 1 panel, 1 plate (thickness `10.0 Umm`), 1 stiffener, 1 material (density `7850.0 Ukgperm3`), FlatBar section (height `100.0 Umm`), 1 coordinate system, 1 ref plane, **zero dangling refs**.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/OCX_Schema.xsd` | Create (vendored) | 2.8.6 XSD, assert-stripped |
| `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/unitsmlSchema_lite-0.9.18.xsd` | Create (copy from `ocx_310/`) | UnitsML import target |
| `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/README.md` | Create | Provenance + assert-strip note |
| `packages/ocx-model-core/src/ocx_model_core/validation/schema.py` | Modify (~line 25) | Add `"2.8.6": "ocx_286"` to `SUPPORTED_VERSIONS` |
| `packages/ocx-model-core/src/ocx_model_core/parsers/parser.py` | Modify (~lines 25–46) | `OcxVersion.get_version` → shared `detect_schema_version` |
| `packages/ocx-model-core/src/ocx_model_core/builders/v286_builder.py` | Create | `Ocx286Builder` (normalisation + FrameTables adapter) |
| `packages/ocx-model-core/src/ocx_model_core/builders/factory.py` | Modify (~lines 11–19) | Register `(2, 8)` and major-fallback `2` |
| `tests/test_ocx286_support.py` | Create | 2.8.6 schema-validation, version-detection, and end-to-end IR tests |
| `tests/test_builders.py` | Modify (TestBuilderFactory, ~line 11) | Factory dispatch tests for 2.8.x |
| `.github/copilot-instructions.md` | Modify | Document 2.8.6 support conventions |

`OcxV3Builder` itself needs **no changes** — the normalisation pass makes the 2.8.6 tree shape-compatible before the inherited build runs.

---

## Shared test fixture — minimal 2.8.6 model

Several tasks use this XML. It parses cleanly and builds a full IR; it is *not* fully schema-valid (a complete valid 2.8.6 model requires ClassificationData, Arrangement, ReferenceSurfaces, etc. — full-validity coverage comes later from a real customer model via stub generation, see Follow-up). **Important:** keep `schemaVersion="2.8.6"` as the *last* attribute of the root element — this intentionally exercises the Task 2 parser fix.

```python
# Module-level constant in tests/test_ocx286_support.py
OCX286_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<ocx:ocxXML xmlns:ocx="http://data.dnvgl.com/Schemas/ocxXMLSchema" ocx:license="x" schemaVersion="2.8.6">
  <ocx:Header time_stamp="2020-01-01T00:00:00" name="test" author="t" organization="t" originating_system="t"/>
  <ocx:Vessel id="vessel1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000001}" name="TestVessel">
    <ocx:CoordinateSystem id="cs1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000009}">
      <ocx:FrameTables>
        <ocx:XRefPlanes>
          <ocx:RefPlane id="fr0" name="FR0">
            <ocx:ReferenceLocation numericvalue="0.0" unit="Um"/>
          </ocx:RefPlane>
        </ocx:XRefPlanes>
      </ocx:FrameTables>
    </ocx:CoordinateSystem>
    <ocx:Panel id="panel1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000002}" name="P1"/>
    <ocx:Plate id="plate1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000004}" name="PL1">
      <ocx:PlateMaterial localRef="mat1">
        <ocx:Thickness numericvalue="10.0" unit="Umm"/>
      </ocx:PlateMaterial>
    </ocx:Plate>
    <ocx:Stiffener id="stf1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000005}" name="ST1">
      <ocx:SectionRef localRef="sec1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000006}" ocx:refType="ocx:BarSection"/>
    </ocx:Stiffener>
  </ocx:Vessel>
  <ocx:ClassCatalogue id="cat1">
    <ocx:MaterialCatalogue id="matcat1">
      <ocx:Material id="mat1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000007}" name="A36">
        <ocx:Density numericvalue="7850" unit="Ukgperm3"/>
        <ocx:YieldStress numericvalue="235" unit="UNpermm2"/>
      </ocx:Material>
    </ocx:MaterialCatalogue>
    <ocx:XSectionCatalogue id="xsec1">
      <ocx:BarSection id="sec1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000008}" name="FB100x10">
        <ocx:FlatBar>
          <ocx:Height numericvalue="100" unit="Umm"/>
          <ocx:Width numericvalue="10" unit="Umm"/>
        </ocx:FlatBar>
      </ocx:BarSection>
    </ocx:XSectionCatalogue>
  </ocx:ClassCatalogue>
</ocx:ocxXML>"""
```

---

### Task 1: Vendor the 2.8.6 XSD and register it in SUPPORTED_VERSIONS

**Files:**
- Create: `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/OCX_Schema.xsd`
- Create: `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/unitsmlSchema_lite-0.9.18.xsd`
- Create: `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/README.md`
- Modify: `packages/ocx-model-core/src/ocx_model_core/validation/schema.py` (~line 25)
- Test: `tests/test_ocx286_support.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ocx286_support.py` (the `OCX286_MODEL` constant from "Shared test fixture" above goes at module level, below the imports — it is used from Task 4 onward, add it now):

```python
"""Tests for OCX 2.8.6 schema support (validation, parsing, IR building)."""
from __future__ import annotations

from pathlib import Path

import pytest


class Test286SchemaRegistry:
    def test_286_registered_and_compiles(self):
        from ocx_model_core.validation.schema import SUPPORTED_VERSIONS, load_schema

        assert SUPPORTED_VERSIONS["2.8.6"] == "ocx_286"
        assert load_schema("2.8.6") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ocx286_support.py -v`
Expected: FAIL with `KeyError: '2.8.6'`

- [ ] **Step 3: Vendor the schema files**

Run (PowerShell, from repo root):

```powershell
$dir = "packages\ocx-model-core\src\ocx_model_core\schemas\ocx_286"
New-Item -ItemType Directory -Force $dir | Out-Null
curl.exe -sL -o "$dir\OCX_Schema.xsd" https://raw.githubusercontent.com/OCXStandard/OCX_Schema/v2.8.6/OCX_Schema.xsd
Copy-Item packages\ocx-model-core\src\ocx_model_core\schemas\ocx_310\unitsmlSchema_lite-0.9.18.xsd $dir
```

Then strip the single XSD-1.1 assert (lxml is XSD 1.0 only):

```powershell
@'
import re
from pathlib import Path
p = Path(r"packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/OCX_Schema.xsd")
text = p.read_text(encoding="utf-8")
assert text.count("<xs:assert") == 1, f"expected exactly 1 xs:assert, found {text.count('<xs:assert')}"
p.write_text(re.sub(r"[ \t]*<xs:assert\b[^>]*/>\r?\n?", "", text), encoding="utf-8")
print("stripped")
'@ | uv run python -
```

Expected output: `stripped`

- [ ] **Step 4: Create the provenance README**

Create `packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286/README.md`:

```markdown
# OCX 2.8.6 vendored schema

- `OCX_Schema.xsd` — from https://github.com/OCXStandard/OCX_Schema, tag `v2.8.6`
  (namespace `http://data.dnvgl.com/Schemas/ocxXMLSchema`), with its single
  XSD 1.1 `<xs:assert>` element removed so the schema compiles under lxml
  (libxml2 supports XSD 1.0 only). The assert only enforced that an
  `EntityRefBase` carries a `localRef` and/or a `GUIDRef`; validation is
  otherwise unchanged. Do not use the `v2.8.6_fix` tag — it pins
  `schemaVersion="2.8.6_fix"`, which real 2.8.6 models do not declare.
- `unitsmlSchema_lite-0.9.18.xsd` — same file as vendored for 3.x
  (copied from `../ocx_310/`). Note: the copy shipped inside the `ocx`
  PyPI package's `ocx_286/` folder is corrupt (it is actually the OCX
  3.0.1 schema) and must not be used.
```

- [ ] **Step 5: Register the version**

In `packages/ocx-model-core/src/ocx_model_core/validation/schema.py`, change:

```python
SUPPORTED_VERSIONS: dict[str, str] = {
    "3.0.0": "ocx_300",
```

to:

```python
SUPPORTED_VERSIONS: dict[str, str] = {
    "2.8.6": "ocx_286",
    "3.0.0": "ocx_300",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_ocx286_support.py tests/test_schema_validation.py -v`
Expected: all PASS. `test_schema_validation.py`'s registry tests iterate `SUPPORTED_VERSIONS`, so they now also compile 2.8.6 (including the fully-offline subprocess test — this proves the vendored files resolve without network access).

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/schemas/ocx_286 packages/ocx-model-core/src/ocx_model_core/validation/schema.py tests/test_ocx286_support.py
git commit -m "feat: vendor OCX 2.8.6 XSD and register it for schema validation"
```

---

### Task 2: Fix OcxVersion.get_version via shared detect_schema_version

The current implementation splits the XML text on whitespace and slices `item[item.find("=") + 2 : -1]`, which returns `2.8.6"` (trailing quote) whenever `schemaVersion` is the last attribute before `>`. The shared regex in `parsers/version.py` is robust; use it.

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/parsers/parser.py` (~lines 25–46)
- Test: `tests/test_ocx286_support.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ocx286_support.py`:

```python
class TestVersionDetection286:
    def test_get_version_schema_version_as_last_attribute(self, tmp_path: Path):
        """schemaVersion directly before '>' must not pick up the quote/bracket."""
        from ocx_model_core.parsers.parser import OcxVersion

        model = tmp_path / "last_attr.3docx"
        model.write_text(
            '<ocx:ocxXML xmlns:ocx="http://data.dnvgl.com/Schemas/ocxXMLSchema" '
            'schemaVersion="2.8.6"></ocx:ocxXML>',
            encoding="utf-8",
        )
        assert OcxVersion.get_version(model) == "2.8.6"

    def test_detect_schema_version_286_document(self):
        from ocx_model_core.parsers.version import detect_schema_version

        assert detect_schema_version(OCX286_MODEL) == "2.8.6"
```

- [ ] **Step 2: Run tests to verify the first fails**

Run: `uv run pytest tests/test_ocx286_support.py::TestVersionDetection286 -v`
Expected: `test_get_version_schema_version_as_last_attribute` FAILS with `assert '2.8.6"' == '2.8.6'`; the `detect_schema_version` test PASSES (it already works — it pins the contract).

- [ ] **Step 3: Fix OcxVersion.get_version**

In `packages/ocx-model-core/src/ocx_model_core/parsers/parser.py`, replace the body of `OcxVersion.get_version`:

```python
    @staticmethod
    def get_version(model: Path) -> str:
        """
        The schema version of the model.
        Args:
            model: The source file path or uri

        Returns:
            The schema version of the 3Docx XML model, or ``"NA"`` if none is declared.
        """
        try:
            content = model.read_text(encoding="utf-8")
        except OSError as e:
            raise SourceError(f"Cannot read {model}: {e}") from e
        return detect_schema_version(content) or "NA"
```

and add the import near the other relative imports at the top of the file:

```python
from .version import detect_schema_version
```

Note: the old code caught `SourceError` from `read_text`, which never raises it — `OSError` is what actually occurs; the replacement preserves the documented `SourceError` contract properly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ocx286_support.py tests/test_parser.py -v` (if `tests/test_parser.py` does not exist, run `uv run pytest tests/ -k "parser or 286" -v`)
Expected: PASS

- [ ] **Step 5: Run the full suite (parser change is load-bearing for everything)**

Run: `uv run pytest`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/parsers/parser.py tests/test_ocx286_support.py
git commit -m "fix: robust schemaVersion extraction via shared detect_schema_version"
```

---

### Task 3: Ocx286Builder and factory registration

**Files:**
- Create: `packages/ocx-model-core/src/ocx_model_core/builders/v286_builder.py`
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/factory.py` (~lines 11–19)
- Test: `tests/test_builders.py` (`TestBuilderFactory`, ~line 11)

- [ ] **Step 1: Write the failing tests**

Add to `TestBuilderFactory` in `tests/test_builders.py` (match the style of the existing `test_get_builder_310_returns_v3`):

```python
    def test_get_builder_286_returns_v286(self):
        from ocx_model_core.builders.v286_builder import Ocx286Builder

        assert isinstance(get_builder("2.8.6"), Ocx286Builder)

    def test_get_builder_unknown_28x_minor_falls_back_to_v286(self):
        from ocx_model_core.builders.v286_builder import Ocx286Builder

        assert isinstance(get_builder("2.9.1"), Ocx286Builder)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_builders.py::TestBuilderFactory -v`
Expected: both new tests FAIL with `ModuleNotFoundError: No module named 'ocx_model_core.builders.v286_builder'`

- [ ] **Step 3: Create the builder module**

Create `packages/ocx-model-core/src/ocx_model_core/builders/v286_builder.py` (this exact code was executed successfully during planning):

```python
"""Ocx286Builder — translates OCX schema v2.8.x dataclasses into IR types.

The 2.8.6 element vocabulary is close enough to 3.1.0 that the inherited
``OcxV3Builder`` logic (which reads the newest field name first and falls
back to older names, all via ``getattr``) handles it directly.  Two real
structural differences remain:

1. The 2.8.6 xsdata bindings declare many fields as ``List[...]`` where the
   3.x bindings have scalars (e.g. ``OcxXml.vessel``, ``Plate.plate_material``,
   ``Material.density`` — ~60 fields in total).  ``build`` therefore first
   runs a generic in-place normalisation pass that unwraps any field that is
   a list in the 2.8.6 bindings but a scalar in the 3.1.0 bindings, then
   delegates to the inherited v3 build.
2. 2.8.6 nests the frame-table plane groups inside a ``FrameTables`` wrapper
   on ``CoordinateSystem`` (3.x has ``XRefPlanes``/… directly on it); a small
   adapter re-exposes them under the 3.x field names.
"""
from __future__ import annotations

import dataclasses
import typing

from loguru import logger

from ocx_model_core.parsers.dynamic_loader import DeclarationOfOcxImport, DynamicLoader

from .v3_builder import OcxV3Builder, _first


class _FrameTableCs:
    """Adapter presenting a 2.8.6 CoordinateSystem/FrameTables pair with 3.x field names."""

    def __init__(self, cs, ft) -> None:
        self.id = getattr(cs, "id", None)
        self.name = getattr(cs, "name", None)
        self.is_global = getattr(cs, "is_global", False)
        self.local_cartesian = getattr(cs, "local_cartesian", None)
        self.xref_planes = _first(getattr(ft, "xref_planes", None))
        self.yref_planes = _first(getattr(ft, "yref_planes", None))
        self.zref_planes = _first(getattr(ft, "zref_planes", None))


class Ocx286Builder(OcxV3Builder):
    """Builds an ``IrVessel`` from an OCX v2.8.x root dataclass."""

    #: lazily-built cache: 2.8.6 class name → field names to unwrap
    _unwrap_map: typing.ClassVar[dict[str, set[str]] | None] = None

    def supported_versions(self) -> list[tuple[int, int]]:
        return [(2, 8)]

    def build(self, root):
        """Normalise the raw 2.8.6 tree in place, then run the v3 build."""
        self._normalize(root, set())
        return super().build(root)

    # ------------------------------------------------------------------
    # Generic list→scalar normalisation (guided by the 3.1.0 bindings)
    # ------------------------------------------------------------------

    @classmethod
    def _reference_module(cls):
        """The 3.1.0 bindings module, used as the shape reference."""
        return DynamicLoader.import_module(DeclarationOfOcxImport("ocx", "3.1.0"))

    @classmethod
    def _fields_to_unwrap(cls, node) -> set[str]:
        """Fields of *node*'s class that are lists in 2.8.6 but scalars in 3.1.0."""
        name = type(node).__name__
        if cls._unwrap_map is None:
            cls._unwrap_map = {}
        if name in cls._unwrap_map:
            return cls._unwrap_map[name]
        fields: set[str] = set()
        ref_cls = getattr(cls._reference_module(), name, None)
        if ref_cls is not None and dataclasses.is_dataclass(ref_cls):
            try:
                here = typing.get_type_hints(type(node))
                there = typing.get_type_hints(ref_cls)
            except Exception:  # pragma: no cover — defensive
                here, there = {}, {}
            for f in dataclasses.fields(node):
                if (
                    typing.get_origin(here.get(f.name)) is list
                    and f.name in there
                    and typing.get_origin(there.get(f.name)) is not list
                ):
                    fields.add(f.name)
        cls._unwrap_map[name] = fields
        return fields

    def _normalize(self, node, seen: set[int]) -> None:
        """Recursively unwrap singleton lists where 3.x expects scalars."""
        if node is None or id(node) in seen or not dataclasses.is_dataclass(node):
            return
        seen.add(id(node))
        unwrap = self._fields_to_unwrap(node)
        for f in dataclasses.fields(node):
            value = getattr(node, f.name, None)
            if f.name in unwrap and isinstance(value, list):
                if len(value) > 1:
                    logger.warning(
                        f"2.8.6 normalisation: {type(node).__name__}.{f.name} has "
                        f"{len(value)} entries; keeping the first only"
                    )
                value = _first(value)
                setattr(node, f.name, value)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._normalize(item, seen)
            else:
                self._normalize(value, seen)

    # ------------------------------------------------------------------
    # 2.8.6 structural overrides
    # ------------------------------------------------------------------

    def _build_coordinate_system(self, cs, ir) -> None:
        """2.8.6 wraps the ref-plane groups in <FrameTables>; flatten them."""
        if cs is not None and not isinstance(cs, (list, tuple)):
            ft = _first(getattr(cs, "frame_tables", None))
            if ft is not None and getattr(cs, "xref_planes", None) is None:
                cs = _FrameTableCs(cs, ft)
        super()._build_coordinate_system(cs, ir)
```

- [ ] **Step 4: Register in the factory**

In `packages/ocx-model-core/src/ocx_model_core/builders/factory.py`, add the import and registry entries:

```python
from .base import IOcxBuilder, UnsupportedSchemaVersionError
from .v3_builder import OcxV3Builder
from .v286_builder import Ocx286Builder

# Registry: (major, minor) → builder class.
# Add entries here as new schema families are supported.
_BUILDER_REGISTRY: dict[tuple[int, int], type[IOcxBuilder]] = {
    (2, 8): Ocx286Builder,
    (3, 0): OcxV3Builder,
    (3, 1): OcxV3Builder,
    (3, 2): OcxV3Builder,
}

# Fallback: major-only registry for unknown minor versions within a known family.
_MAJOR_FALLBACK: dict[int, type[IOcxBuilder]] = {
    2: Ocx286Builder,
    3: OcxV3Builder,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_builders.py -v`
Expected: all PASS (including the pre-existing `test_get_builder_unknown_major_raises` — it uses a major other than 2/3).
If `test_get_builder_unknown_major_raises` asserts on major `2`, update it to use an unregistered major such as `9.0.0` — major 2 is now registered by design.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-model-core/src/ocx_model_core/builders/v286_builder.py packages/ocx-model-core/src/ocx_model_core/builders/factory.py tests/test_builders.py
git commit -m "feat: add Ocx286Builder with generic 2.8.6 list normalisation"
```

---

### Task 4: End-to-end 2.8.6 tests — parse → build → IR, and schema-validation plumbing

**Files:**
- Test: `tests/test_ocx286_support.py`

- [ ] **Step 1: Write the end-to-end tests**

Add to `tests/test_ocx286_support.py` (uses the module-level `OCX286_MODEL` constant added in Task 1):

```python
@pytest.fixture()
def model_286(tmp_path: Path) -> Path:
    target = tmp_path / "model286.3docx"
    target.write_text(OCX286_MODEL, encoding="utf-8")
    return target


class Test286EndToEnd:
    def test_parse_resolves_286_bindings(self, model_286: Path):
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        assert type(root).__module__ == "ocx.ocx_286.ocx_286"
        assert root.schema_version == "2.8.6"

    def test_build_full_ir(self, model_286: Path):
        from ocx_model_core.builders.factory import get_builder
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        ir = get_builder(root.schema_version).build(root)

        assert ir.schema_version == "2.8.6"
        assert ir.name == "TestVessel"
        # Vessel-level structural parts
        assert set(ir.panels) == {"panel1"}
        assert set(ir.plates) == {"plate1"}
        assert set(ir.stiffeners) == {"stf1"}
        # Plate material + thickness resolved through normalised PlateMaterial
        plate = ir.plates["plate1"]
        assert plate.thickness is not None
        assert plate.thickness.value == 10.0
        assert plate.thickness.unit == "Umm"
        assert plate.material_ref is not None
        assert plate.material_ref.local_ref == "mat1"
        # Catalogues (root-level ClassCatalogue list, nested catalogue lists)
        assert "mat1" in ir.materials
        assert ir.materials["mat1"].density is not None
        assert ir.materials["mat1"].density.value == 7850.0
        assert "sec1" in ir.sections
        assert ir.sections["sec1"].section_type == "FlatBar"
        assert ir.sections["sec1"].height.value == 100.0
        # FrameTables flattened onto the coordinate system
        assert "cs1" in ir.coordinate_systems
        assert ir.coordinate_systems["cs1"].x_ref_plane_ids == ["fr0"]
        assert "fr0" in ir.ref_planes
        # Stiffener section ref resolves — no dangling references
        assert ir.stiffeners["stf1"].section_ref.local_ref == "sec1"
        assert ir.dangling_refs == []


class Test286SchemaValidation:
    def test_validate_schema_routes_to_286(self, model_286: Path):
        """The 2.8.6 XSD is selected and produces a structured result.

        The minimal model is intentionally not fully schema-valid (a valid
        2.8.6 Vessel requires ClassificationData, Arrangement, etc.), so this
        asserts the plumbing: version routing, error structure, line numbers.
        """
        from ocx_model_core.validation.schema import validate_schema

        result = validate_schema(model_286)
        assert result.schema_version == "2.8.6"
        assert result.valid is False
        assert result.error_count == len(result.errors) > 0
        assert all(e.line > 0 for e in result.errors)
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_ocx286_support.py -v`
Expected: all PASS. (The implementation already exists from Tasks 1–3; these tests pin the end-to-end contract. If `test_build_full_ir` fails on an assertion, debug the normalisation — the expected values above were produced by the exact Task 3 code during planning.)

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_ocx286_support.py
git commit -m "test: end-to-end OCX 2.8.6 parse, build, and schema-validation coverage"
```

---

### Task 5: Documentation

**Files:**
- Modify: `.github/copilot-instructions.md` (Builder conventions section)

- [ ] **Step 1: Update the builder conventions**

In `.github/copilot-instructions.md`, find the "## Builder conventions" section and append this bullet after the existing bullet about OCX 3.2.0 renames:

```markdown
- OCX 2.8.6 (legacy `http://data.dnvgl.com/Schemas/ocxXMLSchema` namespace) is
  handled by `Ocx286Builder` in `builders/v286_builder.py`, registered as
  `(2, 8)` with major-fallback `2`. Its element names are close enough to
  3.1.0 that the inherited v3 logic reads them, but the 2.8.6 bindings declare
  many fields as `List[...]` where 3.x has scalars; `Ocx286Builder.build`
  first runs a generic in-place normalisation pass (unwrap any field that is
  a list in 2.8.6 but a scalar in the 3.1.0 bindings), then delegates to the
  v3 build. The 2.8.6 `FrameTables` wrapper on `CoordinateSystem` is
  flattened by a small adapter. The vendored 2.8.6 XSD
  (`schemas/ocx_286/`) has its single XSD-1.1 `xs:assert` stripped so it
  compiles under lxml — see the README in that folder.
```

- [ ] **Step 2: Commit**

```bash
git add .github/copilot-instructions.md
git commit -m "docs: document OCX 2.8.6 support conventions"
```

---

## Follow-up (requires the real customer model — not automated here)

When a real 2.8.6 customer `.3docx` model is available:

1. Drop it into `models/` at the repo root.
2. Run `uv run python -m ocx_model_core.generate_stubs` — stubs land in `tests/data/ocx_286_stubs/` (digits-only name, auto-discovered by `conftest.py`, so the whole parametrized suite picks the version up).
3. Run `uv run pytest` and fix any parametrized-test tolerance issues (assert fields only when present, per the stub-test convention).
4. Smoke-test the CLI: `validator validate schema <model>.3docx` and `validator report all <model>.3docx`.

## Success criteria

- `uv run pytest` fully green.
- `load_schema("2.8.6")` compiles offline (covered by the existing blackholed-proxy registry test).
- `validator validate schema` on a 2.8.6 model selects the 2.8.6 XSD (exit 0/1 on validity, not exit 2 "cannot validate").
- `validator report all` on a 2.8.6 model produces best-effort reports via the IR (parts, materials, sections, frame table populated).
