# ocx-diagnose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `ocx-diagnose` CLI that checks tolerance and pipeline settings for trimmed-NURBS-panel rendering and writes a self-contained interactive plotly HTML report (plus JSON stats).

**Architecture:** The geometry/render pipeline gets one optional, behaviour-neutral collector (`DiagSink`) passed through `TessellationOptions.diag`; hooks record chart-build counts, mesh-trim snap/reject data and the route each plate took. A new workspace package `ocx-diagnose` runs the pipeline with a sink, computes independent checks (mesh health, chart distortion, surface deviation, neighbour gaps/overlaps, bbox), runs tolerance sweeps and renders plotly figures into one HTML file.

**Tech Stack:** Python 3.12, numpy, scipy, trimesh, shapely, typer, loguru, plotly (new, only in `ocx-diagnose`), pytest, uv workspace.

**Deviation from spec (intentional):** the spec said hooks "return optional frozen stats dataclasses". Returning extra values would change signatures of `make_lscm_chart` / `MeshTrimmer.trim` and break callers, so hooks instead *fill an optional mutable collector* passed in (`diag=None` default). Same information, no signature break. Also added: `--max-plates` (limit per-plate figures to the worst N plates to keep the HTML small).

**Conventions (repo rules):** run everything from the repo root with `uv run`; use `loguru` (`from loguru import logger`), no `print`; commit trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`; line length 100 (ruff).

---

## File structure

| File | Responsibility |
|---|---|
| `packages/ocx-geometry/src/ocx_geometry/diagnostics.py` (create) | `ChartDiag`, `PlateDiag`, `DiagSink` dataclasses only |
| `packages/ocx-geometry/src/ocx_geometry/backend.py` (modify) | `TessellationOptions` gains `diag`, `only_panels` |
| `packages/ocx-geometry/src/ocx_geometry/lscm.py` (modify) | fill `ChartDiag`; `LscmChart.last_stage`; `LscmParam.chart` property |
| `packages/ocx-geometry/src/ocx_geometry/mesh_trim.py` (modify) | `trim(..., diag=None)` records snap + reject reason |
| `packages/ocx-render/src/ocx_render/render.py` (modify) | panel filter; fill `PlateDiag` / `ChartDiag` |
| `packages/ocx-diagnose/pyproject.toml` (create) | package metadata, entrypoint |
| `packages/ocx-diagnose/src/ocx_diagnose/checks.py` (create) | pure numeric checks (no plotly) |
| `packages/ocx-diagnose/src/ocx_diagnose/sweep.py` (create) | tolerance sweep |
| `packages/ocx-diagnose/src/ocx_diagnose/analyse.py` (create) | run pipeline with sink, assemble per-panel results |
| `packages/ocx-diagnose/src/ocx_diagnose/figures.py` (create) | plotly figure builders |
| `packages/ocx-diagnose/src/ocx_diagnose/report.py` (create) | HTML + JSON assembly |
| `packages/ocx-diagnose/src/ocx_diagnose/cli.py` (create) | typer CLI |
| `tests/test_diag_hooks.py`, `tests/test_diag_checks.py`, `tests/test_diag_report.py`, `tests/test_diag_cli.py` (create) | tests |

---

### Task 1: Collector dataclasses and options

**Files:**
- Create: `packages/ocx-geometry/src/ocx_geometry/diagnostics.py`
- Modify: `packages/ocx-geometry/src/ocx_geometry/backend.py` (the `TessellationOptions` class)
- Test: `tests/test_diag_hooks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diag_hooks.py
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import ChartDiag, DiagSink, PlateDiag


def test_options_default_has_no_diag_and_no_panel_filter():
    o = TessellationOptions()
    assert o.diag is None and o.only_panels is None


def test_sink_collects_by_id():
    sink = DiagSink()
    sink.plates["P1"] = PlateDiag(plate_id="P1", panel_id="PN1")
    sink.charts["PN1"] = ChartDiag(n_members=3)
    assert sink.plates["P1"].route == "unknown"
    assert sink.charts["PN1"].n_members == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_hooks.py -v`
Expected: FAIL (`ModuleNotFoundError: ocx_geometry.diagnostics`).

- [ ] **Step 3: Implement**

```python
# packages/ocx-geometry/src/ocx_geometry/diagnostics.py
"""Optional collectors the render pipeline fills for diagnostics.

Hooks never change tessellation results; with no sink they cost nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["ChartDiag", "PlateDiag", "DiagSink"]


@dataclass
class ChartDiag:
    """Build statistics of one panel's shared chart mesh."""
    n_members: int = 0
    members_used: list[int] = field(default_factory=list)
    verts_before_weld: int = 0
    verts_after_weld: int = 0
    boundary_edges_before_stitch: int = 0
    boundary_edges_after_stitch: int = 0
    build_s: float = 0.0
    V: np.ndarray | None = None
    F: np.ndarray | None = None
    tri_member: np.ndarray | None = None


@dataclass
class PlateDiag:
    """What happened to one plate."""
    plate_id: str
    panel_id: str
    route: str = "unknown"          # single | mesh-trim | lscm | best-member
    trim_reject: str | None = None  # why mesh-trim was not used
    snap_m: float | None = None     # worst outer-ring snap distance
    max_snap_m: float | None = None
    chart_stage: str | None = None  # gates | no-gates | tutte (route == lscm)
    local_param: Any = None         # LscmParam of the flattened submesh
    candidates: list = field(default_factory=list)  # exact SurfaceParam members
    contour: np.ndarray | None = None
    seconds: float = 0.0


@dataclass
class DiagSink:
    charts: dict[str, ChartDiag] = field(default_factory=dict)
    plates: dict[str, PlateDiag] = field(default_factory=dict)
```

In `backend.py` add `from typing import Any` and change the options class to:

```python
@dataclass(frozen=True)
class TessellationOptions:
    """Controls tessellation density and contour repair."""
    tolerance_m: float = 0.05        # linear deflection (metres); default 50 mm
    snap_tolerance_m: float = 0.01   # max contour gap snapped shut (metres)
    diag: Any = None                 # optional ocx_geometry.diagnostics.DiagSink
    only_panels: frozenset[str] | None = None  # restrict plates to these panel ids
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_diag_hooks.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-geometry tests/test_diag_hooks.py
git commit -m "Add diagnostics collectors and option fields" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Panel filter and plate recording in `render.py`

