"""Tests for the TOML rule-catalogue loader."""
from __future__ import annotations

import pytest
from ocx_rules.catalogue import CatalogueError, load_catalogue_dir, parse_rules_toml
from ocx_rules.model import Severity

VALID_RULE = '''
[[rule]]
id          = "OCX-TST-001"
title       = "GUIDs must be unique"
description = "No duplicate GUIDRef values."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]

[rule.check]
primitive = "unique"
xpath     = "//*[@ocx:GUIDRef]"
key       = "@ocx:GUIDRef"
'''

CUSTOM_RULE = '''
[[rule]]
id          = "OCX-TST-002"
title       = "Custom check"
description = "Uses a custom callable."
source      = "unittest"
category    = "topology"
severity    = "warning"
requires    = ["ir", "geometry"]

[rule.check]
custom       = "ocx_rules.primitives.geometry:closed_contour"
tolerance_mm = 1.0
'''

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


class TestParseRulesToml:
    def test_primitive_rule(self):
        (spec,) = parse_rules_toml(VALID_RULE, source_name="t.toml")
        assert spec.rule_id == "OCX-TST-001"
        assert spec.severity is Severity.ERROR
        assert spec.requires == frozenset({"xml"})
        assert spec.check.primitive == "unique"
        assert spec.params == {"xpath": "//*[@ocx:GUIDRef]", "key": "@ocx:GUIDRef"}

    def test_custom_rule_params_exclude_custom_key(self):
        (spec,) = parse_rules_toml(CUSTOM_RULE, source_name="t.toml")
        assert spec.check.custom == "ocx_rules.primitives.geometry:closed_contour"
        assert spec.params == {"tolerance_mm": 1.0}

    @pytest.mark.parametrize("bad,repl", [
        ('severity    = "error"', 'severity    = "fatal"'),
        ('primitive = "unique"', 'primitive = "no_such_primitive"'),
        ('requires    = ["xml"]', 'requires    = ["xml", "quantum"]'),
        ('category    = "identity"', 'category    = ""'),
        ('id          = "OCX-TST-001"', 'id          = ""'),
    ])
    def test_invalid_rule_rejected(self, bad, repl):
        with pytest.raises(CatalogueError):
            parse_rules_toml(VALID_RULE.replace(bad, repl), source_name="t.toml")

    def test_unimportable_custom_rejected(self):
        text = CUSTOM_RULE.replace(
            "ocx_rules.primitives.geometry:closed_contour", "no.such.module:fn")
        with pytest.raises(CatalogueError):
            parse_rules_toml(text, source_name="t.toml")

    def test_duplicate_ids_rejected(self):
        with pytest.raises(CatalogueError, match="OCX-TST-001"):
            parse_rules_toml(VALID_RULE + VALID_RULE, source_name="t.toml")


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


class TestLoadCatalogueDir:
    def test_loads_all_toml_files_and_checks_cross_file_duplicates(self, tmp_path):
        (tmp_path / "a.toml").write_text(VALID_RULE, encoding="utf-8")
        (tmp_path / "b.toml").write_text(CUSTOM_RULE, encoding="utf-8")
        specs = load_catalogue_dir(tmp_path)
        assert [s.rule_id for s in specs] == ["OCX-TST-001", "OCX-TST-002"]

        (tmp_path / "c.toml").write_text(VALID_RULE, encoding="utf-8")
        with pytest.raises(CatalogueError, match="OCX-TST-001"):
            load_catalogue_dir(tmp_path)
