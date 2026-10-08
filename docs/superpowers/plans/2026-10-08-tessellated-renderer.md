# Tessellated 3D Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tessellate OCX geometry (trimmed panel/plate surfaces + swept stiffener/pillar sections) from the `IrVessel` IR into a GLB file plus a self-contained HTML viewer, displayable in any web browser.

**Architecture:** A new `ocx_model_validator/render/` package. A pure-Python UV-domain tessellator (behind an `ITessellator` interface) maps each plate's boundary contour into the parent panel surface's parametric space, triangulates with earcut, and lifts vertices back to 3D. Stiffeners/pillars are swept cross-section profiles along their trace curves. A GLB writer (trimesh) emits one named node per part with per-part color and metadata; an HTML writer emits a self-contained three.js viewer with the GLB embedded base64.

**Tech Stack:** `numpy`, `geomdl` (NURBS evaluation), `shapely` (UV-polygon repair), `mapbox-earcut` (2D triangulation), `trimesh` (mesh ops + GLB export), `typer` CLI (existing), `loguru` (existing).

**Spec:** `docs/superpowers/specs/2026-10-08-tessellated-renderer-design.md`

**Conventions used throughout (read first):**

- All geometry is converted to **metres** as early as possible via `LengthResolver` (Task 1). All tolerances are in metres. CLI takes mm and converts.
- `np` is always `import numpy as np`.
- Run all commands from the repo root. Tests: `uv run pytest tests/test_render_<module>.py -v`.
- Every render-path failure on a *single part* is non-fatal: return `None` (or skip) and let the orchestrator record a reason. Never raise for a bad part.
- 2D section profiles use columns `(s, w)`: `s` = lateral axis (across the web), `w` = web axis (0 at the plate, positive away from it).
- One deviation from the spec, agreed during planning: panels **without plates** carry no inline boundary geometry in the IR (`IrLimitedByRef` has refs only), so they are *skipped and counted*, not tessellated. The tan "panel" color constant still exists for future use.

**File map (all new unless noted):**

| File | Responsibility |
|---|---|
| `ocx_model_validator/render/__init__.py` | Public API: `render_model(vessel, options) → RenderResult`; orchestration |
| `ocx_model_validator/render/mesh.py` | `PartMesh` dataclass + per-part color assignment |
| `ocx_model_validator/render/backend.py` | `TessellationOptions`, `RenderResult`, `ITessellator` ABC |
| `ocx_model_validator/render/length.py` | `LengthResolver` — IR quantities/points → metres |
| `ocx_model_validator/render/curves.py` | `sample_curve` / `sample_contour` — IrCurve3D → 3D polyline |
| `ocx_model_validator/render/surfaces.py` | `SurfaceParam` ABC + per-surface parametrizations + `make_param` |
| `ocx_model_validator/render/uv_tessellator.py` | `UvTessellator(ITessellator)` — UV trim/triangulate/lift |
| `ocx_model_validator/render/sections_2d.py` | `section_polygon(IrSection) → (M,2)` profile |
| `ocx_model_validator/render/sweep.py` | frames + `sweep_profile` → stiffener/pillar mesh |
| `ocx_model_validator/render/gltf_writer.py` | `write_glb(list[PartMesh], path)` via trimesh Scene |
| `ocx_model_validator/render/html_viewer.py` | `write_html(glb_path)` — self-contained three.js page |
| `ocx_model_validator/cli.py` (modify) | `validator render` command |
| `tests/test_render_*.py` | one test module per render module |

---

### Task 1: Dependencies, package skeleton, `PartMesh`, options, `LengthResolver`

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `ocx_model_validator/render/__init__.py` (placeholder, filled in Task 10)
- Create: `ocx_model_validator/render/mesh.py`
- Create: `ocx_model_validator/render/backend.py`
- Create: `ocx_model_validator/render/length.py`
- Test: `tests/test_render_basics.py`

- [ ] **Step 1: Add dependencies**

```bash
uv add numpy geomdl shapely mapbox-earcut trimesh
```

Expected: `pyproject.toml` `dependencies` gains `numpy>=…`, `geomdl>=5.4`, `shapely>=2`, `mapbox-earcut>=1`, `trimesh>=4` (exact pins chosen by uv), and `uv.lock` updates.

- [ ] **Step 2: Write the failing test**

Create `tests/test_render_basics.py`:

```python
"""Tests for render/mesh.py, render/backend.py and render/length.py."""
import numpy as np
import pytest

from ocx_model_validator.model.ir.base import IrUnit, Quantity
from ocx_model_validator.model.ir.geometry import IrPoint3D
from ocx_model_validator.render.backend import RenderResult, TessellationOptions
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.mesh import PartMesh, part_color

MM = IrUnit(id="Umm", name="millimeter", symbol="mm",
            dimension_url="D_L", to_si_factor=1e-3, si_symbol="m")
M = IrUnit(id="Um", name="meter", symbol="m",
           dimension_url="D_L", to_si_factor=1.0, si_symbol="m")


class TestLengthResolver:
    def test_to_m_uses_registry_factor(self):
        lr = LengthResolver({"Umm": MM, "Um": M})
        assert lr.to_m(2500.0, "Umm") == pytest.approx(2.5)
        assert lr.to_m(2.5, "Um") == pytest.approx(2.5)

    def test_unknown_unit_falls_back_to_builtin_table(self):
        lr = LengthResolver({})
        assert lr.to_m(1000.0, "Umm") == pytest.approx(1.0)

    def test_completely_unknown_unit_assumes_metres(self):
        lr = LengthResolver({})
        assert lr.to_m(3.0, "Ufurlong") == pytest.approx(3.0)

    def test_point_returns_metre_ndarray(self):
        lr = LengthResolver({"Umm": MM})
        p = lr.point(IrPoint3D(1000.0, 2000.0, 3000.0, "Umm"))
        assert isinstance(p, np.ndarray)
        np.testing.assert_allclose(p, [1.0, 2.0, 3.0])

    def test_qty(self):
        lr = LengthResolver({"Umm": MM})
        assert lr.qty(Quantity(250.0, "Umm")) == pytest.approx(0.25)
        assert lr.qty(None) is None


class TestOptions:
    def test_defaults(self):
        opt = TessellationOptions()
        assert opt.tolerance_m == pytest.approx(0.05)
        assert opt.snap_tolerance_m == pytest.approx(0.01)


class TestPartMesh:
    def test_construction_and_counts(self):
        pm = PartMesh(
            part_id="pl1", name="Plate 1", kind="plate",
            vertices=np.zeros((3, 3)), triangles=np.array([[0, 1, 2]]),
        )
        assert pm.vertices.shape == (3, 3)
        assert pm.triangles.shape == (1, 3)
        assert pm.extras == {}

    def test_part_color_deterministic_and_kind_based(self):
        c1 = part_color("plate", "pl1")
        c2 = part_color("plate", "pl1")
        c3 = part_color("plate", "pl2")
        assert c1 == c2
        assert c1 != c3           # hue jitter differs per id
        assert all(0 <= v <= 255 for v in c1)
        # stiffeners are blueish: blue channel dominates red
        s = part_color("stiffener", "s1")
        assert s[2] > s[0]


class TestRenderResult:
    def test_counts(self):
        res = RenderResult()
        res.meshes.append(PartMesh("a", "a", "plate",
                                   np.zeros((3, 3)), np.array([[0, 1, 2]])))
        res.skipped["b"] = "no contour"
        assert res.rendered_count == 1
        assert res.skipped_count == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_render_basics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_model_validator.render'`

- [ ] **Step 4: Write the implementation**

Create `ocx_model_validator/render/__init__.py`:

```python
"""Tessellated 3D renderer — public API filled in by the orchestrator task."""
```

Create `ocx_model_validator/render/length.py`:

```python
"""Convert IR length quantities and points to metres."""
from __future__ import annotations

import numpy as np
from loguru import logger

from ocx_model_validator.model.ir.base import IrUnit, Quantity
from ocx_model_validator.model.ir.geometry import IrPoint3D

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

Create `ocx_model_validator/render/mesh.py`:

```python
"""PartMesh — the tessellated output unit — and per-part color assignment."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Base colors per part kind (RGB 0-255).
KIND_COLORS: dict[str, tuple[int, int, int]] = {
    "plate": (140, 145, 150),      # steel grey
    "stiffener": (70, 110, 200),   # blue
    "pillar": (80, 170, 110),      # green
    "panel": (205, 170, 125),      # tan (reserved; panels are not tessellated in v1)
}


def part_color(kind: str, part_id: str) -> tuple[int, int, int]:
    """Deterministic per-part color: kind base color + per-id hue jitter."""
    base = KIND_COLORS.get(kind, (180, 180, 180))
    digest = hashlib.md5(part_id.encode("utf-8")).digest()
    # three independent jitters in [-18, +18]
    return tuple(
        int(np.clip(base[i] + (digest[i] % 37) - 18, 0, 255)) for i in range(3)
    )


@dataclass
class PartMesh:
    """A single tessellated part, in metres."""
    part_id: str
    name: str
    kind: str                                  # "plate" | "stiffener" | "pillar" | "panel"
    vertices: np.ndarray                       # (N, 3) float64, metres
    triangles: np.ndarray                      # (M, 3) int
    normals: np.ndarray | None = None          # (N, 3) float64 or None
    color: tuple[int, int, int] | None = None  # filled from part_color if None
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = part_color(self.kind, self.part_id)
```

Create `ocx_model_validator/render/backend.py`:

```python
"""Tessellation backend interface and option/result types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from ocx_model_validator.render.mesh import PartMesh


@dataclass(frozen=True)
class TessellationOptions:
    """Controls tessellation density and contour repair."""
    tolerance_m: float = 0.05        # linear deflection (metres); default 50 mm
    snap_tolerance_m: float = 0.01   # max contour gap snapped shut (metres)


@dataclass
class RenderResult:
    """Outcome of a render: meshes plus a skip log (part id → reason)."""
    meshes: list[PartMesh] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def rendered_count(self) -> int:
        return len(self.meshes)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ITessellator(ABC):
    """Backend interface for trimming+triangulating a surface patch.

    Backends receive geometry already resolved to numpy arrays in metres
    (the orchestrator does IR resolution), so alternative backends (e.g. a
    future OpenCASCADE one) only re-implement the geometric core.
    """

    @abstractmethod
    def tessellate_trimmed_surface(
        self,
        part_id: str,
        name: str,
        kind: str,
        contour_pts: np.ndarray,            # (N, 3) closed boundary polyline, metres
        hole_pts: list[np.ndarray],         # list of (K, 3) closed hole polylines
        surface_param,                       # surfaces.SurfaceParam
        options: TessellationOptions,
    ) -> PartMesh | None:
        """Return the tessellated part, or None if this part cannot be meshed."""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_render_basics.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock ocx_model_validator/render tests/test_render_basics.py
git commit -m "feat(render): package skeleton — PartMesh, options, LengthResolver, ITessellator"
```

---

### Task 2: Curve sampling — line, polyline, arc, circle, ellipse

**Files:**
- Create: `ocx_model_validator/render/curves.py`
- Test: `tests/test_render_curves.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_curves.py`:

```python
"""Tests for render/curves.py — sampling IR curves to 3D polylines (metres)."""
import numpy as np
import pytest

from ocx_model_validator.model.ir.base import IrVector3D, Quantity
from ocx_model_validator.model.ir.geometry import (
    IrCircle3D,
    IrCircumArc3D,
    IrCompositeCurve3D,
    IrEllipse3D,
    IrLine3D,
    IrPoint3D,
    IrPolyLine3D,
)
from ocx_model_validator.render.curves import sample_contour, sample_curve
from ocx_model_validator.render.length import LengthResolver

LR = LengthResolver({})  # empty registry → builtin fallbacks ('Um' → 1.0)


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


