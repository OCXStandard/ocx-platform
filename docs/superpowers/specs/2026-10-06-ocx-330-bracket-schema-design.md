# OCX 3.3.0 Bracket Schema Proposal — Design

**Date:** 2026-10-06
**Source:** OCX-IF Bracket Workshop (March 2026, `ocxIF_BracketWorkshop.pptx`)
**Baseline:** OCX Schema 3.2.0 (`ocx_model_validator/schemas/ocx_320/OCX_Schema.xsd`)

## 1. Purpose

Enhance the OCX Bracket representation for schema version 3.3.0 based on the
limitations identified at the OCX-IF Bracket Workshop, delivering:

1. A concrete, complete **OCX_Schema 3.3.0 XSD** vendored at
   `ocx_model_validator/schemas/ocx_330/OCX_Schema.xsd` so that
   `validator validate schema` works against 3.3.0 models.
2. This document as the human-readable **change proposal** for the OCX-IF.

Runtime support (xsdata bindings, parser/builder for 3.3.0 IR) is **out of
scope** — no 3.3.0 Python data bindings exist yet. This is a schema proposal.

## 2. Workshop limitations → schema changes (traceability)

| # | Limitation in 3.2.0 (workshop slide) | 3.3.0 change |
|---|--------------------------------------|--------------|
| 1 | Bracket topology is an *unordered* `LimitedBy` set; receiving system cannot identify U-arm / V-arm / nose connections (slides 19–20, 28) | Ordered `Support1Limit`…`Support5Limit` elements; `LimitedBy` deprecated on Bracket |
| 2 | No lapped/trimmed property or lap dimension per connected edge (slides 27, 29) | `Lap` quantity + `lapped` flag on each `SupportLimit` |
| 3 | No flange end-cut property (square/sniped) (slide 27) | `FlangeSnipeAngle` on `FlangeEdgeReinforcement` (0/absent = square) |
| 4 | No flange direction w.r.t. bracket normal (slides 17, 27, 29) | `flangeDirection` enum `WithNormal \| AgainstNormal` on `FlangeEdgeReinforcement` |
| 5 | No bracket shape classification (slide 17) | `bracketShape` enum `Triangular \| Rectangular` on `BracketParameters` |
| 6 | Only a single `FeatureCope` per bracket (slide 27) | `FeatureCope` cardinality 0..1 → 0..unbounded |
| 7 | No bracket catalogue; 10,000s of near-identical occurrences bloat the model (~1,850 bytes saved per occurrence, slides 23–26) | `BracketCatalogue` in `ClassCatalogue`; `Bracket` gains a catalogue-occurrence mode (`CatalogueBracketRef` + `Transformation`) |
| 8 | No vendor-catalogue mapping hook for data exchange (slides 7, 15) | `connectionKind` enum + `customerCatalogRefName` attribute on `CatalogueBracket` |
| 9 | Bracket offset from connected object (slide 27) | Already covered: `Offset` exists on `Bracket_T` since 3.2.0 — no change, documented here |

## 3. Design decisions

- **Deliverable form:** full vendored 3.3.0 XSD **and** this proposal document.
- **Compatibility:** *deprecate* — `Bracket` accepts **either** the legacy
  `LimitedBy` **or** the new ordered supports (`xs:choice`); `LimitedBy` on
  Bracket is marked deprecated in its annotation. `LimitedBy_T` itself is
  unchanged (still used by Panel/Plate).
- **Catalogue placement:** `BracketCatalogue` is an optional fourth member of
  the existing `ClassCatalogue` (consistent with Material/XSection/HoleShape).
- **Occurrence representation:** `Bracket` itself becomes a two-mode
  `xs:choice` (inline definition vs. catalogue reference). No new sibling
  element.
- **Topology typing (Option A):** five named elements
  `Support1Limit`…`Support5Limit` sharing one `SupportLimit_T`. Explicit names
  give XSD-enforced ordering and mandatory first support; verbosity cost of
  five near-identical declarations is accepted.

## 4. Schema changes in detail

### 4.1 Topology — `SupportLimit_T` and ordered supports

New complex type:

```xml
<xs:complexType name="SupportLimit_T">
  <xs:sequence>
    <xs:choice>
      <xs:element ref="ocx:BoundedRef"/>
      <xs:element ref="ocx:FreeEdgeCurve3D"/>
    </xs:choice>
    <xs:element name="Lap" type="ocx:Quantity_T" minOccurs="0"/>
      <!-- Lap length of this support edge onto the connected object.
           Absence or 0 means the bracket is trimmed against the object. -->
  </xs:sequence>
  <xs:attribute name="lapped" type="xs:boolean" default="false"/>
</xs:complexType>
```

