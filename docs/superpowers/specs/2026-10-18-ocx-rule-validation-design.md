# OCX Rule-Based Validation — Design Spec

Date: 2026-10-18
Status: Approved
Scope: Step 1 — rule engine framework + declarative rule catalogue. Rule check
implementations follow in a later step.

## 1. Goal

Extend OCX validation beyond strict XSD validation with configurable
best-practice rules sourced from the OCX wiki
(`C:\PythonDev\ocx-wiki\out\wiki-writer`). Each rule has executable code (a
callable) that validates a model and returns valid / not valid with reasons.
Rules are maintainable without detailed Python knowledge: rule definitions are
declarative data files that parameterize a library of check primitives, with a
custom-callable escape hatch for complex checks.

## 2. Decisions made

| Decision | Choice |
| --- | --- |
| Location | New workspace package `ocx-rules` (validator depends on it) |
| Rule input | `ValidationContext` carrying lazy lxml tree + lazy `IrVessel` |
| Plugin discovery | Python entry points, group `ocx_rules.packs` |
| User configuration | TOML file (enable/disable, severity overrides, parameters) |
| Rule definition | Declarative TOML catalogue + check primitives + custom callables |
| Severities | ERROR / WARNING / INFO (wiki shall / should / informative) |
| CLI | `validator validate rules model.3docx` (schema validation stays separate) |
| Step-1 scope | Framework + full catalogue as registered stubs; no check logic yet |

## 3. Architecture

### 3.1 Package layout

```
packages/ocx-rules/src/ocx_rules/
├── __init__.py          ← public API: RuleManager, ValidationContext, RuleResult, …
├── model.py             ← frozen dataclasses: RuleSpec, RuleResult, Finding, Severity, …
├── context.py           ← ValidationContext (lazy lxml tree + lazy IrVessel + model path)
├── catalogue.py         ← load/validate declarative rule TOML files → RuleSpec objects
├── primitives/          ← check-primitive library, one module per family
│   ├── __init__.py      ← PRIMITIVE_REGISTRY: name → callable
│   ├── content.py       ← has_attribute, unique, cardinality, value_in_set, sequence…
│   ├── references.py    ← ref_resolves, no_dangling_refs…
│   └── geometry.py      ← closed_contour, normals_consistent… (lazy ocx-geometry import)
├── manager.py           ← RuleManager: entry-point discovery, config, filtering, execution
├── config.py            ← user TOML config: enable/disable, severity overrides, parameters
└── packs/
    └── best_practice/   ← built-in rule pack
        ├── rules/*.toml ← the catalogue (one file per category)
        └── checks.py    ← custom callables for complex rules (stubs in step 1)
```

Dependencies: `ocx-rules` → `ocx-model-core`; `ocx_rules.primitives.geometry`
imports `ocx-geometry` lazily so content-only validation never loads the numpy
stack. `ocx-model-validator` → `ocx-rules` for the CLI subcommand and report
generator. `ocx-rules` never imports from the validator or render packages.

### 3.2 Execution flow

```
validator validate rules model.3docx
    → RuleManager.discover()            # entry points "ocx_rules.packs"
    → catalogue.load(pack)              # TOML files → RuleSpec, validated at load
    → config.apply(user ocx-rules.toml) # disable, severity override, params
    → for each enabled rule:
          bind primitive or custom callable with params
          execute against ValidationContext
    → collect RuleResults → reporting renderers (rich / markdown / html)
```

Exit codes mirror schema validation: 0 no findings, 1 findings at ERROR (or
any findings when `--strict` is later added — out of scope now), 2 cannot run
(file missing, unparsable catalogue).

### 3.3 Execution semantics

- Each rule executes independently. An exception in one rule produces a
  `RuleResult` with status `CRASHED` (message captured); the run continues.
- Rules whose `requires` cannot be satisfied (e.g. IR build failed, geometry
  unavailable) get status `SKIPPED` with a reason.
- Rules whose check is not yet implemented return status `NOT_IMPLEMENTED`.
- `ValidationContext.xml_tree` and `.vessel` are lazy cached properties: a run
  containing only XML rules never builds the IR.

## 4. Data model (`model.py`, all frozen dataclasses)

- `Severity`: `ERROR | WARNING | INFO`
- `RuleStatus`: `PASSED | FAILED | NOT_IMPLEMENTED | SKIPPED | CRASHED`
- `RuleSpec`: `rule_id`, `title`, `description`, `category`, `severity`,
  `source` (wiki page name), `requires` (subset of `{"xml","ir","geometry"}`),
  `check` (primitive name or custom callable reference), `params: dict`