class TestSampleCurve:
    def test_line(self):
        c = IrLine3D(curve_length=None, start=pt(0, 0, 0), end=pt(1, 2, 3))
        out = sample_curve(c, LR, tol_m=0.01)
        np.testing.assert_allclose(out, [[0, 0, 0], [1, 2, 3]])

    def test_polyline(self):
        c = IrPolyLine3D(curve_length=None,
                         vertices=[pt(0, 0, 0), pt(1, 0, 0), pt(1, 1, 0)])
        out = sample_curve(c, LR, tol_m=0.01)
        assert out.shape == (3, 3)

    def test_arc_through_three_points_stays_on_circle(self):
        # quarter arc of unit circle in XY plane
        c = IrCircumArc3D(curve_length=None, start=pt(1, 0, 0),
                          intermediate=pt(np.sqrt(0.5), np.sqrt(0.5), 0),
                          end=pt(0, 1, 0))
        out = sample_curve(c, LR, tol_m=0.001)
        assert len(out) >= 8
        radii = np.linalg.norm(out, axis=1)
        np.testing.assert_allclose(radii, 1.0, atol=1e-6)
        np.testing.assert_allclose(out[0], [1, 0, 0], atol=1e-9)
        np.testing.assert_allclose(out[-1], [0, 1, 0], atol=1e-9)

    def test_arc_sagitta_respects_tolerance(self):
        c = IrCircumArc3D(curve_length=None, start=pt(1, 0, 0),
                          intermediate=pt(0, 1, 0), end=pt(-1, 0, 0))
        out = sample_curve(c, LR, tol_m=0.001)
        # chord midpoints must deviate < tol from the unit circle
        mid = 0.5 * (out[:-1] + out[1:])
        sag = 1.0 - np.linalg.norm(mid, axis=1)
        assert np.all(sag < 0.001 + 1e-9)

    def test_collinear_arc_degrades_to_segment(self):
        c = IrCircumArc3D(curve_length=None, start=pt(0, 0, 0),
                          intermediate=pt(1, 0, 0), end=pt(2, 0, 0))
        out = sample_curve(c, LR, tol_m=0.01)
        np.testing.assert_allclose(out[0], [0, 0, 0])
        np.testing.assert_allclose(out[-1], [2, 0, 0])

    def test_full_circle_is_closed_loop(self):
        c = IrCircle3D(curve_length=None, center=pt(0, 0, 5),
                       diameter=Quantity(2.0, "Um"),
                       normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.001)
        assert len(out) >= 16
        np.testing.assert_allclose(out[0], out[-1], atol=1e-9)
        radii = np.linalg.norm(out - [0, 0, 5], axis=1)
        np.testing.assert_allclose(radii, 1.0, atol=1e-9)

    def test_ellipse(self):
        c = IrEllipse3D(curve_length=None, center=pt(0, 0, 0),
                        major_diameter=Quantity(4.0, "Um"),
                        minor_diameter=Quantity(2.0, "Um"),
                        major_axis=IrVector3D(1, 0, 0),
                        normal=IrVector3D(0, 0, 1))
        out = sample_curve(c, LR, tol_m=0.001)
        # on the ellipse: (x/2)^2 + y^2 == 1
        vals = (out[:, 0] / 2.0) ** 2 + out[:, 1] ** 2
        np.testing.assert_allclose(vals, 1.0, atol=1e-6)

    def test_unsupported_curve_returns_none(self):
        class Weird:
            pass
        assert sample_curve(Weird(), LR, tol_m=0.01) is None


class TestSampleContour:
    def test_composite_stitching_with_reversed_segment(self):
        # square: second segment supplied tip-to-tip reversed
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1, 1, 0), end=pt(1, 0, 0))  # reversed
        s3 = IrLine3D(None, start=pt(1, 1, 0), end=pt(0, 1, 0))
        s4 = IrLine3D(None, start=pt(0, 1, 0), end=pt(0, 0, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2, s3, s4])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        # closed contour: last point is NOT repeated
        assert not np.allclose(out[0], out[-1])
        assert len(out) == 4

    def test_small_gap_is_snapped(self):
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(1.005, 0, 0), end=pt(1, 1, 0))
        s3 = IrLine3D(None, start=pt(1, 1, 0), end=pt(0, 0.002, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2, s3])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        assert len(out) == 3

    def test_large_gap_returns_none(self):
        s1 = IrLine3D(None, start=pt(0, 0, 0), end=pt(1, 0, 0))
        s2 = IrLine3D(None, start=pt(5, 5, 0), end=pt(0, 1, 0))
        c = IrCompositeCurve3D(None, segments=[s1, s2])
        assert sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01) is None

    def test_open_contour_returns_none(self):
        c = IrPolyLine3D(None, vertices=[pt(0, 0, 0), pt(1, 0, 0), pt(1, 5, 0)])
        assert sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01) is None

    def test_closed_polyline_contour(self):
        c = IrPolyLine3D(None, vertices=[pt(0, 0, 0), pt(1, 0, 0),
                                         pt(1, 1, 0), pt(0, 0, 0)])
        out = sample_contour(c, LR, tol_m=0.01, snap_tol_m=0.01)
        assert out is not None
        assert len(out) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_curves.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` for `render.curves`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/curves.py`:

```python
"""Sample IR curves into 3D polylines (metres).

``sample_curve`` returns an (N, 3) float64 array or ``None`` for unsupported
curve types.  ``sample_contour`` additionally stitches composite segments
tip-to-tail, snaps small gaps and guarantees a *closed* contour (returned
WITHOUT a repeated last point), or returns ``None`` with a logged reason.
"""
from __future__ import annotations

import math

import numpy as np
from loguru import logger

from ocx_model_validator.model.ir.geometry import (
    IrCircle3D,
    IrCircumArc3D,
    IrCompositeCurve3D,
    IrCurve3D,
    IrEllipse3D,
    IrLine3D,
    IrNurbs3D,
    IrPoint3D,
    IrPolyLine3D,
)
from ocx_model_validator.render.length import LengthResolver

_MIN_ARC_SEGS = 8
_MAX_ARC_SEGS = 512


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return v / n


def _any_perp(n: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    return _unit(np.cross(n, ref))


def _angular_step(radius: float, tol_m: float) -> int:
    """Segment count for a full circle so chord sagitta <= tol."""
    if radius <= tol_m:
        return _MIN_ARC_SEGS
    dtheta = 2.0 * math.acos(max(1.0 - tol_m / radius, -1.0))
    return int(np.clip(math.ceil(2.0 * math.pi / dtheta), _MIN_ARC_SEGS, _MAX_ARC_SEGS))


def _sample_arc3(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray,
                 tol_m: float) -> np.ndarray:
    """Sample the circular arc through three points (start, intermediate, end)."""
    a, b = p1 - p0, p2 - p0
    n = np.cross(a, b)
    if np.linalg.norm(n) < 1e-12:            # collinear → straight segment
        return np.array([p0, p2])
    n = _unit(n)
    e1 = _unit(a)
    e2 = _unit(np.cross(n, e1))
    # 2D coords in the arc plane (origin p0): p0=(0,0), p1=(ax,0), p2=(bx,by)
    ax, bx, by = a @ e1, b @ e1, b @ e2
    # circumcenter of (0,0), (ax,0), (bx,by)
    d = 2.0 * (ax * by)
    if abs(d) < 1e-15:
        return np.array([p0, p2])
    cx = ax / 2.0
    cy = (bx * bx + by * by - bx * ax) / (2.0 * by)
    center = p0 + cx * e1 + cy * e2
    r = float(np.linalg.norm(p0 - center))
    ang = [math.atan2((p - center) @ e2, (p - center) @ e1) for p in (p0, p1, p2)]
    a0, a1, a2 = ang
    # choose sweep direction passing through a1
    ccw_mid = (a1 - a0) % (2 * math.pi)
    ccw_end = (a2 - a0) % (2 * math.pi)
    if ccw_mid <= ccw_end:                   # counter-clockwise
        sweep = ccw_end
    else:                                     # clockwise
        sweep = -((a0 - a2) % (2 * math.pi))
    nseg = max(2, int(math.ceil(abs(sweep) / (2 * math.pi) * _angular_step(r, tol_m))))
    t = a0 + sweep * np.linspace(0.0, 1.0, nseg + 1)
    pts = center + r * (np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2))
    pts[0], pts[-1] = p0, p2                  # exact endpoints
    return pts


def _sample_nurbs(curve: IrNurbs3D, length: LengthResolver,
                  tol_m: float) -> np.ndarray | None:
    if curve.degree is None or not curve.control_points or not curve.knot_vector:
        return None
    from geomdl import BSpline, NURBS
    if curve.is_rational and curve.weights:
        c = NURBS.Curve()
    else:
        c = BSpline.Curve()
    c.degree = curve.degree
    c.ctrlpts = [list(length.point(p)) for p in curve.control_points]
    if curve.is_rational and curve.weights:
        c.weights = list(curve.weights)
    c.knotvector = list(curve.knot_vector)
    lo, hi = c.knotvector[c.degree], c.knotvector[-c.degree - 1]
    # start with 32 samples, adaptively bisect while chord sagitta > tol
    us = list(np.linspace(lo, hi, 33))
    for _ in range(6):
        pts = np.array(c.evaluate_list(us))
        mids = [(us[i] + us[i + 1]) / 2.0 for i in range(len(us) - 1)]
        mid_pts = np.array(c.evaluate_list(mids))
        chord_mid = 0.5 * (pts[:-1] + pts[1:])
        sag = np.linalg.norm(mid_pts - chord_mid, axis=1)
        bad = np.where(sag > tol_m)[0]
        if len(bad) == 0 or len(us) > 2048:
            break
        us = sorted(set(us) | {mids[i] for i in bad})
    return np.array(c.evaluate_list(us))


def sample_curve(curve, length: LengthResolver, tol_m: float) -> np.ndarray | None:
    """Dispatch on curve type; return (N, 3) metres polyline or None."""
    if isinstance(curve, IrLine3D):
        if curve.start is None or curve.end is None:
            return None
        return np.array([length.point(curve.start), length.point(curve.end)])

    if isinstance(curve, IrPolyLine3D):
        if len(curve.vertices) < 2:
            return None
        return np.array([length.point(p) for p in curve.vertices])

    if isinstance(curve, IrCircumArc3D):
        if curve.start is None or curve.intermediate is None or curve.end is None:
            return None
        return _sample_arc3(length.point(curve.start),
                            length.point(curve.intermediate),
                            length.point(curve.end), tol_m)

    if isinstance(curve, IrCircle3D):
        if curve.center is None or curve.diameter is None or curve.normal is None:
            return None
        center = length.point(curve.center)
        r = length.qty(curve.diameter) / 2.0
        n = _unit(np.array([curve.normal.x, curve.normal.y, curve.normal.z]))
        e1 = _any_perp(n)
        e2 = np.cross(n, e1)
        t = np.linspace(0.0, 2 * math.pi, _angular_step(r, tol_m) + 1)
        return center + r * (np.outer(np.cos(t), e1) + np.outer(np.sin(t), e2))

    if isinstance(curve, IrEllipse3D):
        if (curve.center is None or curve.major_diameter is None
                or curve.minor_diameter is None or curve.major_axis is None
                or curve.normal is None):
            return None
        center = length.point(curve.center)
        ra = length.qty(curve.major_diameter) / 2.0
        rb = length.qty(curve.minor_diameter) / 2.0
        n = _unit(np.array([curve.normal.x, curve.normal.y, curve.normal.z]))
        e1 = _unit(np.array([curve.major_axis.x, curve.major_axis.y, curve.major_axis.z]))
        e2 = np.cross(n, e1)
        t = np.linspace(0.0, 2 * math.pi, _angular_step(max(ra, rb), tol_m) + 1)
        return center + np.outer(ra * np.cos(t), e1) + np.outer(rb * np.sin(t), e2)

    if isinstance(curve, IrNurbs3D):
        return _sample_nurbs(curve, length, tol_m)

    if isinstance(curve, IrCompositeCurve3D):
        return _sample_composite(curve, length, tol_m, snap_tol_m=tol_m)

    logger.debug("Unsupported curve type for sampling: {}", type(curve).__name__)
    return None


def _sample_composite(curve: IrCompositeCurve3D, length: LengthResolver,
                      tol_m: float, snap_tol_m: float) -> np.ndarray | None:
    """Stitch composite segments tip-to-tail, reversing segments as needed."""
    parts: list[np.ndarray] = []
    for seg in curve.segments:
        pts = sample_curve(seg, length, tol_m)
        if pts is None or len(pts) < 2:
            logger.debug("Composite segment {} unsampleable", type(seg).__name__)
            return None
        parts.append(pts)
    if not parts:
        return None
    out = parts[0]
    for pts in parts[1:]:
        tail = out[-1]
        d_fwd = np.linalg.norm(pts[0] - tail)
        d_rev = np.linalg.norm(pts[-1] - tail)
        if d_rev < d_fwd:
            pts = pts[::-1]
            d_fwd = d_rev
        if d_fwd > snap_tol_m:
            logger.debug("Composite gap {:.4f} m exceeds snap tolerance", d_fwd)
            return None
        # snap: the next segment's first point merges with the current tail
        out = np.vstack([out, pts[1:]])
    return _dedupe(out)


def _dedupe(pts: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) > eps:
            keep.append(i)
    return pts[keep]


def sample_contour(curve, length: LengthResolver, tol_m: float,
                   snap_tol_m: float) -> np.ndarray | None:
    """Sample a *closed* boundary contour.

    Returns the closed loop WITHOUT a repeated last point, or None if the
    curve cannot be sampled or does not close within ``snap_tol_m``.
    """
    if isinstance(curve, IrCompositeCurve3D):
        pts = _sample_composite(curve, length, tol_m, snap_tol_m)
    else:
        pts = sample_curve(curve, length, tol_m)
    if pts is None or len(pts) < 3:
        return None
    pts = _dedupe(pts)
    gap = np.linalg.norm(pts[0] - pts[-1])
    if gap <= snap_tol_m:
        if gap > 1e-12:
            pts = pts[:-1] if len(pts) > 3 else pts
        else:
            pts = pts[:-1]
    else:
        logger.debug("Contour does not close: gap {:.4f} m", gap)
        return None
    if len(pts) < 3:
        return None
    return pts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_curves.py -v`
