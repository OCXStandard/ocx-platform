"""Tests for the OCX 3.3.0 bracket schema enhancements (vendored XSD)."""
from __future__ import annotations

import re
from pathlib import Path

from ocx_model_validator.validation.schema import validate_schema

DATA = Path(__file__).parent / "data"
STUB_320 = DATA / "ocx_320_stubs" / "ocxxml.3docx"
NS_320 = "https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd"
NS_330 = "https://3docx.org/fileadmin//ocx_schema//V330//OCX_Schema.xsd"
GUID = "12345678-1234-1234-1234-123456789012"


class TestRegistry:
    def test_330_schema_compiles(self):
        from ocx_model_validator.validation.schema import SUPPORTED_VERSIONS, load_schema

        assert SUPPORTED_VERSIONS["3.3.0"] == "ocx_330"
        assert load_schema("3.3.0") is not None
