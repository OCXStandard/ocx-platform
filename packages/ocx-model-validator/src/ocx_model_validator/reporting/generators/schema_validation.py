"""Schema validation report generator — SchemaValidationResult → Report."""
from __future__ import annotations

from ocx_model_core.validation.schema import SchemaValidationResult

from ocx_model_validator.reporting.model import Report, ReportSection, ReportTable

_TITLE = "Schema validation report"


def build(result: SchemaValidationResult,
          max_errors: int | None = None) -> Report:
    """Build a Report; *max_errors* caps the table (None = all errors)."""
    shown = result.errors if max_errors is None else result.errors[:max_errors]
    tables = []
    if shown:
        tables.append(ReportTable(
            title="Validation errors",
            columns=["#", "Line", "Column", "Message"],
            rows=[[i + 1, e.line, e.column, e.message]
                  for i, e in enumerate(shown)],
        ))
    notes: list[str] = []
    if max_errors is not None and result.error_count > max_errors:
        notes.append(
            f"Showing first {max_errors} of {result.error_count} errors; "
            "the full list is in the JSON and HTML sidecar files.")
    verdict = "VALID" if result.valid else "INVALID"
    section = ReportSection(
        title=f"Result: {verdict}",
        intro=f"{result.error_count} schema error(s).",
        tables=tables,
        notes=notes,
    )
    metadata = {
        "Source file": result.model,
        "Schema version": result.schema_version,
        "Validated at": result.validated_at,
        "Result": verdict,
    }
    return Report(title=_TITLE, metadata=metadata, sections=[section])