Expected: PASS. If `test_small_gap_is_snapped` fails on the closing gap, check that `sample_contour` compares `pts[0]` to `pts[-1]` *after* stitching (the 0.002 m end gap is within the 0.01 m snap tolerance).

- [ ] **Step 5: Run ruff and the full suite**

Run: `uv run ruff check ocx_model_validator/render tests/test_render_curves.py` then `uv run pytest`
Expected: no lint errors; full suite PASS.

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/render/curves.py tests/test_render_curves.py
git commit -m "feat(render): curve sampling — lines, arcs, circles, ellipses, NURBS, composite stitching"
```

---

### Task 3: Surface parametrizations — plane, cylinder, cone, sphere

**Files:**
- Create: `ocx_model_validator/render/surfaces.py`
- Test: `tests/test_render_surfaces.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_surfaces.py`:

```python
"""Tests for render/surfaces.py — eval/inverse round-trips per surface type."""
import math

import numpy as np
import pytest

from ocx_model_validator.model.ir.base import IrVector3D, Quantity
from ocx_model_validator.model.ir.geometry import (
    IrCone3D,
    IrCylinder3D,
    IrPlane3D,
    IrPoint3D,
    IrSphere3D,
)
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.surfaces import make_param

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def roundtrip(param, pts3d, atol=1e-6):
    uv = param.inverse(np.asarray(pts3d, dtype=float))
    back = param.evaluate(uv)
    np.testing.assert_allclose(back, pts3d, atol=atol)
    return uv


class TestPlane:
    def test_roundtrip(self):
        s = IrPlane3D(id="p", point_on_surface=pt(1, 2, 3),
                      normal=IrVector3D(0, 0, 1))
        param = make_param(s, LR, tol_m=0.01)
        roundtrip(param, [[1, 2, 3], [5, -4, 3], [100, 100, 3]])

    def test_normals_constant(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                      normal=IrVector3D(0, 0, 2))  # non-unit input
        param = make_param(s, LR, tol_m=0.01)
        n = param.normals(np.array([[0.0, 0.0], [5.0, 5.0]]))
        np.testing.assert_allclose(n, [[0, 0, 1], [0, 0, 1]], atol=1e-12)

    def test_plane_needs_no_subdivision(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                      normal=IrVector3D(0, 0, 1))
        param = make_param(s, LR, tol_m=0.01)
        assert param.max_edge_m(0.01) is None


class TestCylinder:
    def make(self, r=2.0):
        s = IrCylinder3D(id="c", origin=pt(0, 0, 0),
                         axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um"))
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip_on_surface(self):
        param = self.make()
        pts = [[2, 0, 0], [0, 2, 5], [-2, 0, -3]]
        roundtrip(param, pts)

    def test_seam_crossing_contour_unwraps_continuously(self):
        """Points circling past the u = ±pi seam must yield monotonic u."""
        param = self.make(r=1.0)
        ang = np.linspace(0.9 * math.pi, 1.1 * math.pi, 9)  # crosses the seam
        pts = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(9)])
        uv = param.inverse(pts)
        du = np.diff(uv[:, 0])
        assert np.all(du > 0)          # no 2π jump back
        roundtrip(param, pts)

    def test_max_edge_scales_with_radius_and_tol(self):
        p1, p2 = self.make(r=1.0), self.make(r=4.0)
        assert p2.max_edge_m(0.01) == pytest.approx(2 * p1.max_edge_m(0.01))


class TestCone:
    def test_roundtrip(self):
        s = IrCone3D(id="k", origin=pt(0, 0, 0), tip=pt(0, 0, 4),
                     base_radius=Quantity(2.0, "Um"),
                     tip_radius=Quantity(1.0, "Um"))
        param = make_param(s, LR, tol_m=0.01)
        # radius at v: 2 + (1-2)*v/4
        pts = [[2, 0, 0], [0, 1.5, 2], [-1, 0, 4]]
        roundtrip(param, pts, atol=1e-6)


class TestSphere:
    def make(self, r=3.0):
        s = IrSphere3D(id="s", origin=pt(0, 0, 0), radius=Quantity(r, "Um"))
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip(self):
        param = self.make()
        pts = 3.0 * np.array([[1, 0, 0], [0, 1, 0],
                              [0.5, 0.5, np.sqrt(0.5)]])
        roundtrip(param, pts)

    def test_pole_inverse_does_not_produce_nan(self):
        param = self.make()
        pts = np.array([[1e-12, 0, 3.0], [3.0, 0, 0]])   # north pole + equator
        uv = param.inverse(pts)
        assert np.all(np.isfinite(uv))

    def test_normals_point_outward(self):
        param = self.make()
        uv = param.inverse(np.array([[3.0, 0.0, 0.0]]))
        n = param.normals(uv)
        np.testing.assert_allclose(n, [[1, 0, 0]], atol=1e-9)


class TestFactory:
    def test_unknown_surface_returns_none(self):
        class Weird:
            pass
        assert make_param(Weird(), LR, tol_m=0.01) is None

    def test_plane_missing_normal_returns_none(self):
        s = IrPlane3D(id="p", point_on_surface=pt(0, 0, 0), normal=None)
        assert make_param(s, LR, tol_m=0.01) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_surfaces.py -v`
Expected: FAIL — `ImportError` for `render.surfaces`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/surfaces.py`:

```python
"""Surface parametrizations: evaluate(u,v), inverse(points), normals.

Each ``SurfaceParam``:
- ``evaluate(uv)``   — (N,2) → (N,3) metres
- ``normals(uv)``    — (N,2) → (N,3) unit normals (numeric by default)
- ``inverse(pts)``   — (N,3) → (N,2); for periodic-u surfaces the u values of
  a *polyline* are unwrapped continuously, so a contour crossing the seam
  stays a single connected run in UV space.
- ``uv_scale()``     — (su, sv) metres per uv unit, for metric subdivision
- ``max_edge_m(tol)``— max metric-UV edge length keeping chordal error <= tol,
  or None when no interior subdivision is needed (planes, ruled directions).
``make_param`` builds the right param from an IrSurface3D, or returns None.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np
from loguru import logger

from ocx_model_validator.model.ir.geometry import (
    IrCone3D,
    IrCylinder3D,
    IrExtrudedSurface,
    IrNurbsSurface,
    IrPlane3D,
    IrSphere3D,
)
from ocx_model_validator.render.curves import _any_perp, _unit, sample_curve
from ocx_model_validator.render.length import LengthResolver


def _vec(v) -> np.ndarray:
    return np.array([v.x, v.y, v.z], dtype=np.float64)


class SurfaceParam(ABC):
    periodic_u: bool = False

    @abstractmethod
    def evaluate(self, uv: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def inverse(self, pts: np.ndarray) -> np.ndarray: ...

    def normals(self, uv: np.ndarray) -> np.ndarray:
        """Numeric normals via central differences (overridden where analytic)."""
        uv = np.asarray(uv, dtype=float)
        span = max(float(np.ptp(uv[:, 0])), float(np.ptp(uv[:, 1])), 1.0)
        eps = 1e-5 * span
        du = self.evaluate(uv + [eps, 0.0]) - self.evaluate(uv - [eps, 0.0])
        dv = self.evaluate(uv + [0.0, eps]) - self.evaluate(uv - [0.0, eps])
        n = np.cross(du, dv)
        norms = np.linalg.norm(n, axis=1, keepdims=True)
        norms[norms < 1e-15] = 1.0
        return n / norms

    def uv_scale(self) -> tuple[float, float]:
        return (1.0, 1.0)

    def max_edge_m(self, tol_m: float) -> float | None:
        return None


def _chord_edge(radius: float, tol_m: float) -> float:
    """Max chord length with sagitta <= tol on a circle of given radius."""
    return math.sqrt(max(8.0 * tol_m * radius, 1e-12))


class PlaneParam(SurfaceParam):
    def __init__(self, origin: np.ndarray, normal: np.ndarray,
                 udir: np.ndarray | None = None) -> None:
        self.o = origin
        self.n = _unit(normal)
        if udir is not None and np.linalg.norm(udir) > 1e-12:
            u = udir - (udir @ self.n) * self.n
            self.u = _unit(u) if np.linalg.norm(u) > 1e-12 else _any_perp(self.n)
        else:
            self.u = _any_perp(self.n)
        self.v = np.cross(self.n, self.u)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        return self.o + np.outer(uv[:, 0], self.u) + np.outer(uv[:, 1], self.v)

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        return np.column_stack([d @ self.u, d @ self.v])

    def normals(self, uv):
        return np.tile(self.n, (len(np.asarray(uv)), 1))


class CylinderParam(SurfaceParam):
    periodic_u = True

    def __init__(self, origin: np.ndarray, axis: np.ndarray, radius: float) -> None:
        self.o, self.a, self.r = origin, _unit(axis), radius
        self.x = _any_perp(self.a)
        self.y = np.cross(self.a, self.x)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        return (self.o
                + self.r * (np.outer(np.cos(u), self.x) + np.outer(np.sin(u), self.y))
                + np.outer(v, self.a))

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        v = d @ self.a
        rad = d - np.outer(v, self.a)
        u = np.arctan2(rad @ self.y, rad @ self.x)
        return np.column_stack([np.unwrap(u), v])

    def normals(self, uv):
        u = np.asarray(uv, dtype=float)[:, 0]
        return np.outer(np.cos(u), self.x) + np.outer(np.sin(u), self.y)

    def uv_scale(self):
        return (self.r, 1.0)

    def max_edge_m(self, tol_m):
        return _chord_edge(self.r, tol_m)


class ConeParam(SurfaceParam):
    """v = metres along the axis from the base origin; radius interpolates
    base_radius → tip_radius over the origin→tip height."""
    periodic_u = True

    def __init__(self, origin: np.ndarray, tip: np.ndarray,
                 base_radius: float, tip_radius: float) -> None:
        self.o = origin
        axis = tip - origin
        self.h = float(np.linalg.norm(axis))
        self.a = _unit(axis)
        self.rb, self.rt = base_radius, tip_radius
        self.x = _any_perp(self.a)
        self.y = np.cross(self.a, self.x)

    def _radius(self, v):
        return self.rb + (self.rt - self.rb) * (v / self.h)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        r = self._radius(v)
        return (self.o
                + (r[:, None] * (np.outer(np.cos(u), self.x)
                                 + np.outer(np.sin(u), self.y)))
                + np.outer(v, self.a))

    def inverse(self, pts):
        d = np.asarray(pts, dtype=float) - self.o
        v = d @ self.a
        rad = d - np.outer(v, self.a)
        u = np.arctan2(rad @ self.y, rad @ self.x)
        return np.column_stack([np.unwrap(u), v])

    def uv_scale(self):
        return (max(self.rb, self.rt), 1.0)

    def max_edge_m(self, tol_m):
        return _chord_edge(max(self.rb, self.rt), tol_m)


class SphereParam(SurfaceParam):
    """u = azimuth (periodic), v = polar angle from the frame z axis."""
    periodic_u = True

    def __init__(self, origin: np.ndarray, radius: float,
                 zdir: np.ndarray | None = None) -> None:
        self.o, self.r = origin, radius
        self.z = _unit(zdir) if zdir is not None and np.linalg.norm(zdir) > 1e-12 \
            else np.array([0.0, 0.0, 1.0])
        self.x = _any_perp(self.z)
        self.y = np.cross(self.z, self.x)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        u, v = uv[:, 0], uv[:, 1]
        return self.o + self.r * (np.outer(np.sin(v) * np.cos(u), self.x)
                                  + np.outer(np.sin(v) * np.sin(u), self.y)
                                  + np.outer(np.cos(v), self.z))

    def inverse(self, pts):
        d = (np.asarray(pts, dtype=float) - self.o) / self.r
        v = np.arccos(np.clip(d @ self.z, -1.0, 1.0))
        u = np.arctan2(d @ self.y, d @ self.x)
        # poles: u is undefined where sin(v) ~ 0 — reuse the neighbour's u
        tiny = np.sin(v) < 1e-9
        for i in np.where(tiny)[0]:
            u[i] = u[i - 1] if i > 0 else 0.0
        return np.column_stack([np.unwrap(u), v])

    def normals(self, uv):
        p = self.evaluate(uv)
        return (p - self.o) / self.r

    def uv_scale(self):
        return (self.r, self.r)

    def max_edge_m(self, tol_m):
        return _chord_edge(self.r, tol_m)


def make_param(surface, length: LengthResolver,
               tol_m: float) -> SurfaceParam | None:
    """Build the parametrization for an IrSurface3D, or None if unsupported
    or missing required fields.  Extended in Task 4 with extruded + NURBS."""
    try:
        if isinstance(surface, IrPlane3D):
            if surface.point_on_surface is None or surface.normal is None:
                return None
            udir = _vec(surface.udirection) if surface.udirection else None
            return PlaneParam(length.point(surface.point_on_surface),
                              _vec(surface.normal), udir)

        if isinstance(surface, IrCylinder3D):
            if surface.origin is None or surface.axis is None or surface.radius is None:
                return None
            return CylinderParam(length.point(surface.origin),
                                 _vec(surface.axis), length.qty(surface.radius))

        if isinstance(surface, IrCone3D):
            if (surface.origin is None or surface.tip is None
                    or surface.base_radius is None or surface.tip_radius is None):
                return None
            return ConeParam(length.point(surface.origin), length.point(surface.tip),
                             length.qty(surface.base_radius),
                             length.qty(surface.tip_radius))

        if isinstance(surface, IrSphere3D):
            if surface.origin is None or surface.radius is None:
                return None
            zdir = _vec(surface.normal) if surface.normal else None
            return SphereParam(length.point(surface.origin),
                               length.qty(surface.radius), zdir)

        if isinstance(surface, (IrExtrudedSurface, IrNurbsSurface)):
            return _make_param_extended(surface, length, tol_m)
    except (ValueError, ZeroDivisionError) as exc:
        logger.debug("Surface parametrization failed for {}: {}",
                     type(surface).__name__, exc)
        return None
    logger.debug("Unsupported surface type: {}", type(surface).__name__)
    return None


def _make_param_extended(surface, length, tol_m):   # implemented in Task 4
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_surfaces.py -v`
Expected: PASS. Note `test_seam_crossing_contour_unwraps_continuously` depends on `np.unwrap` in `inverse` — inverse receives the whole polyline at once, never point-by-point.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/surfaces.py tests/test_render_surfaces.py
git commit -m "feat(render): analytic surface parametrizations with seam-aware inverse"
```

---

### Task 4: Surface parametrizations — extruded surface and NURBS

**Files:**
- Modify: `ocx_model_validator/render/surfaces.py` (replace `_make_param_extended` stub; add two classes)
- Test: `tests/test_render_surfaces_ext.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_surfaces_ext.py`:

```python
"""Tests for extruded + NURBS surface parametrizations."""
import numpy as np
import pytest