**Files:**
- Modify: `packages/ocx-render/src/ocx_render/render.py` (`render_model` ~L324, `_tessellate_plates` ~L178)
- Test: `tests/test_diag_hooks.py`

Use a tiny vessel built in-test is heavy; instead test through the existing tr04 stub-free path is slow. Use the existing helper pattern in `tests/test_render_model.py` (open it first and reuse its vessel/panel factory for a one-panel, one-plate vessel — find it with `grep -n "def _" tests/test_render_model.py`).

- [ ] **Step 1: Write the failing test** (append to `tests/test_diag_hooks.py`; replace `_single_plate_vessel` by the factory found in `tests/test_render_model.py`, importing it with `from tests.test_render_model import <factory>`)

```python
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import DiagSink
from ocx_render.render import render_model

from tests.test_render_model import _single_plate_vessel  # adapt to the real helper name


def test_single_member_plate_is_recorded_with_route_single():
    vessel, plate_id, panel_id = _single_plate_vessel()
    sink = DiagSink()
    res = render_model(vessel, TessellationOptions(diag=sink))
    assert res.rendered_count >= 1
    pd = sink.plates[plate_id]
    assert pd.route == "single" and pd.panel_id == panel_id
    assert pd.contour is not None and len(pd.candidates) == 1
    assert pd.seconds > 0


def test_only_panels_filters_plates():
    vessel, plate_id, panel_id = _single_plate_vessel()
    res = render_model(vessel, TessellationOptions(only_panels=frozenset({"nope"})))
    assert all(m.extras.get("panel_id") != panel_id for m in res.meshes)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_hooks.py -v`
Expected: FAIL (`sink.plates` empty / `KeyError`).

- [ ] **Step 3: Implement**

In `render_model`, skip surface building for filtered-out panels:

```python
    params: dict[str, list[SurfaceParam]] = {}
    for pid, panel in vessel.panels.items():
        if options.only_panels is not None and pid not in options.only_panels:
            continue
        surfs = _resolve_panel_surfaces(panel, vessel)
```

In `_tessellate_plates` pass 1, filtered plates are already skipped because their panel has no `params` entry; to avoid polluting `result.skipped` add right after computing `panel_id`:

```python
        if options.only_panels is not None and panel_id not in options.only_panels:
            continue
```

In pass 2, at the top of the per-plate loop body (after `t_plate = ...`) add:

```python
        sink = options.diag
        pdiag = None
        if sink is not None:
            from ocx_geometry.diagnostics import PlateDiag
            pdiag = PlateDiag(plate_id=plate.id, panel_id=panel_id,
                              candidates=list(candidates), contour=contour,
                              max_snap_m=max(30.0 * options.tolerance_m, 1.5))
            sink.plates[plate.id] = pdiag
        route = "single"
```

Set `route` at each branch: after the `if out is not None and len(out[1]):` block that creates `pm`, add `route = "mesh-trim"`; in the `if pm is None:` branch after `local = chart.param_for(contour)...` add `route = "lscm" if local is not None else "best-member"`; in the retry block (`if pm is None and local is not None:`) set `route = "best-member"` after the retry. After `result.meshes.append(pm)`:

```python
        if pdiag is not None:
            pdiag.route = route
            pdiag.local_param = local
            pdiag.seconds = time.perf_counter() - t_plate
```

Move the `result.meshes.append(pm)` so this block runs only for successful plates (it already does, as failures `continue`).

- [ ] **Step 4: Run to verify it passes, plus regressions**

Run: `uv run pytest tests/test_diag_hooks.py tests/test_render_model.py tests/test_render_lscm.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-render tests/test_diag_hooks.py
git commit -m "Record plate routes in render pipeline and filter by panel" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Chart-build and mesh-trim hooks

**Files:**
- Modify: `packages/ocx-geometry/src/ocx_geometry/lscm.py` (`_build_mesh`, `make_lscm_chart`, `LscmChart.param_for`, `LscmParam`)
- Modify: `packages/ocx-geometry/src/ocx_geometry/mesh_trim.py` (`MeshTrimmer.trim`)
- Modify: `packages/ocx-render/src/ocx_render/render.py` (pass the diag objects)
- Test: `tests/test_diag_hooks.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
import numpy as np
from ocx_geometry.diagnostics import ChartDiag, PlateDiag
from ocx_geometry.lscm import make_lscm_chart
from ocx_geometry.mesh_trim import MeshTrimmer

from tests.test_mesh_trim import _grid, _square
from tests.test_render_lscm import _bilge_members_and_hints


def test_chart_build_fills_chartdiag():
    members, hints = _bilge_members_and_hints()
    cd = ChartDiag()
    chart = make_lscm_chart(members, 0.05, hints, diag=cd)
    assert chart is not None
    assert cd.n_members == 3 and cd.verts_after_weld <= cd.verts_before_weld
    assert cd.boundary_edges_after_stitch <= cd.boundary_edges_before_stitch
    assert cd.F is not None and len(cd.F) == len(chart.mesh[1])


def test_trim_records_snap_and_reject_reason():
    V, F = _grid()
    tr = MeshTrimmer(V, F, 0.05)
    ok = PlateDiag(plate_id="a", panel_id="p")
    assert tr.trim(_square(2.3, 6.7, 3.1, 7.9), [], np.array([4.0, 5.0, 0.16]),
                   diag=ok) is not None
    assert ok.snap_m is not None and ok.trim_reject is None
    bad = PlateDiag(plate_id="b", panel_id="p")
    far = _square(2.3, 6.7, 3.1, 7.9) + np.array([0.0, 0.0, 50.0])
    assert tr.trim(far, [], None, diag=bad) is None
    assert bad.trim_reject == "outer ring unusable"