- `Finding`: one violation — `message`, `element_id`, `guid`, `location`
  (XML line number when available)
- `RuleResult`: `spec`, `status`, `findings: list[Finding]`, `duration_ms`

Check callable signature:
`(context: ValidationContext, params: dict) -> list[Finding]`
(empty list = passed). A `NotImplementedCheck` sentinel marks stubs.

## 5. Rule file format

One TOML file per category under `packs/best_practice/rules/`.

```toml
[[rule]]
id          = "OCX-ID-002"
title       = "GUIDs must be unique"
description = "Duplicate GUIDRef values must not identify different objects."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]

[rule.check]
primitive = "unique"
xpath     = "//*[@ocx:GUIDRef]"
key       = "@ocx:GUIDRef"
```

Complex rules reference a custom callable instead:

```toml
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:panel_limited_by_closed"
tolerance_mm = 1.0
```

All keys in `[rule.check]` other than `primitive`/`custom` become `params`.
`catalogue.py` validates at load time: unknown primitive, unimportable custom
reference, duplicate rule id, invalid severity/category/requires → hard error
before any rule runs.

## 6. User configuration

Optional `ocx-rules.toml`, located via `--config FILE` or current directory:

```toml
[rules]
disable = ["OCX-PROP-001"]

[rules.overrides.OCX-TOP-001]
severity     = "warning"
tolerance_mm = 0.5
```

Overrides may change severity and any check parameter; they cannot change the
check itself.

## 7. Plugin model

- Entry-point group `ocx_rules.packs`; each entry point resolves to a callable
  returning a `RulePack` (name, version, iterable of `RuleSpec`).
- The built-in `best_practice` pack is registered the same way by `ocx-rules`
  itself, so third-party packs are first-class.
- `RuleManager.discover()` loads all packs; duplicate rule ids across packs are
  a load-time error.

## 8. CLI

```
validator validate rules model.3docx [--config FILE] [--category CAT]
                                     [--rule ID] [--max-findings N]
                                     [--destination out.md|out.html]
```

Rich output to stdout by default; markdown/html via `--destination`, reusing
the existing `reporting/renderers`.

## 9. Rule catalogue (step 1 content)

Severity mapping: shall/must → error, should/recommended → warning,
informative → info. Source column names the wiki page folder.

### Category `identity` (content-only)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-ID-001 | Every EntityBase-derived object carries GUIDRef and id | error | guidsidsandnames |
| OCX-ID-002 | GUIDs are unique within the document | error | guidsidsandnames |
| OCX-ID-003 | Local ids are unique within the document | error | guidsidsandnames |
| OCX-ID-004 | IDBase-derived geometry carries a local id | error | guidsidsandnames |
| OCX-ID-005 | Names are not used as identifiers (duplicates allowed) | info | guidsidsandnames |

### Category `document` (content-only)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-DOC-001 | Root xsi:schemaLocation contains the (namespace, XSD location) tuple | error | schema_root_element |
| OCX-DOC-002 | schemaVersion, xmlns:ocx and xmlns:xsi are present on the root | error | schema_root_element |
| OCX-DOC-003 | Every Unit has a unique id and UnitName (missing UnitSymbol → warning) | error | units |
| OCX-DOC-004 | Unit and Dimension references resolve to declared definitions | error | units |
| OCX-DOC-005 | Enumerated UnitsML root units are used when available | warning | units |

### Category `references` (cross-reference resolution)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-REF-001 | All *Ref attributes resolve to existing objects | error | topology |
| OCX-REF-002 | Every Panel contains at least one Plate (ComposedOf) | error | panel |
| OCX-REF-003 | A Stiffener has at most two end configurations, one per end | error | endconfiguration |
| OCX-REF-004 | A two-lug slot has exactly two LugPlateRef references | error | slots |
| OCX-REF-005 | Structural connectivity is encoded explicitly via references | error | structural_connectivity |
| OCX-REF-006 | Exactly one root/global CoordinateSystem exists | error | coordinatesystem |
| OCX-REF-007 | A Panel is represented as OccurrenceGroup, never as a direct Occurrence | error | designview |
| OCX-REF-008 | A hole/slot appears in only one representation (CutBy xor OuterContour) | warning | holeshapecatalogue |

### Category `curves_surfaces` (content + light numeric checks)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-GEO-001 | NURBS control-point count ≥ degree + 1 | error | nurbs |
| OCX-GEO-002 | NURBS knot vectors are non-decreasing | error | nurbs |
| OCX-GEO-003 | NURBS knot multiplicity ≤ degree | error | nurbs |
| OCX-GEO-004 | Closed Polyline3D repeats its first point; adjacent segments coincide | error | polyline3d |
| OCX-GEO-005 | Catalogue hole contours are 2-D (Z = 0) and centered at the origin | warning | pararmetricholesandholeshapecatalogue |