from ocx_model_validator.model.ir.base import IrVector3D
from ocx_model_validator.model.ir.geometry import (
    IrExtrudedSurface,
    IrLine3D,
    IrNurbsSurface,
    IrPoint3D,
)
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.surfaces import make_param

LR = LengthResolver({})


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


class TestExtruded:
    def make(self):
        s = IrExtrudedSurface(
            id="e",
            base_curve=IrLine3D(None, start=pt(0, 0, 0), end=pt(4, 0, 0)),
            sweep=IrVector3D(0, 0, 1),
        )
        return make_param(s, LR, tol_m=0.01)

    def test_roundtrip(self):
        param = self.make()
        pts = np.array([[0.0, 0, 0], [2.0, 0, 3.0], [4.0, 0, -1.0]])
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-6)
        # u is arclength along the base line, v metres along the sweep
        np.testing.assert_allclose(uv[1], [2.0, 3.0], atol=1e-6)

    def test_missing_base_curve_returns_none(self):
        s = IrExtrudedSurface(id="e", base_curve=None, sweep=IrVector3D(0, 0, 1))
        assert make_param(s, LR, tol_m=0.01) is None


def flat_nurbs_surface():
    """Degree-1 x degree-1 B-spline patch spanning [0,4]x[0,2] in the XY plane."""
    return IrNurbsSurface(
        id="n", u_degree=1, v_degree=1,
        u_knot_vector=[0, 0, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(0, 0, 0), pt(0, 2, 0)],
                        [pt(4, 0, 0), pt(4, 2, 0)]],
    )


def curved_nurbs_surface():
    """Degree-2 x degree-1 patch bulging in z."""
    return IrNurbsSurface(
        id="n2", u_degree=2, v_degree=1,
        u_knot_vector=[0, 0, 0, 1, 1, 1], v_knot_vector=[0, 0, 1, 1],
        control_points=[[pt(0, 0, 0), pt(0, 2, 0)],
                        [pt(2, 0, 2), pt(2, 2, 2)],   # raised middle row
                        [pt(4, 0, 0), pt(4, 2, 0)]],
    )


class TestNurbs:
    def test_flat_patch_roundtrip(self):
        param = make_param(flat_nurbs_surface(), LR, tol_m=0.01)
        assert param is not None
        pts = np.array([[1.0, 1.0, 0.0], [3.0, 0.5, 0.0]])
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-5)

    def test_curved_patch_newton_inversion(self):
        param = make_param(curved_nurbs_surface(), LR, tol_m=0.01)
        # take exact surface points, invert, re-evaluate
        probe_uv = np.array([[0.25, 0.5], [0.5, 0.25], [0.75, 0.75]])
        pts = param.evaluate(probe_uv)
        uv = param.inverse(pts)
        np.testing.assert_allclose(param.evaluate(uv), pts, atol=1e-5)

    def test_curved_patch_requests_subdivision(self):
        param = make_param(curved_nurbs_surface(), LR, tol_m=0.001)
        edge = param.max_edge_m(0.001)
        assert edge is not None and edge > 0

    def test_missing_knots_returns_none(self):
        s = IrNurbsSurface(id="n", u_degree=1, v_degree=1,
                           control_points=[[pt(0, 0, 0)]])
        assert make_param(s, LR, tol_m=0.01) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_surfaces_ext.py -v`
Expected: FAIL — `make_param` returns `None` for both types (stub).

- [ ] **Step 3: Write the implementation**

In `ocx_model_validator/render/surfaces.py`, **replace** the `_make_param_extended` stub at the end of the file with:

```python
class ExtrudedParam(SurfaceParam):
    """u = arclength along the sampled base curve; v = metres along sweep."""

    def __init__(self, base_pts: np.ndarray, sweep: np.ndarray) -> None:
        self.b = base_pts
        seg = np.linalg.norm(np.diff(base_pts, axis=0), axis=1)
        self.s = np.concatenate([[0.0], np.cumsum(seg)])
        self.d = _unit(sweep)

    def evaluate(self, uv):
        uv = np.asarray(uv, dtype=float)
        base = np.column_stack(
            [np.interp(uv[:, 0], self.s, self.b[:, k]) for k in range(3)])
        return base + np.outer(uv[:, 1], self.d)

    def inverse(self, pts):
        # project out the sweep direction, then do 2D point-to-segment projection
        def flat(x):
            return x - np.outer(x @ self.d, self.d)

        bp = flat(self.b)
        out = np.empty((len(pts), 2))
        for i, p in enumerate(np.asarray(pts, dtype=float)):
            pp = p - (p @ self.d) * self.d
            best_res, best_u = np.inf, 0.0
            for j in range(len(bp) - 1):
                e = bp[j + 1] - bp[j]
                ll = e @ e
                t = 0.0 if ll < 1e-18 else float(np.clip((pp - bp[j]) @ e / ll, 0.0, 1.0))
                res = float(np.linalg.norm(pp - (bp[j] + t * e)))
                if res < best_res:
                    best_res = res
                    best_u = self.s[j] + t * (self.s[j + 1] - self.s[j])
            base = np.array([np.interp(best_u, self.s, self.b[:, k]) for k in range(3)])
            out[i] = (best_u, (p - base) @ self.d)
        return out


class NurbsSurfaceParam(SurfaceParam):
    """geomdl-backed B-spline surface with Newton point inversion."""

    _GRID = 16          # seed grid resolution per direction
    _NEWTON_ITERS = 25

    def __init__(self, surface: IrNurbsSurface, length: LengthResolver) -> None:
        from geomdl import BSpline
        s = BSpline.Surface()
        s.degree_u = surface.u_degree
        s.degree_v = surface.v_degree
        s.ctrlpts2d = [[list(length.point(p)) for p in row]
                       for row in surface.control_points]
        s.knotvector_u = list(surface.u_knot_vector)
        s.knotvector_v = list(surface.v_knot_vector)
        self.s = s
        ku, kv = s.knotvector_u, s.knotvector_v
        self.du = (ku[s.degree_u], ku[-s.degree_u - 1])
        self.dv = (kv[s.degree_v], kv[-s.degree_v - 1])
        # seed grid for inversion
        us = np.linspace(*self.du, self._GRID)
        vs = np.linspace(*self.dv, self._GRID)
        grid_uv = np.array([(u, v) for u in us for v in vs])
        self._grid_uv = grid_uv
        self._grid_pts = np.array(
            self.s.evaluate_list([tuple(x) for x in grid_uv]))

    def evaluate(self, uv):
        uv = np.clip(np.asarray(uv, dtype=float),
                     [self.du[0], self.dv[0]], [self.du[1], self.dv[1]])
        return np.array(self.s.evaluate_list([tuple(x) for x in uv]))

    def _invert_one(self, p: np.ndarray) -> tuple[float, float]:
        i = int(np.argmin(np.linalg.norm(self._grid_pts - p, axis=1)))
        u, v = self._grid_uv[i]
        for _ in range(self._NEWTON_ITERS):
            d = self.s.derivatives(float(u), float(v), order=1)
            S = np.array(d[0][0])
            Su, Sv = np.array(d[1][0]), np.array(d[0][1])
            r = S - p
            A = np.array([[Su @ Su, Su @ Sv], [Su @ Sv, Sv @ Sv]])
            b = -np.array([Su @ r, Sv @ r])
            try:
                step = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                break
            u = float(np.clip(u + step[0], *self.du))
            v = float(np.clip(v + step[1], *self.dv))
            if abs(step[0]) * np.linalg.norm(Su) \
                    + abs(step[1]) * np.linalg.norm(Sv) < 1e-9:
                break
        return u, v

    def inverse(self, pts):
        return np.array([self._invert_one(p)
                         for p in np.asarray(pts, dtype=float)])

    def uv_scale(self):
        uc = 0.5 * (self.du[0] + self.du[1])
        vc = 0.5 * (self.dv[0] + self.dv[1])
        d = self.s.derivatives(uc, vc, order=1)
        su = float(np.linalg.norm(d[1][0]))
        sv = float(np.linalg.norm(d[0][1]))
        return (max(su, 1e-9), max(sv, 1e-9))

    def max_edge_m(self, tol_m):
        """Estimate min curvature radius from 2nd derivatives on a 3x3 grid."""
        kappa_max = 0.0
        for u in np.linspace(*self.du, 3):
            for v in np.linspace(*self.dv, 3):
                d = self.s.derivatives(float(u), float(v), order=2)
                Su, Sv = np.array(d[1][0]), np.array(d[0][1])
                n = np.cross(Su, Sv)
                nn = np.linalg.norm(n)
                if nn < 1e-12:
                    continue
                n = n / nn
                for second, first in ((d[2][0], Su), (d[0][2], Sv)):
                    denom = np.linalg.norm(first) ** 2
                    if denom > 1e-12:
                        kappa_max = max(kappa_max,
                                        abs(np.array(second) @ n) / denom)
        if kappa_max < 1e-9:
            return None
        return _chord_edge(1.0 / kappa_max, tol_m)


def _make_param_extended(surface, length: LengthResolver,
                         tol_m: float) -> SurfaceParam | None:
    if isinstance(surface, IrExtrudedSurface):
        if surface.base_curve is None or surface.sweep is None:
            return None
        base = sample_curve(surface.base_curve, length, tol_m)
        if base is None or len(base) < 2:
            return None
        return ExtrudedParam(base, _vec(surface.sweep))

    if isinstance(surface, IrNurbsSurface):
        if (surface.u_degree is None or surface.v_degree is None
                or not surface.u_knot_vector or not surface.v_knot_vector
                or not surface.control_points):
            return None
        return NurbsSurfaceParam(surface, length)
    return None
```

**Note:** `IrNurbsSurface` carries no weights field in the IR, so `BSpline.Surface` (non-rational) is always correct here. `geomdl` `ctrlpts2d` is row-major `[u][v]` — matching `IrNurbsSurface.control_points` (outer list = u rows).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_surfaces_ext.py tests/test_render_surfaces.py -v`
Expected: PASS (both files — Task 3 behavior must not regress).

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/surfaces.py tests/test_render_surfaces_ext.py
git commit -m "feat(render): extruded-surface and NURBS parametrizations with Newton inversion"
```

---

### Task 5: UV tessellator — trim, triangulate, subdivide, lift

**Files:**
- Create: `ocx_model_validator/render/uv_tessellator.py`
- Test: `tests/test_render_uv_tessellator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_uv_tessellator.py`:

```python
"""Tests for the pure-Python UV-domain tessellator."""
import numpy as np

