"""Smoke tests for `validator validate rules`."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ocx_model_validator.cli import app

runner = CliRunner(env={"COLUMNS": "200"})


class TestValidateRulesCli:
    def test_runs_clean_on_stub_model(self, stub_dir_310: Path):
        # Step 1 ships stubs only -> every rule is NOT_IMPLEMENTED/SKIPPED -> exit 0.
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx")])
        assert result.exit_code == 0, result.output
        assert "OCX-ID-002" in result.output

    def test_missing_model_exits_2(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(tmp_path / "nope.3docx")])
        assert result.exit_code == 2

    def test_rule_filter(self, stub_dir_310: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--rule", "OCX-ID-002"])
        assert result.exit_code == 0
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_markdown_destination(self, stub_dir_310: Path, tmp_path: Path):
        dest = tmp_path / "rules.md"
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--destination", str(dest)])
        assert result.exit_code == 0
        assert dest.exists()
        assert "OCX-ID-002" in dest.read_text(encoding="utf-8")
