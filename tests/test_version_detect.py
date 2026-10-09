"""Tests for shared OCX schema-version detection."""
from ocx_model_core.parsers.version import detect_schema_version


def test_detects_schema_version_attribute():
    xml = '<ocx:ocxXML xmlns:ocx="https://3docx.org/x" schemaVersion="3.1.0">'
    assert detect_schema_version(xml) == "3.1.0"


def test_detects_version_from_namespace():
    xml = ('<ocx:Panel xmlns:ocx='
           '"https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd"/>')
    assert detect_schema_version(xml) == "3.2.0"


def test_attribute_wins_over_namespace():
    xml = ('<ocx:ocxXML xmlns:ocx='
           '"https://3docx.org/fileadmin//ocx_schema//V310//OCX_Schema.xsd" '
           'schemaVersion="3.1.0">')
    assert detect_schema_version(xml) == "3.1.0"


def test_returns_none_when_undetectable():
    assert detect_schema_version("<foo/>") is None