from ocx_model_validator.model.ir.base import IrVector3D, Quantity
from ocx_model_validator.model.ir.geometry import IrCylinder3D, IrPlane3D, IrPoint3D
from ocx_model_validator.render.backend import TessellationOptions
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.surfaces import make_param
from ocx_model_validator.render.uv_tessellator import UvTessellator

LR = LengthResolver({})
OPT = TessellationOptions()


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def plane_param():
    return make_param(
        IrPlane3D(id="p", point_on_surface=pt(0, 0, 0),
                  normal=IrVector3D(0, 0, 1), udirection=IrVector3D(1, 0, 0)),
        LR, tol_m=OPT.tolerance_m)


def mesh_area(pm):
    v, f = pm.vertices, pm.triangles
    cross = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    return 0.5 * float(np.linalg.norm(cross, axis=1).sum())


class TestPlanarPlate:
    def test_rectangle(self):
        contour = np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [0, 2, 0]], dtype=float)
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl1", "Plate 1", "plate", contour, [], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 8.0, atol=1e-9)
        assert pm.normals is not None and np.allclose(np.abs(pm.normals[:, 2]), 1.0)
        assert np.all(np.isfinite(pm.vertices))

    def test_l_shape_with_hole(self):
        contour = np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [2, 2, 0],
                            [2, 4, 0], [0, 4, 0]], dtype=float)       # area 12
        hole = np.array([[0.5, 0.5, 0], [1.5, 0.5, 0],
                         [1.5, 1.5, 0], [0.5, 1.5, 0]], dtype=float)  # area 1
        pm = UvTessellator().tessellate_trimmed_surface(
            "pl2", "L plate", "plate", contour, [hole], plane_param(), OPT)
        assert pm is not None
        assert np.isclose(mesh_area(pm), 11.0, atol=1e-6)

    def test_degenerate_contour_returns_none(self):
        contour = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)  # zero area
        pm = UvTessellator().tessellate_trimmed_surface(
            "bad", "bad", "plate", contour, [], plane_param(), OPT)
        assert pm is None


class TestCylindricalPlate:
    def test_curved_patch_is_subdivided_and_on_surface(self):
        r = 2.0
        param = make_param(
            IrCylinder3D(id="c", origin=pt(0, 0, 0), axis=IrVector3D(0, 0, 1),
                         radius=Quantity(r, "Um")),
            LR, tol_m=OPT.tolerance_m)
        # half-shell boundary: angles 0..pi at z=0 and z=3 (on-surface polyline)
        ang = np.linspace(0.0, np.pi, 20)
        bottom = np.column_stack([r * np.cos(ang), r * np.sin(ang), np.zeros(20)])
        top = bottom[::-1] + [0, 0, 3.0]
        contour = np.vstack([bottom, top])
        pm = UvTessellator().tessellate_trimmed_surface(
            "cp", "curved", "plate", contour, [], param, OPT)
        assert pm is not None
        # interior vertices must lie on the cylinder, not on boundary chords
        radii = np.linalg.norm(pm.vertices[:, :2], axis=1)
        np.testing.assert_allclose(radii, r, atol=1e-6)
        # subdivision must create interior vertices beyond the boundary samples
        assert len(pm.vertices) > len(contour)
        # analytic area of the half shell: pi * r * h
        assert abs(mesh_area(pm) - np.pi * r * 3.0) / (np.pi * r * 3.0) < 0.02
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_uv_tessellator.py -v`
Expected: FAIL — `ImportError` for `render.uv_tessellator`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/uv_tessellator.py`:

```python
"""Pure-Python UV-domain tessellation backend.

Pipeline per part: inverse-map boundary (and holes) to UV → repair the UV
polygon with shapely → earcut-triangulate → metric subdivision for curved
surfaces → evaluate surface at final UV vertices → PartMesh.
"""
from __future__ import annotations

import mapbox_earcut
import numpy as np
import shapely
import trimesh
from loguru import logger
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient

from ocx_model_validator.render.backend import ITessellator, TessellationOptions
from ocx_model_validator.render.mesh import PartMesh
from ocx_model_validator.render.surfaces import SurfaceParam

_MIN_TRI_AREA = 1e-14


def _largest_polygon(geom) -> Polygon | None:
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area, default=None)
    if hasattr(geom, "geoms"):                       # GeometryCollection
        polys = [g for g in geom.geoms if isinstance(g, Polygon)]
        return max(polys, key=lambda g: g.area, default=None)
    return None


def _clean_polygon(uv: np.ndarray, holes: list[np.ndarray]
                   ) -> tuple[np.ndarray, list[np.ndarray]] | None:
    """Validate/repair the UV polygon; return (exterior, holes) ring arrays."""
    try:
        poly = Polygon(uv, holes=[h for h in holes if len(h) >= 3])
    except (ValueError, TypeError):
        return None
    if not poly.is_valid:
        poly = _largest_polygon(shapely.make_valid(poly))
        if poly is None:
            return None
    if poly.is_empty or poly.area <= 0.0:
        return None
    poly = orient(poly, sign=1.0)                    # CCW exterior, CW holes
    ext = np.array(poly.exterior.coords)[:-1]
    ints = [np.array(r.coords)[:-1] for r in poly.interiors]
    if len(ext) < 3:
        return None
    return ext, ints


def _earcut(ext: np.ndarray, holes: list[np.ndarray]
            ) -> tuple[np.ndarray, np.ndarray] | None:
    rings = [ext] + holes
    verts = np.vstack(rings).astype(np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tris = mapbox_earcut.triangulate_float64(verts, ends)
    if len(tris) == 0:
        return None
    return verts, np.asarray(tris, dtype=np.int64).reshape(-1, 3)


def _drop_degenerate(verts3: np.ndarray, tris: np.ndarray) -> np.ndarray:
    cross = np.cross(verts3[tris[:, 1]] - verts3[tris[:, 0]],
                     verts3[tris[:, 2]] - verts3[tris[:, 0]])
    areas = 0.5 * np.linalg.norm(cross, axis=1)
    return tris[areas > _MIN_TRI_AREA]


class UvTessellator(ITessellator):
    """Default pure-Python tessellation backend."""

    def tessellate_trimmed_surface(
        self,
        part_id: str,
        name: str,
        kind: str,
        contour_pts: np.ndarray,
        hole_pts: list[np.ndarray],
        surface_param: SurfaceParam,
        options: TessellationOptions,
    ) -> PartMesh | None:
        try:
            uv = surface_param.inverse(contour_pts)
            uv_holes = [surface_param.inverse(h) for h in hole_pts]
        except Exception as exc:                      # inversion is best-effort
            logger.debug("UV inversion failed for {}: {}", part_id, exc)
            return None

        cleaned = _clean_polygon(uv, uv_holes)
        if cleaned is None:
            logger.debug("Unrepairable UV polygon for {}", part_id)
            return None
        ext, ints = cleaned

        cut = _earcut(ext, ints)
        if cut is None:
            logger.debug("Earcut produced no triangles for {}", part_id)
            return None
        verts_uv, tris = cut

        # metric subdivision for curved surfaces
        max_edge = surface_param.max_edge_m(options.tolerance_m)
        if max_edge is not None:
            su, sv = surface_param.uv_scale()
            scaled = np.column_stack([verts_uv[:, 0] * su, verts_uv[:, 1] * sv,
                                      np.zeros(len(verts_uv))])
            scaled, tris = trimesh.remesh.subdivide_to_size(
                scaled, tris, max_edge=max_edge, max_iter=8)
            verts_uv = np.column_stack([scaled[:, 0] / su, scaled[:, 1] / sv])
            tris = np.asarray(tris, dtype=np.int64)

        verts3 = surface_param.evaluate(verts_uv)
        if not np.all(np.isfinite(verts3)):
            logger.debug("Non-finite vertices for {}", part_id)
            return None
        tris = _drop_degenerate(verts3, tris)
        if len(tris) == 0:
            return None
        normals = surface_param.normals(verts_uv)
        return PartMesh(part_id=part_id, name=name, kind=kind,
                        vertices=verts3, triangles=tris, normals=normals)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_uv_tessellator.py -v`
Expected: PASS. If the cylinder area check is off by > 2 %, verify that `subdivide_to_size` ran (the `max_edge` for r=2, tol=0.05 is `sqrt(8*0.05*2) ≈ 0.89 m`) and that UV verts were unscaled before `evaluate`.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/uv_tessellator.py tests/test_render_uv_tessellator.py
git commit -m "feat(render): UV-domain tessellator — shapely repair, earcut, metric subdivision"
```

---

### Task 6: Section profiles — `IrSection` → 2D polygon

**Files:**
- Create: `ocx_model_validator/render/sections_2d.py`
- Test: `tests/test_render_sections_2d.py`

Profile convention: columns `(s, w)`; `w = 0` at the plate/trace, web extends to `+w`. Polygons are closed implicitly (no repeated last point) and must be simple (non-self-intersecting).

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_sections_2d.py`:

```python
"""Tests for section → 2D profile polygons."""
import numpy as np
import pytest

from ocx_model_validator.model.ir.base import Quantity
from ocx_model_validator.model.ir.sections import (
    IrAngleSection,
    IrBulbFlatSection,
    IrFlatBarSection,
    IrGenericSection,
    IrISection,
    IrLSection,
    IrRoundSection,
    IrTSection,
    IrTubeSection,
    IrUSection,
)
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.sections_2d import fallback_polygon, section_polygon

LR = LengthResolver({})


def q(v):
    return Quantity(v, "Um")


def polygon_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


class TestProfiles:
    def test_flat_bar(self):
        p = section_polygon(IrFlatBarSection(id="s", height=q(0.2), width=q(0.01)), LR)
        assert p is not None
        assert polygon_area(p) == pytest.approx(0.2 * 0.01)
        assert p[:, 1].min() == pytest.approx(0.0)      # starts at the plate
        assert p[:, 1].max() == pytest.approx(0.2)

    def test_t_section_area(self):
        p = section_polygon(IrTSection(id="s", height=q(0.3), width=q(0.1),
                                       web_thickness=q(0.01),
                                       flange_thickness=q(0.02)), LR)
        # web (h - tf) * tw + flange w * tf
        expected = (0.3 - 0.02) * 0.01 + 0.1 * 0.02
        assert polygon_area(p) == pytest.approx(expected)

    def test_l_section_is_asymmetric(self):
        p = section_polygon(IrLSection(id="s", height=q(0.2), width=q(0.08),
                                       web_thickness=q(0.01),
                                       flange_thickness=q(0.012)), LR)
        assert polygon_area(p) == pytest.approx((0.2 - 0.012) * 0.01 + 0.08 * 0.012)
        # flange extends to one side only
        assert p[:, 0].max() > 0.05 and p[:, 0].min() >= -0.01

    def test_bulb_flat_has_bump(self):
        p = section_polygon(IrBulbFlatSection(id="s", height=q(0.24),
                                              web_thickness=q(0.011),
                                              flange_width=q(0.035)), LR)
        assert p is not None
        assert p[:, 0].max() == pytest.approx(0.035 - 0.011 / 2.0)
        assert p[:, 1].max() == pytest.approx(0.24)

    def test_angle(self):
        p = section_polygon(IrAngleSection(id="s", leg_length=q(0.1),
                                           leg_thickness=q(0.01)), LR)
        assert polygon_area(p) == pytest.approx(0.1 * 0.01 + (0.1 - 0.01) * 0.01)

    def test_tube_is_polygonized_circle(self):
        p = section_polygon(IrTubeSection(id="s", diameter=q(0.2)), LR)
        assert len(p) >= 16
        radii = np.linalg.norm(p - [0.0, 0.1], axis=1)   # centred at (0, d/2)
        np.testing.assert_allclose(radii, 0.1, atol=1e-9)

    def test_round(self):
        p = section_polygon(IrRoundSection(id="s", diameter=q(0.1)), LR)
        assert len(p) >= 16

    def test_u_and_i(self):
        u = section_polygon(IrUSection(id="s", height=q(0.2), width=q(0.08),
                                       web_thickness=q(0.008),
                                       flange_thickness=q(0.012)), LR)
        i = section_polygon(IrISection(id="s", height=q(0.2), width=q(0.1),
                                       web_thickness=q(0.008),
                                       flange_thickness=q(0.012)), LR)
        assert u is not None and i is not None
        assert polygon_area(i) == pytest.approx(
            2 * 0.1 * 0.012 + (0.2 - 2 * 0.012) * 0.008)

    def test_missing_dims_returns_none(self):
        assert section_polygon(IrFlatBarSection(id="s"), LR) is None

    def test_generic_returns_none(self):
        assert section_polygon(IrGenericSection(id="s"), LR) is None

    def test_fallback(self):
        p = fallback_polygon()
        assert polygon_area(p) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_sections_2d.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/sections_2d.py`:

