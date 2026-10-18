"""Smoke tests for `validator validate rules`."""
from __future__ import annotations

from pathlib import Path

from ocx_model_validator.cli import app
from typer.testing import CliRunner

runner = CliRunner(env={"COLUMNS": "200"})


class TestValidateRulesCli:
    def test_reports_on_stub_model(self, stub_dir_310: Path):
        # The stub model contains genuine rule violations (duplicate GUIDs),
        # so exit code may be 0 or 1; the CLI must still render the report.
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx")])
        assert result.exit_code in (0, 1), result.output
        assert "OCX-ID-002" in result.output

    def test_missing_model_exits_2(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(tmp_path / "nope.3docx")])
        assert result.exit_code == 2

    def test_rule_filter(self, stub_dir_310: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--rule", "OCX-ID-002"])
        assert result.exit_code in (0, 1)
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_rule_filter_repeatable(self, stub_dir_310: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--rule", "OCX-ID-002",
                                     "--rule", "OCX-ID-001"])
        assert result.exit_code in (0, 1)
        assert "rules run: 2" in result.output
        assert "OCX-ID-001" in result.output
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_markdown_destination(self, stub_dir_310: Path, tmp_path: Path):
        dest = tmp_path / "rules.md"
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--destination", str(dest)])
        assert result.exit_code in (0, 1)
        assert dest.exists()
        assert "OCX-ID-002" in dest.read_text(encoding="utf-8")
