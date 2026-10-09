"""ocx_model_validator — validation, reporting and CLI for OCX .3docx models.

Parsing, IR and schema validation live in ``ocx_model_core``; the core public
API is re-exported here for backwards compatibility.
"""
from ocx_model_core import (  # noqa: F401 — re-exported for back-compat
    ConverterError,
    ConverterWarning,
    DeclarationOfOcxImport,
    DynamicLoader,
    DynamicLoaderError,
    IrVessel,
    OcxParser,
    SourceError,
    XmlParserError,
    get_builder,
)

__version__ = "0.5.0"

__all__ = [
    "OcxParser",
    "get_builder",
    "IrVessel",
    "DeclarationOfOcxImport",
    "DynamicLoader",
    "XmlParserError",
    "SourceError",
    "DynamicLoaderError",
    "ConverterError",
    "ConverterWarning",
]