### Category `topology` (geometry computation)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-TOP-001 | Panel LimitedBy resolves to one closed contour | error | panel |
| OCX-TOP-002 | CompositeCurve3D segments are ordered end-to-end and continuous | error | compositecurve3d |
| OCX-TOP-003 | Hole contours are closed | error | holeshapecatalogue |
| OCX-TOP-004 | A hole does not split a plate into disjoint regions | error | holeshapecatalogue |
| OCX-TOP-005 | Seams never connect boundary↔hole, seam↔hole or hole↔hole; the seam pattern yields closed plate contours | error | seamsandopenings |
| OCX-TOP-006 | CompartmentFace/ContourBound curves are closed; CellBoundary forms a closed volume | error | compartment |
| OCX-TOP-007 | Compartments do not physically overlap | warning | compartment |
| OCX-TOP-008 | Surface-collection normals are consistently oriented; boundary loops are closed with inner/outer distinguished | error | surfacecollectionnormals, surfaceinnerandouterboundaries |
| OCX-TOP-009 | Stiffener inclinations: no duplicate positions, no web/flange vector flips | error | inclination |

### Category `properties` (geometry + materials)

| Id | Rule | Severity | Source |
| --- | --- | --- | --- |
| OCX-PROP-001 | Plate weight ≈ area × thickness × density within tolerance | warning | property_validation |
| OCX-PROP-002 | Panel weight/CoG consistent with its composed parts | warning | property_validation |
| OCX-PROP-003 | Profile parameters (e.g. bulb flat) reproduce a closed section contour | error | bulbflatparameters |
| OCX-PROP-004 | Renewal thickness is assigned to the part instance, not only a shared definition | error | renewal_thickness |

36 rules total. Categories `identity`, `document`, `references`,
`curves_surfaces` are mostly expressible via primitives; `topology` and
`properties` are mostly custom callables (all stubs in step 1).

## 10. Check-primitive library (signatures in step 1; implementations step 2)

| Primitive | Family | Typical params |
| --- | --- | --- |
| `has_attribute` | content | `xpath`, `attribute` |
| `unique` | content | `xpath`, `key` |
| `cardinality` | content | `xpath`, `child`, `min`, `max` |
| `value_in_set` | content | `xpath`, `key`, `allowed` |
| `sequence` | content | `xpath`, `key`, `order` (`non_decreasing`), `max_run` |
| `ref_resolves` | references | `ref_attribute`, `target_xpath` |
| `closed_contour` | geometry | `target`, `tolerance_mm` |
| `normals_consistent` | geometry | `target`, `angle_tolerance_deg` |

Primitives registered in `PRIMITIVE_REGISTRY`. Geometry primitives import
`ocx-geometry` inside the function body.

## 11. Testing (shared `tests/` suite)

- `test_rules_catalogue.py` — every shipped TOML loads; ids unique; primitive
  and custom references importable; severities/categories valid; every rule
  has source and description.
- `test_rules_manager.py` — entry-point discovery finds the built-in pack;
  config disable/override works; a crashing rule yields `CRASHED` without
  aborting the run; unsatisfied `requires` yields `SKIPPED`.
- `test_rules_context.py` — laziness: an XML-only run never builds the IR
  (asserted via monkeypatched builder).
- `test_rules_primitives.py` — primitive signatures/registry; behaviour tests
  against the existing `ocx_*_stubs` fixtures as implementations land.
- CLI smoke test — `validate rules` on a stub model exits 0/1/2 correctly and
  renders rich and markdown output.

## 12. Step-1 definition of done

1. `ocx-rules` package added to the uv workspace; `uv sync --dev` clean.
2. All 36 rules defined in TOML with full metadata; custom-check rules
   reference stub callables returning `NOT_IMPLEMENTED`.
3. Primitive registry with defined signatures; implementations may be stubs.
4. RuleManager end-to-end (discover → configure → execute → report) exercised
   by tests.
5. `validator validate rules` wired with rich/markdown/html output and exit
   codes 0/1/2.
6. All tests pass; ruff clean.

## 13. Out of scope (later steps)

- Implementing the check primitives and custom geometry checks (step 2+).
- Third-party rule-pack examples, `--strict` mode, MCP-server exposure,
  cross-document GUID consistency for partial transfers / model merge.