def test_param_for_sets_last_stage():
    members, hints = _bilge_members_and_hints()
    chart = make_lscm_chart(members, 0.05, hints)
    param = chart.param_for(hints[:10 * 2])
    if param is not None:
        assert chart.last_stage in {"gates", "no-gates", "tutte"}
        V, F, uv = param.chart
        assert len(uv) == len(V)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_diag_hooks.py -v`
Expected: FAIL (`unexpected keyword argument 'diag'`).

- [ ] **Step 3: Implement**

`lscm.py` — `_build_mesh(members, tol_m, hint_pts, require_connected=True, diag=None)`:
- after `V = np.vstack(pts_all)`: `n_pre = len(V)`; after `V, src, remap = _weld(...)`: `n_post = len(V)`.
- just before `F = _stitch(...)`: `b0 = len(_boundary_edges(F)) if diag is not None else 0`; just after: `b1 = len(_boundary_edges(F)) if diag is not None else 0`.
- at the end, before `return _ChartMesh(...)`:

```python
    cm = _ChartMesh(V, F, src, _tri_members(F, src))
    if diag is not None:
        diag.n_members = len(members)
        diag.members_used = sorted(pieces)
        diag.verts_before_weld, diag.verts_after_weld = n_pre, n_post
        diag.boundary_edges_before_stitch = b0
        diag.boundary_edges_after_stitch = b1
        diag.V, diag.F, diag.tri_member = cm.V, cm.F, cm.tri_member
    return cm
```

`make_lscm_chart(members, tol_m, hint_pts=None, diag=None)` passes `diag=diag` to `_build_mesh`. In `LscmChart.__init__` add `self.last_stage: str | None = None`. In `param_for`, set the stage where each attempt succeeds:

```python
            sub = fresh()
            param = validated(sub, _flatten_gates(sub))
            self.last_stage = "gates" if param is not None else None
            if param is None:
                ...
                param = validated(sub, uv)
                self.last_stage = "no-gates" if param is not None else None
            if param is None:
                ...
                param = validated(sub, uv)
                self.last_stage = "tutte" if param is not None else None
            return param
```

Also set `self.last_stage = None` at the top of `param_for`. `LscmParam` gains:

```python
    @property
    def chart(self):
        """(vertices, faces, metric uv) of the flattened submesh."""
        return self._V, self._F, self._uv
```

`mesh_trim.py` — `trim(self, outer, holes, seed=None, diag=None)`: after `state, snap = self._cut(...)` for the outer ring add `if diag is not None: diag.snap_m = float(snap)`; in the `state is None` branch set `diag.trim_reject = "outer ring unusable"`; in the `mesh is None` branch set `diag.trim_reject = "assembly failed"`.

`render.py`: pass `diag=sink.charts.setdefault(panel_id, ChartDiag())` into `make_lscm_chart` when `sink` is not None and record `build_s` (the existing `time.perf_counter() - t_chart`); pass `diag=pdiag` to `trim`; after `param_for`, `if pdiag is not None: pdiag.chart_stage = chart.last_stage`; in the `except Exception as exc` around `trim` set `pdiag.trim_reject = f"exception: {exc}"`. Because `ChartDiag` import is needed, import it with `PlateDiag` at module top (`from ocx_geometry.diagnostics import ChartDiag, PlateDiag`) and drop the local import from Task 2.

- [ ] **Step 4: Run tests incl. regressions**

Run: `uv run pytest tests/test_diag_hooks.py tests/test_mesh_trim.py tests/test_render_lscm.py tests/test_lscm_plane_trim.py tests/test_render_model.py -q`
Expected: all pass.

- [ ] **Step 5: Verify no behaviour change on a real model (identical triangle counts with/without sink)**

Run:
```powershell
@'
from ocx_render.cli import _load_vessel
from ocx_render.render import render_model, TessellationOptions
from ocx_geometry.diagnostics import DiagSink
from pathlib import Path
v = _load_vessel(Path("models/tr04/tr04_tc14A_outer_shell.3docx"))
a = render_model(v, TessellationOptions())
b = render_model(v, TessellationOptions(diag=DiagSink()))
print(sum(len(m.triangles) for m in a.meshes), sum(len(m.triangles) for m in b.meshes))
'@ | uv run python -
```
Expected: two equal numbers (takes ~40 s).

- [ ] **Step 6: Commit**

```bash
git add packages tests/test_diag_hooks.py
git commit -m "Add chart-build and mesh-trim diagnostic hooks" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Scaffold `ocx-diagnose` package

**Files:**
- Create: `packages/ocx-diagnose/pyproject.toml`, `packages/ocx-diagnose/README.md`, `packages/ocx-diagnose/src/ocx_diagnose/__init__.py`, `packages/ocx-diagnose/src/ocx_diagnose/cli.py`
- Test: `tests/test_diag_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_diag_cli.py
from ocx_diagnose.cli import app
from typer.testing import CliRunner


def test_help_lists_options():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    for opt in ("--panel", "--tolerance-sweep", "--report", "--json", "--max-plates"):
        assert opt in r.output
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_cli.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```toml
# packages/ocx-diagnose/pyproject.toml
[project]
name = "ocx-diagnose"
version = "0.1.0"
description = "Diagnostics for the OCX trimmed-NURBS render pipeline — tolerance sweeps and chart visuals"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "ocx-model-core>=0.5,<0.6",
    "ocx-geometry>=0.1,<0.2",
    "ocx-render>=0.1,<0.2",
    "numpy>=2.0",
    "scipy>=1.11",
    "trimesh>=4.0",
    "plotly>=5.20",
    "typer>=0.9",
    "loguru>=0.7",
]

[project.scripts]
ocx-diagnose = "ocx_diagnose.cli:entrypoint"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ocx_diagnose"]

