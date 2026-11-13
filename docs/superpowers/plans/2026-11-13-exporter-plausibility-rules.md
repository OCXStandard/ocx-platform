# Exporter Plausibility Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five best-practice rules (OCX-TOP-010/011/012, OCX-PROP-005/006) that flag the exporter data bugs found in `iter0.3docx`: off-trace inclination positions, web directions that disagree with the panel surface normal, implausible part COGs, and positions/COGs copied across many parts.

**Architecture:** One new check module `ocx_rules/packs/best_practice/checks/plausibility.py` holding small geometry helpers plus five `check(context, params) -> list[Finding]` functions. They reuse `GeometryContext` (`sample`, `surface_param`, `panel_surface`, `length`) and the existing helpers `_inclination_positions` (topology.py) and `_cog_m` (properties.py). The rules are registered in the pack TOML files and exported from `checks/__init__.py`.

**Tech Stack:** Python 3.12, numpy, loguru, pytest, uv workspace (`C:\PythonDev\ocx-platform`), ruff.

**Spec:** `docs/superpowers/specs/2026-11-13-exporter-plausibility-rules-design.md`.
(Correction to the spec: tests live in the repo root `tests\`, not `packages\ocx-rules\tests`.)

**Branch:** `feat/exporter-plausibility-rules` (already checked out in `C:\PythonDev\ocx-platform`).

---

## Conventions you need to know

- Run everything with `uv` from `C:\PythonDev\ocx-platform` (PowerShell on Windows).
- IR model classes import from `ocx_model_core.model.ir`. Units: tests use an `Umm` unit (`to_si_factor=0.001`); every geometry call returns **metres**.
- `GeometryContext.sample(curve)` → `(N, 3)` metres or `None`. `GeometryContext.surface_param(surface)` → `SurfaceParam` (`inverse(pts)->uv`, `evaluate(uv)->pts`, `normals(uv)->unit normals`) or `None`.
- `GeometryContext.panel_surface(panel)` returns only `ug.surface` / the referenced surface; it ignores `ug.surfaces` (the multi-patch tuple), hence the new helper `_panel_surface_params`.
- `Finding(message, element_id=None, guid=None, location=None)`; pass `guid=part.guidref`.
- Checks never raise for bad model data: wrap per-part work in `try`, `logger.debug` and skip.

## File map

| File | Action | Responsibility |
|---|---|---|
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py` | Create | Helpers + the 5 check functions |
| `tests/test_rules_checks_plausibility.py` | Create | Unit tests on a synthetic `IrVessel` |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/__init__.py` | Modify | Export the 5 checks |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/topology.toml` | Modify | TOP-010/011/012 entries |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml` | Modify | PROP-005/006 entries |
| `tests/test_rules_best_practice_pack.py` | Modify | Rule counts 36 → 41 (topology 12, properties 6) |
| `packages/ocx-rules/CHANGELOG.md` | Modify | "Added" entry |

---

### Task 1: Test fixtures + OCX-TOP-010 (inclination position on trace)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`
- Create: `tests/test_rules_checks_plausibility.py`

- [ ] **Step 1: Write the failing test file (fixtures + TOP-010 tests)**

Create `tests/test_rules_checks_plausibility.py`:

```python
"""Tests for the exporter plausibility checks (checks/plausibility.py)."""
from __future__ import annotations

from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrCog,
    IrCompositeCurve3D,
    IrInclination,
    IrLine3D,
    IrMassProperties,
    IrPanel,
    IrPillar,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrStiffener,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
)

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")

# z = 0 plane (normal +z) and a far plane y = 5 m (normal +y).
_Z_PLANE = IrPlane3D(id="zp", point_on_surface=IrPoint3D(x=0, y=0, z=0, unit="Umm"),
                     normal=IrVector3D(x=0.0, y=0.0, z=1.0))
_FAR_PLANE = IrPlane3D(id="fp", point_on_surface=IrPoint3D(x=0, y=5000, z=0, unit="Umm"),
                       normal=IrVector3D(x=0.0, y=1.0, z=0.0))


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(a, b) -> IrLine3D:
    return IrLine3D(curve_length=None, start=_pt(*a), end=_pt(*b))


def _mass(cog_mm) -> IrMassProperties | None:
    return None if cog_mm is None else IrMassProperties(
        moulded_cog=IrCog(*cog_mm, unit="Umm"))


def _incl(pos=(500, 0, 0), web=(0.0, 0.0, 1.0)) -> IrInclination:
    return IrInclination(
        position=None if pos is None else _pt(*pos),
        web_direction=None if web is None else IrVector3D(x=web[0], y=web[1], z=web[2]))


def _stiffener(sid: str, *, panel: str | None = "p1", incls=None,
               trace=((0, 0, 0), (1000, 0, 0)), cog=None) -> IrStiffener:
    parent = (ParentRef(kind=ParentKind.PANEL, id=panel) if panel
              else ParentRef(kind=ParentKind.VESSEL, id="v1"))
    return IrStiffener(id=sid, guidref=f"g-{sid}", parent_ref=parent,
                       trace=_line(*trace),
                       inclinations=[_incl()] if incls is None else incls,
                       mass_properties=_mass(cog))


def _pillar(pid: str, *, incls=None, cog=None) -> IrPillar:
    return IrPillar(id=pid, guidref=f"g-{pid}",
                    parent_ref=ParentRef(kind=ParentKind.VESSEL, id="v1"),
                    trace=_line((0, 0, 0), (0, 0, 3000)),
                    inclinations=[] if incls is None else incls,
                    mass_properties=_mass(cog))


def _plate(pid: str, *, cog=None) -> IrPlate:
    a, b, c, d = (0, 0, 0), (1000, 0, 0), (1000, 1000, 0), (0, 1000, 0)
    contour = IrCompositeCurve3D(curve_length=None, segments=[
        _line(a, b), _line(b, c), _line(c, d), _line(d, a)])
    return IrPlate(id=pid, guidref=f"g-{pid}",
                   parent_ref=ParentRef(kind=ParentKind.PANEL, id="p1"),
                   outer_contour=contour, mass_properties=_mass(cog))


def _panel(pid: str = "p1", surfaces=(_Z_PLANE,)) -> IrPanel:
    ug = (IrUnboundedGeometry(surface=surfaces[0], surfaces=tuple(surfaces))
          if surfaces else None)
    return IrPanel(id=pid, unbounded_geometry=ug)


def _ctx(*, panels=(), stiffeners=(), pillars=(), plates=()) -> SimpleNamespace:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    v.panels.update({p.id: p for p in panels})
    v.stiffeners.update({s.id: s for s in stiffeners})
    v.pillars.update({p.id: p for p in pillars})
    v.plates.update({p.id: p for p in plates})
    return SimpleNamespace(vessel=v, geometry=GeometryContext(v))


class TestInclinationPositionOnTrace:
    PARAMS = {"position_tolerance_mm": 50.0}

    def test_position_on_trace_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1")])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []

    def test_position_within_tolerance_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=(500, 40, 0))])])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []

    def test_stiffener_position_off_trace_fails(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=(500, 1000, 0))])])
        (finding,) = inclination_position_on_trace(ctx, self.PARAMS)
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "Inclination 0" in finding.message
        assert "1.000 m" in finding.message

    def test_pillar_position_off_trace_fails(self):
        ctx = _ctx(pillars=[_pillar("c1", incls=[_incl(pos=(2000, 0, 1000))])])
        (finding,) = inclination_position_on_trace(ctx, self.PARAMS)
        assert finding.element_id == "c1"
        assert "2.000 m" in finding.message

    def test_missing_position_is_skipped(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", incls=[_incl(pos=None)])])
        assert inclination_position_on_trace(ctx, self.PARAMS) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'ocx_rules.packs.best_practice.checks.plausibility'`.

- [ ] **Step 3: Create the module with the polyline helper and TOP-010**

Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`:

```python
"""Exporter plausibility checks (OCX-TOP-010..012, OCX-PROP-005/006).

These rules catch data that is well-formed but physically implausible —
typically exporter bugs that copy one value onto many parts: inclination
positions off the trace, web directions that disagree with the panel
surface normal, COGs outside the part, and values shared by many parts.
"""
from __future__ import annotations

from itertools import chain
from typing import Any

import numpy as np
from loguru import logger

from ocx_rules.model import Finding
from ocx_rules.packs.best_practice.checks.topology import _inclination_positions


def _nearest_on_polyline(poly: np.ndarray,
                         p: np.ndarray) -> tuple[np.ndarray, float]:
    """Closest point on an (N, 3) polyline to ``p`` and its distance."""
    if len(poly) == 1:
        return poly[0], float(np.linalg.norm(p - poly[0]))
    a, b = poly[:-1], poly[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    t = np.einsum("ij,ij->i", p - a, ab) / np.where(denom > 1e-30, denom, 1.0)
    q = a + np.clip(t, 0.0, 1.0)[:, None] * ab
    d = np.linalg.norm(q - p, axis=1)
    i = int(np.argmin(d))
    return q[i], float(d[i])


def inclination_position_on_trace(context,
                                  params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-010: every inclination Position must lie on the part's trace."""
    tol_mm = float(params.get("position_tolerance_mm", 50.0))
    tol_m = tol_mm / 1000.0
    geo = context.geometry
    vessel = context.vessel
    findings: list[Finding] = []
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        if not part.inclinations:
            continue
        try:
            poly = geo.sample(part.trace)
            if poly is None or len(poly) == 0:
                continue
            positions = _inclination_positions(geo, part.inclinations)
            for i, pos in enumerate(positions):
                if pos is None:
                    continue
                _, dist = _nearest_on_polyline(poly, pos)
                if dist > tol_m:
                    findings.append(Finding(
                        f"Inclination {i} position is {dist:.3f} m off the "
                        f"trace (tolerance {tol_mm:.0f} mm)",
                        element_id=part.id, guid=part.guidref))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("TOP-010: part {} skipped: {}", part.id, exc)
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Lint and commit**

```powershell
uv run ruff check packages/ocx-rules tests/test_rules_checks_plausibility.py
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py tests/test_rules_checks_plausibility.py
git commit -m "feat(rules): OCX-TOP-010 inclination position on trace check" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Web-angle helper + OCX-TOP-011 / OCX-TOP-012

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`
- Modify: `tests/test_rules_checks_plausibility.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_rules_checks_plausibility.py`, add `import math` above `from types import SimpleNamespace`, and change the plausibility import to:

```python
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
    web_near_normal,
    web_not_in_plate,
)
```

Append:

```python
_S45 = math.sqrt(0.5)


class TestWebDirection:
    NOT_IN_PLATE = {"max_angle_deg": 80.0}
    NEAR_NORMAL = {"warn_angle_deg": 30.0, "max_angle_deg": 80.0}

    def _run(self, ctx):
        return (web_not_in_plate(ctx, self.NOT_IN_PLATE),
                web_near_normal(ctx, self.NEAR_NORMAL))

    def test_web_along_normal_passes_both(self):
        ctx = _ctx(panels=[_panel()], stiffeners=[_stiffener("s1")])
        assert self._run(ctx) == ([], [])

    def test_flipped_normal_is_equivalent(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 0.0, -1.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_web_at_45_degrees_warns_only(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, _S45, _S45))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, warnings = self._run(ctx)
        assert errors == []
        (finding,) = warnings
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "45.0" in finding.message

    def test_web_in_plate_plane_is_error_only(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, warnings = self._run(ctx)
        assert warnings == []
        (finding,) = errors
        assert finding.element_id == "s1"
        assert "90.0" in finding.message

    def test_off_trace_position_is_evaluated_on_trace(self):
        s = _stiffener("s1", incls=[_incl(pos=(500, 3000, 0), web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_missing_position_uses_trace_start(self):
        s = _stiffener("s1", incls=[_incl(pos=None, web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_uses_nearest_of_several_panel_surfaces(self):
        # ug.surface is the far plane; only ug.surfaces holds the z-plane.
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel(surfaces=(_FAR_PLANE, _Z_PLANE))], stiffeners=[s])
        errors, _ = self._run(ctx)
        assert len(errors) == 1

    def test_stiffener_without_panel_is_skipped(self):
        s = _stiffener("s1", panel=None, incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_panel_without_surface_is_skipped(self):
        s = _stiffener("s1", incls=[_incl(web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel(surfaces=())], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_trace_far_from_surface_is_skipped(self):
        s = _stiffener("s1", trace=((0, 0, 1000), (1000, 0, 1000)),
                       incls=[_incl(pos=(500, 0, 1000), web=(0.0, 1.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])

    def test_missing_or_zero_web_is_skipped(self):
        s = _stiffener("s1", incls=[_incl(web=None), _incl(web=(0.0, 0.0, 0.0))])
        ctx = _ctx(panels=[_panel()], stiffeners=[s])
        assert self._run(ctx) == ([], [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'web_near_normal'`.

- [ ] **Step 3: Implement the helpers and the two checks**

In `plausibility.py`, extend the imports:

```python
import math
from itertools import chain
from typing import Any

import numpy as np
from loguru import logger
from ocx_model_core.model.ir.base import ParentKind

from ocx_rules.model import Finding
from ocx_rules.packs.best_practice.checks.topology import _inclination_positions
```

Add below `_nearest_on_polyline`:

```python
# A stiffener farther than this from every panel surface is free-standing;
# its web is not compared with a surface normal.
_SURFACE_GAP_M = 0.05


def _normalize(vec: np.ndarray) -> np.ndarray | None:
    """Unit copy of ``vec``, or None when zero/non-finite."""
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(vec).all() or norm < 1e-12:
        return None
    return vec / norm


def _unit_vector(v) -> np.ndarray | None:
    """IrVector3D -> unit (3,) array, or None when missing/zero/non-finite."""
    if v is None:
        return None
    return _normalize(np.array([v.x, v.y, v.z], dtype=float))


def _panel_surface_params(geo, panel) -> list:
    """SurfaceParams for every support surface of a panel.

    Uses every inline patch (``UnboundedGeometry.surfaces``) and falls back
    to ``GeometryContext.panel_surface`` (inline surface, SurfaceRef, GridRef).
    """
    ug = panel.unbounded_geometry
    surfaces = list(ug.surfaces) if ug is not None and ug.surfaces else []
    if not surfaces:
        single = geo.panel_surface(panel)
        surfaces = [single] if single is not None else []
    params = (geo.surface_param(s) for s in surfaces)
    return [p for p in params if p is not None]


def _surface_normal_at(params: list, point: np.ndarray) -> np.ndarray | None:
    """Unit normal of the surface nearest ``point`` (None beyond the gap)."""
    best: tuple[float, Any, np.ndarray] | None = None
    for sp in params:
        uv = sp.inverse(point[None, :])
        dist = float(np.linalg.norm(sp.evaluate(uv)[0] - point))
        if best is None or dist < best[0]:
            best = (dist, sp, uv)
    if best is None or best[0] > _SURFACE_GAP_M:
        return None
    return _normalize(best[1].normals(best[2])[0])


def _web_angles(context) -> list[tuple[Any, int, float]]:
    """(stiffener, inclination index, web-to-surface-normal angle in degrees).

    Shared by OCX-TOP-011/012. Evaluated at the trace point nearest the
    inclination position (trace start when it has none). Stiffeners without
    a panel, a resolvable surface, or within 50 mm of it are skipped.
    """
    geo = context.geometry
    vessel = context.vessel
    surface_cache: dict[str, list] = {}
    out: list[tuple[Any, int, float]] = []
    for stiffener in vessel.stiffeners.values():
        parent = stiffener.parent_ref
        if (not stiffener.inclinations or parent is None
                or parent.kind is not ParentKind.PANEL):
            continue
        panel = vessel.panels.get(parent.id)
        if panel is None:
            continue
        try:
            if panel.id not in surface_cache:
                surface_cache[panel.id] = _panel_surface_params(geo, panel)
            params = surface_cache[panel.id]
            if not params:
                continue
            poly = geo.sample(stiffener.trace)
            if poly is None or len(poly) == 0:
                continue
            positions = _inclination_positions(geo, stiffener.inclinations)
            angles: list[tuple[Any, int, float]] = []
            for i, (entry, pos) in enumerate(zip(stiffener.inclinations,
                                                 positions, strict=True)):
                web = _unit_vector(entry.web_direction)
                if web is None:
                    continue
                point = poly[0] if pos is None else _nearest_on_polyline(poly, pos)[0]
                normal = _surface_normal_at(params, point)
                if normal is None:
                    continue
                cos = min(abs(float(web @ normal)), 1.0)
                angles.append((stiffener, i, math.degrees(math.acos(cos))))
            out.extend(angles)
        except Exception as exc:  # noqa: BLE001 — skip stiffener
            logger.debug("TOP-011/012: stiffener {} skipped: {}",
                         stiffener.id, exc)
    return out


def web_not_in_plate(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-011: the web must not lie in the plate plane."""
    max_deg = float(params.get("max_angle_deg", 80.0))
    return [
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (lies in the plate plane; limit "
                f"{max_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in _web_angles(context) if angle >= max_deg]


def web_near_normal(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-012: the web should be close to the panel surface normal."""
    warn_deg = float(params.get("warn_angle_deg", 30.0))
    max_deg = float(params.get("max_angle_deg", 80.0))
    return [
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (warning above {warn_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in _web_angles(context) if warn_deg < angle < max_deg]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: `16 passed`.

- [ ] **Step 5: Lint and commit**

```powershell
uv run ruff check packages/ocx-rules tests/test_rules_checks_plausibility.py
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py tests/test_rules_checks_plausibility.py
git commit -m "feat(rules): OCX-TOP-011/012 web direction vs panel surface normal" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: OCX-PROP-005 (part COG within part geometry)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`
- Modify: `tests/test_rules_checks_plausibility.py`

- [ ] **Step 1: Write the failing tests**

Add `part_cog_within_geometry` to the plausibility import list in the test file (keep it alphabetical):

```python
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
    part_cog_within_geometry,
    web_near_normal,
    web_not_in_plate,
)
```

Append:

```python
class TestPartCogWithinGeometry:
    PARAMS = {"margin_mm": 500.0}

    def test_stiffener_cog_on_trace_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 0, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_cog_within_margin_passes(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 400, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_stiffener_cog_far_outside_fails(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", cog=(500, 5000, 0))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "s1"
        assert finding.guid == "g-s1"
        assert "4.500 m" in finding.message

    def test_plate_cog_inside_contour_box_passes(self):
        ctx = _ctx(plates=[_plate("pl1", cog=(500, 500, 0))])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []

    def test_plate_cog_outside_fails(self):
        ctx = _ctx(plates=[_plate("pl1", cog=(500, 500, 6000))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "pl1"
        assert "5.500 m" in finding.message

    def test_pillar_cog_outside_fails(self):
        ctx = _ctx(pillars=[_pillar("c1", cog=(3000, 0, 1000))])
        (finding,) = part_cog_within_geometry(ctx, self.PARAMS)
        assert finding.element_id == "c1"

    def test_part_without_mass_properties_is_skipped(self):
        ctx = _ctx(stiffeners=[_stiffener("s1")], plates=[_plate("pl1")])
        assert part_cog_within_geometry(ctx, self.PARAMS) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'part_cog_within_geometry'`.

- [ ] **Step 3: Implement**

In `plausibility.py` add the import (next to the topology import):

```python
from ocx_rules.packs.best_practice.checks.properties import _cog_m
```

Append:

```python
def _parts_with_geometry(vessel):
    """(part, curve) pairs: plate outer contours, stiffener/pillar traces."""
    for plate in vessel.plates.values():
        yield plate, plate.outer_contour
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        yield part, part.trace


def part_cog_within_geometry(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-005: the moulded COG must lie near the part's geometry."""
    margin_mm = float(params.get("margin_mm", 500.0))
    margin_m = margin_mm / 1000.0
    geo = context.geometry
    findings: list[Finding] = []
    for part, curve in _parts_with_geometry(context.vessel):
        mp = part.mass_properties
        cog = mp.moulded_cog if mp is not None else None
        if cog is None or curve is None:
            continue
        try:
            pts = geo.sample(curve)
            if pts is None or len(pts) == 0:
                continue
            c = _cog_m(geo.length, cog)
            lo = pts.min(axis=0) - margin_m
            hi = pts.max(axis=0) + margin_m
            gap = np.maximum(np.maximum(lo - c, c - hi), 0.0)
            dist = float(np.linalg.norm(gap))
            if dist > 0.0:
                findings.append(Finding(
                    f"Moulded COG ({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}) m is "
                    f"{dist:.3f} m outside the part's bounding box "
                    f"(margin {margin_mm:.0f} mm)",
                    element_id=part.id, guid=part.guidref))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-005: part {} skipped: {}", part.id, exc)
    return findings
```

Check: stiffener trace box is x∈[0,1], y=0, z=0; inflated by 0.5 m; COG y = 5 m → gap 4.5 m. Plate box z=0; COG z = 6 m → gap 5.5 m. Pillar trace x=0; COG x = 3 m → gap 2.5 m.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: `23 passed`.

- [ ] **Step 5: Lint and commit**

```powershell
uv run ruff check packages/ocx-rules tests/test_rules_checks_plausibility.py
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py tests/test_rules_checks_plausibility.py
git commit -m "feat(rules): OCX-PROP-005 part COG within part geometry" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: OCX-PROP-006 (positions / COGs shared across parts)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`
- Modify: `tests/test_rules_checks_plausibility.py`

- [ ] **Step 1: Write the failing tests**

Add `shared_positions_and_cogs` to the test import list:

```python
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
    part_cog_within_geometry,
    shared_positions_and_cogs,
    web_near_normal,
    web_not_in_plate,
)
```

Append:

```python
class TestSharedPositionsAndCogs:
    PARAMS = {"tolerance_mm": 1.0, "min_parts": 3}

    def test_three_parts_sharing_a_position_fail(self):
        ctx = _ctx(stiffeners=[_stiffener(f"s{i}") for i in range(3)])
        findings = shared_positions_and_cogs(ctx, self.PARAMS)
        assert sorted(f.element_id for f in findings) == ["s0", "s1", "s2"]
        assert all("Inclination position (0.500, 0.000, 0.000)" in f.message
                   for f in findings)
        assert all("shared by 3 parts" in f.message for f in findings)

    def test_two_parts_sharing_a_position_pass(self):
        ctx = _ctx(stiffeners=[_stiffener(f"s{i}") for i in range(2)])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_part_repeating_its_own_position_counts_once(self):
        twice = _stiffener("s0", incls=[_incl(), _incl()])
        ctx = _ctx(stiffeners=[twice, _stiffener("s1")])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_values_within_tolerance_are_grouped(self):
        ctx = _ctx(stiffeners=[
            _stiffener("s0", incls=[_incl(pos=(500.0, 0, 0))]),
            _stiffener("s1", incls=[_incl(pos=(500.2, 0, 0))]),
            _stiffener("s2", incls=[_incl(pos=(499.9, 0, 0))])])
        assert len(shared_positions_and_cogs(ctx, self.PARAMS)) == 3

    def test_distinct_positions_pass(self):
        ctx = _ctx(stiffeners=[
            _stiffener(f"s{i}", incls=[_incl(pos=(100 * i, 0, 0))]) for i in range(3)])
        assert shared_positions_and_cogs(ctx, self.PARAMS) == []

    def test_cog_shared_across_part_kinds_fails(self):
        cog = (195404, 24082, 2964)
        ctx = _ctx(plates=[_plate("pl1", cog=cog)],
                   stiffeners=[_stiffener("s1", incls=[], cog=cog)],
                   pillars=[_pillar("c1", cog=cog)])
        findings = shared_positions_and_cogs(ctx, self.PARAMS)
        assert sorted(f.element_id for f in findings) == ["c1", "pl1", "s1"]
        assert all(f.message.startswith("Moulded COG (195.404, 24.082, 2.964)")
                   for f in findings)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: collection ERROR — `ImportError: cannot import name 'shared_positions_and_cogs'`.

- [ ] **Step 3: Implement**

In `plausibility.py`, add `from collections import defaultdict` to the stdlib imports, then append:

```python
def _grid_key(p: np.ndarray, step_m: float) -> tuple[int, int, int]:
    return tuple(int(round(float(c) / step_m)) for c in p)


class _Pool:
    """Parts grouped by a rounded 3D value (one entry per part per key)."""

    def __init__(self, label: str, step_m: float) -> None:
        self.label = label
        self.step_m = step_m
        self.parts: dict[tuple, dict[str, Any]] = defaultdict(dict)
        self.values: dict[tuple, np.ndarray] = {}

    def add(self, part, value: np.ndarray) -> None:
        key = _grid_key(value, self.step_m)
        self.parts[key][part.id] = part
        self.values.setdefault(key, value)

    def findings(self, min_parts: int) -> list[Finding]:
        out: list[Finding] = []
        for key, parts in self.parts.items():
            if len(parts) < min_parts:
                continue
            v = self.values[key]
            msg = (f"{self.label} ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f}) is "
                   f"shared by {len(parts)} parts")
            out.extend(Finding(msg, element_id=p.id, guid=p.guidref)
                       for p in parts.values())
        return out


def shared_positions_and_cogs(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-006: positions/COGs must not be copied across many parts."""
    step_m = float(params.get("tolerance_mm", 1.0)) / 1000.0
    min_parts = int(params.get("min_parts", 3))
    geo = context.geometry
    vessel = context.vessel
    positions = _Pool("Inclination position", step_m)
    cogs = _Pool("Moulded COG", step_m)
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        try:
            for pos in _inclination_positions(geo, part.inclinations):
                if pos is not None:
                    positions.add(part, pos)
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-006: part {} positions skipped: {}", part.id, exc)
    for part in chain(vessel.plates.values(), vessel.stiffeners.values(),
                      vessel.pillars.values()):
        mp = part.mass_properties
        cog = mp.moulded_cog if mp is not None else None
        if cog is None:
            continue
        try:
            cogs.add(part, _cog_m(geo.length, cog))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-006: part {} COG skipped: {}", part.id, exc)
    return positions.findings(min_parts) + cogs.findings(min_parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
Expected: `29 passed`.

- [ ] **Step 5: Lint and commit**

```powershell
uv run ruff check packages/ocx-rules tests/test_rules_checks_plausibility.py
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py tests/test_rules_checks_plausibility.py
git commit -m "feat(rules): OCX-PROP-006 positions and COGs shared across parts" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Register the five rules in the pack

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/__init__.py`
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/topology.toml` (append after OCX-TOP-009, line ~105)
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml` (append at end)
- Test: `tests/test_rules_best_practice_pack.py`

- [ ] **Step 1: Update the pack test (failing)**

In `tests/test_rules_best_practice_pack.py` set:

```python
EXPECTED_CATEGORIES = {
    "identity": 5,
    "document": 5,
    "references": 8,
    "curves_surfaces": 5,
    "topology": 12,
    "properties": 6,
}


class TestBestPracticePack:
    def test_loads_41_rules(self):
        pack = load_pack()
        assert pack.name == "best_practice"
        assert len(pack.rules) == 41
```

Append to the class:

```python
    def test_plausibility_rule_defaults(self):
        by_id = {r.rule_id: r for r in load_pack().rules}
        assert by_id["OCX-TOP-010"].params["position_tolerance_mm"] == 50.0
        assert by_id["OCX-TOP-011"].severity is Severity.ERROR
        assert by_id["OCX-TOP-012"].severity is Severity.WARNING
        assert by_id["OCX-TOP-012"].params["warn_angle_deg"] == 30.0
        assert by_id["OCX-PROP-005"].params["margin_mm"] == 500.0
        assert by_id["OCX-PROP-006"].params["min_parts"] == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_rules_best_practice_pack.py -q`
Expected: FAIL — `assert 36 == 41`, category mismatch, `KeyError: 'OCX-TOP-010'`.

- [ ] **Step 3: Export the checks**

In `checks/__init__.py`, add after the `geometry_stubs` import block:

```python
from ocx_rules.packs.best_practice.checks.plausibility import (
    inclination_position_on_trace,
    part_cog_within_geometry,
    shared_positions_and_cogs,
    web_near_normal,
    web_not_in_plate,
)
```

Replace `__all__` with (alphabetical, new names included):

```python
__all__ = [
    "catalogue_holes_planar", "compartment_closure", "compartments_disjoint",
    "composite_curve_continuous", "entitybase_has_guid_and_id",
    "enumerated_root_units", "explicit_connectivity", "hole_contours_closed",
    "hole_not_splitting_plate", "hole_single_representation", "idbase_has_id",
    "inclination_position_on_trace", "names_not_identifiers",
    "nurbs_control_points", "nurbs_knot_multiplicity",
    "nurbs_knots_non_decreasing", "panel_as_occurrence_group",
    "panel_limited_by_closed", "panel_weight_cog_consistent",
    "part_cog_within_geometry", "plate_weight_consistent", "polyline_closed",
    "profile_closed_section", "renewal_thickness_on_instance",
    "root_declarations", "schema_location_tuple", "seam_topology",
    "shared_positions_and_cogs", "slot_lug_plate_refs",
    "stiffener_end_configurations", "stiffener_inclinations",
    "surface_normals_and_boundaries", "unit_definitions", "unit_refs_resolve",
    "web_near_normal", "web_not_in_plate",
]
```

Also update the module docstring's last sentence to mention: `Exporter plausibility checks (OCX-TOP-010..012, OCX-PROP-005/006) live in plausibility.`

- [ ] **Step 4: Add the TOML entries**

Append to `rules/topology.toml` after the OCX-TOP-009 block:

```toml

[[rule]]
id          = "OCX-TOP-010"
title       = "Inclination position on trace"
description = "Every stiffener/pillar inclination Position must lie on the part's trace line."
source      = "inclination"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom                = "ocx_rules.packs.best_practice.checks:inclination_position_on_trace"
position_tolerance_mm = 50.0

[[rule]]
id          = "OCX-TOP-011"
title       = "Web direction not in plate plane"
description = "A stiffener's WebDirection must not lie in the plane of its panel surface (angle to the surface normal below the limit)."
source      = "inclination"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom        = "ocx_rules.packs.best_practice.checks:web_not_in_plate"
max_angle_deg = 80.0

[[rule]]
id          = "OCX-TOP-012"
title       = "Web direction close to surface normal"
description = "A stiffener's WebDirection should be close to its panel surface normal; larger inclinations are reported for review."
source      = "inclination"
category    = "topology"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom         = "ocx_rules.packs.best_practice.checks:web_near_normal"
warn_angle_deg = 30.0
max_angle_deg  = 80.0
```

Append to `rules/properties.toml`:

```toml

[[rule]]
id          = "OCX-PROP-005"
title       = "Part COG within part geometry"
description = "A plate/stiffener/pillar MouldedCOG must lie within the bounding box of the part's geometry (contour or trace) inflated by a margin."
source      = "mass_properties"
category    = "properties"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom    = "ocx_rules.packs.best_practice.checks:part_cog_within_geometry"
margin_mm = 500.0

[[rule]]
id          = "OCX-PROP-006"
title       = "Position/COG not shared across parts"
description = "Inclination positions and MouldedCOGs must not be identical across many parts (typical exporter copy bug)."
source      = "mass_properties"
category    = "properties"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:shared_positions_and_cogs"
tolerance_mm = 1.0
min_parts    = 3
```

- [ ] **Step 5: Run the pack and plausibility tests**

Run: `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_checks_plausibility.py -q`
Expected: all pass (`40 passed`).

- [ ] **Step 6: Run the full suite and lint**

Run: `uv run pytest -q` then `uv run ruff check packages tests`
Expected: all tests pass (previous baseline 1111 + 30 new); ruff `All checks passed!`. If any other test hard-codes the rule count 36 (e.g. a CLI or MCP test), update it to 41 and note it in the commit.

- [ ] **Step 7: Commit**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice tests/test_rules_best_practice_pack.py
git commit -m "feat(rules): register OCX-TOP-010..012 and OCX-PROP-005/006" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: CHANGELOG

**Files:**
- Modify: `packages/ocx-rules/CHANGELOG.md` (under `## Unreleased` → `### Added`, as the first bullet)

- [ ] **Step 1: Add the entry**

```markdown
- Exporter plausibility rules (`checks/plausibility.py`):
  `OCX-TOP-010` inclination Position must lie on the trace (error,
  50 mm); `OCX-TOP-011` stiffener WebDirection must not lie in the panel
  surface plane (error, ≥ 80° from the normal); `OCX-TOP-012` WebDirection
  more than 30° from the surface normal (warning); `OCX-PROP-005`
  MouldedCOG outside the part's bounding box + 500 mm (warning);
  `OCX-PROP-006` inclination positions / MouldedCOGs shared by ≥ 3 parts
  (warning, one finding per part). Web checks use every inline patch of
  multi-surface panels (`UnboundedGeometry.surfaces`).
```

- [ ] **Step 2: Commit**

```powershell
git add packages/ocx-rules/CHANGELOG.md
git commit -m "docs(rules): changelog for exporter plausibility rules" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Manual verification on iter0

No code changes. Verifies the rules find the bugs that motivated them.

- [ ] **Step 1: Run the new rules on a temp copy (the CLI writes a `.rules.json` sidecar next to the model)**

```powershell
Copy-Item C:\PythonDev\ocx-render\example-models\iter0.3docx $env:TEMP\iter0.3docx
uv run ocx-validate validate rules $env:TEMP\iter0.3docx --rule OCX-TOP-010 --rule OCX-TOP-011 --rule OCX-TOP-012 --rule OCX-PROP-005 --rule OCX-PROP-006 --max-findings 5
```

- [ ] **Step 2: Count findings per rule from the sidecar**

```powershell
@'
import collections, json, os
data = json.load(open(os.path.join(os.environ["TEMP"], "iter0.rules.json"), encoding="utf-8"))
print(json.dumps(data, indent=1)[:600])
'@ | uv run python -
```

Inspect the structure, then count findings per rule id and check findings on `nplcid34858`.

Expected (from the investigation):
- OCX-PROP-006: ≥ 156 findings with message `Inclination position (195.404, 24.082, 2.964) is shared by 156 parts`; COG findings for the same point.
- OCX-TOP-010: many findings (positions up to ~25 m off the trace).
- OCX-TOP-011: about 6 stiffeners (nplcid35141–35156 range).
- OCX-TOP-012: about 15 stiffeners, including `nplcid34858` at ~37°.
- OCX-PROP-005: findings on parts whose COG is the shared point.
- No rule CRASHED; runtime of the five rules well under a minute.

If counts deviate materially, debug (superpowers:systematic-debugging) before claiming done.

- [ ] **Step 3: Clean up**

```powershell
Remove-Item $env:TEMP\iter0.3docx, $env:TEMP\iter0.rules.json
```
