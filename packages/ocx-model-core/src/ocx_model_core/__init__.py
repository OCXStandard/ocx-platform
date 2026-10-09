"""ocx_model_core — parse OCX .3docx ship model files into a schema-neutral IR.

Public API
----------
OcxParser       — parse a .3docx file into an OCX root dataclass
get_builder     — return the correct IR builder for a schema version
IrVessel        — root IR dataclass (schema-neutral)

Exceptions
----------
XmlParserError, SourceError, DynamicLoaderError, ConverterError
"""
from ocx_model_core.builders.factory import get_builder
from ocx_model_core.exeptions import (
    ConverterError,
    ConverterWarning,
    DynamicLoaderError,
    SourceError,
    XmlParserError,
)
from ocx_model_core.model.ir import IrVessel
from ocx_model_core.parsers.dynamic_loader import DeclarationOfOcxImport, DynamicLoader
from ocx_model_core.parsers.parser import OcxParser

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
