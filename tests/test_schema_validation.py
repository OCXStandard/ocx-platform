"""Tests for XSD schema validation (ocx_model_validator.validation.schema)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_model_validator.exeptions import SchemaVersionError, XmlParserError

STUB_MODEL = Path(__file__).parent / "data" / "ocx_310_stubs" / "ocxxml.3docx"


@pytest.fixture()
def valid_model(tmp_path: Path) -> Path:
    """Copy of the full 3.1.0 stub model in a writable directory."""
    target = tmp_path / "model.3docx"
    target.write_text(STUB_MODEL.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture()
def invalid_model(tmp_path: Path) -> Path:
    """Valid stub with a bogus element injected into the Vessel."""
    text = STUB_MODEL.read_text(encoding="utf-8")
    assert "</ocx:Vessel>" in text
    text = text.replace("</ocx:Vessel>", "<ocx:NotARealElement/></ocx:Vessel>", 1)
    target = tmp_path / "broken.3docx"
    target.write_text(text, encoding="utf-8")
    return target


class TestValidateSchema:
    def test_valid_model(self, valid_model: Path):
        from ocx_model_validator.validation.schema import validate_schema

        result = validate_schema(valid_model)
        assert result.valid is True
        assert result.errors == []
        assert result.error_count == 0
        assert result.schema_version == "3.1.0"
        assert result.model == str(valid_model)
        assert result.validated_at  # ISO timestamp set

    def test_invalid_model_reports_errors_with_lines(self, invalid_model: Path):
        from ocx_model_validator.validation.schema import validate_schema

        result = validate_schema(invalid_model)
        assert result.valid is False
        assert result.error_count == len(result.errors) > 0
        first = result.errors[0]
        assert first.line > 0
        assert "NotARealElement" in first.message

    def test_unknown_schema_version_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "odd.3docx"
        model.write_text(
            '<ocx:ocxXML xmlns:ocx="https://3docx.org/x" schemaVersion="9.9.9"/>',
            encoding="utf-8",
        )
        with pytest.raises(SchemaVersionError) as exc_info:
            validate_schema(model)
        assert "3.1.0" in str(exc_info.value)  # lists supported versions

    def test_missing_schema_version_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "noversion.3docx"
        model.write_text("<foo/>", encoding="utf-8")
        with pytest.raises(SchemaVersionError):
            validate_schema(model)

    def test_malformed_xml_raises(self, tmp_path: Path):
        from ocx_model_validator.validation.schema import validate_schema

        model = tmp_path / "malformed.3docx"
        model.write_text('<ocx:ocxXML schemaVersion="3.1.0"><unclosed>', encoding="utf-8")
        with pytest.raises(XmlParserError):
            validate_schema(model)


class TestSchemaRegistry:
    def test_all_vendored_schemas_compile(self):
        """Every vendored schema dir must compile (catches corrupt files)."""
        from ocx_model_validator.validation.schema import SUPPORTED_VERSIONS, load_schema

        for version in SUPPORTED_VERSIONS:
            assert load_schema(version) is not None
