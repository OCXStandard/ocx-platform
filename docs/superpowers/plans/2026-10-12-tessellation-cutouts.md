# Tessellation Cutout (CutBy) Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the tessellated renderer from `feature/tessellated-renderer` into the uv-workspace layout, then add OCX `CutBy` opening support so plates render with their holes cut.

**Architecture:** Tessellation math moves into `packages/ocx-geometry` (pure numpy/shapely/geomdl, no display stack); GLB/HTML writers + `render_model` orchestration go into a new `packages/ocx-render` with its own `ocx-render` CLI. Cutouts: the core builder captures `CutBy` faithfully (`HoleRef` + placement `Transformation`); the renderer resolves catalogue hole shapes into 2D profiles, places them in 3D, and feeds them to the existing `hole_pts` → UV-inversion → earcut pipeline.

**Tech Stack:** Python 3.12, uv workspace, xsdata bindings (`ocx` package, loaded dynamically), numpy, shapely, mapbox-earcut, geomdl, trimesh, typer, loguru, pytest.

**Spec:** `docs/superpowers/specs/2026-10-12-tessellation-cutouts-design.md`

---

## Context primer (read first)

- Repo root: `C:\PythonDev\ocx-platform`. All commands run from the root. Package manager is **uv** (`uv sync --dev`, `uv run pytest`, `uv add --package <member> <dep>`).
- Workspace members live in `packages/`; the root `pyproject.toml` is a virtual workspace root (`[tool.uv.workspace] members = ["packages/*"]`). Single shared test suite in `tests/` (configured with `pythonpath = ["."]`, `addopts = -m "not integration"`).
- The renderer source to port lives on branch **`feature/tessellated-renderer`** under `ocx_model_validator/render/` and `tests/test_render_*.py`. Extract files with `git show feature/tessellated-renderer:<path>` — do **not** merge the branch (it predates the workspace split).
- IR conventions: frozen dataclasses (except container records like `IrPlate`/`IrPanel`), every optional field defaults to `None`/`[]`, quantities keep raw OCX unit-id strings (`Quantity(value, "Um")`). Builders access raw OCX objects only via `getattr(obj, "field", None)`.
- Logging is `loguru` everywhere; no `print()`/stdlib logging in library code.
- xsdata binding field names (verified against `ocx.ocx_320.ocx_320`):
  - `Panel.cut_by` → `CutBy(hole2_dcontour, inner_contour)`
  - `Plate.plate_cut_by` → `PlateCutBy(hole2_dcontour, inner_contour, slot_contour)`
  - `Hole2Dcontour(id, name, guidref, hole_ref, transformation, …)`
  - `Transformation(origin, primary_axis, secondary_axis)`
  - `OcxXml.class_catalogue.hole_shape_catalogue` (the reference model's catalogue location)
  - Parametric variants: `RectangularHole(height, width, fillet_radius)`, `SymmetricalHole(height, width)`, `ParametricCircle(diameter)`, `Ellipse(major_diameter, minor_diameter)`, `RectangularMickeyMouseEars(height, width, radius, displacement)`, `SuperElliptical(major_diameter, minor_diameter, exponent)`.
- Reference model: `models/TR04/tr04_tc13_nast.3docx` (OCX 3.2.0) — 1 panel, 1 plate, 9 `Hole2DContour` entries on the panel, 7 catalogue `Hole2D` shapes.

### Task 0: Branch setup

- [ ] **Step 1: Create the working branch from `feat/add-test-models`** (it contains the committed models)

```powershell
git switch feat/add-test-models
git switch -c feat/tessellation-cutouts
```

---

## Phase 1 — Port the renderer into the workspace

### Task 1: Scaffold `packages/ocx-render` and add geometry dependencies

**Files:**
- Create: `packages/ocx-render/pyproject.toml`
- Create: `packages/ocx-render/README.md`
- Create: `packages/ocx-render/src/ocx_render/__init__.py` (stub for now)
- Modify: `packages/ocx-geometry/pyproject.toml` (via `uv add`)

- [ ] **Step 1: Create `packages/ocx-render/pyproject.toml`**

```toml
[project]
name = "ocx-render"
version = "0.1.0"
description = "Tessellated 3D renderer for OCX models — GLB + self-contained HTML viewer"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "ocx-model-core>=0.5,<0.6",
    "ocx-geometry>=0.1,<0.2",
    "numpy>=2.0",
    "trimesh>=4.0",
    "typer>=0.9",
    "loguru>=0.7",
]

[project.scripts]
ocx-render = "ocx_render.cli:entrypoint"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ocx_render"]

[tool.uv.sources]
ocx-model-core = { workspace = true }
ocx-geometry = { workspace = true }
```

- [ ] **Step 2: Create `packages/ocx-render/README.md`**

```markdown
# ocx-render

Tessellates OCX `.3docx` models (via the schema-neutral IR from `ocx-model-core`
and the geometry kernel in `ocx-geometry`) into a GLB file plus a self-contained
three.js HTML viewer.

    ocx-render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]

Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
2 cannot parse/build the model.
```

- [ ] **Step 3: Create a placeholder `packages/ocx-render/src/ocx_render/__init__.py`** (replaced in Task 3)

```python
"""ocx_render — GLB/HTML rendering of OCX models."""
__version__ = "0.1.0"
```

- [ ] **Step 4: Add dependencies and sync**

```powershell
uv add --package ocx-geometry geomdl shapely mapbox-earcut
uv sync --dev
```

Expected: lockfile updates; `uv run python -c "import shapely, mapbox_earcut, geomdl, trimesh"` succeeds.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-render packages/ocx-geometry/pyproject.toml pyproject.toml uv.lock
git commit -m "chore: scaffold ocx-render package; add geometry tessellation deps"
```

### Task 2: Port tessellation math into ocx-geometry

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/backend.py`, `curves.py`, `mesh.py`, `sections_2d.py`, `surfaces.py`, `sweep.py`, `uv_tessellator.py` (from branch)
- Modify: `packages/ocx-geometry/src/ocx_geometry/measure.py` (absorb `LengthResolver`)

- [ ] **Step 1: Extract the branch files**

```powershell
$dst = "packages/ocx-geometry/src/ocx_geometry"
foreach ($f in "backend","curves","mesh","sections_2d","surfaces","sweep","uv_tessellator") {
  git show "feature/tessellated-renderer:ocx_model_validator/render/$f.py" | Set-Content "$dst/$f.py" -Encoding utf8
}
```

- [ ] **Step 2: Append `LengthResolver` to `measure.py`**

Add the needed imports to the top of `packages/ocx-geometry/src/ocx_geometry/measure.py`:

```python
import numpy as np
from loguru import logger

from ocx_model_core.model.ir.base import IrUnit, Quantity
from ocx_model_core.model.ir.geometry import IrPoint3D
```

and append the class (verbatim from branch `render/length.py`, imports already rewritten):

```python
# Fallback factors for models without a usable unit registry (bare fragments).
_FALLBACK_TO_M = {"Um": 1.0, "Umm": 1e-3, "Ucm": 1e-2, "Udm": 0.1, "Ukm": 1e3}


class LengthResolver:
    """Resolve OCX unit ids to metres, with graceful fallbacks."""

    def __init__(self, registry: dict[str, IrUnit] | None) -> None:
        self._registry = registry or {}
        self._warned: set[str] = set()

    def to_m(self, value: float, unit_id: str) -> float:
        unit = self._registry.get(unit_id)
        if unit is not None:
            return value * unit.to_si_factor
        factor = _FALLBACK_TO_M.get(unit_id)
        if factor is not None:
            return value * factor
        if unit_id not in self._warned:
            self._warned.add(unit_id)
            logger.warning("Unknown length unit id {!r}; assuming metres", unit_id)
        return value

    def point(self, p: IrPoint3D) -> np.ndarray:
        return np.array([self.to_m(p.x, p.unit),
                         self.to_m(p.y, p.unit),
                         self.to_m(p.z, p.unit)], dtype=np.float64)

    def qty(self, q: Quantity | None) -> float | None:
        if q is None:
            return None
        return self.to_m(q.value, q.unit)
```

- [ ] **Step 3: Rewrite imports in the ported files**

Apply these ordered regex replacements to the seven ported files (`backend, curves, mesh, sections_2d, surfaces, sweep, uv_tessellator`):

```powershell
$files = Get-ChildItem packages/ocx-geometry/src/ocx_geometry/*.py -Exclude __init__.py,measure.py
foreach ($f in $files) {
  $t = Get-Content $f.FullName -Raw
  $t = $t -replace 'ocx_model_validator\.render\.length', 'ocx_geometry.measure'
  $t = $t -replace 'ocx_model_validator\.render', 'ocx_geometry'
  $t = $t -replace 'ocx_model_validator\.model', 'ocx_model_core.model'
  Set-Content $f.FullName $t -NoNewline -Encoding utf8
}
```

- [ ] **Step 4: Export the public surface from `ocx_geometry/__init__.py`**

Replace the `__init__.py` content with:

```python
"""ocx_geometry — geometry evaluation kernel for the OCX IR.

Pure computation on ``ocx_model_core`` IR geometry: curve/surface evaluation,
length and area measurement, contour-closure checks and tessellation into
plain numpy mesh arrays. No display or rendering stack.
"""
from ocx_geometry.backend import ITessellator, RenderResult, TessellationOptions
from ocx_geometry.measure import LengthResolver, polyline_length
from ocx_geometry.mesh import PartMesh

__version__ = "0.1.0"

__all__ = [
    "ITessellator",
    "LengthResolver",
    "PartMesh",
    "RenderResult",
    "TessellationOptions",
    "polyline_length",
]
```

Note: `RenderResult` stays physically in `ocx_geometry.backend` (it is the tessellation result container the backends fill); `ocx_render.render` re-exports it as the public API (Task 3).

- [ ] **Step 5: Smoke-check imports**

```powershell
uv run python -c "from ocx_geometry import ITessellator, LengthResolver, PartMesh; from ocx_geometry.uv_tessellator import UvTessellator; print('ok')"
```

Expected: `ok`.

- [ ] **Step 6: Commit**

```powershell
git add packages/ocx-geometry
git commit -m "feat(geometry): port tessellation kernel from feature/tessellated-renderer"
```

### Task 3: Port orchestration and writers into ocx-render

**Files:**
- Create: `packages/ocx-render/src/ocx_render/render.py` (from branch `render/__init__.py`)
- Create: `packages/ocx-render/src/ocx_render/gltf_writer.py`, `html_viewer.py` (from branch)
- Modify: `packages/ocx-render/src/ocx_render/__init__.py`

- [ ] **Step 1: Extract the branch files**

```powershell
$dst = "packages/ocx-render/src/ocx_render"
git show "feature/tessellated-renderer:ocx_model_validator/render/__init__.py" | Set-Content "$dst/render.py" -Encoding utf8
git show "feature/tessellated-renderer:ocx_model_validator/render/gltf_writer.py" | Set-Content "$dst/gltf_writer.py" -Encoding utf8
git show "feature/tessellated-renderer:ocx_model_validator/render/html_viewer.py" | Set-Content "$dst/html_viewer.py" -Encoding utf8
```

- [ ] **Step 2: Rewrite imports** (same rule set; all `render.*` submodules ported in Task 2 now live in `ocx_geometry`)

```powershell
foreach ($f in Get-ChildItem packages/ocx-render/src/ocx_render/render.py, packages/ocx-render/src/ocx_render/gltf_writer.py, packages/ocx-render/src/ocx_render/html_viewer.py) {
  $t = Get-Content $f.FullName -Raw
  $t = $t -replace 'ocx_model_validator\.render\.length', 'ocx_geometry.measure'
  $t = $t -replace 'ocx_model_validator\.render', 'ocx_geometry'
  $t = $t -replace 'ocx_model_validator\.model', 'ocx_model_core.model'
  Set-Content $f.FullName $t -NoNewline -Encoding utf8
}
```

- [ ] **Step 3: Replace `packages/ocx-render/src/ocx_render/__init__.py`**

```python
"""ocx_render — GLB/HTML rendering of OCX models.

``render_model(vessel, options)`` tessellates an ``IrVessel`` into
``PartMesh`` objects; ``gltf_writer``/``html_viewer`` export them.
"""
from ocx_geometry.backend import RenderResult, TessellationOptions
from ocx_geometry.mesh import PartMesh

from ocx_render.render import render_model

__version__ = "0.1.0"

__all__ = ["PartMesh", "RenderResult", "TessellationOptions", "render_model"]
```

- [ ] **Step 4: Smoke-check**

```powershell
uv sync --dev
uv run python -c "from ocx_render import render_model, TessellationOptions; from ocx_render.gltf_writer import write_glb; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-render pyproject.toml uv.lock
git commit -m "feat(render): port render_model orchestration and GLB/HTML writers"
```

### Task 4: The `ocx-render` CLI

**Files:**
- Create: `packages/ocx-render/src/ocx_render/cli.py`

- [ ] **Step 1: Write `cli.py`** (single-command typer app — invoked as `ocx-render MODEL`, no subcommand)

```python
"""ocx-render — tessellate a .3docx model into GLB + a self-contained HTML viewer."""
from __future__ import annotations

import sys
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
) -> None:
    """Tessellate MODEL into a GLB file plus a self-contained HTML viewer.

    Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
    2 cannot parse/build the model.
    """
    from ocx_render.gltf_writer import write_glb
    from ocx_render.html_viewer import write_html
    from ocx_render.render import TessellationOptions, render_model

    try:
        vessel = _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        logger.error("Cannot parse/build {}: {}", model, exc)
        raise typer.Exit(code=2) from exc

    result = render_model(
        vessel, TessellationOptions(tolerance_m=tolerance_mm / 1000.0))
    if not result.meshes:
        logger.error("No renderable geometry in {} ({} parts skipped)",
                     model, result.skipped_count)
        raise typer.Exit(code=1)

    glb = destination if destination is not None else model.with_suffix(".glb")
    write_glb(result.meshes, glb)
    typer.echo(f"GLB written to {glb} "
               f"({result.rendered_count} parts, {result.skipped_count} skipped)")
    if not no_html:
        html = write_html(glb)
        typer.echo(f"Viewer written to {html}")


def entrypoint() -> None:
    configure_logging()
    app()
```

Note: `ocx_render.render` must re-export `TessellationOptions` — it already imports it from `ocx_geometry.backend` (ported file), so `from ocx_render.render import TessellationOptions, render_model` works.

- [ ] **Step 2: Smoke-check the entrypoint**

```powershell
uv sync --dev
uv run ocx-render --help
```

Expected: usage text with `--destination`, `--tolerance`, `--no-html`.

- [ ] **Step 3: Commit**

```powershell
git add packages/ocx-render uv.lock
git commit -m "feat(render): ocx-render CLI entrypoint (GLB + HTML viewer)"
```

### Task 5: Port the render test suite

**Files:**
- Create: `tests/test_render_basics.py`, `test_render_cli.py`, `test_render_curves.py`, `test_render_gltf.py`, `test_render_html.py`, `test_render_model.py`, `test_render_sections_2d.py`, `test_render_surfaces.py`, `test_render_surfaces_ext.py`, `test_render_sweep.py`, `test_render_uv_tessellator.py` (from branch)

- [ ] **Step 1: Extract and rewrite imports**

```powershell
foreach ($f in "basics","cli","curves","gltf","html","model","sections_2d","surfaces","surfaces_ext","sweep","uv_tessellator") {
  git show "feature/tessellated-renderer:tests/test_render_$f.py" | Set-Content "tests/test_render_$f.py" -Encoding utf8
}
foreach ($f in Get-ChildItem tests/test_render_*.py) {
  $t = Get-Content $f.FullName -Raw
  $t = $t -replace 'ocx_model_validator\.render\.length', 'ocx_geometry.measure'
  $t = $t -replace 'from ocx_model_validator\.render import', 'from ocx_render.render import'
  $t = $t -replace 'ocx_model_validator\.render\.gltf_writer', 'ocx_render.gltf_writer'
  $t = $t -replace 'ocx_model_validator\.render\.html_viewer', 'ocx_render.html_viewer'
  $t = $t -replace 'ocx_model_validator\.render', 'ocx_geometry'
  $t = $t -replace 'ocx_model_validator\.model', 'ocx_model_core.model'
  $t = $t -replace 'ocx_model_validator\.cli', 'ocx_render.cli'
  Set-Content $f.FullName $t -NoNewline -Encoding utf8
}
```

- [ ] **Step 2: Fix CLI invocations in `tests/test_render_cli.py`**

The old CLI was `validator render MODEL`; the new app is single-command, so drop the leading `"render"` argument in every `runner.invoke(app, [...])` call:

```python
# before
result = runner.invoke(app, ["render", str(bad)])
# after
result = runner.invoke(app, [str(bad)])
```

Also check any monkeypatching of `ocx_render.cli` module attributes (`cli_mod._load_vessel`, writer functions) still targets existing names — `_load_vessel` kept its name in Task 4. If the old test monkeypatches `cli_mod` render imports, note the new CLI imports writers *inside* the command function, so monkeypatch `ocx_render.gltf_writer.write_glb` / `ocx_render.html_viewer.write_html` directly instead.

- [ ] **Step 3: Run the full suite**

```powershell
uv run pytest
```

Expected: PASS (all pre-existing tests plus the ported render tests). Fix any residual import path issues; functional changes are out of scope for this task.

- [ ] **Step 4: Commit**

```powershell
git add tests
git commit -m "test(render): port render test suite to workspace layout"
```

---

## Phase 2 — CutBy cutout support

### Task 6: IR types for transformations and CutBy holes

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/geometry.py` (add `IrTransformation`)
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/catalogues.py` (add `IrParametricHole`; retype `IrHole2D.parametric`)
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/structural.py` (add `IrHole2DContour`; new fields on `IrPlate`/`IrPanel`)
- Modify: `packages/ocx-model-core/src/ocx_model_core/model/ir/__init__.py` (exports)
- Test: `tests/test_ir_cutby.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_ir_cutby.py`

```python
"""IR types for CutBy openings: IrTransformation, IrHole2DContour, IrParametricHole."""
from ocx_model_core.model.ir import (
    IrHole2D,
    IrHole2DContour,
    IrParametricHole,
    IrTransformation,
)
from ocx_model_core.model.ir.base import Quantity, Ref
from ocx_model_core.model.ir.geometry import IrPoint3D, IrVector3D
from ocx_model_core.model.ir.structural import IrPanel, IrPlate


def test_transformation_defaults():
    t = IrTransformation()
    assert t.origin is None and t.primary_axis is None and t.secondary_axis is None


def test_hole2dcontour_fields():
    t = IrTransformation(origin=IrPoint3D(1, 2, 3, "Um"),
                         primary_axis=IrVector3D(1, 0, 0),
                         secondary_axis=IrVector3D(0, 0, 1))
    hc = IrHole2DContour(id="hc1", hole_ref=Ref("H1"), transformation=t)
    assert hc.hole_ref.local_ref == "H1"
    assert hc.transformation.origin.y == 2
    assert hc.name is None and hc.guidref is None


def test_parametric_hole_defaults_and_hole2d_typing():
    p = IrParametricHole(variant="rectangular_hole",
                         height=Quantity(0.8, "Um"), width=Quantity(0.6, "Um"))
    assert p.fillet_radius is None and p.exponent is None
    h = IrHole2D(id="h1", parametric=p)
    assert h.parametric.variant == "rectangular_hole"


def test_panel_and_plate_cutby_defaults():
    panel = IrPanel(id="p1")
    assert panel.cut_by_holes == [] and panel.cut_by_contours == []
    from ocx_model_core.model.ir.base import ParentKind, ParentRef
    plate = IrPlate(id="pl1", parent_ref=ParentRef(ParentKind.PANEL, "p1"))
    assert plate.cut_by_holes == [] and plate.cut_by_contours == []
```

- [ ] **Step 2: Run it to verify it fails**

```powershell
uv run pytest tests/test_ir_cutby.py
```

Expected: FAIL — `ImportError: cannot import name 'IrHole2DContour'`.

- [ ] **Step 3: Implement the IR types**

In `model/ir/geometry.py`, next to the other primitive types, add:

```python
@dataclass(frozen=True)
class IrTransformation:
    """OCX Transformation — a local placement frame (origin + two axes)."""
    origin: IrPoint3D | None = None
    primary_axis: IrVector3D | None = None
    secondary_axis: IrVector3D | None = None
```

In `model/ir/catalogues.py`, above `IrHole2D`, add:

```python
@dataclass(frozen=True)
class IrParametricHole:
    """Dimensions of a parametric hole-shape variant from the catalogue."""
    variant: str
    height: Quantity | None = None
    width: Quantity | None = None
    radius: Quantity | None = None
    fillet_radius: Quantity | None = None
    diameter: Quantity | None = None
    major_diameter: Quantity | None = None
    minor_diameter: Quantity | None = None
    displacement: Quantity | None = None
    exponent: Quantity | None = None
```

and retype `IrHole2D.parametric`:

```python
    parametric: IrParametricHole | None = None
```

In `model/ir/structural.py` (imports: add `IrTransformation` to the `geometry` import block; `IrParametricHole` is not needed here), add above `IrPlate`:

```python
@dataclass(frozen=True)
class IrHole2DContour:
    """A CutBy opening placement: catalogue hole ref + local placement frame."""
    id: str
    name: str | None = None
    guidref: str | None = None
    hole_ref: Ref | None = None
    transformation: IrTransformation | None = None
```

Add to `IrPlate` (after `cut_by_contours`):

```python
    cut_by_holes: list[IrHole2DContour] = field(default_factory=list)
```

Add to `IrPanel` (after `unbounded_geometry`):

```python
    cut_by_holes: list[IrHole2DContour] = field(default_factory=list)
    cut_by_contours: list[IrCurve3D] = field(default_factory=list)
```

In `model/ir/__init__.py`: add `IrParametricHole` to the `catalogues` import and `__all__`; add `IrHole2DContour` to the `structural` import and `__all__`; add `IrTransformation` to the `geometry` import and `__all__`.

- [ ] **Step 4: Run tests**

```powershell
uv run pytest tests/test_ir_cutby.py tests/test_ir_package_surface.py
```

Expected: `test_ir_cutby.py` PASSES. If `test_ir_package_surface.py` asserts a fixed export list, add the three new names there.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-model-core tests/test_ir_cutby.py tests/test_ir_package_surface.py
git commit -m "feat(ir): IrTransformation, IrHole2DContour, IrParametricHole; CutBy fields on panel/plate"
```

### Task 7: Builder — parametric hole dimensions + catalogue discovery under ClassCatalogue

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (`_build_hole_catalogue`, its call site in `build()`, new `_parametric_hole`)
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/catalogues.py:120` (parametric now a dataclass)
- Modify: `tests/test_builder_320_gap.py:377`, `tests/test_builder_extensions.py:473`, `tests/test_reporting_generators.py:193-194`
- Test: `tests/test_builder_cutby.py` (new)

- [ ] **Step 1: Write the failing tests** — create `tests/test_builder_cutby.py`

```python
"""Builder coverage for CutBy openings and parametric hole dimensions."""
from types import SimpleNamespace as NS

from ocx_model_core.builders.v3_builder import OcxV3Builder
from ocx_model_core.model.ir import IrVessel


def _b() -> OcxV3Builder:
    return OcxV3Builder()


def _qty(value, unit="Um"):
    return NS(numericvalue=value, unit=unit)


def _hole2d(hid, **variants):
    base = dict(id=hid, name=None, guidref=f"guid-{hid}", contour=None,
                ellipse=None, rectangular_mickey_mouse_ears=None,
                rectangular_hole=None, super_elliptical=None,
                symmetrical_hole=None, parametric_circle=None)
    base.update(variants)
    return NS(**base)


class TestParametricDimensions:
    def test_rectangular_hole_dims(self):
        cat = NS(id="HC", name=None, hole2_d=[_hole2d(
            "H1", rectangular_hole=NS(height=_qty(0.8), width=_qty(0.6),
                                      fillet_radius=_qty(0.15)))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        p = ir.hole_shape_catalogue.holes["H1"].parametric
        assert p.variant == "rectangular_hole"
        assert p.height.value == 0.8 and p.width.value == 0.6
        assert p.fillet_radius.value == 0.15
        assert p.diameter is None

    def test_circle_and_superellipse_dims(self):
        cat = NS(id="HC", name=None, hole2_d=[
            _hole2d("H2", parametric_circle=NS(diameter=_qty(0.5))),
            _hole2d("H3", super_elliptical=NS(major_diameter=_qty(1.2),
                                              minor_diameter=_qty(0.6),
                                              exponent=_qty(2.5, "UDimless")))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        assert ir.hole_shape_catalogue.holes["H2"].parametric.diameter.value == 0.5
        p3 = ir.hole_shape_catalogue.holes["H3"].parametric
        assert p3.variant == "super_elliptical" and p3.exponent.value == 2.5
```

- [ ] **Step 2: Run to verify failure**

```powershell
uv run pytest tests/test_builder_cutby.py
```

Expected: FAIL — `parametric` is a dict (`{"variant": ...}`) with no `.variant` attribute / no dims.

- [ ] **Step 3: Implement in `v3_builder.py`**

Add `IrParametricHole` to the catalogues import at the top. Add this method next to `_build_hole_catalogue`:

```python
    _PARAMETRIC_ATTRS = ("ellipse", "rectangular_mickey_mouse_ears",
                         "rectangular_hole", "super_elliptical",
                         "symmetrical_hole", "parametric_circle")

    def _parametric_hole(self, h) -> IrParametricHole | None:
        """First present parametric variant on a raw Hole2D, with dimensions."""
        for attr in self._PARAMETRIC_ATTRS:
            p = getattr(h, attr, None)
            if p is None:
                continue
            return IrParametricHole(
                variant=attr,
                height=self._qty(getattr(p, "height", None)),
                width=self._qty(getattr(p, "width", None)),
                radius=self._qty(getattr(p, "radius", None)),
                fillet_radius=self._qty(getattr(p, "fillet_radius", None)),
                diameter=self._qty(getattr(p, "diameter", None)),
                major_diameter=self._qty(getattr(p, "major_diameter", None)),
                minor_diameter=self._qty(getattr(p, "minor_diameter", None)),
                displacement=self._qty(getattr(p, "displacement", None)),
                exponent=self._qty(getattr(p, "exponent", None)))
        return None
```

In `_build_hole_catalogue`, replace the `parametric = None / for attr in (...)` block with:

```python
            parametric = self._parametric_hole(h)
```

At the call site in `build()` (currently ~line 233), extend the lookup to cover `ClassCatalogue`:

```python
        self._build_hole_catalogue(
            getattr(root, "hole_shape_catalogue", None)
            or getattr(vessel_raw, "hole_shape_catalogue", None)
            or _first(getattr(_first(getattr(root, "class_catalogue", None)),
                              "hole_shape_catalogue", None)),
            ir)
```

(`_first` is the existing module-level helper; `getattr(None, ..., None)` is safe.)

- [ ] **Step 4: Update the three existing consumers**

`tests/test_builder_320_gap.py:377`:

```python
    assert ir.hole_shape_catalogue.holes["H1"].parametric.variant == "ellipse"
```

`tests/test_builder_extensions.py:473`:

```python
    assert v.hole_shape_catalogue.holes["H2"].parametric.variant == "rectangular_hole"
```

`tests/test_reporting_generators.py:193-194` — replace the dict with a typed value (add `IrParametricHole` and `Quantity` to that file's imports):

```python
        holes={"H1": IrHole2D(id="H1", name="Manhole",
                              parametric=IrParametricHole(
                                  variant="symmetrical_hole",
                                  height=Quantity(600, "Umm"),
                                  width=Quantity(400, "Umm")))},
```

and update that test's expected cell string to `"symmetrical_hole; height=600 Umm; width=400 Umm"`.

`packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/catalogues.py:120` — replace the dict join:

```python
            p = h.parametric
            if p is None:
                parametric = None
            else:
                from dataclasses import fields as _dc_fields
                dims = [f"{f.name}={getattr(p, f.name).value} {getattr(p, f.name).unit}".rstrip()
                        for f in _dc_fields(p)
                        if f.name != "variant" and getattr(p, f.name) is not None]
                parametric = "; ".join([p.variant, *dims])
```

(move the `fields` import to the top of the module with the other imports).

- [ ] **Step 5: Run the affected tests**

```powershell
uv run pytest tests/test_builder_cutby.py tests/test_builder_320_gap.py tests/test_builder_extensions.py tests/test_reporting_generators.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages tests
git commit -m "feat(builder): parametric hole dimensions; find HoleShapeCatalogue under ClassCatalogue"
```

### Task 8: Builder — parse CutBy on panels and plates

**Files:**
- Modify: `packages/ocx-model-core/src/ocx_model_core/builders/v3_builder.py` (new `_build_hole2d_contours`; wire into `_build_panel` and `_build_plate`)
- Test: `tests/test_builder_cutby.py` (extend)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_builder_cutby.py`

```python
def _transformation():
    return NS(origin=NS(coordinates=[8.5, 10.0, 9.9], unit="Um"),
              primary_axis=NS(direction=[0.0, 0.0, -1.0]),
              secondary_axis=NS(direction=[1.0, 0.0, 0.0]))


def _hole2d_contour(cid, ref):
    return NS(id=cid, name=None, guidref=f"guid-{cid}",
              hole_ref=NS(local_ref=ref, guidref=f"guid-{ref}", ref_type="ocx:Hole2D",
                          offset=None, offset_direction=None),
              transformation=_transformation())


class TestCutByParsing:
    def test_panel_cut_by_holes(self):
        raw = NS(id="pan1", name="P", guidref=None, function_type=None,
                 tightness=None, point_on_surface=None,
                 composed_of=None, stiffened_by=None, limited_by=None,
                 unbounded_geometry=None,
                 cut_by=NS(hole2_dcontour=[_hole2d_contour("hc1", "H1"),
                                           _hole2d_contour("hc2", "H2")],
                           inner_contour=[]))
        ir = IrVessel(id="v1")
        panel = _b()._build_panel(raw, ir, "v1")
        assert len(panel.cut_by_holes) == 2
        hc = panel.cut_by_holes[0]
        assert hc.id == "hc1"
        assert hc.hole_ref.local_ref == "H1"
        assert hc.transformation.origin.x == 8.5
        assert hc.transformation.primary_axis.z == -1.0
        assert hc.transformation.secondary_axis.x == 1.0

    def test_panel_without_cut_by_is_empty(self):
        raw = NS(id="pan2", name=None, guidref=None, function_type=None,
                 tightness=None, point_on_surface=None, composed_of=None,
                 stiffened_by=None, limited_by=None, unbounded_geometry=None)
        ir = IrVessel(id="v1")
        panel = _b()._build_panel(raw, ir, "v1")
        assert panel.cut_by_holes == [] and panel.cut_by_contours == []

    def test_plate_cut_by_holes_from_plate_cut_by(self):
        from ocx_model_core.model.ir.base import ParentKind, ParentRef
        raw = NS(id="pl1", name=None, guidref=None, plate_material=None,
                 net_area=None, function_type=None, outer_contour=None,
                 point_on_surface=None,
                 plate_cut_by=NS(hole2_dcontour=[_hole2d_contour("hc3", "H3")],
                                 inner_contour=[], slot_contour=[]))
        plate = _b()._build_plate(raw, ParentRef(ParentKind.PANEL, "pan1"))
        assert len(plate.cut_by_holes) == 1
        assert plate.cut_by_holes[0].hole_ref.local_ref == "H3"

    def test_missing_transformation_is_none(self):
        hc = _hole2d_contour("hc4", "H4")
        hc.transformation = None
        raw_cut_by = NS(hole2_dcontour=[hc], inner_contour=[])
        out = _b()._build_hole2d_contours(raw_cut_by)
        assert out[0].transformation is None
```

- [ ] **Step 2: Run to verify failure**

```powershell
uv run pytest tests/test_builder_cutby.py -k CutByParsing
```

Expected: FAIL — `AttributeError: 'OcxV3Builder' object has no attribute '_build_hole2d_contours'` (and missing panel fields).

- [ ] **Step 3: Implement**

Add `IrHole2DContour` to the structural import and `IrTransformation` to the geometry import at the top of `v3_builder.py`. Add below `_cut_by_contours`:

```python
    def _build_hole2d_contours(self, cut_by) -> list[IrHole2DContour]:
        """Extract CutBy/PlateCutBy Hole2DContour placements (ref + frame)."""
        out: list[IrHole2DContour] = []
        if cut_by is None:
            return out
        for hc in _children(getattr(cut_by, "hole2_dcontour", None) or []):
            tr = getattr(hc, "transformation", None)
            transformation = None
            if tr is not None:
                transformation = IrTransformation(
                    origin=self._pt(getattr(tr, "origin", None)),
                    primary_axis=self._vec(getattr(tr, "primary_axis", None)),
                    secondary_axis=self._vec(getattr(tr, "secondary_axis", None)))
            out.append(IrHole2DContour(
                id=getattr(hc, "id", None) or "",
                name=getattr(hc, "name", None),
                guidref=getattr(hc, "guidref", None),
                hole_ref=self._ref(getattr(hc, "hole_ref", None)),
                transformation=transformation))
        return out
```

In `_build_panel`, add to the `IrPanel(...)` constructor call (after `unbounded_geometry=...`):

```python
            cut_by_holes=self._build_hole2d_contours(getattr(raw, "cut_by", None)),
            cut_by_contours=self._cut_by_contours(getattr(raw, "cut_by", None)),
```

(`_cut_by_contours` already reads `inner_contour` first, which is `CutBy`'s inline-contour field.)

In `_build_plate`, add to the `IrPlate(...)` constructor call (after `cut_by_contours=...`):

```python
            cut_by_holes=self._build_hole2d_contours(getattr(raw, "plate_cut_by", None)),
```

- [ ] **Step 4: Run tests**

```powershell
uv run pytest tests/test_builder_cutby.py tests/test_ir_builder.py tests/test_builders.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-model-core tests/test_builder_cutby.py
git commit -m "feat(builder): capture CutBy Hole2DContour placements on panels and plates"
```

### Task 9: `ocx_geometry/holes.py` — parametric profiles and 3D placement

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/holes.py`
- Test: `tests/test_render_holes.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_render_holes.py`

```python
"""Parametric hole profiles and 3D placement."""
import numpy as np
import pytest
from shapely.geometry import Polygon

from ocx_geometry.holes import parametric_profile, place_hole
from ocx_geometry.measure import LengthResolver
from ocx_model_core.model.ir.base import Quantity
from ocx_model_core.model.ir.catalogues import IrParametricHole
from ocx_model_core.model.ir.geometry import IrPoint3D, IrTransformation, IrVector3D

L = LengthResolver(None)
TOL = 0.005


def q(v):
    return Quantity(v, "Um")


def _bbox(p):
    return (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())


def _poly(p):
    poly = Polygon(p)
    assert poly.is_valid and poly.is_simple
    return poly


class TestParametricProfiles:
    def test_circle(self):
        p = parametric_profile(
            IrParametricHole("parametric_circle", diameter=q(0.5)), L, TOL)
        assert np.allclose(_bbox(p), (-0.25, -0.25, 0.25, 0.25), atol=0.01)
        assert len(p) >= 12
        assert _poly(p).area == pytest.approx(np.pi * 0.25**2, rel=0.02)

    def test_ellipse(self):
        p = parametric_profile(
            IrParametricHole("ellipse", major_diameter=q(1.2),
                             minor_diameter=q(0.6)), L, TOL)
        assert np.allclose(_bbox(p), (-0.6, -0.3, 0.6, 0.3), atol=0.01)
        assert _poly(p).area == pytest.approx(np.pi * 0.6 * 0.3, rel=0.02)

    def test_rectangle_sharp(self):
        p = parametric_profile(
            IrParametricHole("rectangular_hole", height=q(1.0), width=q(0.7),
                             fillet_radius=q(0.0)), L, TOL)
        assert _poly(p).area == pytest.approx(0.7, rel=1e-6)

    def test_rectangle_fillet(self):
        p = parametric_profile(
            IrParametricHole("rectangular_hole", height=q(0.8), width=q(0.6),
                             fillet_radius=q(0.15)), L, TOL)
        expected = 0.8 * 0.6 - (4.0 - np.pi) * 0.15**2
        assert _poly(p).area == pytest.approx(expected, rel=0.02)

    def test_stadium(self):
        p = parametric_profile(
            IrParametricHole("symmetrical_hole", height=q(0.8), width=q(0.6)),
            L, TOL)
        assert np.allclose(_bbox(p), (-0.3, -0.4, 0.3, 0.4), atol=0.01)
        expected = 0.6 * (0.8 - 0.6) + np.pi * 0.3**2
        assert _poly(p).area == pytest.approx(expected, rel=0.02)

    def test_superellipse_exponent_2_matches_ellipse(self):
        p = parametric_profile(
            IrParametricHole("super_elliptical", major_diameter=q(1.2),
                             minor_diameter=q(0.6),
                             exponent=Quantity(2.0, "UDimless")), L, TOL)
        assert _poly(p).area == pytest.approx(np.pi * 0.6 * 0.3, rel=0.02)

    def test_mickey_ears_bigger_than_rectangle(self):
        p = parametric_profile(
            IrParametricHole("rectangular_mickey_mouse_ears", height=q(0.8),
                             width=q(2.0), radius=q(0.05),
                             displacement=q(0.01)), L, TOL)
        assert _poly(p).area > 0.8 * 2.0

    def test_unknown_variant_returns_none(self):
        assert parametric_profile(IrParametricHole("weird"), L, TOL) is None

    def test_missing_dimensions_return_none(self):
        assert parametric_profile(
            IrParametricHole("parametric_circle"), L, TOL) is None
        assert parametric_profile(None, L, TOL) is None


class TestPlaceHole:
    def _frame(self):
        return IrTransformation(origin=IrPoint3D(1.0, 2.0, 3.0, "Um"),
                                primary_axis=IrVector3D(1, 0, 0),
                                secondary_axis=IrVector3D(0, 0, 1))

    def test_unit_square_placement(self):
        square = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        out = place_hole(square, self._frame(), L)
        assert np.allclose(out[0], [1.0, 2.0, 3.0])
        assert np.allclose(out[1], [2.0, 2.0, 3.0])   # +x along primary
        assert np.allclose(out[2], [2.0, 2.0, 4.0])   # +y along secondary
    def test_secondary_axis_is_orthogonalized(self):
        t = IrTransformation(origin=IrPoint3D(0, 0, 0, "Um"),
                             primary_axis=IrVector3D(1, 0, 0),
                             secondary_axis=IrVector3D(1, 1, 0))
        out = place_hole(np.array([[0.0, 1.0]]), t, L)
        assert np.allclose(out[0], [0.0, 1.0, 0.0], atol=1e-9)

    def test_degenerate_frames_return_none(self):
        sq = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        assert place_hole(sq, None, L) is None
        t = IrTransformation(origin=IrPoint3D(0, 0, 0, "Um"),
                             primary_axis=IrVector3D(1, 0, 0),
                             secondary_axis=IrVector3D(1, 0, 0))  # parallel
        assert place_hole(sq, t, L) is None
```

- [ ] **Step 2: Run to verify failure**

```powershell
uv run pytest tests/test_render_holes.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_geometry.holes'`.

- [ ] **Step 3: Implement `packages/ocx-geometry/src/ocx_geometry/holes.py`**

```python
"""Hole-shape profile generation and 3D placement for CutBy openings.

``parametric_profile`` turns an ``IrParametricHole`` into a closed (N, 2)
polygon in metres centred on the local origin; ``place_hole`` maps a 2D
profile onto its 3D placement frame (origin + primary/secondary axes).
"""
from __future__ import annotations

import numpy as np
from loguru import logger
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import box
from shapely.ops import unary_union

from ocx_geometry.measure import LengthResolver
from ocx_model_core.model.ir.catalogues import IrParametricHole
from ocx_model_core.model.ir.geometry import IrTransformation

_MIN_SEGMENTS = 12


def _circle_segments(r: float, tol: float) -> int:
    """Segment count so the sagitta of each chord stays below ``tol``."""
    if r <= tol:
        return _MIN_SEGMENTS
    return max(_MIN_SEGMENTS,
               int(np.ceil(2.0 * np.pi / (2.0 * np.arccos(1.0 - tol / r)))))


def _ring(poly) -> np.ndarray | None:
    """Exterior ring of a shapely polygon as an open (N, 2) array."""
    try:
        coords = np.asarray(poly.exterior.coords, dtype=np.float64)[:-1, :2]
    except Exception:  # noqa: BLE001 — degenerate geometry disqualifies itself
        return None
    return coords if len(coords) >= 3 else None


def parametric_profile(hole: IrParametricHole | None, length: LengthResolver,
                       tol: float) -> np.ndarray | None:
    """Closed (N, 2) polygon in metres, centred on the local origin, or None."""
    if hole is None:
        return None
    v = hole.variant

    if v == "parametric_circle":
        d = length.qty(hole.diameter)
        if not d or d <= 0:
            return None
        r = d / 2.0
        t = np.linspace(0.0, 2.0 * np.pi, _circle_segments(r, tol),
                        endpoint=False)
        return np.column_stack([r * np.cos(t), r * np.sin(t)])

    if v in ("ellipse", "super_elliptical"):
        a = length.qty(hole.major_diameter)
        b = length.qty(hole.minor_diameter)
        if not a or not b or a <= 0 or b <= 0:
            return None
        a, b = a / 2.0, b / 2.0
        e = 2.0
        if v == "super_elliptical" and hole.exponent is not None:
            e = hole.exponent.value or 2.0
        t = np.linspace(0.0, 2.0 * np.pi, _circle_segments(max(a, b), tol),
                        endpoint=False)
        c, s = np.cos(t), np.sin(t)
        return np.column_stack([a * np.sign(c) * np.abs(c) ** (2.0 / e),
                                b * np.sign(s) * np.abs(s) ** (2.0 / e)])

    if v in ("rectangular_hole", "symmetrical_hole"):
        h = length.qty(hole.height)
        w = length.qty(hole.width)
        if not h or not w or h <= 0 or w <= 0:
            return None
        if v == "symmetrical_hole":
            rf = min(h, w) / 2.0                       # stadium: semicircular ends
        else:
            rf = length.qty(hole.fillet_radius) or 0.0
        rf = min(rf, h / 2.0, w / 2.0)
        if rf <= 0.0:
            return _ring(box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0))
        q = max(2, _circle_segments(rf, tol) // 4)
        core = box(-(w / 2.0 - rf), -(h / 2.0 - rf), w / 2.0 - rf, h / 2.0 - rf)
        return _ring(core.buffer(rf, quad_segs=q))

    if v == "rectangular_mickey_mouse_ears":
        h = length.qty(hole.height)
        w = length.qty(hole.width)
        r = length.qty(hole.radius)
        disp = length.qty(hole.displacement) or 0.0
        if not h or not w or not r or h <= 0 or w <= 0 or r <= 0:
            return None
        q = max(2, _circle_segments(r, tol) // 4)
        cx, cy = w / 2.0 - disp, h / 2.0 - disp
        ears = [ShapelyPoint(sx * cx, sy * cy).buffer(r, quad_segs=q)
                for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        return _ring(unary_union(
            [box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0), *ears]))

    logger.debug("Unknown parametric hole variant {!r}", v)
    return None


def place_hole(profile_2d: np.ndarray,
               transformation: IrTransformation | None,
               length: LengthResolver) -> np.ndarray | None:
    """Map a local (N, 2) profile onto its 3D placement frame → (N, 3) metres."""
    if transformation is None or transformation.origin is None:
        return None
    p, s = transformation.primary_axis, transformation.secondary_axis
    if p is None or s is None:
        return None
    pv = np.array([p.x, p.y, p.z], dtype=np.float64)
    sv = np.array([s.x, s.y, s.z], dtype=np.float64)
    p_len = np.linalg.norm(pv)
    if p_len < 1e-12:
        return None
    pv /= p_len
    sv = sv - (sv @ pv) * pv                            # re-orthogonalize
    s_len = np.linalg.norm(sv)
    if s_len < 1e-12:
        return None
    sv /= s_len
    origin = length.point(transformation.origin)
    return (origin[None, :]
            + profile_2d[:, :1] * pv[None, :]
            + profile_2d[:, 1:2] * sv[None, :])
```

> Dimension semantics note: `SymmetricalHole` is modelled as a stadium
> (rectangle with semicircular ends on the shorter dimension) and the
> mickey-ears lobes sit at all four corners offset inward by `displacement`.
> Cross-check both against the schema annotations in
> `ocx.ocx_320.ocx_320` docstrings while implementing; adjust the generator
> (not the interface) if the annotations say otherwise.

- [ ] **Step 4: Run tests**

```powershell
uv run pytest tests/test_render_holes.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-geometry/src/ocx_geometry/holes.py tests/test_render_holes.py
git commit -m "feat(geometry): parametric hole profiles and 3D placement for CutBy openings"
```

### Task 10: Wire CutBy holes into `render_model`

**Files:**
- Modify: `packages/ocx-render/src/ocx_render/render.py`
- Test: `tests/test_render_model.py` (extend)

- [ ] **Step 1: Write the failing test** — append to `tests/test_render_model.py`

```python
def _triangle_area(m):
    v, t = m.vertices, m.triangles
    a = v[t[:, 1]] - v[t[:, 0]]
    b = v[t[:, 2]] - v[t[:, 0]]
    return 0.5 * float(np.linalg.norm(np.cross(a, b), axis=1).sum())


class TestCutByHoles:
    def _vessel_with_hole(self, with_transformation=True):
        from ocx_model_core.model.ir.base import Quantity as Q
        from ocx_model_core.model.ir.catalogues import (
            IrHole2D,
            IrHoleShapeCatalogue,
            IrParametricHole,
        )
        from ocx_model_core.model.ir.geometry import IrTransformation
        from ocx_model_core.model.ir.structural import IrHole2DContour

        vessel = make_vessel()
        vessel.hole_shape_catalogue = IrHoleShapeCatalogue(
            id="HC", holes={"H1": IrHole2D(
                id="H1", parametric=IrParametricHole(
                    "parametric_circle", diameter=Q(1.0, "Um")))})
        tr = (IrTransformation(origin=pt(2, 1, 0),
                               primary_axis=IrVector3D(1, 0, 0),
                               secondary_axis=IrVector3D(0, 1, 0))
              if with_transformation else None)
        vessel.panels["pan1"].cut_by_holes.append(
            IrHole2DContour(id="hc1", hole_ref=Ref("H1"), transformation=tr))
        return vessel

    def test_panel_hole_is_cut_from_plate(self):
        full = _triangle_area(next(
            m for m in render_model(make_vessel()).meshes if m.kind == "plate"))
        holed = _triangle_area(next(
            m for m in render_model(self._vessel_with_hole()).meshes
            if m.kind == "plate"))
        # plate is 4 x 2 m; the Ø1 m hole removes ~0.785 m²
        assert holed == pytest.approx(full - np.pi * 0.5**2, rel=0.05)

    def test_unresolvable_hole_ref_is_logged_not_fatal(self):
        vessel = self._vessel_with_hole()
        vessel.hole_shape_catalogue.holes.clear()
        result = render_model(vessel)
        assert any(m.kind == "plate" for m in result.meshes)
        assert result.skipped.get("hole:hc1") == "unresolvable HoleRef"

    def test_missing_transformation_is_logged_not_fatal(self):
        result = render_model(self._vessel_with_hole(with_transformation=False))
        assert any(m.kind == "plate" for m in result.meshes)
        assert result.skipped.get("hole:hc1") == "missing or degenerate transformation"
```

Also add `import pytest` to the file's imports if not present.

- [ ] **Step 2: Run to verify failure**

```powershell
uv run pytest tests/test_render_model.py -k CutByHoles
```

Expected: FAIL — hole area not removed (`holed == full`) and no `hole:hc1` skip entries.

- [ ] **Step 3: Implement in `packages/ocx-render/src/ocx_render/render.py`**

Add to the imports:

```python
from ocx_geometry.holes import parametric_profile, place_hole
from ocx_geometry.measure import LengthResolver
```

(`LengthResolver` import may already exist from the port — keep one.)

Add this module-level function above `_tessellate_plates`:

```python
def _hole_polylines(plate, panel, vessel: IrVessel, length: LengthResolver,
                    options: TessellationOptions
                    ) -> tuple[list[np.ndarray], dict[str, str]]:
    """All hole polylines for one plate: inline contours + resolved CutBy holes.

    Returns (hole polylines in metres, failures keyed ``hole:<id>``).
    Panel-level holes are offered to every plate of the panel; the UV
    polygon clean-up clips or drops holes outside the plate region.
    """
    holes: list[np.ndarray] = []
    failures: dict[str, str] = {}

    inline = list(plate.cut_by_contours)
    if panel is not None:
        inline += panel.cut_by_contours
    for c in inline:
        h = sample_contour(c, length, options.tolerance_m,
                           options.snap_tolerance_m)
        if h is not None:
            holes.append(h)

    entries = list(plate.cut_by_holes)
    if panel is not None:
        entries += panel.cut_by_holes
    if not entries:
        return holes, failures

    cat = vessel.hole_shape_catalogue
    for hc in entries:
        key = f"hole:{hc.id or (hc.hole_ref.local_ref if hc.hole_ref else '?')}"
        shape = None
        if cat is not None and hc.hole_ref is not None:
            shape = cat.holes.get(hc.hole_ref.local_ref)
            if shape is None and hc.hole_ref.guidref:
                shape = next((h for h in cat.holes.values()
                              if h.guidref == hc.hole_ref.guidref), None)
        if shape is None:
            failures[key] = "unresolvable HoleRef"
            continue
        if shape.contour is not None:
            pts = sample_contour(shape.contour, length, options.tolerance_m,
                                 options.snap_tolerance_m)
            profile = pts[:, :2] if pts is not None else None
        else:
            profile = parametric_profile(shape.parametric, length,
                                         options.tolerance_m)
        if profile is None or len(profile) < 3:
            failures[key] = "unusable hole profile"
            continue
        placed = place_hole(profile, hc.transformation, length)
        if placed is None:
            failures[key] = "missing or degenerate transformation"
            continue
        holes.append(placed)
    return holes, failures
```

In `_tessellate_plates`, replace the existing hole block

```python
        holes = []
        for c in plate.cut_by_contours:
            h = sample_contour(c, length, options.tolerance_m,
                               options.snap_tolerance_m)
            if h is not None:
                holes.append(h)
```

with

```python
        panel = vessel.panels.get(panel_id)
        holes, hole_failures = _hole_polylines(plate, panel, vessel, length,
                                               options)
        for key, reason in hole_failures.items():
            logger.warning("CutBy hole not applied to {} — {} ({})",
                           plate.id, reason, key)
        result.skipped.update(hole_failures)
```

- [ ] **Step 4: Run tests**

```powershell
uv run pytest tests/test_render_model.py
```

Expected: PASS, including the pre-existing `test_renders_plate_and_stiffener_skips_bad_pillar` (its vessel has no holes, so `skipped` is unchanged).

- [ ] **Step 5: Commit**

```powershell
git add packages/ocx-render tests/test_render_model.py
git commit -m "feat(render): cut CutBy openings from plates via catalogue hole resolution"
```

### Task 11: Integration test on the reference model + docs

**Files:**
- Create: `tests/test_render_integration.py`
- Modify: `.github/copilot-instructions.md` (layout + CLI sections)

- [ ] **Step 1: Write the integration test** — create `tests/test_render_integration.py`

```python
"""Integration: render the TR04 cutout reference model (needs models/TR04)."""
from pathlib import Path

import numpy as np
import pytest

MODEL = (Path(__file__).resolve().parents[1]
         / "models" / "TR04" / "tr04_tc13_nast.3docx")

pytestmark = pytest.mark.integration


def _plate_area(meshes) -> float:
    total = 0.0
    for m in meshes:
        if m.kind != "plate":
            continue
        v, t = m.vertices, m.triangles
        a = v[t[:, 1]] - v[t[:, 0]]
        b = v[t[:, 2]] - v[t[:, 0]]
        total += 0.5 * float(np.linalg.norm(np.cross(a, b), axis=1).sum())
    return total


@pytest.mark.skipif(not MODEL.exists(), reason="reference model not present")
def test_tr04_tc13_renders_with_cutouts():
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser
    from ocx_render.render import TessellationOptions, render_model

    root = OcxParser().parse(str(MODEL))
    vessel = get_builder(root.schema_version).build(root)

    # Builder captured the catalogue and all 9 panel-level hole placements.
    assert vessel.hole_shape_catalogue is not None
    assert len(vessel.hole_shape_catalogue.holes) == 7
    panel = next(iter(vessel.panels.values()))
    assert len(panel.cut_by_holes) == 9

    result = render_model(vessel, TessellationOptions())
    assert any(m.kind == "plate" for m in result.meshes)
    hole_failures = {k: v for k, v in result.skipped.items()
                     if k.startswith("hole:")}
    assert hole_failures == {}
    area_holed = _plate_area(result.meshes)

    # Rendering with the holes stripped must give a measurably larger area.
    for p in vessel.panels.values():
        p.cut_by_holes.clear()
        p.cut_by_contours.clear()
    for pl in vessel.plates.values():
        pl.cut_by_holes.clear()
        pl.cut_by_contours.clear()
    area_full = _plate_area(render_model(vessel, TessellationOptions()).meshes)
    assert area_holed < area_full * 0.995
```

- [ ] **Step 2: Run it** (integration tests are excluded by default, so select the marker)

```powershell
uv run pytest tests/test_render_integration.py -m integration
```

Expected: PASS. If `hole_failures` is non-empty, the reasons name the failing stage (resolution, profile, transformation) — fix there, not in the test.

- [ ] **Step 3: Manual render — the visual success criterion**

```powershell
uv run ocx-render models/TR04/tr04_tc13_nast.3docx
```

Expected: `GLB written to models/TR04/tr04_tc13_nast.glb (… parts, 0 skipped)` + viewer HTML. Open `models/TR04/tr04_tc13_nast.html` in a browser and confirm all 9 openings are visible in the panel (reference: the TC13 drawing — 9 holes in a diagonal row: circles, ovals/stadiums, rectangles, a pear-shaped contour hole near the top). Do not commit the generated `.glb`/`.html`.

- [ ] **Step 4: Full suite + lint**

```powershell
uv run pytest
uv run ruff check packages tests
```

Expected: all green.

- [ ] **Step 5: Update `.github/copilot-instructions.md`**

- In the project-layout tree: add `ocx-render` under `packages/` (`render.py`, `gltf_writer.py`, `html_viewer.py`, `cli.py`) and the new `ocx-geometry` modules (`backend.py`, `surfaces.py`, `curves.py`, `sweep.py`, `sections_2d.py`, `uv_tessellator.py`, `holes.py`, `mesh.py`).
- In the CLI section, add:

```bash
# Tessellate to GLB + self-contained HTML viewer (exit 0 rendered / 1 nothing renderable / 2 cannot parse)
ocx-render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]
```

- Update the dependency-direction sentence: `ocx-render` depends on core + geometry.

- [ ] **Step 6: Final commit**

```powershell
git add tests/test_render_integration.py .github/copilot-instructions.md
git commit -m "test(render): TR04 tc13 cutout integration test; document ocx-render"
```

---

## Self-review checklist (for the plan author — already applied)

- Spec §1 port → Tasks 1–5; §2 IR/builder → Tasks 6–8; §3 holes/cutting → Tasks 9–10; §4 testing/criteria → Tasks 10–11. ClassCatalogue discovery (spec §2 note) → Task 7.
- Hole-skip accounting uses `result.skipped["hole:<id>"]` — visible in the CLI "skipped" count and queryable in tests.
- `IrHole2D.parametric` type change consumers all updated in Task 7 (reporting generator + 3 tests).
