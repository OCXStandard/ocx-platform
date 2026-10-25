# Rule Schema-Support Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `schemas = ["X.Y", ...]` marker to TOML rule definitions so the rule runner skips rules not applicable to the loaded model's schema version.

**Architecture:** Four small, sequential changes along the existing load→filter→execute pipeline: `RuleSpec.schemas` field (model), TOML parsing/validation (catalogue), lazy `schema_version` on `ValidationContext`, and a skip check in `RuleManager._unsatisfied`. One catalogue change: `OCX-PROP-004` gets `schemas = ["3.2", "3.3"]`. Reuses `RuleStatus.SKIPPED` — no renderer/CLI/exit-code changes.

**Tech Stack:** Python 3.11+ (dataclasses, tomllib, lxml), pytest, uv. All commands run from repo root `C:\PythonDev\ocx-platform`.

**Spec:** `docs/superpowers/specs/2026-10-25-rule-schema-markers-design.md`

---

### Task 1: `ValidationContext.schema_version`

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\context.py`
- Test: `tests\test_rules_context.py`

- [ ] **Step 1: Write the failing tests** — append to `TestValidationContext` in `tests\test_rules_context.py`:

```python
    def test_schema_version_read_from_root(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        assert ctx.schema_version == "3.1.0"

    def test_schema_version_none_when_attribute_missing(self, tmp_path: Path):
        doc = tmp_path / "nov.3docx"
        doc.write_text("<root><a/></root>")
        ctx = ValidationContext(doc)
        assert ctx.schema_version is None

    def test_schema_version_none_when_unparseable(self, tmp_path: Path):
        doc = tmp_path / "bad.3docx"
        doc.write_text("<root><unclosed></root>")
        ctx = ValidationContext(doc)
        assert ctx.schema_version is None
```

Note: `vessel_stub` is the existing fixture (`stub_dir_310 / "ocxxml.3docx"`); the 3.1.0 stub root carries `schemaVersion="3.1.0"` (verify the literal in the stub file first; if it differs, assert the actual value).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules_context.py -k schema_version -v`
Expected: 3 FAILED with `AttributeError: 'ValidationContext' object has no attribute 'schema_version'`

- [ ] **Step 3: Implement** — add to `ValidationContext` in `context.py` (after `xml_tree`):

```python
    @cached_property
    def schema_version(self) -> str | None:
        """The model's declared schemaVersion, or None when undetectable."""
        try:
            return self.xml_tree.getroot().get("schemaVersion")
        except Exception as exc:
            logger.debug("Cannot determine schema version: {}", exc)
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_context.py -v`
Expected: all PASS (new 3 + existing 6)

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/context.py tests/test_rules_context.py
git commit -m "feat(ocx-rules): expose model schemaVersion on ValidationContext" --no-verify
```

(Include the standard Co-authored-by trailer.)

---

### Task 2: `RuleSpec.schemas` + catalogue parsing/validation

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\model.py` (RuleSpec)
- Modify: `packages\ocx-rules\src\ocx_rules\catalogue.py` (`_parse_rule`)
- Test: `tests\test_rules_catalogue.py`

- [ ] **Step 1: Write the failing tests** — append to `tests\test_rules_catalogue.py`:

```python
SCHEMA_RULE = '''
[[rule]]
id          = "OCX-TST-003"
title       = "Version-restricted rule"
description = "Only applies to newer schemas."
source      = "unittest"
category    = "properties"
severity    = "error"
requires    = ["xml"]
schemas     = ["3.2", "3.3"]

[rule.check]
primitive = "unique"
xpath     = "//*[@id]"
key       = "@id"
'''


class TestSchemasMarker:
    def test_schemas_parsed_to_frozenset(self):
        (spec,) = parse_rules_toml(SCHEMA_RULE, source_name="t.toml")
        assert spec.schemas == frozenset({"3.2", "3.3"})
        assert "schemas" not in spec.params

    def test_schemas_omitted_means_none(self):
        (spec,) = parse_rules_toml(VALID_RULE, source_name="t.toml")
        assert spec.schemas is None

    @pytest.mark.parametrize("bad", [
        'schemas     = "3.2"',          # not a list
        'schemas     = []',             # empty list
        'schemas     = ["3.2", "3.2"]', # duplicates
        'schemas     = ["3"]',          # not major.minor
        'schemas     = ["3.2.0"]',      # full version, not prefix
        'schemas     = ["v3.2"]',       # malformed
        'schemas     = [32]',           # wrong element type
    ])
    def test_invalid_schemas_raise(self, bad):
        toml = SCHEMA_RULE.replace('schemas     = ["3.2", "3.3"]', bad)
        with pytest.raises(CatalogueError):
            parse_rules_toml(toml, source_name="t.toml")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules_catalogue.py::TestSchemasMarker -v`
Expected: `test_schemas_parsed_to_frozenset` FAILS with `AttributeError: ... no attribute 'schemas'`; `test_schemas_omitted_means_none` FAILS likewise; the 7 invalid cases FAIL with `DID NOT RAISE` (the loader currently ignores unknown top-level keys — verify this is the actual failure mode; if `schemas` leaks into nothing, the test output will show it).

- [ ] **Step 3: Implement**

In `model.py`, add the field to `RuleSpec` (after `params`):

```python
    #: Supported schema families as "major.minor" prefixes; None = all versions.
    schemas: frozenset[str] | None = None
```

In `catalogue.py`, add a module-level regex and parse helper, and wire it into `_parse_rule`:

```python
import re

_SCHEMA_PREFIX_RE = re.compile(r"^\d+\.\d+$")


def _parse_schemas(raw: dict, rule_id: str, source_name: str) -> frozenset[str] | None:
    if "schemas" not in raw:
        return None
    value = raw["schemas"]
    if not isinstance(value, list) or not value:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} 'schemas' must be a non-empty list")
    for entry in value:
        if not isinstance(entry, str) or not _SCHEMA_PREFIX_RE.match(entry):
            raise CatalogueError(
                f"{source_name}: rule {rule_id!r} has invalid schema prefix "
                f"{entry!r} (expected 'major.minor', e.g. '3.2')")
    if len(set(value)) != len(value):
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} has duplicate schema prefixes")
    return frozenset(value)
```

In `_parse_rule`, call it and pass to `RuleSpec`:

```python
    schemas = _parse_schemas(raw, rule_id, source_name)
```

and add `schemas=schemas,` to the `RuleSpec(...)` construction.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_catalogue.py tests/test_rules_model.py -v`
Expected: all PASS (new 9 + existing)

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/model.py packages/ocx-rules/src/ocx_rules/catalogue.py tests/test_rules_catalogue.py
git commit -m "feat(ocx-rules): parse optional per-rule schema-support markers" --no-verify
```

---

### Task 3: Manager skips non-applicable rules

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\manager.py` (`_unsatisfied`)
- Test: `tests\test_rules_manager.py`

- [ ] **Step 1: Write the failing tests** — in `tests\test_rules_manager.py`, extend the `_spec` helper with a `schemas=None` keyword and add a test class. Change `_spec` to:

```python
def _spec(rule_id, custom, requires=frozenset({"xml"}), category="identity",
          severity=Severity.ERROR, schemas=None):
    return RuleSpec(
        rule_id=rule_id, title=rule_id, description="d", category=category,
        severity=severity, source="unittest", requires=requires,
        check=CheckRef(custom=f"{_HERE}:{custom}"), params={}, schemas=schemas)
```

Add (the shared `context` fixture is the 3.1.0 `ocxxml.3docx` stub, whose root declares `schemaVersion="3.1.0"`):

```python
class TestSchemaApplicability:
    def test_matching_schema_runs(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-NEW", "check_passes", schemas=frozenset({"3.1", "3.2"})))])
        (result,) = manager.run(context)
        assert result.status is RuleStatus.PASSED

    def test_non_matching_schema_skips(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-NEW", "check_passes", schemas=frozenset({"3.2", "3.3"})))])
        (result,) = manager.run(context)
        assert result.status is RuleStatus.SKIPPED
        assert result.reason == "not applicable to schema 3.1.0"

    def test_unknown_version_skips_restricted_rule(self, tmp_path):
        doc = tmp_path / "nov.3docx"
        doc.write_text("<root><a/></root>")
        ctx = ValidationContext(doc)
        manager = RuleManager(packs=[_pack(
            _spec("R-NEW", "check_passes", requires=frozenset(),
                  schemas=frozenset({"3.2"})))])
        (result,) = manager.run(ctx)
        assert result.status is RuleStatus.SKIPPED
        assert result.reason == "schema version unknown"

    def test_unrestricted_rule_ignores_unknown_version(self, tmp_path):
        doc = tmp_path / "nov.3docx"
        doc.write_text("<root><a/></root>")
        ctx = ValidationContext(doc)
        manager = RuleManager(packs=[_pack(
            _spec("R-ANY", "check_passes", requires=frozenset()))])
        (result,) = manager.run(ctx)
        assert result.status is RuleStatus.PASSED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rules_manager.py::TestSchemaApplicability -v`
Expected: `test_matching_schema_runs` and `test_unrestricted_rule_ignores_unknown_version` PASS (no skip logic yet, rule just runs); `test_non_matching_schema_skips` and `test_unknown_version_skips_restricted_rule` FAIL with `assert <RuleStatus.PASSED> is <RuleStatus.SKIPPED>`. The two failing tests are the behavior being added; the two passing ones are regression guards.

- [ ] **Step 3: Implement** — in `manager.py`, add at the top of `_unsatisfied` (before the `"xml"` check):

```python
        if spec.schemas is not None:
            version = context.schema_version
            if version is None:
                return "schema version unknown"
            family = ".".join(version.split(".")[:2])
            if family not in spec.schemas:
                return f"not applicable to schema {version}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_manager.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/manager.py tests/test_rules_manager.py
git commit -m "feat(ocx-rules): skip rules not applicable to the model schema version" --no-verify
```

---

### Task 4: Mark OCX-PROP-004 + pack regression

**Files:**
- Modify: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\properties.toml`
- Test: `tests\test_rules_best_practice_pack.py`

- [ ] **Step 1: Write the failing test** — append to the test class in `tests\test_rules_best_practice_pack.py`:

```python
    def test_schema_markers(self):
        pack = load_best_practice_pack()
        by_id = {r.rule_id: r for r in pack.rules}
        assert by_id["OCX-PROP-004"].schemas == frozenset({"3.2", "3.3"})
        unrestricted = [r.rule_id for r in pack.rules
                        if r.rule_id != "OCX-PROP-004" and r.schemas is not None]
        assert unrestricted == []
```

(Use the same pack-loading call the existing tests in that file use — check the import at the top of the file and reuse it verbatim.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rules_best_practice_pack.py -v`
Expected: `test_schema_markers` FAILS with `assert None == frozenset({'3.2', '3.3'})`; all other tests PASS.

- [ ] **Step 3: Implement** — in `properties.toml`, add one line to the OCX-PROP-004 rule block (after its `requires` line):

```toml
schemas     = ["3.2", "3.3"]
```

Rationale (from the spec): `RenewalThickness` exists only in the 3.2.0 and 3.3.0 XSDs; on older schemas the rule would silently PASS.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_corpus.py -v`
Expected: all PASS (corpus runs the pack against real models — confirms no load-time regression).

- [ ] **Step 5: Full suite + commit**

Run: `uv run pytest -q`
Expected: all tests pass.

```bash
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml tests/test_rules_best_practice_pack.py
git commit -m "feat(ocx-rules): restrict OCX-PROP-004 to schema 3.2/3.3" --no-verify
```

---

### Task 5: Documentation touch-up

**Files:**
- Modify: `.github/copilot-instructions.md` — only if it describes the rule TOML keys (check first; if it only describes the packages at folder level, no change needed).
- Modify: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-PROP-004.md` — add a `Supported schemas | 3.2, 3.3` row to the metadata table and one sentence in the Description noting the marker (keeps the wiki pages consistent with the catalogue; this file is outside the repo, no commit).

- [ ] **Step 1: Check and update docs as above**
- [ ] **Step 2: Commit any repo-side doc change**

```bash
git add -A
git commit -m "docs: note schema-support marker in rule docs" --no-verify
```

(Skip the commit if only the external wiki page changed.)
