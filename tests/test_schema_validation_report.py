"""Tests for the schema-validation report generator."""
from __future__ import annotations

from ocx_model_validator.validation.schema import (SchemaError,
                                                   SchemaValidationResult)


def _result(n_errors: int) -> SchemaValidationResult:
    errors = [SchemaError(line=i + 1, column=0, message=f"error {i}",
                          domain="SCHEMAV_TEST") for i in range(n_errors)]
    return SchemaValidationResult(
        model="m.3docx", schema_version="3.1.0", valid=n_errors == 0,
        error_count=n_errors, errors=errors,
        validated_at="2026-10-04T00:00:00+00:00")


def test_valid_result_has_no_error_table():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(0))
    assert report.metadata["Result"] == "VALID"
    assert report.sections[0].tables == []


def test_invalid_result_lists_errors():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(3))
    assert report.metadata["Result"] == "INVALID"
    table = report.sections[0].tables[0]
    assert len(table.rows) == 3
    assert table.rows[0][1] == 1  # line number of first error


def test_max_errors_caps_rows_and_adds_note():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(10), max_errors=4)
    table = report.sections[0].tables[0]
    assert len(table.rows) == 4
    assert any("first 4 of 10" in n for n in report.sections[0].notes)


def test_max_errors_above_count_adds_no_note():
    from ocx_model_validator.reporting.generators import schema_validation

    report = schema_validation.build(_result(2), max_errors=50)
    assert len(report.sections[0].tables[0].rows) == 2
    assert report.sections[0].notes == []