```python
"""Turn IrSection catalogue entries into closed 2D profile polygons.

Convention: columns (s, w).  s = lateral axis, w = web axis with w=0 on the
plate/trace and +w pointing away from it.  All polygons are simple, CCW,
without a repeated last point.  Returns None when required dimensions are
missing; callers fall back to ``fallback_polygon()``.
"""
from __future__ import annotations

import numpy as np

from ocx_model_validator.model.ir.sections import (
    IrAngleSection,
    IrBulbFlatSection,
    IrFlatBarSection,
    IrISection,
    IrLSection,
    IrLSectionOvershootFlange,
    IrLSectionOvershootWeb,
    IrRoundSection,
    IrSection,
    IrSquareSection,
    IrTSection,
    IrTubeSection,
    IrUSection,
    IrZSection,
)
from ocx_model_validator.render.length import LengthResolver

_CIRCLE_SEGS = 16


def _rect(s0, s1, w0, w1) -> np.ndarray:
    return np.array([[s0, w0], [s1, w0], [s1, w1], [s0, w1]], dtype=float)


def _circle(center_s, center_w, r) -> np.ndarray:
    t = np.linspace(0.0, 2 * np.pi, _CIRCLE_SEGS, endpoint=False)
    return np.column_stack([center_s + r * np.cos(t), center_w + r * np.sin(t)])


def fallback_polygon(height: float = 0.1, thickness: float = 0.01) -> np.ndarray:
    """Flat-bar proxy used when a section is unknown or missing dimensions."""
    return _rect(-thickness / 2.0, thickness / 2.0, 0.0, height)


def section_polygon(section: IrSection | None,
                    length: LengthResolver) -> np.ndarray | None:
    """Dispatch to the profile builder for this section type, or None."""
    if section is None:
        return None
    q = length.qty

    if isinstance(section, IrFlatBarSection):
        h, w = q(section.height), q(section.width)
        if h is None or w is None:
            return None
        return _rect(-w / 2.0, w / 2.0, 0.0, h)

    if isinstance(section, IrTSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf], [w / 2, h - tf],
            [w / 2, h], [-w / 2, h], [-w / 2, h - tf], [-tw / 2, h - tf],
        ])

    if isinstance(section, (IrLSection, IrLSectionOvershootFlange,
                            IrLSectionOvershootWeb)):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf],
            [w - tw / 2, h - tf], [w - tw / 2, h], [-tw / 2, h],
        ])

    if isinstance(section, IrBulbFlatSection):
        h, tw = q(section.height), q(section.web_thickness)
        bw = q(section.flange_width)
        if None in (h, tw, bw):
            return None
        bulb_h = min(0.2 * h, h)               # bulb occupies top ~20 % of web
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - bulb_h],
            [bw - tw / 2, h - 0.4 * bulb_h], [bw - tw / 2, h],
            [-tw / 2, h],
        ])

    if isinstance(section, IrAngleSection):
        ll, lt = q(section.leg_length), q(section.leg_thickness)
        if None in (ll, lt):
            return None
        return np.array([
            [-lt / 2, 0], [lt / 2, 0], [lt / 2, ll - lt],
            [ll - lt / 2, ll - lt], [ll - lt / 2, ll], [-lt / 2, ll],
        ])

    if isinstance(section, IrUSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        # channel opening sideways: web vertical, two flanges to +s
        return np.array([
            [-tw / 2, 0], [w - tw / 2, 0], [w - tw / 2, tf], [tw / 2, tf],
            [tw / 2, h - tf], [w - tw / 2, h - tf], [w - tw / 2, h],
            [-tw / 2, h],
        ])

    if isinstance(section, IrISection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-w / 2, 0], [w / 2, 0], [w / 2, tf], [tw / 2, tf],
            [tw / 2, h - tf], [w / 2, h - tf], [w / 2, h], [-w / 2, h],
            [-w / 2, h - tf], [-tw / 2, h - tf], [-tw / 2, tf], [-w / 2, tf],
        ])

    if isinstance(section, IrZSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-w + tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf],
            [w - tw / 2, h - tf], [w - tw / 2, h], [-tw / 2, h],
            [-tw / 2, tf], [-w + tw / 2, tf],
        ])

    if isinstance(section, IrTubeSection):
        d = q(section.diameter)
        if d is None:
            return None
        return _circle(0.0, d / 2.0, d / 2.0)   # tangent to the trace plane

    if isinstance(section, IrRoundSection):
        d = q(section.diameter)
        if d is None:
            return None
        return _circle(0.0, d / 2.0, d / 2.0)

    if isinstance(section, IrSquareSection):
        h = q(section.height)
        if h is None:
            return None
        return _rect(-h / 2.0, h / 2.0, 0.0, h)

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_sections_2d.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/sections_2d.py tests/test_render_sections_2d.py
git commit -m "feat(render): 2D profile polygons for the section catalogue"
```

---

### Task 7: Sweep — stiffener/pillar profiles along trace curves

**Files:**
- Create: `ocx_model_validator/render/sweep.py`
- Test: `tests/test_render_sweep.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_sweep.py`:

```python
"""Tests for the section sweep along trace polylines."""
import numpy as np

from ocx_model_validator.model.ir.base import IrVector3D
from ocx_model_validator.model.ir.geometry import IrPoint3D
from ocx_model_validator.model.ir.structural import IrInclination
from ocx_model_validator.render.sweep import resolve_web_dirs, sweep_profile

SQUARE = np.array([[-0.05, 0.0], [0.05, 0.0], [0.05, 0.1], [-0.05, 0.1]])


def straight_trace(n=5, length=4.0):
    t = np.linspace(0.0, length, n)
    return np.column_stack([t, np.zeros(n), np.zeros(n)])


class TestResolveWebDirs:
    def test_inclination_hint_is_used_and_orthogonalized(self):
        pts = straight_trace()
        incl = [IrInclination(web_direction=IrVector3D(0.1, 0.0, 1.0))]
        dirs = resolve_web_dirs(pts, incl)
        assert dirs.shape == pts.shape
        # orthogonal to the +x tangent and normalized
        np.testing.assert_allclose(dirs @ np.array([1.0, 0, 0]), 0.0, atol=1e-9)
        np.testing.assert_allclose(np.linalg.norm(dirs, axis=1), 1.0, atol=1e-9)
        # dominated by +z after orthogonalization
        assert np.all(dirs[:, 2] > 0.9)

    def test_no_inclination_transport_has_no_flips(self):
        # quarter-circle trace in the XY plane
        ang = np.linspace(0.0, np.pi / 2.0, 20)
        pts = np.column_stack([np.cos(ang), np.sin(ang), np.zeros(20)])
        dirs = resolve_web_dirs(pts, [])
        dots = np.einsum("ij,ij->i", dirs[:-1], dirs[1:])
        assert np.all(dots > 0.99)          # consecutive frames nearly parallel


class TestSweepProfile:
    def test_vertex_and_face_counts(self):
        pts = straight_trace(n=5)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE)
        m, n = len(SQUARE), len(pts)
        assert len(verts) == m * n
        # sides: 2 tris per profile edge per span; caps: earcut of a quad = 2 tris each
        assert len(faces) == 2 * m * (n - 1) + 2 * 2

    def test_watertight_straight_sweep(self):
        import trimesh
        pts = straight_trace(n=3)
        dirs = resolve_web_dirs(pts, [IrInclination(web_direction=IrVector3D(0, 0, 1))])
        verts, faces = sweep_profile(pts, dirs, SQUARE)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
        assert mesh.is_watertight
        # abs(): winding sign is not guaranteed, only closedness
        assert np.isclose(abs(mesh.volume), 4.0 * 0.1 * 0.1, rtol=1e-6)

    def test_too_short_trace_returns_none(self):
        assert sweep_profile(np.zeros((1, 3)), np.zeros((1, 3)), SQUARE) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_sweep.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/sweep.py`:

```python
"""Sweep a 2D section profile along a 3D trace polyline.

Frames per trace point come from (in priority order):
1. ``IrInclination`` web-direction hints (nearest hint by position, or the
   single hint applied everywhere),
2. projection-transport of an initial perpendicular (rotation-minimizing
   approximation) — never a Frenet frame.
"""
from __future__ import annotations

import mapbox_earcut
import numpy as np

from ocx_model_validator.model.ir.structural import IrInclination
from ocx_model_validator.render.curves import _any_perp, _unit


def _tangents(pts: np.ndarray) -> np.ndarray:
    t = np.gradient(pts, axis=0)
    n = np.linalg.norm(t, axis=1, keepdims=True)
    n[n < 1e-15] = 1.0
    return t / n


def _orthogonalize(web: np.ndarray, tangent: np.ndarray) -> np.ndarray | None:
    w = web - (web @ tangent) * tangent
    nn = np.linalg.norm(w)
    if nn < 1e-9:
        return None
    return w / nn


def resolve_web_dirs(pts: np.ndarray,
                     inclinations: list[IrInclination],
                     incl_positions_m: np.ndarray | None = None) -> np.ndarray:
    """Per-point web directions, orthogonal to the trace tangent, unit length.

    ``incl_positions_m`` — optional (K,3) metre positions matching the
    inclination hints; when given, each trace point uses the nearest hint.
    """
    tangents = _tangents(pts)
    hints = [np.array([i.web_direction.x, i.web_direction.y, i.web_direction.z])
             for i in inclinations if i.web_direction is not None]

    dirs = np.empty_like(pts)
    prev: np.ndarray | None = None
    for i, t in enumerate(tangents):
        w = None
        if hints:
            if incl_positions_m is not None and len(incl_positions_m) == len(hints):
                k = int(np.argmin(np.linalg.norm(incl_positions_m - pts[i], axis=1)))
                w = _orthogonalize(hints[k], t)
            else:
                w = _orthogonalize(hints[0], t)
        if w is None and prev is not None:            # transport previous frame
            w = _orthogonalize(prev, t)
        if w is None:                                 # bootstrap
            w = _unit(np.cross(t, _any_perp(t)))
        dirs[i] = w
        prev = w
    return dirs


def sweep_profile(pts: np.ndarray, web_dirs: np.ndarray,
                  profile: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    """Sweep ``profile`` (M,2) along ``pts`` (N,3); returns (verts, faces).

    Ring vertex = p + s*side + w*web, side = tangent x web.  Sides are
    quads split into triangles; both ends are capped (earcut of the profile).
    """
    n, m = len(pts), len(profile)
    if n < 2 or m < 3:
        return None
    tangents = _tangents(pts)
    rings = []
    for i in range(n):
        w = web_dirs[i]
        side = _unit(np.cross(tangents[i], w))
        rings.append(pts[i]
                     + np.outer(profile[:, 0], side)
                     + np.outer(profile[:, 1], w))
    verts = np.vstack(rings)

    faces: list[list[int]] = []
    for i in range(n - 1):
        a, b = i * m, (i + 1) * m
        for j in range(m):
            k = (j + 1) % m
            faces.append([a + j, b + j, b + k])
            faces.append([a + j, b + k, a + k])

    cap = mapbox_earcut.triangulate_float64(
        profile.astype(np.float64), np.array([m], dtype=np.uint32))
    cap = np.asarray(cap, dtype=np.int64).reshape(-1, 3)
    start = cap[:, ::-1]                     # reversed winding at the start
    end = cap + (n - 1) * m
    faces_arr = np.vstack([np.array(faces, dtype=np.int64), start, end])
    return verts, faces_arr
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_sweep.py -v`
Expected: PASS. If `test_watertight_straight_sweep` fails, check cap winding (`cap[:, ::-1]` for the start cap) and that side/web axes form a right-handed frame with the tangent.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/sweep.py tests/test_render_sweep.py
git commit -m "feat(render): profile sweep along trace with inclination-hint frames"
```

---

### Task 8: GLB writer

**Files:**
- Create: `ocx_model_validator/render/gltf_writer.py`
- Test: `tests/test_render_gltf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_gltf.py`:

```python
"""Tests for GLB export — written file must reload with named parts."""
import numpy as np
import trimesh

from ocx_model_validator.render.gltf_writer import write_glb
from ocx_model_validator.render.mesh import PartMesh


def square_mesh(part_id, kind, panel_id=None):
    extras = {"id": part_id, "kind": kind}
    if panel_id:
        extras["panel_id"] = panel_id
    return PartMesh(
        part_id=part_id, name=f"Name {part_id}", kind=kind,
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        triangles=np.array([[0, 1, 2], [0, 2, 3]]),
        normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        extras=extras,
    )