[tool.uv.sources]
ocx-model-core = { workspace = true }
ocx-geometry = { workspace = true }
ocx-render = { workspace = true }
```

`README.md`: one paragraph plus the usage block from the spec. `__init__.py`: `"""Render pipeline diagnostics."""`.

```python
# packages/ocx-diagnose/src/ocx_diagnose/cli.py
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
        write_report(results, html, max_plates, title=model.name)
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
```

Then: `uv sync --dev` (refreshes `uv.lock`, installs plotly).

- [ ] **Step 4: Run to verify it passes**

Run: `uv sync --dev; uv run pytest tests/test_diag_cli.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose uv.lock tests/test_diag_cli.py
git commit -m "Scaffold ocx-diagnose package and CLI" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Numeric checks (`checks.py`)

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/checks.py`
- Test: `tests/test_diag_checks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diag_checks.py
import numpy as np
import pytest
from ocx_diagnose.checks import (
    chart_distortion, mesh_health, neighbour_overlaps_and_gaps,
    snap_vectors, surface_deviation,
)
from ocx_geometry.surfaces import PlaneParam


def _quad(z=0.0, x0=0.0):
    V = np.array([[x0, 0, z], [x0 + 1, 0, z], [x0 + 1, 1, z], [x0, 1, z]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def test_mesh_health_counts_boundary_and_nonmanifold():
    V, F = _quad()
    h = mesh_health(V, F)
    assert h["boundary_edges"] == 4 and h["non_manifold_edges"] == 0
    # a third triangle on the shared diagonal makes it non-manifold
    V2 = np.vstack([V, [0.5, 0.5, 1.0]])
    F2 = np.vstack([F, [[0, 2, 4]]])
    assert mesh_health(V2, F2)["non_manifold_edges"] == 1


def test_deviation_zero_on_plane_and_offset_detected():
    plane = PlaneParam(np.zeros(3), np.array([0.0, 0.0, 1.0]))
    pts = np.random.default_rng(0).uniform(-1, 1, (50, 3)) * [1, 1, 0]
    assert surface_deviation(pts, [plane]).max() < 1e-9
    assert surface_deviation(pts + [0, 0, 0.01], [plane]).min() == pytest.approx(0.01)


def test_overlap_and_gap_detected_between_plates():
    A = _quad()
    B_overlap = _quad(x0=0.0)                 # coincident with A
    B_gap = _quad(x0=1.0 + 0.002)             # 2 mm gap next to A
    ov = neighbour_overlaps_and_gaps({"A": A, "B": B_overlap}, gap_max_m=0.05)
    assert ov["B"]["overlap_faces"] > 0
    gp = neighbour_overlaps_and_gaps({"A": A, "B": B_gap}, gap_max_m=0.05)
    assert gp["A"]["gap_vertices"] > 0 and gp["A"]["max_gap_m"] == pytest.approx(0.002, abs=1e-6)


def test_snap_vectors_point_to_nearest_mesh_vertex():
    V, F = _quad()
    ring = np.array([[0.1, 0.1, 0.3]])
    starts, ends = snap_vectors(ring, V)
    assert np.allclose(starts[0], ring[0]) and np.allclose(ends[0], V[0])


def test_chart_distortion_flags_flipped_triangle():
    V, F = _quad()
    uv = V[:, :2].copy()
    uv[[2, 3]] = uv[[3, 2]]                    # swap -> second triangle flips
    d = chart_distortion(V, F, uv)
    assert d.flipped.sum() >= 1 and 0 < d.flipped_frac <= 1
    ok = chart_distortion(V, F, V[:, :2])
    assert ok.flipped.sum() == 0 and ok.spread_max == pytest.approx(1.0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_diag_checks.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# packages/ocx-diagnose/src/ocx_diagnose/checks.py
"""Pure numeric diagnostics on meshes and charts (no plotting)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy.spatial import cKDTree

_OVERLAP_TOL_M = 1e-3   # a face centroid this close to another plate's surface overlaps it
_GAP_MIN_M = 1e-6       # closer than this is a shared (welded) edge, not a gap


def _edge_counts(F: np.ndarray):
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0, return_counts=True)


def mesh_health(V: np.ndarray, F: np.ndarray) -> dict:
    """Triangle count and boundary / non-manifold edge counts."""
    if len(F) == 0:
        return {"triangles": 0, "boundary_edges": 0, "non_manifold_edges": 0}
    _, cnt = _edge_counts(F)
    return {"triangles": int(len(F)), "boundary_edges": int((cnt == 1).sum()),
            "non_manifold_edges": int((cnt > 2).sum())}


def edge_segments(V: np.ndarray, F: np.ndarray, kind: str) -> np.ndarray:
    """(k, 2, 3) segments of ``kind`` = 'boundary' | 'non_manifold' edges."""
    if len(F) == 0:
        return np.zeros((0, 2, 3))
    edges, cnt = _edge_counts(F)
    sel = edges[(cnt == 1) if kind == "boundary" else (cnt > 2)]
    return V[sel] if len(sel) else np.zeros((0, 2, 3))


def surface_deviation(points: np.ndarray, members: list, max_samples: int = 5000) -> np.ndarray:
    """Distance from points to the nearest exact member surface (inf if none project)."""
    pts = np.asarray(points, dtype=float)
    if len(pts) > max_samples:
        pts = pts[np.linspace(0, len(pts) - 1, max_samples).astype(int)]
    best = np.full(len(pts), np.inf)
    for m in members:
        try:
            uv = m.inverse(pts)
            d = np.linalg.norm(np.asarray(m.evaluate(uv)) - pts, axis=1)
        except Exception:  # noqa: BLE001 — a member that cannot project is skipped
            continue
        best = np.minimum(best, np.where(np.isfinite(d), d, np.inf))
    return best


def neighbour_overlaps_and_gaps(meshes: dict[str, tuple[np.ndarray, np.ndarray]],
                                gap_max_m: float) -> dict[str, dict]:
    """Per plate: faces overlapping another plate, and boundary vertices that
    almost (but do not) touch another plate (a gap in (1e-6, gap_max_m])."""
    out: dict[str, dict] = {}
    for pid, (V, F) in meshes.items():
        others = [(v, f) for k, (v, f) in meshes.items() if k != pid and len(f)]
        res = {"overlap_faces": 0, "gap_vertices": 0, "max_gap_m": 0.0}
        out[pid] = res
        if not others or len(F) == 0:
            continue
        off, ov, of = 0, [], []
        for v, f in others:
            ov.append(v)
            of.append(f + off)
            off += len(v)
        tm = trimesh.Trimesh(np.vstack(ov), np.vstack(of), process=False)
        cent = V[F].mean(axis=1)
        d_c = trimesh.proximity.closest_point(tm, cent)[1]
        res["overlap_faces"] = int((d_c < _OVERLAP_TOL_M).sum())
        edges, cnt = _edge_counts(F)
        bv = np.unique(edges[cnt == 1])
        if len(bv):
            d_b = trimesh.proximity.closest_point(tm, V[bv])[1]
            gap = d_b[(d_b > _GAP_MIN_M) & (d_b <= gap_max_m)]
            res["gap_vertices"] = int(len(gap))
            res["max_gap_m"] = float(gap.max()) if len(gap) else 0.0
    return out


def snap_vectors(ring: np.ndarray, mesh_vertices: np.ndarray, max_vectors: int = 300):
    """Segments from (subsampled) ring points to their nearest mesh vertex."""
    ring = np.asarray(ring, dtype=float)
    if len(ring) > max_vectors:
        ring = ring[np.linspace(0, len(ring) - 1, max_vectors).astype(int)]
    _, idx = cKDTree(mesh_vertices).query(ring)
    return ring, mesh_vertices[idx]


@dataclass
class Distortion:
    flipped: np.ndarray        # (n_faces,) bool
    flipped_frac: float        # flipped 3-D area / total 3-D area
    spread: np.ndarray         # (n_faces,) per-triangle scale / median scale (>= 1)
    spread_max: float


def chart_distortion(V: np.ndarray, F: np.ndarray, uv: np.ndarray) -> Distortion:
    """Flips and per-triangle scale spread of a UV flattening of a 3-D mesh."""
    t3 = V[F]
    a3 = 0.5 * np.linalg.norm(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]), axis=1)
    t2 = uv[F]
    a2 = 0.5 * ((t2[:, 1, 0] - t2[:, 0, 0]) * (t2[:, 2, 1] - t2[:, 0, 1])
                - (t2[:, 2, 0] - t2[:, 0, 0]) * (t2[:, 1, 1] - t2[:, 0, 1]))
    major = 1.0 if a2.sum() >= 0.0 else -1.0
    flipped = np.sign(a2) != major
    ratio = a3 / np.maximum(np.abs(a2), 1e-300)
    med = float(np.median(ratio))
    spread = np.maximum(ratio / med, med / np.maximum(ratio, 1e-300))
    return Distortion(flipped=flipped,
                      flipped_frac=float(a3[flipped].sum() / max(a3.sum(), 1e-300)),
                      spread=spread, spread_max=float(spread.max()))
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_diag_checks.py -v`
Expected: 5 passed. If `test_overlap_and_gap...` fails on `max_gap_m`, print the measured distances: the gap case uses boundary vertices at x=1.0 vs 1.002, so the nearest distance is exactly 0.002.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose tests/test_diag_checks.py
git commit -m "Add numeric diagnostic checks" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Analysis and tolerance sweep (`analyse.py`, `sweep.py`)

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/analyse.py`, `packages/ocx-diagnose/src/ocx_diagnose/sweep.py`
- Test: `tests/test_diag_checks.py` (append)

Data model (used by Tasks 7–8; keep these exact names):

```python
@dataclass
class PlateResult:
    plate_id: str
    route: str
    trim_reject: str | None
    snap_m: float | None
    max_snap_m: float | None
    chart_stage: str | None
    seconds: float
    health: dict                    # mesh_health
    dev_mean_m: float | None
    dev_max_m: float | None
    overlap_faces: int
    gap_vertices: int
    max_gap_m: float
    bbox_delta_m: float             # max |mesh bbox - contour bbox| over 6 sides
    flipped_frac: float | None      # only route == "lscm"
    spread_max: float | None
    mesh: PartMesh                  # kept for figures
    diag: PlateDiag
    score: float                    # badness; sorts the "worst" plates

@dataclass
class PanelResult:
    panel_id: str
    chart: ChartDiag | None
    plates: list[PlateResult]
    skipped: dict[str, str]
    sweep: list[SweepPoint]
    seconds: float
```

`SweepPoint(tol_mm, seconds, triangles, parts, skipped, dev_mean_m, dev_max_m)`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_diag_checks.py`)

```python
from ocx_diagnose.analyse import analyse_model
from tests.test_render_model import _single_plate_vessel  # adapt to the real helper name


def test_analyse_model_returns_panel_and_plate_results_and_sweep():
    vessel, plate_id, panel_id = _single_plate_vessel()
    res = analyse_model(vessel, {panel_id}, 50.0, [25.0, 100.0])
    assert [p.panel_id for p in res] == [panel_id]
    pr = res[0].plates[0]
    assert pr.plate_id == plate_id and pr.route == "single"
    assert pr.dev_max_m is not None and pr.dev_max_m <= 0.05 * 2
    assert [s.tol_mm for s in res[0].sweep] == [25.0, 100.0]
    assert res[0].sweep[0].triangles >= res[0].sweep[1].triangles
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_checks.py::test_analyse_model_returns_panel_and_plate_results_and_sweep -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# packages/ocx-diagnose/src/ocx_diagnose/sweep.py
"""Tolerance sweep: triangle count, time and deviation per tolerance."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from loguru import logger
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import DiagSink
from ocx_render.render import render_model

from ocx_diagnose.checks import surface_deviation


@dataclass
class SweepPoint:
    tol_mm: float
    seconds: float
    triangles: int
    parts: int
    skipped: int
    dev_mean_m: float | None
    dev_max_m: float | None


def deviations(result, sink: DiagSink) -> np.ndarray:
    """Face-centroid distance to the exact surface for all plate meshes."""
    parts = []
    for m in result.meshes:
        pd = sink.plates.get(m.part_id)
        if pd is None or len(m.triangles) == 0:
            continue
        d = surface_deviation(m.vertices[m.triangles].mean(axis=1), pd.candidates)
        parts.append(d[np.isfinite(d)])
    return np.concatenate(parts) if parts else np.zeros(0)


def run_sweep(vessel, panel_ids: set[str] | None,
              tolerances_mm: list[float]) -> list[SweepPoint]:
    points = []
    for tol in tolerances_mm:
        sink = DiagSink()
        opts = TessellationOptions(
            tolerance_m=tol / 1000.0, diag=sink,
            only_panels=frozenset(panel_ids) if panel_ids else None)
        t0 = time.perf_counter()
        res = render_model(vessel, opts)
        secs = time.perf_counter() - t0
        dev = deviations(res, sink)
        points.append(SweepPoint(
            tol_mm=tol, seconds=secs,
            triangles=int(sum(len(m.triangles) for m in res.meshes)),
            parts=res.rendered_count, skipped=res.skipped_count,
            dev_mean_m=float(dev.mean()) if len(dev) else None,
            dev_max_m=float(dev.max()) if len(dev) else None))
        logger.info("Sweep {:.1f} mm: {} tris, {:.1f}s, max dev {}", tol,
                    points[-1].triangles, secs, points[-1].dev_max_m)
    return points
```

`analyse.py` — `analyse_model(vessel, panel_ids, tolerance_mm, sweep_mm) -> list[PanelResult]`:
1. Render once with a `DiagSink` and `only_panels` (as in `run_sweep`), timing it.
2. Group `result.meshes` by `m.extras["panel_id"]` and `sink.plates`.
3. For each panel, build `meshes = {part_id: (V, F)}` and call `neighbour_overlaps_and_gaps(meshes, gap_max_m=max(10 * tol_m, 0.1))` once per panel.
4. Per plate:
   - `health = mesh_health(V, F)`;
   - `dev = surface_deviation(V[F].mean(axis=1), pd.candidates)`, finite part → `dev_mean_m`, `dev_max_m` (None if empty);
   - `bbox_delta_m = max(abs(V.min(0) - c.min(0)).max(), abs(V.max(0) - c.max(0)).max())` where `c = pd.contour`;
   - if `pd.route == "lscm"` and `pd.local_param is not None`: `Vc, Fc, uv = pd.local_param.chart`; `d = chart_distortion(Vc, Fc, uv)` → `flipped_frac`, `spread_max`; else None;
   - `score = (dev_max_m or 0) / tol_m + (snap_m or 0) / max_snap_m + 10 * (flipped_frac or 0) + (route in ("lscm","best-member")) + health["non_manifold_edges"] + overlap_faces / 10 + (gap_vertices > 0) + bbox_delta_m / (10 * tol_m)`.
5. `PanelResult.sweep = run_sweep(vessel, {panel_id}, sweep_mm)` for each analysed panel when `sweep_mm` is non-empty (the sweep reruns per panel so its numbers are per panel; this is the cost of a per-panel plot).
6. `skipped = {k: v for k, v in result.skipped.items() if k.split("/")[0] in panel_plate_ids}`.

Return panels sorted by `panel_id`; plates sorted by `plate_id`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_diag_checks.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose tests/test_diag_checks.py
git commit -m "Add analysis driver and tolerance sweep" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Plotly figures (`figures.py`)

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/figures.py`
- Test: `tests/test_diag_report.py`

Each builder returns a `plotly.graph_objects.Figure`; none touches the filesystem.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diag_report.py
import numpy as np
from ocx_diagnose import figures as fg


def _tri():
    V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def test_each_builder_returns_figure_with_traces():
    V, F = _tri()
    uv = V[:, :2]
    assert len(fg.chart_mesh_fig(V, F, np.array([0, 1]), "members").data) >= 1
    assert len(fg.uv_layout_fig(uv, F, np.array([False, True])).data) >= 1
    assert len(fg.ring_fig(V, F, V[:3] + [0, 0, 0.1], "ring").data) >= 2
    assert len(fg.deviation_fig(V, V[:, 2] + 0.01, 0.05).data) >= 1
    assert len(fg.edges_fig(V, F).data) >= 1
    assert len(fg.sweep_fig([10.0, 50.0], [0.003, 0.02], [4000, 900]).data) >= 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_report.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# packages/ocx-diagnose/src/ocx_diagnose/figures.py
"""Plotly figure builders for the diagnostic report."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from ocx_diagnose.checks import edge_segments, snap_vectors

_SCENE = dict(aspectmode="data")


def _lines(segments: np.ndarray):
    """(k, 2, 3) segments -> x, y, z arrays with None separators."""
    if len(segments) == 0:
        return [], [], []
    pad = np.full((len(segments), 1, 3), np.nan)
    flat = np.concatenate([segments, pad], axis=1).reshape(-1, 3)
    return [None if np.isnan(v) else float(v) for v in flat[:, 0]], \
           [None if np.isnan(v) else float(v) for v in flat[:, 1]], \
           [None if np.isnan(v) else float(v) for v in flat[:, 2]]


def chart_mesh_fig(V, F, face_value, title, colorscale="Turbo", flipped=None):
    """3-D mesh coloured per face; flipped faces (bool mask) drawn red on top."""
    fig = go.Figure(go.Mesh3d(
        x=V[:, 0], y=V[:, 1], z=V[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
        intensity=np.asarray(face_value, float), intensitymode="cell",
        colorscale=colorscale, showscale=True, flatshading=True))
    if flipped is not None and flipped.any():
        Ff = F[flipped]
        fig.add_trace(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                                i=Ff[:, 0], j=Ff[:, 1], k=Ff[:, 2],
                                color="red", name="flipped"))
    fig.update_layout(title=title, scene=_SCENE, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def uv_layout_fig(uv, F, flipped):
    """2-D UV flattening: edges grey, flipped triangles red."""
    def edges(mask):
        t = uv[F[mask]]
        xs, ys = [], []
        for tri in t:
            for a, b in ((0, 1), (1, 2), (2, 0)):
                xs += [tri[a, 0], tri[b, 0], None]
                ys += [tri[a, 1], tri[b, 1], None]
        return xs, ys

    fig = go.Figure()
    xs, ys = edges(~flipped)
    fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", name="ok",
                               line=dict(color="#888", width=1)))
    if flipped.any():
        xs, ys = edges(flipped)
        fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", name="flipped",
                                   line=dict(color="red", width=2)))
    fig.update_layout(title="UV layout", yaxis=dict(scaleanchor="x"),
                      margin=dict(l=0, r=0, t=40, b=0))
    return fig


def ring_fig(V, F, ring, title):
    """Plate mesh (translucent), contour ring, and ring -> mesh snap vectors."""
    fig = go.Figure(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                              i=F[:, 0], j=F[:, 1], k=F[:, 2],
                              color="lightsteelblue", opacity=0.5, name="plate"))
    closed = np.vstack([ring, ring[:1]])
    fig.add_trace(go.Scatter3d(x=closed[:, 0], y=closed[:, 1], z=closed[:, 2],
                               mode="lines", name="contour",
                               line=dict(color="black", width=4)))
    s, e = snap_vectors(ring, V)
    x, y, z = _lines(np.stack([s, e], axis=1))
    fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode="lines", name="snap",
                               line=dict(color="red", width=3)))
    fig.update_layout(title=title, scene=_SCENE, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def deviation_fig(points, dev, tol_m):
    """Sample points coloured by deviation from the exact surface (m)."""
    ok = np.isfinite(dev)
    fig = go.Figure(go.Scatter3d(
        x=points[ok, 0], y=points[ok, 1], z=points[ok, 2], mode="markers",
        marker=dict(size=2, color=dev[ok], colorscale="Turbo", cmin=0.0,
                    cmax=2.0 * tol_m, colorbar=dict(title="dev (m)"))))
    fig.update_layout(title=f"Deviation (colour max = 2 x tol = {2 * tol_m:.3f} m)",
                      scene=_SCENE, margin=dict(l=0, r=0, t=40, b=0))
    return fig


def edges_fig(V, F):
    """Mesh with boundary edges (orange) and non-manifold edges (red)."""
    fig = go.Figure(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                              i=F[:, 0], j=F[:, 1], k=F[:, 2],
                              color="lightgrey", opacity=0.4, name="plate"))
    for kind, color in (("boundary", "orange"), ("non_manifold", "red")):
        x, y, z = _lines(edge_segments(V, F, kind))
        fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode="lines", name=kind,
                                   line=dict(color=color, width=4)))
    fig.update_layout(title="Boundary / non-manifold edges", scene=_SCENE,
                      margin=dict(l=0, r=0, t=40, b=0))
    return fig


def sweep_fig(tol_mm, dev_max_m, triangles):
    """Max deviation vs tolerance, with the y = x target line, and triangle count."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tol_mm, y=[d * 1000 if d is not None else None for d in dev_max_m],
                             mode="lines+markers", name="max deviation (mm)"))
    fig.add_trace(go.Scatter(x=tol_mm, y=tol_mm, mode="lines", name="target (= tolerance)",
                             line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=tol_mm, y=triangles, mode="lines+markers",
                             name="triangles", yaxis="y2"))
    fig.update_layout(title="Tolerance sweep", xaxis=dict(title="tolerance (mm)", type="log"),
                      yaxis=dict(title="deviation (mm)"),
                      yaxis2=dict(title="triangles", overlaying="y", side="right"),
                      margin=dict(l=0, r=0, t=40, b=0))
    return fig
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_diag_report.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose tests/test_diag_report.py
git commit -m "Add plotly figure builders" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: HTML and JSON report (`report.py`)

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/report.py`
- Test: `tests/test_diag_report.py` (append)

Behaviour:
- `write_report(results, path, max_plates, title)`: one HTML file. Plotly.js is embedded **once** (`plotly.offline.get_plotlyjs()` in a `<script>`); every figure is `fig.to_html(full_html=False, include_plotlyjs=False)`. No network access.
- Page layout: summary table (one row per panel: plates, route counts, worst score, max deviation, sweep present), then tabs (small inline JS toggling `display`) one per panel. A panel tab contains: stats table of the chart (`ChartDiag` counts), the chart-mesh figure coloured by `tri_member`, the sweep figure if present, a plates table (all plates: route, snap/max_snap, reject reason, dev max, overlaps, gaps, flipped, health), and for the `max_plates` highest-`score` plates a `<details>` block with `ring_fig`, `deviation_fig`, `edges_fig`, and for LSCM plates `chart_mesh_fig` (face value = `Distortion.spread`, `flipped=Distortion.flipped`) and `uv_layout_fig`.
- `write_json(results, path)`: dict `{panel_id: {chart: {...counts}, plates: {plate_id: {scalar fields of PlateResult}}, sweep: [asdict(SweepPoint)]}}`; excludes arrays/`mesh`/`diag`.

- [ ] **Step 1: Write the failing test** (append)

```python
import json

from ocx_diagnose.analyse import analyse_model
from ocx_diagnose.report import write_json, write_report
from tests.test_render_model import _single_plate_vessel  # adapt to the real helper name


def test_report_and_json_are_written_and_self_contained(tmp_path):
    vessel, plate_id, panel_id = _single_plate_vessel()
    res = analyse_model(vessel, {panel_id}, 50.0, [25.0, 100.0])
    html = tmp_path / "r.html"
    js = tmp_path / "r.json"
    write_report(res, html, max_plates=5, title="t")
    write_json(res, js)
    text = html.read_text(encoding="utf-8")
    assert panel_id in text and plate_id in text
    assert "https://cdn.plot.ly" not in text            # plotly.js is embedded
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data[panel_id]["plates"][plate_id]["route"] == "single"
    assert len(data[panel_id]["sweep"]) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_diag_report.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `report.py` following the behaviour list above. Skeleton (fill every helper; keep each under ~40 lines):

```python
# packages/ocx-diagnose/src/ocx_diagnose/report.py
"""Assemble the interactive HTML report and the JSON stats."""
from __future__ import annotations

import html as _html
import json
from dataclasses import asdict
from pathlib import Path

import plotly.offline

from ocx_diagnose import figures as fg
from ocx_diagnose.checks import chart_distortion, surface_deviation

_CSS = ("body{font-family:sans-serif;margin:1em}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:2px 6px;font-size:12px}"
        ".tab{display:none}.tab.on{display:block}button.on{font-weight:bold}")
_JS = ("function show(id){document.querySelectorAll('.tab').forEach(e=>"
       "e.classList.toggle('on',e.id===id));document.querySelectorAll('button.tb')"
       ".forEach(b=>b.classList.toggle('on',b.dataset.t===id));"
       "window.dispatchEvent(new Event('resize'));}")

_PLATE_SCALARS = ("route", "trim_reject", "snap_m", "max_snap_m", "chart_stage", "seconds",
                  "dev_mean_m", "dev_max_m", "overlap_faces", "gap_vertices", "max_gap_m",
                  "bbox_delta_m", "flipped_frac", "spread_max", "score")


def _fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_html.escape(_fmt(c))}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


# plate_section(pr, tol_m) -> str       : <details> with ring/deviation/edges/(lscm) figures
# panel_section(panel, max_plates, tol_m) -> str
# write_report(results, path, max_plates, title) -> None
# write_json(results, path) -> None
```

`plate_section` details: deviation points = `pr.mesh.vertices[pr.mesh.triangles].mean(axis=1)` subsampled to ≤3000, `dev = surface_deviation(points, pr.diag.candidates)`; tolerance `tol_m` is carried on `PanelResult` — add a `tol_m: float` field to `PanelResult` in Task 6 if not already present (analyse_model has `tolerance_mm`). Use `Path(path).write_text(..., encoding="utf-8")`; the page `<script>` contains `plotly.offline.get_plotlyjs()` once.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_diag_report.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose tests/test_diag_report.py
git commit -m "Add HTML and JSON report writer" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: End-to-end CLI test, real-model smoke run, docs

**Files:**
- Modify: `tests/test_diag_cli.py`, `README.md`, `packages/ocx-diagnose/README.md`

- [ ] **Step 1: Add tests**

```python
import pytest
from typer.testing import CliRunner

from ocx_diagnose.cli import app


def test_bad_sweep_value_is_rejected():
    r = CliRunner().invoke(app, ["x.3docx", "--tolerance-sweep", "10,abc"])
    assert r.exit_code != 0


@pytest.mark.integration
def test_tr04_smoke(tmp_path):
    out = tmp_path / "r.html"
    r = CliRunner().invoke(app, [
        "models/tr04/tr04_tc14A_outer_shell.3docx", "--report", str(out),
        "--json", str(tmp_path / "r.json"), "--max-plates", "3"])
    assert r.exit_code == 0, r.output
    assert out.stat().st_size > 100_000
```

(`typer.Argument(exists=True)` makes the first test fail on the missing file with exit code 2 — either way non-zero; keep the assertion as `!= 0`.)

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_diag_cli.py -q; uv run pytest tests/test_diag_cli.py -m integration -q`
Expected: unit tests pass; integration smoke passes (~1–2 min).

- [ ] **Step 3: Manual check of the real report**

Run: `uv run ocx-diagnose models\tr04\tr04_tc14A_outer_shell.3docx --tolerance-sweep 25,50,100 --report $env:TEMP\tr04.diagnose.html -l INFO`
Then open the HTML. Expected: a panel tab per panel; the hull-bottom panel shows route counts, a chart-mesh figure, a sweep plot whose deviation line stays at or below the target line, and per-plate figures for the worst plates. Remove the temp file afterwards.

- [ ] **Step 4: Docs** — add to `README.md` a short `ocx-diagnose` bullet and usage block (same options as the spec's Command section); add the CLI to the package README.

- [ ] **Step 5: Full suite, lint, install tool, commit**

```bash
uv run pytest -q
uv run ruff check packages tests
uv tool install --editable .\packages\ocx-diagnose --force
git add -A packages tests README.md uv.lock
git commit -m "Add ocx-diagnose end-to-end tests and docs" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
Expected: full suite passes (previously 749 passed), ruff clean, `ocx-diagnose --help` works from outside the repo.

---

## Self-review

**Spec coverage**
- Command surface (`--panel`, `--tolerance-sweep`, `--report`, `--json`, log level): Task 4; `--max-plates` added (noted).
- Tolerance sweep (triangles, time, mean/max deviation vs target): Tasks 6, 7 (`sweep_fig`).
- Chart quality (flips, scale spread, weld/stitch counts, Tutte fallback): Tasks 3 (`ChartDiag`, `last_stage`), 5 (`chart_distortion`), 6. Pinch-split and zip counts are folded into the boundary-edge before/after-stitch counts and vertex counts; they are not reported separately.
- Trim fidelity (accept/reject reason, snap distribution vs `max_snap`, route): Tasks 2, 3, 7 (`ring_fig`). Snap is the worst outer-ring snap per plate, not a full distribution; the plot shows every snap vector.
- Geometry sanity (boundary/non-manifold, gaps/overlaps, bbox vs extents): Task 5 and 6 (`bbox_delta_m` compares against the plate contour bbox).
- Visuals (chart mesh coloured, UV layout, rings + snap vectors, deviation heatmap, edges, sweep curve): Tasks 7, 8.
- Hooks without behaviour change + identical-output regression: Task 3 Step 5.
- Slow smoke test on tr04: Task 9.

**Placeholder scan:** the only intentional adaptation points are the test-vessel helper name in `tests/test_render_model.py` (Task 2 says how to find it) and the helper bodies sketched in `report.py` (behaviour fully specified above them).

**Type consistency:** `DiagSink/ChartDiag/PlateDiag` fields, `PlateResult/PanelResult/SweepPoint` names, `chart_distortion(V, F, uv)` → `Distortion(flipped, flipped_frac, spread, spread_max)`, `LscmParam.chart` → `(V, F, uv)`, `LscmChart.last_stage` are used identically in Tasks 2–8. `PanelResult` needs a `tol_m` field (used by Task 8); define it in Task 6 together with the rest of the dataclass.
