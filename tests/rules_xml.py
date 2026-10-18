"""Inline OCX document builders for rule-check unit tests."""
from __future__ import annotations

from pathlib import Path

import lxml.etree as etree
from ocx_rules.context import ValidationContext

OCX_NS = "https://3docx.org/fileadmin//ocx_schema//V310//OCX_Schema.xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
UNITSML_NS = "urn:oasis:names:tc:unitsml:schema:xsd:UnitsMLSchema_lite-0.9.18"

DEFAULT_ROOT_ATTRS = f'xsi:schemaLocation="{OCX_NS} {OCX_NS}" schemaVersion="3.1.0"'


def ocx_doc(body: str = "", *, root_attrs: str | None = None) -> etree._ElementTree:
    """Wrap *body* fragments in a 3.1.0 ocxXML root with standard namespaces."""
    attrs = DEFAULT_ROOT_ATTRS if root_attrs is None else root_attrs
    xml = (
        f'<ocx:ocxXML xmlns:ocx="{OCX_NS}" xmlns:xsi="{XSI_NS}" '
        f'xmlns:unitsml="{UNITSML_NS}" {attrs}>\n{body}\n</ocx:ocxXML>'
    )
    return etree.ElementTree(etree.fromstring(xml.encode()))


def context_for(body: str = "", *, root_attrs: str | None = None) -> ValidationContext:
    """ValidationContext whose xml_tree is the inline document (no file I/O)."""
    ctx = ValidationContext(Path("inline.3docx"))
    ctx.__dict__["xml_tree"] = ocx_doc(body, root_attrs=root_attrs)
    return ctx


def context_for_xml(xml: str) -> ValidationContext:
    """ValidationContext for a complete raw XML document string."""
    ctx = ValidationContext(Path("inline.3docx"))
    ctx.__dict__["xml_tree"] = etree.ElementTree(etree.fromstring(xml.encode()))
    return ctx