class TestWriteGlb:
    def test_roundtrip(self, tmp_path):
        meshes = [square_mesh("pl1", "plate", panel_id="pan1"),
                  square_mesh("st1", "stiffener", panel_id="pan1"),
                  square_mesh("pi1", "pillar")]
        out = tmp_path / "model.glb"
        write_glb(meshes, out)
        assert out.exists() and out.stat().st_size > 0

        scene = trimesh.load(str(out))
        assert isinstance(scene, trimesh.Scene)
        node_names = set(scene.graph.nodes)
        assert "plate_pl1" in node_names
        assert "stiffener_st1" in node_names
        assert "pillar_pi1" in node_names
        assert "Panel_pan1" in node_names          # grouping node
        # geometry survived
        total_tris = sum(len(g.faces) for g in scene.geometry.values())
        assert total_tris == 6
        # vertices are finite
        for g in scene.geometry.values():
            assert np.all(np.isfinite(g.vertices))

    def test_distinct_part_colors(self, tmp_path):
        meshes = [square_mesh("pl1", "plate"), square_mesh("pl2", "plate")]
        out = tmp_path / "two.glb"
        write_glb(meshes, out)
        scene = trimesh.load(str(out))
        colors = set()
        for g in scene.geometry.values():
            mat = g.visual.material
            colors.add(tuple(np.asarray(mat.baseColorFactor).round(4)))
        assert len(colors) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_gltf.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/gltf_writer.py`:

```python
"""Assemble PartMeshes into a trimesh Scene and export binary glTF (GLB).

Node naming: ``<kind>_<part_id>`` per part; parts with a ``panel_id`` extra
are parented under a ``Panel_<panel_id>`` grouping node.  Part extras are
attached as mesh metadata (exported into glTF mesh ``extras``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

from ocx_model_validator.render.mesh import PartMesh


def _material(color: tuple[int, int, int]) -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[color[0] / 255.0, color[1] / 255.0, color[2] / 255.0, 1.0],
        metallicFactor=0.1,
        roughnessFactor=0.8,
        doubleSided=True,
    )


def write_glb(meshes: list[PartMesh], destination: Path) -> Path:
    """Write all parts to a single .glb file; returns the destination path."""
    scene = trimesh.Scene()
    groups: set[str] = set()

    for pm in meshes:
        tm = trimesh.Trimesh(
            vertices=pm.vertices,
            faces=pm.triangles,
            vertex_normals=pm.normals,
            process=False,
        )
        tm.visual = trimesh.visual.TextureVisuals(material=_material(pm.color))
        tm.metadata.update(pm.extras)

        parent = None
        panel_id = pm.extras.get("panel_id")
        if panel_id:
            parent = f"Panel_{panel_id}"
            if parent not in groups:
                scene.graph.update(frame_to=parent,
                                   frame_from=scene.graph.base_frame,
                                   matrix=np.eye(4))
                groups.add(parent)

        scene.add_geometry(
            tm,
            node_name=f"{pm.kind}_{pm.part_id}",
            geom_name=pm.name or pm.part_id,
            parent_node_name=parent or scene.graph.base_frame,
        )

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(destination))            # format inferred from .glb suffix
    return destination
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_gltf.py -v`
Expected: PASS. If `baseColorFactor` is missing after reload, your trimesh version may normalize materials — assert on `g.visual.material.baseColorFactor` with `np.asarray(...)` as in the test; if trimesh returns a `SimpleMaterial`, upgrade the assertion to read `mat.diffuse` instead and note it in the test.

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/gltf_writer.py tests/test_render_gltf.py
git commit -m "feat(render): GLB writer with named nodes, panel grouping, PBR colors"
```

---

### Task 9: Orchestrator — `render_model`

**Files:**
- Modify: `ocx_model_validator/render/__init__.py` (replace placeholder)
- Test: `tests/test_render_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_model.py`:

```python
"""End-to-end render_model test on a synthetic IrVessel."""
import numpy as np

from ocx_model_validator.model.ir.base import IrVector3D, ParentKind, ParentRef, Quantity, Ref
from ocx_model_validator.model.ir.geometry import (
    IrLine3D,
    IrPlane3D,
    IrPoint3D,
    IrPolyLine3D,
    IrUnboundedGeometry,
)
from ocx_model_validator.model.ir.sections import IrFlatBarSection
from ocx_model_validator.model.ir.structural import (
    IrPanel,
    IrPillar,
    IrPlate,
    IrStiffener,
    IrVessel,
)
from ocx_model_validator.render import render_model
from ocx_model_validator.render.backend import TessellationOptions


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def make_vessel():
    panel = IrPanel(
        id="pan1", name="Deck",
        unbounded_geometry=IrUnboundedGeometry(
            surface=IrPlane3D(id="s1", point_on_surface=pt(0, 0, 0),
                              normal=IrVector3D(0, 0, 1))),
        plate_ids=["pl1"], stiffener_ids=["st1"],
    )
    plate = IrPlate(
        id="pl1", parent_ref=ParentRef(ParentKind.PANEL, "pan1"), name="Plate 1",
        outer_contour=IrPolyLine3D(None, vertices=[
            pt(0, 0, 0), pt(4, 0, 0), pt(4, 2, 0), pt(0, 2, 0), pt(0, 0, 0)]),
    )
    stiffener = IrStiffener(
        id="st1", parent_ref=ParentRef(ParentKind.PANEL, "pan1"), name="Stiff 1",
        section_ref=Ref("fb100"),
        trace=IrLine3D(None, start=pt(0, 1, 0), end=pt(4, 1, 0)),
    )
    pillar_no_trace = IrPillar(
        id="pi1", parent_ref=ParentRef(ParentKind.VESSEL, "v"), name="Pillar 1",
    )
    vessel = IrVessel(id="v", name="Test vessel")
    vessel.panels["pan1"] = panel
    vessel.plates["pl1"] = plate
    vessel.stiffeners["st1"] = stiffener
    vessel.pillars["pi1"] = pillar_no_trace
    vessel.sections["fb100"] = IrFlatBarSection(
        id="fb100", height=Quantity(0.1, "Um"), width=Quantity(0.01, "Um"))
    return vessel


class TestRenderModel:
    def test_renders_plate_and_stiffener_skips_bad_pillar(self):
        result = render_model(make_vessel(), TessellationOptions())
        kinds = {m.kind for m in result.meshes}
        assert kinds == {"plate", "stiffener"}
        assert result.rendered_count == 2
        assert result.skipped == {"pi1": "no trace"}

    def test_extras_carry_identity_and_grouping(self):
        result = render_model(make_vessel())
        plate = next(m for m in result.meshes if m.kind == "plate")
        assert plate.extras["id"] == "pl1"
        assert plate.extras["panel_id"] == "pan1"
        stiff = next(m for m in result.meshes if m.kind == "stiffener")
        assert stiff.extras["panel_id"] == "pan1"

    def test_all_vertices_finite_and_in_metres(self):
        result = render_model(make_vessel())
        for m in result.meshes:
            assert np.all(np.isfinite(m.vertices))
        plate = next(m for m in result.meshes if m.kind == "plate")
        assert plate.vertices[:, 0].max() <= 4.0 + 1e-9    # metres, not mm

    def test_plate_without_panel_surface_is_skipped(self):
        vessel = make_vessel()
        vessel.panels["pan1"].unbounded_geometry = None
        result = render_model(vessel)
        assert result.skipped["pl1"] == "no resolvable panel surface"

    def test_unknown_section_falls_back_to_proxy(self):
        vessel = make_vessel()
        del vessel.sections["fb100"]          # dangling section ref
        result = render_model(vessel)
        assert any(m.kind == "stiffener" for m in result.meshes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_model'`

- [ ] **Step 3: Write the implementation**

Replace the contents of `ocx_model_validator/render/__init__.py` with:

```python
"""Tessellated 3D renderer — public API.

``render_model(vessel, options)`` tessellates all renderable parts of an
``IrVessel`` into ``PartMesh`` objects.  Single-part failures are recorded
in ``RenderResult.skipped`` and never abort the render.
"""
from __future__ import annotations

import numpy as np
from loguru import logger

from ocx_model_validator.model.ir.base import ParentKind
from ocx_model_validator.model.ir.structural import IrPanel, IrVessel
from ocx_model_validator.render.backend import (
    ITessellator,
    RenderResult,
    TessellationOptions,
)
from ocx_model_validator.render.curves import sample_contour, sample_curve
from ocx_model_validator.render.length import LengthResolver
from ocx_model_validator.render.mesh import PartMesh
from ocx_model_validator.render.sections_2d import fallback_polygon, section_polygon
from ocx_model_validator.render.surfaces import SurfaceParam, make_param
from ocx_model_validator.render.sweep import resolve_web_dirs, sweep_profile
from ocx_model_validator.render.uv_tessellator import UvTessellator

__all__ = ["render_model", "RenderResult", "TessellationOptions", "PartMesh"]


def _resolve_panel_surface(panel: IrPanel, vessel: IrVessel):
    ug = panel.unbounded_geometry
    if ug is None:
        return None
    if ug.surface is not None:
        return ug.surface
    if ug.surface_ref:
        s = vessel.surfaces.get(ug.surface_ref)
        if s is not None and s.geometry is not None:
            return s.geometry
        for coll in vessel.surface_collections.values():
            for member in coll.surfaces:
                if member.id == ug.surface_ref and member.geometry is not None:
                    return member.geometry
        return None
    if ug.grid_ref:
        rp = vessel.ref_planes.get(ug.grid_ref)
        if rp is not None:
            return rp.reference_plane
    return None


def _tessellate_plates(vessel: IrVessel, params: dict[str, SurfaceParam | None],
                       tess: ITessellator, length: LengthResolver,
                       options: TessellationOptions, result: RenderResult) -> None:
    for plate in vessel.plates.values():
        panel_id = (plate.parent_ref.id
                    if plate.parent_ref.kind == ParentKind.PANEL else None)
        param = params.get(panel_id) if panel_id else None
        if param is None:
            result.skipped[plate.id] = "no resolvable panel surface"
            continue
        if plate.outer_contour is None:
            result.skipped[plate.id] = "no outer contour"
            continue
        contour = sample_contour(plate.outer_contour, length,
                                 options.tolerance_m, options.snap_tolerance_m)
        if contour is None:
            result.skipped[plate.id] = "contour unsampleable or open"
            continue
        holes = []
        for c in plate.cut_by_contours:
            h = sample_contour(c, length, options.tolerance_m,
                               options.snap_tolerance_m)
            if h is not None:
                holes.append(h)
        pm = tess.tessellate_trimmed_surface(
            plate.id, plate.name or plate.id, "plate", contour, holes,
            param, options)
        if pm is None:
            result.skipped[plate.id] = "triangulation failed"
            continue
        pm.extras.update({"id": plate.id, "guid": plate.guidref,
                          "kind": "plate", "functionType": plate.function_type,
                          "panel_id": panel_id})
        result.meshes.append(pm)


def _sweep_part(part, kind: str, vessel: IrVessel, length: LengthResolver,
                options: TessellationOptions, result: RenderResult) -> None:
    if part.trace is None:
        result.skipped[part.id] = "no trace"
        return
    pts = sample_curve(part.trace, length, options.tolerance_m)
    if pts is None or len(pts) < 2:
        result.skipped[part.id] = "trace unsampleable"
        return

    section = None
    if part.section_ref is not None:
        section = vessel.sections.get(part.section_ref.local_ref)
    profile = section_polygon(section, length)
    if profile is None:
        logger.debug("{} {}: no usable section profile, using flat-bar proxy",
                     kind, part.id)
        profile = fallback_polygon()

    hints = [i for i in part.inclinations if i.web_direction is not None]
    positions = None
    if hints and all(i.position is not None for i in hints):
        positions = np.array([length.point(i.position) for i in hints])
    web = resolve_web_dirs(pts, part.inclinations, positions)

    out = sweep_profile(pts, web, profile)
    if out is None:
        result.skipped[part.id] = "sweep failed"
        return
    verts, faces = out
    panel_id = (part.parent_ref.id
                if part.parent_ref.kind == ParentKind.PANEL else None)
    pm = PartMesh(part_id=part.id, name=part.name or part.id, kind=kind,
                  vertices=verts, triangles=faces,
                  extras={"id": part.id, "guid": part.guidref, "kind": kind,
                          "functionType": part.function_type,
                          "panel_id": panel_id})
    result.meshes.append(pm)


def render_model(vessel: IrVessel,
                 options: TessellationOptions | None = None) -> RenderResult:
    """Tessellate all renderable parts of ``vessel``; never raises per-part."""
    options = options or TessellationOptions()
    length = LengthResolver(vessel.unit_registry)
    tess = UvTessellator()
    result = RenderResult()

    params: dict[str, SurfaceParam | None] = {}
    for pid, panel in vessel.panels.items():
        surf = _resolve_panel_surface(panel, vessel)
        params[pid] = (make_param(surf, length, options.tolerance_m)
                       if surf is not None else None)

    _tessellate_plates(vessel, params, tess, length, options, result)
    for stiffener in vessel.stiffeners.values():
        _sweep_part(stiffener, "stiffener", vessel, length, options, result)
    for pillar in vessel.pillars.values():
        _sweep_part(pillar, "pillar", vessel, length, options, result)

    logger.info("Render: {} parts tessellated, {} skipped",
                result.rendered_count, result.skipped_count)
    if result.skipped:
        for part_id, reason in result.skipped.items():
            logger.debug("Skipped {}: {}", part_id, reason)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_model.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`
Expected: PASS — no regressions in existing tests.

- [ ] **Step 6: Commit**

```bash
git add ocx_model_validator/render/__init__.py tests/test_render_model.py
git commit -m "feat(render): render_model orchestration with per-part skip accounting"
```

---

### Task 10: Self-contained HTML viewer

**Files:**
- Create: `ocx_model_validator/render/html_viewer.py`
- Test: `tests/test_render_html.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_html.py`:

```python
"""Tests for the self-contained HTML viewer writer."""
import base64

from ocx_model_validator.render.html_viewer import write_html


class TestWriteHtml:
    def test_writes_self_contained_page(self, tmp_path):
        glb = tmp_path / "boat.glb"
        payload = b"glTF-fake-binary-content"
        glb.write_bytes(payload)

        out = write_html(glb)
        assert out == tmp_path / "boat.html"
        html = out.read_text(encoding="utf-8")
        assert "<title>boat</title>" in html
        assert "importmap" in html
        assert "three@0.160.0" in html                     # pinned CDN version
        assert base64.b64encode(payload).decode() in html  # GLB embedded
        assert "__GLB_B64__" not in html                   # placeholder replaced
        assert "__TITLE__" not in html

    def test_explicit_destination(self, tmp_path):
        glb = tmp_path / "boat.glb"
        glb.write_bytes(b"x")
        out = write_html(glb, destination=tmp_path / "custom.html")
        assert out.name == "custom.html" and out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_html.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Write the implementation**

Create `ocx_model_validator/render/html_viewer.py`:

```python
"""Write a self-contained three.js HTML viewer next to a GLB file.

