"""Shared OCX schema-version detection from raw XML text."""
from __future__ import annotations

import re

_SCHEMA_VERSION_RE = re.compile(r'\bschemaVersion="([^"]+)"')
_NAMESPACE_RE = re.compile(r"//V(\d)(\d)(\d)//OCX_Schema\.xsd")


def detect_schema_version(xml_text: str) -> str | None:
    """Return the OCX schema version declared in *xml_text*, or ``None``.

    Checks the ``schemaVersion`` attribute first, then falls back to the
    version encoded in the OCX namespace URI (``//V310//OCX_Schema.xsd``).
    """
    match = _SCHEMA_VERSION_RE.search(xml_text)
    if match:
        return match.group(1)
    match = _NAMESPACE_RE.search(xml_text)
    if match:
        return ".".join(match.groups())
    return None
