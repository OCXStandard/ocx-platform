"""Smoke tests for `validator validate rules`."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from ocx_model_validator.cli import app
from typer.testing import CliRunner

runner = CliRunner(env={"COLUMNS": "200"})


@pytest.fixture
def model(stub_dir_310: Path, tmp_path: Path) -> Path:
    """Copy of the stub model in tmp_path (the CLI writes a sidecar beside it)."""
    return Path(shutil.copy(stub_dir_310 / "ocxxml.3docx",
                            tmp_path / "ocxxml.3docx"))


class TestValidateRulesCli:
    def test_reports_on_stub_model(self, model: Path):
        # The stub model contains genuine rule violations (duplicate GUIDs),
        # so exit code may be 0 or 1; the CLI must still render the report.
        result = runner.invoke(app, ["validate", "rules", str(model)])
        assert result.exit_code in (0, 1), result.output
        assert "OCX-ID-002" in result.output

    def test_missing_model_exits_2(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(tmp_path / "nope.3docx")])
        assert result.exit_code == 2

    def test_rule_filter(self, model: Path):
        result = runner.invoke(app, ["validate", "rules", str(model),
                                     "--rule", "OCX-ID-002"])
        assert result.exit_code in (0, 1)
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_rule_filter_repeatable(self, model: Path):
        result = runner.invoke(app, ["validate", "rules", str(model),
                                     "--rule", "OCX-ID-002",
                                     "--rule", "OCX-ID-001"])
        assert result.exit_code in (0, 1)
        assert "rules run: 2" in result.output
        assert "OCX-ID-001" in result.output
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_json_sidecar_written(self, model: Path, tmp_path: Path):
        result = runner.invoke(app, ["validate", "rules", str(model)])
        assert result.exit_code in (0, 1)
        sidecar = tmp_path / "ocxxml.rules.json"
        assert sidecar.exists(), result.output
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        assert doc["report"] == "ocx-rule-validation"
        assert doc["model"] == str(model)
        rule_ids = {r["rule_id"] for r in doc["results"]}
        assert "OCX-ID-002" in rule_ids
        # every result carries source provenance
        assert all(r["source"] for r in doc["results"])

    def test_markdown_destination(self, model: Path, tmp_path: Path):
        dest = tmp_path / "rules.md"
        result = runner.invoke(app, ["validate", "rules", str(model),
                                     "--destination", str(dest)])
        assert result.exit_code in (0, 1)
        assert dest.exists()
        assert "OCX-ID-002" in dest.read_text(encoding="utf-8")
