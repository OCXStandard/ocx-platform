"""XSD validation of .3docx models against vendored OCX schemas.

Independent of the IR pipeline: validates raw XML with lxml, fully
offline. The vendored XSDs live in ``ocx_model_validator/schemas/``;
a custom resolver remaps the remote UnitsML ``xs:import`` URL to the
local copy so no network access ever occurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import lxml.etree as etree
from loguru import logger

from ocx_model_validator.exeptions import SchemaVersionError, SourceError, XmlParserError
from ocx_model_validator.parsers.version import detect_schema_version

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_UNITSML_FILE = "unitsmlSchema_lite-0.9.18.xsd"

#: OCX schema version -> vendored schema directory name
SUPPORTED_VERSIONS: dict[str, str] = {
    "3.0.0": "ocx_300",
    "3.0.1": "ocx_301",
    "3.1.0": "ocx_310",
    "3.2.0": "ocx_320",
}


@dataclass(frozen=True)
class SchemaError:
    """One XSD validation error."""

    line: int
    column: int
    message: str
    domain: str


@dataclass(frozen=True)
class SchemaValidationResult:
    """Outcome of validating one model file against its OCX XSD."""

    model: str
    schema_version: str
    valid: bool
    error_count: int
    errors: list[SchemaError]
    validated_at: str


class _LocalUnitsmlResolver(etree.Resolver):
    """Remap the remote UnitsML schemaLocation to the vendored local file."""

    def __init__(self, schema_dir: Path) -> None:
        super().__init__()
        self._schema_dir = schema_dir

    def resolve(self, url, pubid, context):  # noqa: ANN001 — lxml signature
        if url and "unitsmlSchema_lite" in url:
            return self.resolve_filename(str(self._schema_dir / _UNITSML_FILE), context)
        return None


_schema_cache: dict[str, etree.XMLSchema] = {}


def load_schema(version: str) -> etree.XMLSchema:
    """Return the compiled XMLSchema for *version* (cached per process)."""
    if version in _schema_cache:
        return _schema_cache[version]
    folder = SUPPORTED_VERSIONS.get(version)
    if folder is None:
        raise SchemaVersionError(
            f"No bundled XSD for schema version {version!r}; supported "
            f"versions: {', '.join(sorted(SUPPORTED_VERSIONS))}"
        )
    schema_dir = _SCHEMAS_DIR / folder
    parser = etree.XMLParser()
    parser.resolvers.add(_LocalUnitsmlResolver(schema_dir))
    doc = etree.parse(str(schema_dir / "OCX_Schema.xsd"), parser)
    schema = etree.XMLSchema(doc)
    _schema_cache[version] = schema
    return schema


def validate_schema(model: Path) -> SchemaValidationResult:
    """Validate *model* against the bundled XSD for its declared version.

    Raises:
        SourceError: the file cannot be read.
        SchemaVersionError: no version declared, or no bundled XSD for it.
        XmlParserError: the file is not well-formed XML.
    """
    try:
        xml_bytes = model.read_bytes()
    except OSError as exc:
        raise SourceError(f"Cannot read {model}: {exc}") from exc

    version = detect_schema_version(xml_bytes.decode("utf-8", errors="replace"))
    if version is None:
        raise SchemaVersionError(
            f"{model} declares no OCX schema version; supported versions: "
            f"{', '.join(sorted(SUPPORTED_VERSIONS))}"
        )
    schema = load_schema(version)

    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise XmlParserError(f"{model} is not well-formed XML: {exc}") from exc

    valid = schema.validate(doc)
    errors = [
        SchemaError(line=e.line, column=e.column, message=e.message, domain=e.type_name)
        for e in schema.error_log
    ]
    logger.info(
        "Schema validation of {}: {} ({} error(s), schema {})",
        model,
        "VALID" if valid else "INVALID",
        len(errors),
        version,
    )
    return SchemaValidationResult(
        model=str(model),
        schema_version=version,
        valid=valid,
        error_count=len(errors),
        errors=errors,
        validated_at=datetime.now(timezone.utc).isoformat(),
    )
