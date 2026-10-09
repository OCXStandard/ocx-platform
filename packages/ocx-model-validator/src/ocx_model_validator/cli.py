"""CLI entrypoint for ocx-model-validator.

Usage::

    validator report frame-table MODEL.3docx [--format rich|markdown|html] [--destination FILE]
    validator report compartments MODEL.3docx ...
    validator report catalogues MODEL.3docx [--catalogue material|section|opening|all] ...
    validator report panels MODEL.3docx ...
    validator report plates MODEL.3docx ...
    validator report stiffeners MODEL.3docx ...
    validator report brackets MODEL.3docx ...
    validator report pillars MODEL.3docx ...
    validator report bom MODEL.3docx ...
    validator report all MODEL.3docx ...
    validator validate schema MODEL.3docx [--max-errors N]
"""
from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import typer
from loguru import logger
from rich.console import Console

from ocx_model_validator.reporting.model import Report
from ocx_model_validator.reporting.renderers import get_renderer
from ocx_model_validator.reporting.renderers.rich import RichRenderer


def configure_logging(level: str = "INFO") -> None:
    """Replace the default loguru sink with a stderr sink at *level*."""
    logger.remove()
    logger.add(sys.stderr, level=level)


app = typer.Typer(
    name="validator",
    help="OCX model validator — tools for parsing, reporting and validating .3docx ship models.",
    no_args_is_help=True,
)
report_app = typer.Typer(help="Generate model reports.", no_args_is_help=True)
app.add_typer(report_app, name="report")
validate_app = typer.Typer(help="Validate models.", no_args_is_help=True)
app.add_typer(validate_app, name="validate")


class ReportFormat(str, Enum):
    rich = "rich"
    markdown = "markdown"
    html = "html"


_MODEL_ARG = typer.Argument(..., exists=True, readable=True,
                            help="Path to a .3docx model file.")
_FORMAT_OPT = typer.Option(None, "--format", "-f",
                           help="Output format (default: rich to stdout; "
                                "markdown with --destination, or html when "
                                "the destination ends in .html/.htm).")
_DEST_OPT = typer.Option(None, "--destination", "-d",
                         help="Write the report to this file "
                              "(markdown, or html for .html/.htm).")


def _load_vessel(model: Path):
    """Parse and build the IR; exit code 1 on failure."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.dynamic_loader import DeclarationOfOcxImport
    from ocx_model_core.parsers.parser import OcxParser

    try:
        version = _detect_schema_version(model)
        parser = OcxParser()
        if version is None:
            root = parser.parse(str(model))
            version = root.schema_version
        else:
            logger.warning(
                "{} has no schemaVersion attribute and is being loaded as a "
                "bare fragment; units and catalogues will be unavailable.",
                model,
            )
            root = SimpleNamespace(
                vessel=parser.parse_from_string(
                    xml_str=model.read_text(encoding="utf-8"),
                    declaration=DeclarationOfOcxImport("ocx", version),
                ),
                schema_version=version,
            )
        builder = get_builder(version)
        vessel = builder.build(root)
        from ocx_model_validator.reporting.summary import model_summary

        logger.info(model_summary(vessel))
        return vessel
    except Exception as exc:
        logger.error("Failed to parse/build {}: {}", model, exc)
        raise typer.Exit(code=1) from exc


def _detect_schema_version(model: Path) -> str | None:
    from ocx_model_core.parsers.version import detect_schema_version

    xml = model.read_text(encoding="utf-8")
    if re.search(r'\bschemaVersion="', xml):
        return None
    return detect_schema_version(xml)


_HTML_SUFFIXES = {".html", ".htm"}


def _emit(report: Report, fmt: ReportFormat | None, destination: Path | None) -> None:
    if destination is not None:
        if fmt == ReportFormat.rich:
            raise typer.BadParameter(
                "--destination cannot be combined with --format rich")
        if fmt is None:
            fmt = (ReportFormat.html
                   if destination.suffix.lower() in _HTML_SUFFIXES
                   else ReportFormat.markdown)
        try:
            destination.write_text(get_renderer(fmt.value).render(report),
                                   encoding="utf-8")
        except OSError as exc:
            logger.error("Cannot write {}: {}", destination, exc)
            raise typer.Exit(code=1) from exc
        typer.echo(f"Report written to {destination}")
        return
    if fmt is None or fmt == ReportFormat.rich:
        RichRenderer().render_to_console(report, Console())
    else:
        typer.echo(get_renderer(fmt.value).render(report), nl=False)


@report_app.command("frame-table")
def frame_table_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Frame table: frame 0 offset, spacing entries and frame positions."""
    from ocx_model_validator.reporting.generators import frame_table

    vessel = _load_vessel(model)
    _emit(frame_table.build(vessel, source_file=str(model)), fmt, destination)