The GLB is embedded base64 so the page works when opened via file:// with no
server.  three.js is loaded from a pinned CDN version via an import map.
Placeholders are replaced with str.replace (not str.format) so the template
can contain CSS/JS braces freely.
"""
from __future__ import annotations

import base64
from pathlib import Path

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;font-family:system-ui,sans-serif}
  #tree{position:absolute;top:0;left:0;bottom:0;width:280px;overflow:auto;
        background:#1e1e1ecc;color:#ddd;font-size:12px;padding:8px;box-sizing:border-box}
  #tree div{cursor:pointer;padding:1px 4px;white-space:nowrap}
  #tree div:hover{background:#444}
  #tree div.sel{background:#2a6}
  #info{position:absolute;right:8px;top:8px;background:#1e1e1ecc;color:#ddd;
        font-size:12px;padding:8px;max-width:320px;white-space:pre-wrap}
</style>
<script type="importmap">
{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js",
"three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}
</script>
</head>
<body>
<div id="tree"></div><div id="info"></div>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const GLB_B64 = "__GLB_B64__";
const bin = Uint8Array.from(atob(GLB_B64), c => c.charCodeAt(0)).buffer;

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x202830);
const camera = new THREE.PerspectiveCamera(50, innerWidth/innerHeight, 0.01, 1e6);
const controls = new OrbitControls(camera, renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.2));
const dir = new THREE.DirectionalLight(0xffffff, 1.5);
dir.position.set(1, 2, 3);
scene.add(dir);

const tree = document.getElementById('tree');
const info = document.getElementById('info');
let selected = null;

new GLTFLoader().parse(bin, '', (gltf) => {
  scene.add(gltf.scene);
  const box = new THREE.Box3().setFromObject(gltf.scene);
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length() || 10;
  camera.position.copy(c).add(new THREE.Vector3(size*0.6, size*0.4, size*0.6));
  controls.target.copy(c);
  gltf.scene.traverse(o => {
    if (!o.isMesh) return;
    const row = document.createElement('div');
    row.textContent = o.name || '(unnamed)';
    row.onclick = () => select(o, row);
    tree.appendChild(row);
  });
}, (err) => { info.textContent = 'Failed to load model: ' + err; });

function select(obj, row) {
  if (selected) {
    if (selected.obj.material.emissive) selected.obj.material.emissive.setHex(0x000000);
    selected.row.classList.remove('sel');
  }
  obj.material = obj.material.clone();
  if (obj.material.emissive) obj.material.emissive.setHex(0x22aa55);
  row.classList.add('sel');
  selected = {obj, row};
  info.textContent = obj.name + "\\n" + JSON.stringify(obj.userData, null, 1);
}

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
(function loop() { requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();
</script>
</body>
</html>
"""


def write_html(glb_path: Path, destination: Path | None = None) -> Path:
    """Write ``<glb stem>.html`` (or ``destination``) with the GLB embedded."""
    glb_path = Path(glb_path)
    destination = destination or glb_path.with_suffix(".html")
    b64 = base64.b64encode(glb_path.read_bytes()).decode("ascii")
    html = _TEMPLATE.replace("__TITLE__", glb_path.stem).replace("__GLB_B64__", b64)
    destination.write_text(html, encoding="utf-8")
    return destination
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_html.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ocx_model_validator/render/html_viewer.py tests/test_render_html.py
git commit -m "feat(render): self-contained three.js HTML viewer with embedded GLB"
```

---

### Task 11: CLI — `validator render`

**Files:**
- Modify: `ocx_model_validator/cli.py` (add command after the `validate` sub-app commands, before `entrypoint`)
- Test: `tests/test_render_cli.py`

Exit codes: 0 = rendered (skips allowed) · 1 = nothing renderable · 2 = cannot parse/build.
Note `_load_vessel` exits with code 1 on parse failure; the render command re-maps that to 2.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_cli.py`:

```python
"""CLI tests for `validator render`."""
from pathlib import Path

from typer.testing import CliRunner

from ocx_model_validator.cli import app

runner = CliRunner()

STUB = Path("tests/data/ocx_310_stubs/panel.3docx")


class TestRenderCommand:
    def test_unparseable_file_exits_2(self, tmp_path):
        bad = tmp_path / "bad.3docx"
        bad.write_text("this is not xml", encoding="utf-8")
        result = runner.invoke(app, ["render", str(bad)])
        assert result.exit_code == 2

    def test_model_without_renderable_geometry_exits_1(self):
        assert STUB.exists(), "panel stub fixture missing"
        result = runner.invoke(app, ["render", str(STUB)])
        assert result.exit_code == 1

    def test_synthetic_model_renders(self, tmp_path, monkeypatch):
        """Patch the load step to return a renderable vessel and check outputs."""
        import ocx_model_validator.cli as cli_mod
        from tests.test_render_model import make_vessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        glb = tmp_path / "out.glb"
        result = runner.invoke(
            app, ["render", str(dummy), "--destination", str(glb)])
        assert result.exit_code == 0, result.output
        assert glb.exists()
        assert glb.with_suffix(".html").exists()

    def test_no_html_flag(self, tmp_path, monkeypatch):
        import ocx_model_validator.cli as cli_mod
        from tests.test_render_model import make_vessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        glb = tmp_path / "out.glb"
        result = runner.invoke(
            app, ["render", str(dummy), "--destination", str(glb), "--no-html"])
        assert result.exit_code == 0, result.output
        assert glb.exists()
        assert not glb.with_suffix(".html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_cli.py -v`
Expected: FAIL — `render` is not a known command (usage error, exit code 2 from typer for *all* tests, including the ones expecting 0/1).

- [ ] **Step 3: Write the implementation**

In `ocx_model_validator/cli.py`, add after the `validate_schema_cmd` function (keep the lazy-import style used by the other commands):

```python
@app.command("render")
def render_cmd(
    model: Path = _MODEL_ARG,
    destination: Path | None = typer.Option(
        None, "--destination", "-d",
        help="Output .glb path (default: next to the model)."),
    tolerance_mm: float = typer.Option(
        50.0, "--tolerance",
        help="Linear deflection tolerance in millimetres."),
    no_html: bool = typer.Option(
        False, "--no-html", help="Skip writing the HTML viewer page."),
) -> None:
    """Tessellate the model into a GLB file plus a self-contained HTML viewer.

    Exit codes: 0 rendered (parts may be skipped), 1 nothing renderable,
    2 cannot parse/build the model.
    """
    from ocx_model_validator.render import TessellationOptions, render_model
    from ocx_model_validator.render.gltf_writer import write_glb
    from ocx_model_validator.render.html_viewer import write_html

    try:
        vessel = _load_vessel(model)
    except typer.Exit as exc:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_render_cli.py -v`
Expected: PASS. If `test_model_without_renderable_geometry_exits_1` fails because the stub actually produces no vessel at all (exit 2), inspect `tests/data/ocx_310_stubs/panel.3docx` — the test's purpose is the exit-1 path; if the stub cannot build a vessel, switch the fixture to `plate.3docx` or construct a vessel via monkeypatch with an empty `IrVessel(id="v")` instead and keep the exit-1 assertion.

- [ ] **Step 5: Smoke-test manually against a real model (if available)**

```bash
uv run validator render models/TR05/tr05_tc17_cadhu_demo.3docx --destination demo.glb
```

Expected: exit 0, `demo.glb` + `demo.html` written; opening `demo.html` in a browser shows the model with a part tree. (Skip if no real model is present; clean up `demo.glb`/`demo.html` afterwards.)

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run pytest
git add ocx_model_validator/cli.py tests/test_render_cli.py
git commit -m "feat(cli): validator render — GLB + HTML viewer output"
```

---

### Task 12: Integration test against real models + documentation

**Files:**
- Create: `tests/test_render_integration.py`
- Modify: `.github/copilot-instructions.md` (CLI section)
- Modify: `README.md` (usage section, if a usage section exists)

- [ ] **Step 1: Write the integration test (marked, skipped by default)**

Create `tests/test_render_integration.py`:

```python
"""Integration render test against real .3docx models in ./models/.

Runs only with `uv run pytest -m integration` (default addopts exclude it).
"""
from pathlib import Path

import numpy as np
import pytest
import trimesh

MODELS = sorted(Path("models").glob("**/*.3docx")) if Path("models").exists() else []

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not MODELS, reason="no .3docx models in ./models/")
@pytest.mark.parametrize("model_file", MODELS, ids=lambda p: p.name)
def test_render_real_model(model_file, tmp_path):
    from ocx_model_validator.cli import _load_vessel
    from ocx_model_validator.render import render_model
    from ocx_model_validator.render.gltf_writer import write_glb

    vessel = _load_vessel(model_file)
    result = render_model(vessel)
    assert result.rendered_count > 0, f"nothing rendered; skips: {result.skipped}"

    glb = tmp_path / (model_file.stem + ".glb")
    write_glb(result.meshes, glb)
    scene = trimesh.load(str(glb))
    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) == result.rendered_count
    for g in scene.geometry.values():
        assert np.all(np.isfinite(g.vertices))
        assert len(g.faces) > 0
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest -m integration tests/test_render_integration.py -v`
Expected: PASS for models present in `./models/` (or SKIP if none). Investigate any model where `rendered_count == 0` — the skip-reason dict in the assertion message tells you which pipeline stage rejected each part. Fix genuine pipeline bugs; models whose parts legitimately lack geometry are acceptable skips but must not fail the whole render.

- [ ] **Step 3: Update documentation**

In `.github/copilot-instructions.md`, in the `## CLI` code block after the `validator validate schema` line, add:

```bash
# Tessellate to GLB + self-contained three.js HTML viewer
# (exit 0 rendered / 1 nothing renderable / 2 cannot parse)
validator render model.3docx [--destination out.glb] [--tolerance MM] [--no-html]
```

In `README.md`, mirror the same command in the usage/CLI section if one exists (add a short "3D rendering" bullet: renders plates as trimmed shells and stiffeners/pillars as swept sections into a GLB; the `.html` file next to it opens in any browser).

- [ ] **Step 4: Final verification**

```bash
uv run ruff check ocx_model_validator tests
uv run pytest
```

Expected: lint clean, full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_render_integration.py .github/copilot-instructions.md README.md
git commit -m "test(render): integration render of real models; document validator render"
```

---

## Spec coverage checklist (self-review aid)

| Spec requirement | Task |
|---|---|
| `render/` package layout, `ITessellator`, `PartMesh`, options | 1 |
| Boundary sampling, composite stitching, gap snapping | 2 |
| Plane/cylinder/cone/sphere parametrization, seam unwrap, pole handling | 3 |
| Extruded + NURBS parametrization, Newton inversion | 4 |
| shapely repair, earcut, holes, curvature subdivision, lift + normals | 5 |
| Section catalogue → 2D profiles, flat-bar fallback | 6 |
| Sweep with `IrInclination` frames, no Frenet flips, watertight caps | 7 |
| GLB: named nodes, panel grouping, colors, extras, metres | 8 |
| Orchestration, surface resolution (inline/ref/grid), skip accounting | 9 |
| Self-contained HTML viewer (pinned CDN, base64 GLB, part tree, highlight) | 10 |
| CLI `validator render`, exit codes 0/1/2, `--tolerance` mm, `--no-html` | 11 |
| Integration test on real models, docs | 12 |




