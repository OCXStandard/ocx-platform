"""ocx-diagnose — check render tolerance/settings and visualise chart problems."""
from __future__ import annotations

import time
from pathlib import Path

import typer
from loguru import logger
from ocx_render.cli import _load_vessel, configure_logging

app = typer.Typer(add_completion=False)


def _parse_sweep(text: str | None) -> list[float]:
    if not text:
        return []
    try:
        vals = [float(t) for t in text.split(",") if t.strip()]
    except ValueError as exc:
        raise typer.BadParameter("expected comma-separated millimetres, e.g. 10,25,50") from exc
    if any(v <= 0 for v in vals):
        raise typer.BadParameter("tolerances must be positive")
    return vals


@app.command()
def diagnose(
    model: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False,
                                 help="Path to the .3docx model."),
    panel: list[str] = typer.Option(
        [], "--panel", help="Panel id to analyse (repeatable; default: all)."),
    tolerance_mm: float = typer.Option(
        50.0, "--tolerance", help="Base tolerance in millimetres."),
    sweep: str = typer.Option(
        "", "--tolerance-sweep", help="Comma-separated tolerances in mm, e.g. 10,25,50,100."),
    report: Path | None = typer.Option(
        None, "--report", help="Output HTML report (default: <model>.diagnose.html)."),
    json_out: Path | None = typer.Option(None, "--json", help="Also write JSON stats here."),
    max_plates: int = typer.Option(
        12, "--max-plates", help="Per-plate figures only for the N worst plates per panel."),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level."),
) -> None:
    """Diagnose the render of MODEL and write an interactive HTML report.

    Exit codes: 0 ok, 2 cannot parse/build the model, 3 cannot write output.
    """
    configure_logging(log_level.upper())
    sweep_mm = _parse_sweep(sweep)
    t0 = time.perf_counter()
    try:
        vessel = _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        logger.error("Cannot parse/build {}: {}", model, exc)
        raise typer.Exit(code=2) from exc
    logger.debug("Timing: parse+build in {:.2f}s", time.perf_counter() - t0)

    from ocx_diagnose.analyse import analyse_model
    from ocx_diagnose.report import write_json, write_report

    results = analyse_model(vessel, set(panel) or None, tolerance_mm, sweep_mm)
    html = report if report is not None else model.with_suffix(".diagnose.html")
    try:
        write_report(results, html, max_plates, title=model.name, header=vessel.header)
        typer.echo(f"Report written to {html}")
        if json_out is not None:
            write_json(results, json_out)
            typer.echo(f"JSON written to {json_out}")
    except OSError as exc:
        logger.error("Cannot write output for {}: {}", model, exc)
        raise typer.Exit(code=3) from exc


def entrypoint() -> None:
    configure_logging()
    app()
