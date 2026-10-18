# OCX Rule Checks — Phase A (Content Checks) Design

Date: 2026-10-18
Status: approved
Predecessor: `2026-10-18-ocx-rule-validation-design.md` (step 1: engine + 36 rule stubs, merged to master)

## Goal

Implement real check logic for the 24 best-practice rules that do **not**
require `ocx-geometry`: all `identity`, `document`, `references` and
`curves_surfaces` rules plus OCX-PROP-004. The 12 geometry rules (topology
9, properties 3) remain stubs and are deferred to Phase B.

Phase A rule set:

| Category | Rules | Checks |
|---|---|---|
| identity | OCX-ID-001..005 | 3 custom + 2 primitive (`unique`) |
| document | OCX-DOC-001..005 | 5 custom |
| references | OCX-REF-001..008 | 5 custom + 3 primitive (`ref_resolves`, `cardinality` ×2) |
| curves_surfaces | OCX-GEO-001..005 | 5 custom (pure XML numeric) |
| properties | OCX-PROP-004 | 1 custom (IR-based) |

OCX-REF-005 and OCX-PROP-004 use the parsed IR (`context.vessel`) but no
geometry math — they are in scope.

## Architecture

### XmlIndex (new module `ocx_rules/xml_index.py`)

A lazily-built, cached index over the lxml tree so that identity/reference
checks share one document scan:

- `ElementInfo` (frozen dataclass): `tag` (localname), `id`, `guid`, `name`,
  `sourceline`.
- `XmlIndex.build(tree)` produces:
  - `nsmap` — `{"ocx": <root namespace>, "xsi": ..., "unitsml": ...}` detected
    from the document root. Rules written with the `ocx:` prefix therefore
    work for OCX 3.x and the legacy 2.8.6 namespace alike.
  - `by_id` / `by_guid` — first occurrence maps value → `ElementInfo`;
    `duplicate_ids` / `duplicate_guids` list every extra occurrence.
  - `refs` — every attribute whose localname ends in `Ref` (except
    `GUIDRef`): `RefInfo(attr, value, owner: ElementInfo)`.
  - `xpath(expr)` — evaluates an expression with `nsmap`.
- `ValidationContext` gains `cached_property xml_index` (lazy, mirrors
  `xml_tree` / `vessel`).

### Check code layout

`packs/best_practice/checks.py` becomes a thin facade re-exporting from a new
`packs/best_practice/checks/` package split by category: `identity.py`,
`document.py`, `references.py`, `curves.py`, `properties.py`, plus
`geometry_stubs.py` holding the 12 remaining `_stub(...)` definitions. All
TOML `custom = "ocx_rules.packs.best_practice.checks:<name>"` references stay
unchanged.

Primitive implementations replace the stubs in `primitives/content.py` and
`primitives/references.py`; `primitives/geometry.py` stays stubbed.

`Finding.location` is populated with the lxml `sourceline` everywhere.

## Primitive semantics

Signature unchanged: `(context, params) -> list[Finding]`; empty list = pass.

| Primitive | Params | Check |
|---|---|---|
| `has_attribute` | `xpath`, `attribute` | each matched element carries a non-empty attribute (ns-aware) |
| `unique` | `xpath`, `key` | one Finding per duplicated key value, listing all source lines |
| `cardinality` | `xpath`, `child`, `min?`, `max?` | per matched element, child count within bounds |
| `value_in_set` | `xpath`, `key`, `allowed` | key value is a member of `allowed` |
| `sequence` | `xpath`, `key`, `order="non_decreasing"`, `max_run?` | space-separated numeric list obeys ordering / max repetition |
| `ref_resolves` | `ref_attribute` (glob, e.g. `*Ref`), `target_xpath?` | every indexed `*Ref` value resolves to an existing `id` or `GUIDRef`; Finding names attr, value, owner, line |

`ref_resolves` resolves against the union of ids and GUIDs (OCX references
may use either). Zero matched elements = pass (vacuous truth, consistent
with XSD semantics).

## Custom check semantics (19 implementations)

