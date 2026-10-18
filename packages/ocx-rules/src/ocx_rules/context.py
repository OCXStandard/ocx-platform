"""ValidationContext — lazy access to the raw XML tree and the parsed IR.

Rules declare what they need via ``RuleSpec.requires``; the context only pays
for what is actually accessed. A run containing only XML rules never builds
the IR.
"""
from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import lxml.etree as etree
from loguru import logger

if TYPE_CHECKING:
    from ocx_rules.geometry_context import GeometryContext
    from ocx_rules.xml_index import XmlIndex


def _build_vessel(model_path: Path):
    """Parse *model_path* and build the IR (module-level so tests can patch it)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser

    parser = OcxParser()
    root = parser.parse(str(model_path))
    builder = get_builder(root.schema_version)
    return builder.build(root)


class ValidationContext:
    """Shared, lazily-populated inputs for all rule checks on one model."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)

    @cached_property
    def xml_tree(self) -> etree._ElementTree:
        """The raw lxml tree (line numbers preserved for Finding.location)."""
        logger.debug("Parsing XML tree: {}", self.model_path)
        # collect_ids=False: lxml's default parser raises on duplicate xml:id,
        # but the duplicate-id checks (e.g. OCX-DOC-003) must see such
        # documents rather than have every xml rule skipped on a parse error.
        xml_parser = etree.XMLParser(collect_ids=False)
        return etree.parse(str(self.model_path), parser=xml_parser)

    @cached_property
    def vessel(self):
        """The schema-neutral IR (IrVessel); built on first access."""
        logger.debug("Building IR: {}", self.model_path)
        return _build_vessel(self.model_path)

    @cached_property
    def xml_index(self) -> "XmlIndex":
        """Shared identity/reference index over the XML tree."""
        from ocx_rules.xml_index import XmlIndex

        return XmlIndex(self.xml_tree)

    @cached_property
    def geometry(self) -> "GeometryContext":
        """Shared geometry facade over the IR; built on first access."""
        from ocx_rules.geometry_context import GeometryContext

        return GeometryContext(self.vessel)