Five global elements `Support1Limit` … `Support5Limit`, all of type
`ocx:SupportLimit_T`, with annotations documenting the semantics:

- `Support1Limit` — connection along the local **U arm** (mandatory).
- `Support2Limit` — connection along the local **V arm**.
- `Support3Limit` — connection along the **U-arm nose**.
- `Support4Limit` — connection along the **V-arm nose**.
- `Support5Limit` — a fifth support for multi-limit configurations.

Free edges are representable by `FreeEdgeCurve3D` inside a `SupportLimit`.

`Bracket_T` topology content:

```xml
<xs:choice minOccurs="0">
  <xs:element ref="ocx:LimitedBy"/>  <!-- DEPRECATED since 3.3.0 -->
  <xs:sequence>
    <xs:element ref="ocx:Support1Limit"/>
    <xs:element ref="ocx:Support2Limit" minOccurs="0"/>
    <xs:element ref="ocx:Support3Limit" minOccurs="0"/>
    <xs:element ref="ocx:Support4Limit" minOccurs="0"/>
    <xs:element ref="ocx:Support5Limit" minOccurs="0"/>
  </xs:sequence>
</xs:choice>
```

### 4.2 `BracketParameters_T`

- New optional attribute `bracketShape`, enum `Triangular | Rectangular`.
  The `OuterContour` remains authoritative for any other shape.
- `FeatureCope` cardinality: `minOccurs="0" maxOccurs="unbounded"`
  (was `minOccurs="0"` / implicit max 1).
- All existing fields unchanged: `ArmLengthU/V`, `UDirection`, `VDirection`,
  `Origin`, `Unose`, `Vnose`, `FreeEdgeRadius`, `FlangeEdgeReinforcement`,
  attributes `hasEdgeReinforcement`, `numberOfSupports`, `reinforcementType`.

### 4.3 `FlangeEdgeReinforcement_T`

- New optional element `FlangeSnipeAngle` of type `ocx:Quantity_T` (angle);
  absence or value 0 means a square flange end.
- New optional attribute `flangeDirection`, enum `WithNormal | AgainstNormal`
  (flange direction relative to the bracket surface normal).

### 4.4 Bracket catalogue

`ClassCatalogue_T` gains an optional fourth member:

```xml
<xs:element ref="ocx:BracketCatalogue" minOccurs="0"/>
```

```xml
<xs:complexType name="BracketCatalogue_T">   <!-- extends DescriptionBase_T -->
  <xs:sequence>
    <xs:element ref="ocx:CatalogueBracket" maxOccurs="unbounded"/>
  </xs:sequence>
</xs:complexType>

<xs:complexType name="CatalogueBracket_T">   <!-- extends DescriptionBase_T -->
  <xs:sequence>
    <xs:element ref="ocx:BracketParameters"/>   <!-- invariant parameters -->
    <xs:element ref="ocx:OuterContour"/>        <!-- 2D catalogue space, z = 0 plane -->
  </xs:sequence>
  <!-- id / GUIDRef: declare here only if not already inherited from the
       base type chain (EntityBase_T / DescriptionBase_T); verify at
       implementation time against the 3.2.0 base types. -->
  <xs:attribute name="connectionKind" use="optional">
    <!-- enum: PlatePlate, PlateStiffenerWeb, PlateStiffenerFlange,
         PlateEdgeReinforcement, StiffenerFlangeStiffenerFlange,
         StiffenerWebStiffenerWeb, StiffenerEdgeReinforcement,
         EdgeReinforcementEdgeReinforcement, MultiLimit -->
  </xs:attribute>
  <xs:attribute name="customerCatalogRefName" type="xs:string" use="optional"/>
    <!-- Hook for mapping to a vendor/project bracket catalogue entry. -->
</xs:complexType>
```

New reference element following the `HoleRef` pattern:

```xml
<xs:element name="CatalogueBracketRef" type="ocx:CatalogueBracketRef_T"
            substitutionGroup="ocx:CatalogueRef"/>
<xs:complexType name="CatalogueBracketRef_T">
  <xs:complexContent>
    <xs:extension base="ocx:CatalogueRef_T">
      <xs:attribute ref="ocx:refType" use="required" fixed="ocx:CatalogueBracket"/>
    </xs:extension>
  </xs:complexContent>
</xs:complexType>
```