**identity**
- `entitybase_has_guid_and_id` (ID-001): every element of the EntityBase tag
  set (Vessel, Panel, Plate, Stiffener, Bracket, Pillar, Compartment, Seam,
  Material/Steel/Aluminium, ...) carries both `GUIDRef` and `id`.
- `idbase_has_id` (ID-004): curve/surface tag set carries `id`.
- `names_not_identifiers` (ID-005, info): report name collisions — elements
  whose `name` duplicates another element's name while their ids differ.
  Conservative heuristic; reports collisions only.

**document**
- `schema_location_tuple` (DOC-001): parse `xsi:schemaLocation` pairs; the
  OCX namespace must be present, mismatched pair → finding.
- `root_declarations` (DOC-002): root has `schemaVersion` and declares the
  ocx and xsi namespaces.
- `unit_definitions` (DOC-003): every `Unit` has a unique id and a
  `UnitName`; missing `UnitSymbol` → warning-text finding.
- `unit_refs_resolve` (DOC-004): every unit/dimension ref attribute resolves
  to a declared UnitsML definition.
- `enumerated_root_units` (DOC-005, warning): units whose symbol matches a
  known UnitsML root-unit enumeration should use the enumerated id.

**references**
- `stiffener_end_configurations` (REF-003): per Stiffener, at most two end
  configurations and no duplicated end position.
- `slot_lug_plate_refs` (REF-004): slots with two lug plates carry exactly
  two `LugPlateRef`.
- `explicit_connectivity` (REF-005, ir): structural parts whose IR
  `limited_by`/connection lists are empty while sibling parts have them →
  finding (heuristic, clearly worded).
- `panel_as_occurrence_group` (REF-007): every Panel GUID appears as an
  OccurrenceGroup reference in a DesignView, never as a direct Occurrence
  reference.
- `hole_single_representation` (REF-008, warning): a hole GUID referenced
  from `CutBy` must not also be embedded in an `OuterContour`.

**curves_surfaces** (pure XML numeric, no geometry kernel)
- `nurbs_control_points` (GEO-001): control-point count >= degree + 1.
- `nurbs_knots_non_decreasing` (GEO-002): knot vectors non-decreasing.
- `nurbs_knot_multiplicity` (GEO-003): knot multiplicity <= degree.
- `polyline_closed` (GEO-004): closed Polyline3D first == last point within
  `tolerance_mm`.
- `catalogue_holes_planar` (GEO-005, warning): catalogue hole contour points
  have Z ~ 0 within `tolerance_mm`.

**properties**
- `renewal_thickness_on_instance` (PROP-004, ir): plates whose renewal
  thickness exists only on a shared definition, not on the instance.

## Error handling

Checks never raise for malformed content: missing or unparsable
attributes/values yield findings or make the element not-applicable. The
manager's per-rule crash isolation remains the backstop. 2.8.6 documents are
handled through the dynamic namespace map.

## Testing

**Unit tests** — one module per check module
(`test_rules_primitives_impl.py`, `test_rules_checks_identity.py`, ...).
Fixtures are small inline OCX XML strings via a shared builder
(`tests/rules_xml.py` wraps fragments in a 3.1.0 root with correct
namespaces). Every check gets at least one passing and one failing fixture,
asserting finding count, message content and source line. Existing stub
tests asserting `CheckNotImplemented` for the 24 Phase A rules are updated;
geometry stub tests stay.

**Integration test** — `tests/test_rules_corpus.py`, marked `integration`
(deselected by default): iterates every `models/**/*.3docx`, runs the full
RuleManager, asserts no rule reports CRASHED on any model, and logs a
per-model status summary for manual inspection. Reference models are
expected to fail some rules — failures are acceptable; crashes are not.

## Definition of done

- All 24 Phase A rules report real PASSED/FAILED on stub and corpus models;
  the 12 geometry rules remain NOT_IMPLEMENTED.
- `validator validate rules models/D-VLCC_1-HOLD-OCX-simple_v3.3docx`
  produces a meaningful report.
- Full test suite and `ruff check .` green.
- Integration corpus run: zero CRASHED rules across all models.
