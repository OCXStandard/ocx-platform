"""Tests for the user rule-configuration (TOML) layer."""
from __future__ import annotations

import pytest
from ocx_rules.config import ConfigError, RuleConfig, apply_config, load_config
from ocx_rules.model import CheckRef, RuleSpec, Severity

CONFIG_TOML = '''
[rules]
disable = ["OCX-TST-002"]

[rules.overrides.OCX-TST-001]
severity     = "warning"
tolerance_mm = 0.5
'''


def _spec(rule_id: str) -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id, title="t", description="d", category="identity",
        severity=Severity.ERROR, source="unittest", requires=frozenset({"xml"}),
        check=CheckRef(primitive="unique"), params={"xpath": "//*", "tolerance_mm": 1.0})


class TestLoadConfig:
    def test_none_path_gives_empty_config(self):
        cfg = load_config(None)
        assert cfg.disabled == frozenset() and cfg.overrides == {}

    def test_load_from_file(self, tmp_path):
        path = tmp_path / "ocx-rules.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.disabled == frozenset({"OCX-TST-002"})
        assert cfg.overrides["OCX-TST-001"]["severity"] == "warning"

    def test_invalid_severity_override_rejected(self, tmp_path):
        path = tmp_path / "ocx-rules.toml"
        path.write_text(CONFIG_TOML.replace('"warning"', '"fatal"'), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(tmp_path / "nope.toml")


class TestApplyConfig:
    def test_disable_removes_rule(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        out = apply_config([_spec("OCX-TST-001"), _spec("OCX-TST-002")], cfg)
        assert [s.rule_id for s in out] == ["OCX-TST-001"]

    def test_override_changes_severity_and_params(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        (out,) = apply_config([_spec("OCX-TST-001")], cfg)
        assert out.severity is Severity.WARNING
        assert out.params["tolerance_mm"] == 0.5
        assert out.params["xpath"] == "//*"  # untouched params survive

    def test_empty_config_is_identity(self):
        specs = [_spec("OCX-TST-001")]
        assert apply_config(specs, RuleConfig()) == specs