The `ocx:refType` enumeration gains value `ocx:CatalogueBracket`.

### 4.5 `Bracket_T` — two modes

```xml
<xs:complexType name="Bracket_T">
  <xs:complexContent>
    <xs:extension base="ocx:StructurePart_T">
      <xs:choice>
        <!-- Mode 1: inline definition (3.2.0 content + new topology choice) -->
        <xs:sequence>
          <xs:element ref="ocx:BracketParameters"/>
          <xs:element ref="ocx:PlateMaterial"/>
          <xs:element ref="ocx:Offset" minOccurs="0"/>
          <xs:element ref="ocx:OuterContour"/>
          <xs:element ref="ocx:UnboundedGeometry" minOccurs="0"/>
          <!-- topology choice from §4.1 -->
          <xs:element ref="ocx:CutBy" minOccurs="0"/>
          <xs:element ref="ocx:InnerContour" minOccurs="0" maxOccurs="unbounded"/>
          <xs:element ref="ocx:StiffenedBy" minOccurs="0"/>
        </xs:sequence>
        <!-- Mode 2: catalogue occurrence -->
        <xs:sequence>
          <xs:element ref="ocx:CatalogueBracketRef"/>
          <xs:element ref="ocx:Transformation"/>
            <!-- Maps the 2D catalogue space (z = 0) into 3D model space. -->
          <xs:element ref="ocx:PlateMaterial"/>
          <xs:element ref="ocx:Offset" minOccurs="0"/>
          <xs:element ref="ocx:UnboundedGeometry" minOccurs="0"/>
          <!-- topology choice from §4.1 -->
          <xs:element ref="ocx:CutBy" minOccurs="0"/>
          <xs:element ref="ocx:InnerContour" minOccurs="0" maxOccurs="unbounded"/>
          <xs:element ref="ocx:StiffenedBy" minOccurs="0"/>
        </xs:sequence>
      </xs:choice>
      <xs:attribute ref="ocx:functionType"/>
    </xs:extension>
  </xs:complexContent>
</xs:complexType>
```

Occurrence carries the *variable* data (material/thickness, supports, cuts,
stiffening, inner contours); the catalogue entry carries the *invariant*
shape and parameters — the split from workshop slide 24. `MassProperties`
and `ExternalGeometryRef` remain per-occurrence via `StructurePart_T`.

### 4.6 Version bookkeeping

- Root `xs:schema` `version` attribute → `3.3.0`.
- The fixed/default value of the `schemaVersion` attribute → `3.3.0`.
- Header comment documents the 3.3.0 bracket changes.
- `unitsmlSchema_lite-0.9.18.xsd` copied unchanged into `ocx_330/`.

## 5. Repository integration

- New directory `ocx_model_validator/schemas/ocx_330/` with the two XSDs
  (package data; covered by the existing `schemas/` packaging glob —
  verify, and update `pyproject.toml`/`validation/schema.py` if any
  version list is hardcoded).
- `validator validate schema model.3docx` must resolve a model declaring
  `schemaVersion="3.3.0"` to the new XSD.

## 6. Success criteria

1. The 3.3.0 XSD compiles offline with lxml via the existing
   `validation/schema.py` loader.
2. Positive fixtures validate against 3.3.0:
   - inline bracket using `Support1Limit`–`Support3Limit` with `Lap`,
     `lapped`, `bracketShape`, `FlangeSnipeAngle`, `flangeDirection`,
     and two `FeatureCope`s;
   - catalogue: `BracketCatalogue` + `CatalogueBracket`, and a `Bracket`
     occurrence using `CatalogueBracketRef` + `Transformation`;
   - legacy bracket using `LimitedBy` (deprecated path still valid).
3. Negative fixture fails: `Support2Limit` present without `Support1Limit`.
4. A valid 3.2.0 bracket document, re-labelled 3.3.0, still validates
   (deprecation, not removal).
5. Existing test suite (`uv run pytest`) still passes.

## 7. Out of scope

- xsdata Python bindings for 3.3.0 and parser/builder/IR support.
- Bracket test *models* (workshop slide 30) beyond the validation fixtures above.
- Panel/Plate topology changes — `LimitedBy_T` is untouched.