class CatalogueKind(str, Enum):
    material = "material"
    section = "section"
    opening = "opening"
    all = "all"


@report_app.command("compartments")
def compartments_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Compartments: name, tank type, volume, COG and extents."""
    from ocx_model_validator.reporting.generators import compartments

    vessel = _load_vessel(model)
    _emit(compartments.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("catalogues")
def catalogues_cmd(
    model: Path = _MODEL_ARG,
    catalogue: CatalogueKind = typer.Option(
        CatalogueKind.all, "--catalogue",
        help="Which catalogue to report."),
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Catalogues: materials, cross sections and openings."""
    from ocx_model_validator.reporting.generators import catalogues

    vessel = _load_vessel(model)
    _emit(catalogues.build(vessel, which=catalogue.value,
                           source_file=str(model)), fmt, destination)


@report_app.command("panels")
def panels_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Panels: attributes, physical properties and child counts."""
    from ocx_model_validator.reporting.generators import panels

    vessel = _load_vessel(model)
    _emit(panels.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("plates")
def plates_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Plates: attributes, thicknesses, net area and opening counts."""
    from ocx_model_validator.reporting.generators import plates

    vessel = _load_vessel(model)
    _emit(plates.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("stiffeners")
def stiffeners_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Stiffeners: attributes, profile, trace length and connection counts."""
    from ocx_model_validator.reporting.generators import stiffeners

    vessel = _load_vessel(model)
    _emit(stiffeners.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("brackets")
def brackets_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Brackets: attributes, thicknesses and all bracket parameters."""
    from ocx_model_validator.reporting.generators import brackets

    vessel = _load_vessel(model)
    _emit(brackets.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("pillars")
def pillars_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Pillars: attributes, profile, trace length and counts."""
    from ocx_model_validator.reporting.generators import pillars

    vessel = _load_vessel(model)
    _emit(pillars.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("bom")
def bom_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Bill of material grouped by material, with weights and totals."""
    from ocx_model_validator.reporting.generators import bom

    vessel = _load_vessel(model)
    _emit(bom.build(vessel, source_file=str(model)), fmt, destination)


@report_app.command("all")
def all_cmd(
    model: Path = _MODEL_ARG,
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """All reports merged into one document (report defaults; no per-report flags)."""
    from ocx_model_validator.reporting.generators import (
        bom,
        brackets,
        catalogues,
        compartments,
        frame_table,
        model_extent,
        panels,
        pillars,
        plates,
        stiffeners,
    )

    vessel = _load_vessel(model)
    source = str(model)
    parts = [
        model_extent.build(vessel, source_file=source),
        frame_table.build(vessel, source_file=source),
        compartments.build(vessel, source_file=source),
        panels.build(vessel, source_file=source),
        plates.build(vessel, source_file=source),
        stiffeners.build(vessel, source_file=source),
        brackets.build(vessel, source_file=source),
        pillars.build(vessel, source_file=source),
        catalogues.build(vessel, source_file=source),
        bom.build(vessel, source_file=source),
    ]
    merged = Report(
        title="Model report",
        metadata=parts[0].metadata,
        sections=[s for p in parts for s in p.sections],
    )
    _emit(merged, fmt, destination)


@validate_app.command("schema")
def validate_schema_cmd(
    model: Path = _MODEL_ARG,
    max_errors: int = typer.Option(
        50, "--max-errors", min=1,
        help="Maximum number of errors shown in the terminal table "
             "(sidecar files always contain the full list)."),
) -> None:
    """Validate the model against its bundled OCX XSD (offline).

    Exit codes: 0 = valid, 1 = validation errors, 2 = cannot validate.
    Always writes MODEL.validation.json and MODEL.validation.html beside
    the model file.
    """
    import json
    from dataclasses import asdict

    from ocx_model_core.exeptions import SchemaVersionError, SourceError, XmlParserError
    from ocx_model_core.validation.schema import validate_schema

    from ocx_model_validator.reporting.generators import schema_validation

    try:
        result = validate_schema(model)
    except (SchemaVersionError, SourceError, XmlParserError) as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc

    RichRenderer().render_to_console(
        schema_validation.build(result, max_errors=max_errors), Console())

    json_path = model.with_suffix(".validation.json")
    html_path = model.with_suffix(".validation.html")
    try:
        json_path.write_text(json.dumps(asdict(result), indent=2),
                             encoding="utf-8")
        html_path.write_text(
            get_renderer("html").render(schema_validation.build(result)),
            encoding="utf-8")
        typer.echo(f"Sidecars written: {json_path}, {html_path}")
    except OSError as exc:
        logger.error("Cannot write sidecar files: {}", exc)

    raise typer.Exit(code=0 if result.valid else 1)


def entrypoint() -> None:
    configure_logging()
    app()
