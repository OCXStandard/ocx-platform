"""CLI tests for `validator validate schema` (typer CliRunner)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ocx_model_validator.cli import app

runner = CliRunner()

STUB_MODEL = Path(__file__).parent / "data" / "ocx_310_stubs" / "ocxxml.3docx"


@pytest.fixture()
def valid_model(tmp_path: Path) -> Path:
    target = tmp_path / "model.3docx"
    target.write_text(STUB_MODEL.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture()
def invalid_model(tmp_path: Path) -> Path:
    text = STUB_MODEL.read_text(encoding="utf-8").replace(
        "</ocx:Vessel>", "<ocx:NotARealElement/></ocx:Vessel>", 1)
    target = tmp_path / "broken.3docx"
    target.write_text(text, encoding="utf-8")
    return target


def test_valid_model_exit_0_and_sidecars(valid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(valid_model)])
    assert result.exit_code == 0
    assert "VALID" in result.output
    json_path = valid_model.with_suffix(".validation.json")
    html_path = valid_model.with_suffix(".validation.html")
    assert json_path.exists() and html_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["valid"] is True
    assert data["schema_version"] == "3.1.0"
    assert data["errors"] == []


def test_invalid_model_exit_1_with_full_json(invalid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(invalid_model)])
    assert result.exit_code == 1
    assert "INVALID" in result.output
    data = json.loads(invalid_model.with_suffix(".validation.json")
                      .read_text(encoding="utf-8"))
    assert data["valid"] is False
    assert data["error_count"] == len(data["errors"]) > 0
    assert data["errors"][0]["line"] > 0


def test_max_errors_caps_table_not_json(invalid_model: Path):
    result = runner.invoke(app, ["validate", "schema", str(invalid_model),
                                 "--max-errors", "1"])
    assert result.exit_code == 1
    data = json.loads(invalid_model.with_suffix(".validation.json")
                      .read_text(encoding="utf-8"))
    # JSON always carries the full list even when the table is capped
    assert len(data["errors"]) == data["error_count"]


def test_unknown_schema_version_exit_2(tmp_path: Path):
    model = tmp_path / "odd.3docx"
    model.write_text('<ocx:ocxXML xmlns:ocx="https://3docx.org/x" '
                     'schemaVersion="9.9.9"/>', encoding="utf-8")
    result = runner.invoke(app, ["validate", "schema", str(model)])
    assert result.exit_code == 2
    assert not model.with_suffix(".validation.json").exists()


def test_malformed_xml_exit_2(tmp_path: Path):
    model = tmp_path / "malformed.3docx"
    model.write_text('<ocx:ocxXML schemaVersion="3.1.0"><unclosed>',
                     encoding="utf-8")
    result = runner.invoke(app, ["validate", "schema", str(model)])
    assert result.exit_code == 2
    assert not model.with_suffix(".validation.json").exists()


def test_missing_file_nonzero_exit():
    result = runner.invoke(app, ["validate", "schema", "no_such.3docx"])
    assert result.exit_code != 0
