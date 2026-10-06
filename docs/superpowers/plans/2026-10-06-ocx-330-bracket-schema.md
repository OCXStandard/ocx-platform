# OCX 3.3.0 Bracket Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a vendored OCX 3.3.0 XSD implementing the bracket-workshop enhancements (ordered supports, laps, flange snipe/direction, shape, multiple copes, bracket catalogue) so `validator validate schema` works on 3.3.0 models.

**Architecture:** Copy the vendored 3.2.0 XSD to `ocx_model_validator/schemas/ocx_330/`, relabel namespace/version, then apply six schema edits per the spec. Validation goes through the existing lxml-based `validation/schema.py` — only the `SUPPORTED_VERSIONS` registry changes in Python. All new tests live in one new test module that derives 3.3.0 fixture models from the existing full 3.2.0 stub by string relabelling + XML injection.

**Tech Stack:** XSD 1.0, lxml (via existing `validation/schema.py`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-10-06-ocx-330-bracket-schema-design.md`

---

## Context you must know before starting

- Run everything from the repo root with `uv run pytest …`. Never plain `pytest`.
- The vendored XSDs use **TAB indentation**. Match it when inserting blocks.
- The OCX namespace encodes the version: `https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd`. 3.3.0 uses `…//V330//…`. `detect_schema_version()` (in `ocx_model_validator/parsers/version.py`) already handles any `schemaVersion="x.y.z"` attribute and any `//Vxyz//` namespace — **no change needed there**.
- lxml enforces `xs:ID`/`xs:IDREF` integrity during XSD validation. Every `localRef="…"` and `unit="…"` in a fixture must point at an `id`/`xml:id` that exists **in the same document**. The full 3.2.0 stub `tests/data/ocx_320_stubs/ocxxml.3docx` contains: material ids `nplcid21`, `nplcid39`; panel id `nplcid7`; unit ids `Um`, `URad`, `UKg`, `Umm`, …
- `BoundedRef_T` (base of `GridRef`/`PanelRef`/…) requires children `ContourBounds`, `Offset`, `OffsetDirection` — so fixtures **copy a complete `<ocx:GridRef>…</ocx:GridRef>` block out of the stub** instead of hand-writing one.
- `elementFormDefault="qualified"`, `attributeFormDefault="unqualified"`: new *local* elements (e.g. `Lap`) are written `<ocx:Lap …/>` in instances, but new *local* attributes (`lapped`, `bracketShape`, `flangeDirection`, `connectionKind`, `customerCatalogRefName`) are written **without** prefix.
- Do NOT create `tests/data/ocx_330_stubs/` — `conftest.py` auto-discovers `ocx_\d+_stubs` directories and would try to import non-existent `ocx.ocx_330` xsdata bindings. All 3.3.0 fixtures are built in-memory in the test module.

## File structure

| File | Responsibility |
|---|---|
| `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` | Create — the 3.3.0 schema (copy of 3.2.0 + edits) |
| `ocx_model_validator/schemas/ocx_330/unitsmlSchema_lite-0.9.18.xsd` | Create — unchanged copy from `ocx_320/` |
| `ocx_model_validator/validation/schema.py` | Modify — add `"3.3.0": "ocx_330"` to `SUPPORTED_VERSIONS` |
| `tests/test_ocx330_bracket_schema.py` | Create — all 3.3.0 fixture helpers and tests |
| `README.md` | Modify — line 27: `3.0.0–3.2.0` → `3.0.0–3.3.0` |

---

### Task 1: Vendor and register the 3.3.0 schema

**Files:**
- Create: `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd`
- Create: `ocx_model_validator/schemas/ocx_330/unitsmlSchema_lite-0.9.18.xsd`
- Modify: `ocx_model_validator/validation/schema.py` (SUPPORTED_VERSIONS, ~line 25)
- Test: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ocx330_bracket_schema.py`:

```python
"""Tests for the OCX 3.3.0 bracket schema enhancements (vendored XSD)."""
from __future__ import annotations

import re
from pathlib import Path

from ocx_model_validator.validation.schema import validate_schema

DATA = Path(__file__).parent / "data"
STUB_320 = DATA / "ocx_320_stubs" / "ocxxml.3docx"
NS_320 = "https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd"
NS_330 = "https://3docx.org/fileadmin//ocx_schema//V330//OCX_Schema.xsd"
GUID = "12345678-1234-1234-1234-123456789012"


class TestRegistry:
    def test_330_schema_compiles(self):
        from ocx_model_validator.validation.schema import SUPPORTED_VERSIONS, load_schema

        assert SUPPORTED_VERSIONS["3.3.0"] == "ocx_330"
        assert load_schema("3.3.0") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: FAIL with `KeyError: '3.3.0'`

- [ ] **Step 3: Copy and relabel the schema**

```powershell
New-Item -ItemType Directory ocx_model_validator\schemas\ocx_330
Copy-Item ocx_model_validator\schemas\ocx_320\OCX_Schema.xsd ocx_model_validator\schemas\ocx_330\
Copy-Item ocx_model_validator\schemas\ocx_320\unitsmlSchema_lite-0.9.18.xsd ocx_model_validator\schemas\ocx_330\
```

In `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` make exactly two edits:

1. **Line 4** — replace both `V320` occurrences (in `xmlns:ocx` and `targetNamespace`) with `V330`.
2. **Line ~73** (inside `DocumentBase_T`) — change:

```xml
<xs:attribute name="schemaVersion" type="xs:string" use="required" fixed="3.2.0">
```
to
```xml
<xs:attribute name="schemaVersion" type="xs:string" use="required" fixed="3.3.0">
```

- [ ] **Step 4: Register the version**

In `ocx_model_validator/validation/schema.py`, change:

```python
SUPPORTED_VERSIONS: dict[str, str] = {
    "3.0.0": "ocx_300",
    "3.0.1": "ocx_301",
    "3.1.0": "ocx_310",
    "3.2.0": "ocx_320",
}
```
to
```python
SUPPORTED_VERSIONS: dict[str, str] = {
    "3.0.0": "ocx_300",
    "3.0.1": "ocx_301",
    "3.1.0": "ocx_310",
    "3.2.0": "ocx_320",
    "3.3.0": "ocx_330",
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py tests/test_schema_validation.py -v`
Expected: all PASS (the registry tests in `test_schema_validation.py` iterate `SUPPORTED_VERSIONS` and now also compile 3.3.0).

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/schemas/ocx_330 ocx_model_validator/validation/schema.py tests/test_ocx330_bracket_schema.py
git commit -m "feat: vendor OCX 3.3.0 schema (3.2.0 copy, relabelled) and register it"
```

---

### Task 2: Fixture helpers and backward-compatibility tests

These tests pass immediately (the 3.3.0 schema is still identical to 3.2.0) — they are the regression guards for Tasks 3–6 and spec success-criterion 4.

**Files:**
- Modify: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Add fixture helpers and the legacy bracket constant**

Append to `tests/test_ocx330_bracket_schema.py` (below `GUID = …`):

```python
# ---------------------------------------------------------------- fixtures
_GRIDREF_RE = re.compile(r"<ocx:GridRef\b.*?</ocx:GridRef>", re.DOTALL)

_MASS = """
<ocx:MassProperties>
  <ocx:MouldedDryWeight numericvalue="4.0" unit="UKg"/>
  <ocx:MouldedCenterOfGravity coordinates="0.75 4.97 1.61" unit="Um"/>
  <ocx:PhysicalDryWeight numericvalue="4.0" unit="UKg"/>
  <ocx:PhysicalCenterOfGravity coordinates="0.75 4.97 1.61" unit="Um"/>
</ocx:MassProperties>"""

# localRef must resolve: nplcid21 is a Steel material in the 3.2.0 full stub.
_MATERIAL = """
<ocx:PlateMaterial localRef="nplcid21" ocx:GUIDRef="{guid}" ocx:refType="ocx:Material">
  <ocx:Thickness numericvalue="0.01" unit="Um"/>
</ocx:PlateMaterial>""".format(guid=GUID)


def _contour(pid: str) -> str:
    """A closed triangular-ish outer contour (copied from the 3.2.0 bracket stub)."""
    return f"""
<ocx:OuterContour>
  <ocx:CompositeCurve3D id="{pid}_oc" is2D="false">
    <ocx:CurveLength numericvalue="1.0260326" unit="Um"/>
    <ocx:Line3D id="{pid}_l1" is2D="false">
      <ocx:CurveLength numericvalue="0.27" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.053445 1.4999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 4.783445 1.4999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l2" is2D="false">
      <ocx:CurveLength numericvalue="0.025" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 4.783445 1.4999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 4.783445 1.5249375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l3" is2D="false">
      <ocx:CurveLength numericvalue="0.3889087" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 4.783445 1.5249375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.058445 1.7999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l4" is2D="false">
      <ocx:CurveLength numericvalue="0.025" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.058445 1.7999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.083445 1.7999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l5" is2D="false">
      <ocx:CurveLength numericvalue="0.27" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.083445 1.7999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.083445 1.5299375" unit="Um"/>
    </ocx:Line3D>
    <ocx:CircumArc3D id="{pid}_a6" is2D="false">
      <ocx:CurveLength numericvalue="0.0471239" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.083445 1.5299375" unit="Um"/>
      <ocx:IntermediatePoint coordinates="0.750005 5.0622318 1.5211507" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.053445 1.4999375" unit="Um"/>
    </ocx:CircumArc3D>
  </ocx:CompositeCurve3D>
</ocx:OuterContour>"""


def _params(extra_elements: str = "", extra_attrs: str = "") -> str:
    return f"""
<ocx:BracketParameters ocx:hasEdgeReinforcement="false" numberOfSupports="2"{extra_attrs}>
  <ocx:ArmLengthU numericvalue="0.3" unit="Um"/>
  <ocx:ArmLengthV numericvalue="0.3" unit="Um"/>
  <ocx:UDirection direction="0.0 -1.0 0.0"/>
  <ocx:VDirection direction="0.0 0.0 1.0"/>
  <ocx:Origin coordinates="0.750005 5.083445 1.499938" unit="Um"/>
  {extra_elements}
</ocx:BracketParameters>"""


def _bracket(pid: str, params: str, topology: str = "") -> str:
    """An inline (mode 1) Bracket; topology goes after OuterContour."""
    return (
        f'<ocx:Bracket id="{pid}" name="Bkt {pid}" ocx:GUIDRef="{GUID}">'
        f"{_MASS}{params}{_MATERIAL}{_contour(pid)}{topology}</ocx:Bracket>"
    )


def _as_330(text: str) -> str:
    return text.replace(NS_320, NS_330).replace(
        'schemaVersion="3.2.0"', 'schemaVersion="3.3.0"'
    )


def _stub_330() -> str:
    return _as_330(STUB_320.read_text(encoding="utf-8"))


def _first_gridref(text: str) -> str:
    """A complete, valid GridRef block (BoundedRef needs ContourBounds etc.)."""
    match = _GRIDREF_RE.search(text)
    assert match, "no GridRef in stub model"
    return match.group(0)


def _write_model(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "model.3docx"
    target.write_text(text, encoding="utf-8")
    return target


def _inject_bracket(text: str, bracket_xml: str) -> str:
    assert "</ocx:Vessel>" in text
    return text.replace("</ocx:Vessel>", bracket_xml + "</ocx:Vessel>", 1)


def _assert_valid(result) -> None:
    messages = "; ".join(e.message for e in result.errors[:5])
    assert result.valid, f"expected valid, got {result.error_count} error(s): {messages}"
```

- [ ] **Step 2: Add the backward-compatibility tests**

Append:

```python
class TestBackwardCompatibility:
    def test_relabelled_320_model_is_valid_330(self, tmp_path):
        """Spec criterion 4: a valid 3.2.0 document relabelled 3.3.0 still validates."""
        model = _write_model(tmp_path, _stub_330())
        result = validate_schema(model)
        assert result.schema_version == "3.3.0"
        _assert_valid(result)

    def test_legacy_bracket_with_limitedby_is_valid(self, tmp_path):
        """Deprecated LimitedBy topology remains schema-valid in 3.3.0."""
        text = _stub_330()
        topology = f"<ocx:LimitedBy>{_first_gridref(text)}</ocx:LimitedBy>"
        bracket = _bracket("bkt330leg", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        _assert_valid(validate_schema(model))
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: all PASS. If `test_legacy_bracket_with_limitedby_is_valid` fails, read the assertion message — it prints the first schema errors (most likely an ID/IDREF or element-order problem in the fixture); fix the fixture, not the schema.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ocx330_bracket_schema.py
git commit -m "test: 3.3.0 fixture helpers and backward-compat guards"
```

---

### Task 3: Ordered support topology (Support1Limit…Support5Limit)

**Files:**
- Modify: `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` (Bracket_T ~line 1437; insert new declarations directly after Bracket_T's closing `</xs:complexType>`)
- Test: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to the test module:

```python
class TestOrderedSupports:
    def test_ordered_supports_with_lap_are_valid(self, tmp_path):
        text = _stub_330()
        grid = _first_gridref(text)
        topology = (
            f'<ocx:Support1Limit lapped="true">{grid}'
            f'<ocx:Lap numericvalue="0.05" unit="Um"/></ocx:Support1Limit>'
            f"<ocx:Support2Limit>{grid}</ocx:Support2Limit>"
            f"<ocx:Support3Limit>{grid}</ocx:Support3Limit>"
        )
        bracket = _bracket("bkt330sup", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        _assert_valid(validate_schema(model))

    def test_support2_without_support1_is_invalid(self, tmp_path):
        text = _stub_330()
        topology = f"<ocx:Support2Limit>{_first_gridref(text)}</ocx:Support2Limit>"
        bracket = _bracket("bkt330bad", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        result = validate_schema(model)
        assert result.valid is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py::TestOrderedSupports -v`
Expected: both FAIL (`Support1Limit`/`Support2Limit` are unknown elements, so even the "invalid" model fails for the wrong reason — the test asserting `valid is False` may accidentally pass; that is acceptable, the positive test is the driver).

- [ ] **Step 3: Add the new declarations to the 3.3.0 XSD**

Insert directly **after** the closing `</xs:complexType>` of `Bracket_T` (search for `<xs:complexType name="StructurePart_T"` and insert just above it), using TAB indentation:

```xml
	<xs:complexType name="SupportLimit_T">
		<xs:annotation>
			<xs:documentation>Type definition of one ordered bracket support limit. Introduced in 3.3.0. Refers to the connected object (BoundedRef) or a free edge curve, with optional lap information.</xs:documentation>
		</xs:annotation>
		<xs:sequence>
			<xs:choice>
				<xs:element ref="ocx:BoundedRef"/>
				<xs:element ref="ocx:FreeEdgeCurve3D"/>
			</xs:choice>
			<xs:element name="Lap" type="ocx:Quantity_T" minOccurs="0">
				<xs:annotation>
					<xs:documentation>Lap length of this support edge onto the connected object. Absence or a value of 0 means the bracket is trimmed against the connected object.</xs:documentation>
				</xs:annotation>
			</xs:element>
		</xs:sequence>
		<xs:attribute name="lapped" type="xs:boolean" default="false">
			<xs:annotation>
				<xs:documentation>True if the bracket edge is lapped onto the connected object; false (default) if trimmed.</xs:documentation>
			</xs:annotation>
		</xs:attribute>
	</xs:complexType>
	<xs:element name="Support1Limit" type="ocx:SupportLimit_T">
		<xs:annotation>
			<xs:documentation>Connection along the bracket local U arm. Mandatory when ordered supports are used. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:element name="Support2Limit" type="ocx:SupportLimit_T">
		<xs:annotation>
			<xs:documentation>Connection along the bracket local V arm. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:element name="Support3Limit" type="ocx:SupportLimit_T">
		<xs:annotation>
			<xs:documentation>Connection along the U-arm nose. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:element name="Support4Limit" type="ocx:SupportLimit_T">
		<xs:annotation>
			<xs:documentation>Connection along the V-arm nose. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:element name="Support5Limit" type="ocx:SupportLimit_T">
		<xs:annotation>
			<xs:documentation>A fifth support for multi-limit bracket configurations. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:group name="BracketTopology">
		<xs:annotation>
			<xs:documentation>Bracket topology: EITHER the legacy unordered LimitedBy set (DEPRECATED since 3.3.0) OR the ordered Support1Limit..Support5Limit sequence.</xs:documentation>
		</xs:annotation>
		<xs:choice>
			<xs:element ref="ocx:LimitedBy">
				<xs:annotation>
					<xs:documentation>DEPRECATED since 3.3.0 for Bracket: superseded by the ordered SupportNLimit elements. Retained for backward compatibility.</xs:documentation>
				</xs:annotation>
			</xs:element>
			<xs:sequence>
				<xs:element ref="ocx:Support1Limit"/>
				<xs:element ref="ocx:Support2Limit" minOccurs="0"/>
				<xs:element ref="ocx:Support3Limit" minOccurs="0"/>
				<xs:element ref="ocx:Support4Limit" minOccurs="0"/>
				<xs:element ref="ocx:Support5Limit" minOccurs="0"/>
			</xs:sequence>
		</xs:choice>
	</xs:group>
```

- [ ] **Step 4: Use the group in Bracket_T**

In `Bracket_T` (the 3.3.0 copy), replace:

```xml
					<xs:element ref="ocx:LimitedBy" minOccurs="0"/>
```
with
```xml
					<xs:group ref="ocx:BracketTopology" minOccurs="0"/>
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: all PASS, including both `TestBackwardCompatibility` tests (legacy `LimitedBy` path still valid via the group).

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd tests/test_ocx330_bracket_schema.py
git commit -m "feat(xsd-330): ordered Support1-5Limit bracket topology with laps; deprecate LimitedBy on Bracket"
```

---

### Task 4: BracketParameters — bracketShape + multiple FeatureCopes

**Files:**
- Modify: `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` (`BracketParameters_T`, ~line 1649)
- Test: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Write the failing test**

```python
class TestBracketParameters330:
    def test_shape_and_multiple_copes_are_valid(self, tmp_path):
        copes = (
            '<ocx:FeatureCope><ocx:CopeRadius numericvalue="0.03" unit="Um"/></ocx:FeatureCope>'
            '<ocx:FeatureCope><ocx:CopeRadius numericvalue="0.05" unit="Um"/></ocx:FeatureCope>'
        )
        params = _params(extra_elements=copes, extra_attrs=' bracketShape="Triangular"')
        bracket = _bracket("bkt330shape", params)
        model = _write_model(tmp_path, _inject_bracket(_stub_330(), bracket))
        _assert_valid(validate_schema(model))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py::TestBracketParameters330 -v`
Expected: FAIL (attribute `bracketShape` not allowed; second `FeatureCope` not allowed).

- [ ] **Step 3: Edit BracketParameters_T in the 3.3.0 XSD**

Replace:

```xml
			<xs:element ref="ocx:FeatureCope" minOccurs="0"/>
```
with
```xml
			<xs:element ref="ocx:FeatureCope" minOccurs="0" maxOccurs="unbounded">
				<xs:annotation>
					<xs:documentation>Cope features of the bracket. Cardinality raised from 0..1 to 0..n in 3.3.0.</xs:documentation>
				</xs:annotation>
			</xs:element>
```

(Only the `BracketParameters_T` occurrence — `EndCut_T` also references `FeatureCope`; leave that one untouched.)

Then, after the existing line `<xs:attribute ref="ocx:reinforcementType"/>` inside `BracketParameters_T`, add:

```xml
		<xs:attribute name="bracketShape" use="optional">
			<xs:annotation>
				<xs:documentation>Bracket shape classification introduced in 3.3.0. The OuterContour remains authoritative for other shapes.</xs:documentation>
			</xs:annotation>
			<xs:simpleType>
				<xs:restriction base="xs:string">
					<xs:enumeration value="Triangular"/>
					<xs:enumeration value="Rectangular"/>
				</xs:restriction>
			</xs:simpleType>
		</xs:attribute>
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd tests/test_ocx330_bracket_schema.py
git commit -m "feat(xsd-330): bracketShape enum and multiple FeatureCopes on BracketParameters"
```

---

### Task 5: FlangeEdgeReinforcement — snipe angle + flange direction

**Files:**
- Modify: `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` (`FlangeEdgeReinforcement_T`, ~line 1716)
- Test: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Write the failing test**

```python
class TestFlangeEdgeReinforcement330:
    def test_snipe_angle_and_direction_are_valid(self, tmp_path):
        flange = (
            '<ocx:FlangeEdgeReinforcement flangeDirection="AgainstNormal">'
            '<ocx:FlangeWidth numericvalue="0.075" unit="Um"/>'
            '<ocx:Radius numericvalue="0.025" unit="Um"/>'
            '<ocx:FlangeSnipeAngle numericvalue="0.5236" unit="URad"/>'
            "</ocx:FlangeEdgeReinforcement>"
        )
        params = _params(extra_elements=flange).replace(
            'ocx:hasEdgeReinforcement="false"', 'ocx:hasEdgeReinforcement="true"'
        )
        bracket = _bracket("bkt330flg", params)
        model = _write_model(tmp_path, _inject_bracket(_stub_330(), bracket))
        _assert_valid(validate_schema(model))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py::TestFlangeEdgeReinforcement330 -v`
Expected: FAIL (`FlangeSnipeAngle` / `flangeDirection` not allowed).

- [ ] **Step 3: Edit FlangeEdgeReinforcement_T in the 3.3.0 XSD**

The type currently is:

```xml
	<xs:complexType name="FlangeEdgeReinforcement_T">
		<xs:sequence>
			<xs:element ref="ocx:FlangeWidth">…</xs:element>
			<xs:element ref="ocx:Radius">…</xs:element>
		</xs:sequence>
	</xs:complexType>
```

After the `ocx:Radius` element (inside the sequence), add:

```xml
			<xs:element name="FlangeSnipeAngle" type="ocx:Quantity_T" minOccurs="0">
				<xs:annotation>
					<xs:documentation>Snipe angle of the flange end. Absence or a value of 0 means a square flange end. Introduced in 3.3.0.</xs:documentation>
				</xs:annotation>
			</xs:element>
```

After the closing `</xs:sequence>` (before `</xs:complexType>`), add:

```xml
		<xs:attribute name="flangeDirection" use="optional">
			<xs:annotation>
				<xs:documentation>Flange direction relative to the bracket surface normal. Introduced in 3.3.0.</xs:documentation>
			</xs:annotation>
			<xs:simpleType>
				<xs:restriction base="xs:string">
					<xs:enumeration value="WithNormal"/>
					<xs:enumeration value="AgainstNormal"/>
				</xs:restriction>
			</xs:simpleType>
		</xs:attribute>
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd tests/test_ocx330_bracket_schema.py
git commit -m "feat(xsd-330): FlangeSnipeAngle and flangeDirection on FlangeEdgeReinforcement"
```

---

### Task 6: Bracket catalogue and occurrence mode

**Files:**
- Modify: `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd`:
  - `CatalogueBracketRef` after `HoleRef_T` (~line 347)
  - `refType` enumeration (~line 804)
  - `Bracket_T` (~line 1437)
  - `ClassCatalogue_T` (~line 4643) and new catalogue types after `HoleShapeCatalogue_T` (~line 4800)
- Test: `tests/test_ocx330_bracket_schema.py`

- [ ] **Step 1: Write the failing tests**

```python
def _catalogue_xml() -> str:
    return (
        '<ocx:BracketCatalogue id="bktcat330" name="Bracket catalogue">'
        '<ocx:CatalogueBracket id="cbkt1" name="Plate-Plate 300"'
        ' connectionKind="PlatePlate" customerCatalogRefName="VENDOR-BKT-42">'
        + _params()
        + _contour("cbkt1g")
        + "</ocx:CatalogueBracket></ocx:BracketCatalogue>"
    )


def _occurrence_bracket(pid: str) -> str:
    transformation = (
        "<ocx:Transformation>"
        '<ocx:Origin coordinates="0.75 5.08 1.5" unit="Um"/>'
        '<ocx:PrimaryAxis direction="0.0 -1.0 0.0"/>'
        '<ocx:SecondaryAxis direction="0.0 0.0 1.0"/>'
        "</ocx:Transformation>"
    )
    ref = (
        f'<ocx:CatalogueBracketRef localRef="cbkt1" ocx:GUIDRef="{GUID}"'
        ' ocx:refType="ocx:CatalogueBracket"/>'
    )
    return (
        f'<ocx:Bracket id="{pid}" name="BktOcc" ocx:GUIDRef="{GUID}">'
        f"{_MASS}{ref}{transformation}{_MATERIAL}</ocx:Bracket>"
    )


class TestBracketCatalogue:
    def test_catalogue_and_occurrence_are_valid(self, tmp_path):
        text = _stub_330()
        assert "</ocx:ClassCatalogue>" in text
        text = text.replace(
            "</ocx:ClassCatalogue>", _catalogue_xml() + "</ocx:ClassCatalogue>", 1
        )
        text = _inject_bracket(text, _occurrence_bracket("bkt330occ"))
        model = _write_model(tmp_path, text)
        _assert_valid(validate_schema(model))

    def test_occurrence_without_catalogue_ref_target_is_invalid(self, tmp_path):
        """localRef is xs:IDREF: an occurrence pointing nowhere must fail."""
        text = _inject_bracket(_stub_330(), _occurrence_bracket("bkt330orph"))
        model = _write_model(tmp_path, text)
        result = validate_schema(model)
        assert result.valid is False
```

- [ ] **Step 2: Run tests to verify the positive test fails**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py::TestBracketCatalogue -v`
Expected: `test_catalogue_and_occurrence_are_valid` FAILS (`BracketCatalogue` unknown).

- [ ] **Step 3: Add CatalogueBracketRef (after `HoleRef_T`'s closing `</xs:complexType>`, before the `PlateMaterial` element)**

```xml
	<xs:element name="CatalogueBracketRef" type="ocx:CatalogueBracketRef_T" substitutionGroup="ocx:CatalogueRef">
		<xs:annotation>
			<xs:documentation>A reference to a catalogue bracket. Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:complexType name="CatalogueBracketRef_T">
		<xs:annotation>
			<xs:documentation>Type definition of the reference to a catalogue bracket.</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="ocx:CatalogueRef_T">
				<xs:attribute ref="ocx:refType" use="required" fixed="ocx:CatalogueBracket"/>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
```

- [ ] **Step 4: Extend the refType enumeration**

In the `<xs:attribute name="refType">` enumeration (~line 804), after the `ocx:BarSection` enumeration block, add:

```xml
				<xs:enumeration value="ocx:CatalogueBracket">
					<xs:annotation>
						<xs:documentation>A reference to a catalogue bracket. Introduced in 3.3.0.</xs:documentation>
					</xs:annotation>
				</xs:enumeration>
```

- [ ] **Step 5: Add the catalogue types (after `HoleShapeCatalogue_T`'s closing `</xs:complexType>`)**

```xml
	<xs:element name="BracketCatalogue" type="ocx:BracketCatalogue_T">
		<xs:annotation>
			<xs:documentation>Catalogue of standard bracket definitions. Introduced in 3.3.0: bracket occurrences reference catalogue entries via CatalogueBracketRef and a Transformation from the 2D catalogue space to 3D model space.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:complexType name="BracketCatalogue_T">
		<xs:annotation>
			<xs:documentation>Type definition of the catalogue of standard bracket definitions.</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="ocx:DescriptionBase_T">
				<xs:sequence>
					<xs:element ref="ocx:CatalogueBracket" maxOccurs="unbounded"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="CatalogueBracket" type="ocx:CatalogueBracket_T">
		<xs:annotation>
			<xs:documentation>One standard bracket definition holding the invariant data: parameters and the outer contour in 2D catalogue space (z = 0 plane). Introduced in 3.3.0.</xs:documentation>
		</xs:annotation>
	</xs:element>
	<xs:complexType name="CatalogueBracket_T">
		<xs:annotation>
			<xs:documentation>Type definition of one standard bracket definition in the bracket catalogue.</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="ocx:DescriptionBase_T">
				<xs:sequence>
					<xs:element ref="ocx:BracketParameters"/>
					<xs:element ref="ocx:OuterContour">
						<xs:annotation>
							<xs:documentation>The bracket outer contour in 2D catalogue space (z = 0 plane).</xs:documentation>
						</xs:annotation>
					</xs:element>
				</xs:sequence>
				<xs:attribute ref="ocx:GUIDRef"/>
				<xs:attribute name="connectionKind" use="optional">
					<xs:annotation>
						<xs:documentation>Classification of the bracket by the kind of objects it connects.</xs:documentation>
					</xs:annotation>
					<xs:simpleType>
						<xs:restriction base="xs:string">
							<xs:enumeration value="PlatePlate"/>
							<xs:enumeration value="PlateStiffenerWeb"/>
							<xs:enumeration value="PlateStiffenerFlange"/>
							<xs:enumeration value="PlateEdgeReinforcement"/>
							<xs:enumeration value="StiffenerFlangeStiffenerFlange"/>
							<xs:enumeration value="StiffenerWebStiffenerWeb"/>
							<xs:enumeration value="StiffenerEdgeReinforcement"/>
							<xs:enumeration value="EdgeReinforcementEdgeReinforcement"/>
							<xs:enumeration value="MultiLimit"/>
						</xs:restriction>
					</xs:simpleType>
				</xs:attribute>
				<xs:attribute name="customerCatalogRefName" type="xs:string" use="optional">
					<xs:annotation>
						<xs:documentation>Hook for mapping this catalogue entry to a vendor or project bracket catalogue entry.</xs:documentation>
					</xs:annotation>
				</xs:attribute>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
```

- [ ] **Step 6: Register the catalogue in ClassCatalogue_T**

After the `HoleShapeCatalogue` element ref inside `ClassCatalogue_T`'s sequence, add:

```xml
					<xs:element ref="ocx:BracketCatalogue" minOccurs="0">
						<xs:annotation>
							<xs:documentation>Catalogue of standard bracket definitions. Introduced in 3.3.0.</xs:documentation>
						</xs:annotation>
					</xs:element>
```

- [ ] **Step 7: Restructure Bracket_T into two modes**

Replace the entire sequence inside `Bracket_T`'s `<xs:extension base="ocx:StructurePart_T">` (keeping the `functionType` attribute) with:

```xml
				<xs:choice>
					<xs:sequence>
						<xs:annotation>
							<xs:documentation>Mode 1: inline bracket definition.</xs:documentation>
						</xs:annotation>
						<xs:element ref="ocx:BracketParameters"/>
						<xs:element ref="ocx:PlateMaterial"/>
						<xs:element ref="ocx:Offset" minOccurs="0"/>
						<xs:element ref="ocx:OuterContour"/>
						<xs:element ref="ocx:UnboundedGeometry" minOccurs="0"/>
						<xs:group ref="ocx:BracketTopology" minOccurs="0"/>
						<xs:element ref="ocx:CutBy" minOccurs="0"/>
						<xs:element ref="ocx:InnerContour" minOccurs="0" maxOccurs="unbounded"/>
						<xs:element ref="ocx:StiffenedBy" minOccurs="0"/>
					</xs:sequence>
					<xs:sequence>
						<xs:annotation>
							<xs:documentation>Mode 2: occurrence of a catalogue bracket, introduced in 3.3.0. The Transformation maps the 2D catalogue space (z = 0) into 3D model space. The occurrence carries the variable data; the catalogue entry carries the invariant shape and parameters.</xs:documentation>
						</xs:annotation>
						<xs:element ref="ocx:CatalogueBracketRef"/>
						<xs:element ref="ocx:Transformation"/>
						<xs:element ref="ocx:PlateMaterial"/>
						<xs:element ref="ocx:Offset" minOccurs="0"/>
						<xs:element ref="ocx:UnboundedGeometry" minOccurs="0"/>
						<xs:group ref="ocx:BracketTopology" minOccurs="0"/>
						<xs:element ref="ocx:CutBy" minOccurs="0"/>
						<xs:element ref="ocx:InnerContour" minOccurs="0" maxOccurs="unbounded"/>
						<xs:element ref="ocx:StiffenedBy" minOccurs="0"/>
					</xs:sequence>
				</xs:choice>
```

Note: the mode-1 sequence is byte-identical to the pre-task-6 content (including the Task 3 group ref) — only wrapped in the choice. `xs:annotation` must be the first child of `xs:sequence`; if lxml rejects the annotation placement, move the documentation into an XML comment above each sequence instead.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_ocx330_bracket_schema.py -v`
Expected: all PASS (including every earlier inline-bracket test — mode 1 is unchanged).

- [ ] **Step 9: Commit**

```bash
git add ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd tests/test_ocx330_bracket_schema.py
git commit -m "feat(xsd-330): BracketCatalogue, CatalogueBracket and catalogue-occurrence mode on Bracket"
```

---

### Task 7: Docs and full-suite verification

**Files:**
- Modify: `README.md:27`

- [ ] **Step 1: Update README**

Line 27, change `OCX 3.0.0–3.2.0 schemas` to `OCX 3.0.0–3.3.0 schemas`.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest`
Expected: all tests PASS (the offline-compile subprocess test now also covers 3.3.0).

- [ ] **Step 3: Verify the CLI end-to-end**

```powershell
$t = Get-Content tests\data\ocx_320_stubs\ocxxml.3docx -Raw
$t = $t -replace 'V320','V330' -replace 'schemaVersion="3\.2\.0"','schemaVersion="3.3.0"'
Set-Content $env:TEMP\m330.3docx $t -Encoding UTF8
uv run validator validate schema $env:TEMP\m330.3docx
Remove-Item $env:TEMP\m330.3docx
```

Expected: exit code 0, output reports schema 3.3.0 valid. (Also remove any sidecar `.validation.html/.json` files the command writes next to the model.)

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: list OCX 3.3.0 among supported schema versions"
```
