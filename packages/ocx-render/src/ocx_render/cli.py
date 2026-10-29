"""ocx-render — tessellate a .3docx model into GLB + a self-contained HTML viewer."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(add_completion=False)


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(sys.stderr, level=level)


def _load_vessel(model: Path):
    """Parse the model and build the IR (raises on failure)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser

    root = OcxParser().parse(str(model))
    return get_builder(root.schema_version).build(root)


@app.command()
def render(
    model: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False,
                                 help="Path to the .3docx model."),
    destination: Path | None = typer.Option(
        None, "--destination", "-d",
        help="Output .glb path (default: next to the model)."),
    tolerance_mm: float = typer.Option(
        50.0, "--tolerance",
        help="Linear deflection tolerance in millimetres."),
    no_html: bool = typer.Option(
        False, "--no-html", help="Skip writing the HTML viewer page."),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l",
        help="Log level (DEBUG shows per-stage and per-plate timing)."),
) -> None:
    """Tessellate MODEL into a GLB file plus a self-contained HTML viewer.

    Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
    2 cannot parse/build the model, 3 cannot write output.
    """
    from ocx_render.gltf_writer import write_glb
    from ocx_render.html_viewer import write_html
    from ocx_render.render import TessellationOptions, render_model

    configure_logging(log_level.upper())
    t0 = time.perf_counter()
    try:
        vessel = _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        logger.error("Cannot parse/build {}: {}", model, exc)
        raise typer.Exit(code=2) from exc
    logger.debug("Timing: parse+build in {:.2f}s", time.perf_counter() - t0)

    try:
        result = render_model(
            vessel, TessellationOptions(tolerance_m=tolerance_mm / 1000.0))
    except Exception as exc:  # noqa: BLE001 — a whole-model failure renders nothing
        logger.error("Cannot render {}: {}", model, exc)
        raise typer.Exit(code=1) from exc
    if not result.meshes:
        logger.error("No renderable geometry in {} ({} parts skipped)",
                     model, result.skipped_count)
        raise typer.Exit(code=1)

    glb = destination if destination is not None else model.with_suffix(".glb")
    try:
        write_glb(result.meshes, glb)
        typer.echo(f"GLB written to {glb} "
                   f"({result.rendered_count} parts, "
                   f"{result.skipped_count} skipped)")
        if not no_html:
            html = write_html(glb)
            typer.echo(f"Viewer written to {html}")
    except Exception as exc:  # noqa: BLE001 — any write/export failure is exit 3
        logger.error("Cannot write output for {}: {}", model, exc)
        raise typer.Exit(code=3) from exc


def entrypoint() -> None:
    configure_logging()
    app()
