# Schema-support markers for best-practice rules — design

**Date:** 2026-10-25
**Status:** approved

## Goal

Rules may not be valid for every supported OCX schema version. Add a
declarative schema-support marker to the TOML rule definitions so the rule
runner skips rules that do not apply to the loaded 3Docx model's schema
version, instead of producing misleading PASS results.

## Evidence base

All five vendored XSDs (`ocx_286`, `ocx_300`, `ocx_301`, `ocx_310`,
`ocx_320` under `packages/ocx-model-core/src/ocx_model_core/schemas/`) were
checked for every element/attribute the 36 rules inspect:

- `XmlIndex` binds the `ocx:` prefix to the document root's actual namespace,
  so xml rules are namespace-agnostic across 2.8.6 and 3.x.
- IR/geometry rules go through the version-normalizing builders
  (e.g. `PhysicalProperties` → `IrMassProperties`), so they are
  version-neutral by construction.
- Every inspected element exists in all five schemas with one exception:
  **`RenewalThickness` exists only in 3.2.0 (and 3.3.0)** — rule OCX-PROP-004
  scans the XML for it and would silently PASS on older schemas that cannot
  contain it.

## TOML marker

Optional per-rule key, a list of `major.minor` prefix strings:

```toml
[[rule]]
id      = "OCX-PROP-004"
schemas = ["3.2", "3.3"]
```

- **Omitted** means the rule applies to **all** schema versions (the default;
  markers are only added where support is restricted).
- Each entry must match `^\d+\.\d+$`; anything else (wrong type, empty list,
  malformed entry, duplicates) is a load-time `CatalogueError`.
- A model whose `schemaVersion` is `X.Y.Z` matches an entry `"X.Y"`.

## Components

1. **`model.py`** — `RuleSpec` gains `schemas: frozenset[str] | None = None`
   (`None` = unrestricted). Frozen dataclass, keyword default, no other model
   changes.
2. **`catalogue.py`** — `_parse_rule` parses and validates the optional
   `schemas` key (list of unique `major.minor` strings; empty list invalid)
   and passes it to `RuleSpec`.
3. **`context.py`** — `ValidationContext.schema_version` cached property:
   reads the `schemaVersion` attribute from the XML root (cheap; no IR
   build). Returns the raw string or `None` when absent/unreadable.
4. **`manager.py`** — `RuleManager._unsatisfied` gains a schema check (before
   the existing requirement checks): when `spec.schemas` is not `None`,
   derive `major.minor` from `context.schema_version`;
   - no match → skip with reason
     `"not applicable to schema <version>"`;
   - version undetectable (missing attribute or unparseable document) → skip
     with reason `"schema version unknown"`.
   Unrestricted rules (`schemas is None`) never consult the version.
5. **`packs/best_practice/rules/properties.toml`** — add
   `schemas = ["3.2", "3.3"]` to OCX-PROP-004. No other rule gets a marker
   (all 35 remaining rules apply to 2.8/3.0/3.1/3.2 per the evidence above).

## Reporting

Reuses `RuleStatus.SKIPPED` with the reasons above. No changes to the status
model, renderers, CLI, or exit codes (skips already do not affect exit
codes).

## Testing

TDD throughout (failing test first):

- Catalogue: `schemas` parsed to frozenset; omitted → `None`; invalid type /
  malformed entry / empty list → `CatalogueError`.
- Context: `schema_version` from a stub model root; `None` when attribute
  missing.
- Manager: restricted rule runs on matching version; SKIPPED with
  `not applicable…` reason on non-matching version; SKIPPED with
  `schema version unknown` when version undetectable; unrestricted rule
  unaffected.
- Pack regression: loading the best-practice pack still yields 36 rules and
  OCX-PROP-004 carries `frozenset({"3.2", "3.3"})`.

## Boundaries

- No new statuses, config keys, or CLI flags.
- No behavior change for any rule without a marker.
- Rule documentation pages in the external wiki store are out of scope for
  this change (the marker surface may be added to the pages in a later pass).
