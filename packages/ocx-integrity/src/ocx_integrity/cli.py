"""ocx-integrity — salted aspect-hash manifests, verification, diffs and disclosure bundles."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import typer
from loguru import logger

from ocx_integrity.diff import diff_manifests, format_report
from ocx_integrity.errors import IntegrityError, PartDriftError
from ocx_integrity.manifest import (
    Manifest,
    build_manifest,
    load_manifest,
    save_manifest,
    source_info,
)
from ocx_integrity.proof import DisclosureBundle, check_bundle
from ocx_integrity.proof import prove as prove_bundle
from ocx_integrity.salts import KEY_ENV, generate_key, load_key
from ocx_integrity.verify import verify_model

T = TypeVar("T")

app = typer.Typer(add_completion=False, help=__doc__)

KEY_HELP = f"Hex key file (default: ${KEY_ENV}). The key is never written to any output."


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(sys.stderr, level=level)


def _load_vessel(model: Path):
    """Parse the model and build the IR (raises on failure)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser

    root = OcxParser().parse(str(model))
    return get_builder(root.schema_version).build(root)


def _fail(code: int, message: str, *args: Any) -> typer.Exit:
    logger.error(message, *args)
    return typer.Exit(code=code)


def _key(path: Path | None) -> bytes:
    try:
        return load_key(path)
    except IntegrityError as exc:
        raise _fail(2, "Bad key: {}", exc) from exc


def _vessel(model: Path):
    try:
        return _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        raise _fail(2, "Cannot parse/build {}: {}", model, exc) from exc


def _read_json(path: Path, loader: Callable[[dict[str, Any]], T]) -> T:
    try:
        return loader(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IntegrityError) as exc:
        raise _fail(2, "Cannot load {}: {}", path, exc) from exc


def _read_manifest(path: Path) -> Manifest:
    """Load an untrusted manifest strictly (incl. duplicate-key rejection); exit 2 on failure."""
    try:
        return load_manifest(path)
    except (OSError, IntegrityError) as exc:
        raise _fail(2, "Cannot load {}: {}", path, exc) from exc


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise _fail(3, "Cannot write {}: {}", path, exc) from exc


@app.command()
def keygen(
    output: Path = typer.Option(
        ..., "--output", "-o", dir_okay=False, help="Key file to create (refuses to overwrite)."
    ),
) -> None:
    """Create a new random 32-byte key (hex). Keep it secret; never share it."""
    if output.exists():
        raise _fail(2, "Refusing to overwrite existing key file {}", output)
    _write_text(output, generate_key() + "\n")
    typer.echo(f"Key written to {output} (keep it secret)")


@app.command()
def manifest(
    model: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="Path to the .3docx model."
    ),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        dir_okay=False,
        help="Manifest path (default: <model>.manifest.json).",
    ),
) -> None:
    """Hash every part of MODEL and write the shareable integrity manifest."""
    k = _key(key)
    vessel = _vessel(model)
    try:
        result = build_manifest(vessel, k, source=source_info(model, vessel.schema_version))
    except IntegrityError as exc:
        raise _fail(2, "Cannot build manifest for {}: {}", model, exc) from exc
    for warning in result.warnings:
        logger.warning(warning)
    out = output if output is not None else model.with_suffix(".manifest.json")
    try:
        save_manifest(result, out)
    except OSError as exc:
        raise _fail(3, "Cannot write {}: {}", out, exc) from exc
    typer.echo(
        f"Manifest written to {out}: root {result.root}, "
        f"{result.part_count} parts, {len(result.warnings)} warnings"
    )


@app.command()
def verify(
    model: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="Path to the .3docx model."
    ),
    manifest_file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Stored manifest.json."
    ),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
) -> None:
    """Rebuild MODEL's hashes and compare them with MANIFEST_FILE (exit 1 on any change)."""
    stored = _read_manifest(manifest_file)
    k = _key(key)
    vessel = _vessel(model)
    try:
        report = verify_model(vessel, stored, k)
    except IntegrityError as exc:
        raise _fail(2, "Cannot verify {}: {}", model, exc) from exc
    typer.echo(format_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


@app.command()
def prove(
    model: Path = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="Path to the .3docx model."
    ),
    manifest_file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Stored manifest.json."
    ),
    part: str = typer.Option(..., "--part", "-p", help="Part ID to disclose."),
    aspect: list[str] | None = typer.Option(
        None, "--aspect", "-a", help="Aspect to disclose (repeatable; default: all)."
    ),
    output: Path = typer.Option(
        ..., "--output", "-o", dir_okay=False, help="Bundle path to write."
    ),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
) -> None:
    """Write a disclosure bundle for one part (refused if the part has drifted)."""
    stored = _read_manifest(manifest_file)
    k = _key(key)
    vessel = _vessel(model)
    try:
        bundle = prove_bundle(vessel, stored, k, part, aspect or None)
    except PartDriftError as exc:
        raise _fail(1, "{}", exc) from exc
    except IntegrityError as exc:
        raise _fail(2, "{}", exc) from exc
    _write_text(output, json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False) + "\n")
    typer.echo(f"Bundle written to {output}: part {part}, disclosed {', '.join(bundle.disclosed)}")


@app.command()
def check(
    bundle_file: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Disclosure bundle.json."
    ),
    root: str | None = typer.Option(
        None, "--root", help="Expected root (hex), e.g. taken from the signed manifest."
    ),
) -> None:
    """Verify a disclosure bundle without the key (exit 1 if invalid)."""
    bundle = _read_json(bundle_file, DisclosureBundle.from_dict)
    result = check_bundle(bundle, root=root)
    if result.valid:
        disclosed = ", ".join(bundle.disclosed) or "no aspects"
        typer.echo(
            f"VALID: part {bundle.part_id} ({disclosed}) is included under root {bundle.root}"
        )
        return
    typer.echo("INVALID:")
    for error in result.errors:
        typer.echo(f"  {error}")
    raise typer.Exit(code=1)


@app.command()
def diff(
    old: Path = typer.Argument(..., exists=True, dir_okay=False, help="Older manifest.json."),
    new: Path = typer.Argument(..., exists=True, dir_okay=False, help="Newer manifest.json."),
    fmt: str = typer.Option("text", "--format", "-f", help="Output format: text or json."),
) -> None:
    """Compare two manifests part by part and aspect by aspect (exit 1 on any change)."""
    if fmt not in ("text", "json"):
        raise typer.BadParameter("expected 'text' or 'json'", param_hint="--format")
    a = _read_manifest(old)
    b = _read_manifest(new)
    try:
        report = diff_manifests(a, b)
    except IntegrityError as exc:
        raise _fail(2, "Cannot diff: {}", exc) from exc
    typer.echo(json.dumps(report.to_dict(), indent=2) if fmt == "json" else format_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


def entrypoint() -> None:
    configure_logging()
    app()
