# ocx-diagnose advice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-based findings (root cause, mesh-setting steps, OCX-source NURBS steps) to the `ocx-diagnose` HTML report and JSON.

**Architecture:** `probes.py` measures source-geometry facts (duplicate members, degenerate members, contour closure) from the render's `ChartDiag`/`PlateDiag`. `advice.py` holds a `Finding` dataclass and pure rule functions mapping plate/panel metrics + probe output to findings. `analyse.py` calls `advise_panel` once per panel; `report.py` renders the boxes and JSON.

**Tech Stack:** Python, numpy, scipy `cKDTree`, plotly (existing), pytest, loguru. Run everything with `uv run` from the repo root. Spec: `docs/superpowers/specs/2026-10-16-diagnose-advice-design.md`. Branch: `feat/ocx-diagnose` (already checked out).

Facts you need:
- `ChartDiag` (`ocx_geometry/diagnostics.py`): `n_members`, `members_used` (list[int]), `boundary_edges_before_stitch`, `boundary_edges_after_stitch`, `V` (n,3), `F` (m,3), `tri_member` (m,) member index per chart face (-1 unattributed). Member indices index `PlateDiag.candidates`.
- `PlateDiag.candidates` = list of `SurfaceParam` (`.evaluate(uv)`, `.inverse(pts)`); `PlateDiag.contour` = (k,3) ndarray or None.
- `checks._project_distance(member, pts)` returns distance from pts to the member surface (inf on failure).
- `PlateResult`/`PanelResult` live in `analyse.py`; tests build a model with `make_vessel()` from `tests/test_render_model.py`.
- Run diag tests: `uv run pytest -q tests/test_diag_probes.py tests/test_diag_advice.py tests/test_diag_report.py tests/test_diag_cli.py`.

## File structure
- Create `packages/ocx-diagnose/src/ocx_diagnose/probes.py` — source-geometry probes.
- Create `packages/ocx-diagnose/src/ocx_diagnose/advice.py` — `Finding`, rules, `advise_panel`.
- Modify `packages/ocx-diagnose/src/ocx_diagnose/analyse.py` — `findings` fields, call `advise_panel`.
- Modify `packages/ocx-diagnose/src/ocx_diagnose/report.py` — boxes, summary column, JSON.
- Create `tests/test_diag_probes.py`, `tests/test_diag_advice.py`; extend `tests/test_diag_report.py`.
- Modify `README.md` (diagnose section).

---

### Task 1: Probes

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/probes.py`
- Test: `tests/test_diag_probes.py`

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
from ocx_diagnose.probes import (
    contour_probe,
    degenerate_members,
    duplicate_members,
)
from ocx_geometry.diagnostics import ChartDiag
from ocx_geometry.surfaces import PlaneParam


def _grid_chart(offsets):
    """One 1x1 quad (2 faces) per member, member i lying in the plane z=offsets[i]."""
    V, F, tm = [], [], []
    for i, z in enumerate(offsets):
        b = len(V)
        V += [[0, 0, z], [1, 0, z], [1, 1, z], [0, 1, z]]
        F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
        tm += [i, i]
    return ChartDiag(n_members=len(offsets), members_used=list(range(len(offsets))),
                     V=np.array(V, float), F=np.array(F), tri_member=np.array(tm))


def _planes(offsets):
    return [PlaneParam(np.array([0.0, 0.0, z]), np.array([0.0, 0.0, 1.0])) for z in offsets]


def test_duplicate_members_found_for_coincident_planes():
    chart = _grid_chart([0.0, 0.0, 5.0])
    pairs = duplicate_members(chart, _planes([0.0, 0.0, 5.0]), eps_m=1e-3)
    assert [(a, b) for a, b, _ in pairs] == [(0, 1)]


def test_no_duplicates_for_separate_planes():
    chart = _grid_chart([0.0, 1.0, 5.0])
    assert duplicate_members(chart, _planes([0.0, 1.0, 5.0]), eps_m=1e-3) == []


def test_degenerate_members_by_area_and_missing_faces():
    chart = _grid_chart([0.0, 1.0])
    chart.V[4:8] = chart.V[4:8] * 0.001          # member 1 collapses to 1 mm
    chart.n_members = 3                          # member 2 has no faces at all
    assert degenerate_members(chart, min_area_m2=1e-4) == [1, 2]


def test_contour_probe_closed_open_and_touching():
    t = np.linspace(0, 2 * np.pi, 41)[:-1]
    ring = np.c_[np.cos(t), np.sin(t), np.zeros_like(t)]
    assert contour_probe(ring).open_gap_m < 0.5 and contour_probe(ring).touching == 0
    opened = ring[:30]
    assert contour_probe(opened).open_gap_m > 0.5
    pinched = np.vstack([ring, ring[10:11]])     # revisits a point of the ring
    assert contour_probe(pinched).touching >= 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_diag_probes.py`
Expected: FAIL — `ModuleNotFoundError: ocx_diagnose.probes`.

- [ ] **Step 3: Implement `probes.py`**

```python
"""Cheap source-geometry probes over a panel's chart mesh and a plate's contour."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from ocx_diagnose.checks import _project_distance

_SAMPLES_PER_MEMBER = 6
_NEIGHBOUR_FACES = 8


def duplicate_members(chart, members: list, eps_m: float = 1e-3) -> list[tuple[int, int, int]]:
    """Member pairs (a, b, hits) whose surfaces coincide within ``eps_m``.

    Up to a few face centroids of each member are projected onto the members of
    the nearest other-member chart faces; a pair is a duplicate when at least
    half of a member's samples lie on the other surface.
    """
    if chart is None or chart.F is None or len(chart.F) == 0 or chart.tri_member is None:
        return []
    cent = chart.V[chart.F].mean(axis=1)
    owner = np.asarray(chart.tri_member)
    valid = np.flatnonzero(owner >= 0)
    if len(valid) == 0:
        return []
    tree = cKDTree(cent[valid])
    hits: dict[tuple[int, int], int] = {}
    nsamp: dict[int, int] = {}
    for a in np.unique(owner[valid]):
        faces = np.flatnonzero(owner == a)
        pick = faces[np.linspace(0, len(faces) - 1, min(_SAMPLES_PER_MEMBER, len(faces))).astype(int)]
        pts = cent[pick]
        nsamp[int(a)] = len(pts)
        k = min(_NEIGHBOUR_FACES, len(valid))
        _, near = tree.query(pts, k=k)
        near = np.atleast_2d(near.reshape(len(pts), k))
        for si in range(len(pts)):
            for b in {int(owner[valid[j]]) for j in near[si]} - {int(a)}:
                if b < len(members) and _project_distance(members[b], pts[si:si + 1])[0] < eps_m:
                    key = (int(a), b)
                    hits[key] = hits.get(key, 0) + 1
    out = []
    for (a, b), n in hits.items():
        if a < b and n >= max(2, nsamp[a] // 2) and hits.get((b, a), 0) >= max(2, nsamp[b] // 2):
            out.append((a, b, n))
    return sorted(out, key=lambda t: -t[2])


def degenerate_members(chart, min_area_m2: float = 1e-4) -> list[int]:
    """Members with no chart faces or a total chart area below ``min_area_m2``."""
    if chart is None or chart.F is None:
        return []
    area = np.zeros(chart.n_members)
    if len(chart.F):
        t = chart.V[chart.F]
        a = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        owner = np.asarray(chart.tri_member)
        ok = (owner >= 0) & (owner < chart.n_members)
        np.add.at(area, owner[ok], a[ok])
    return [int(i) for i in np.flatnonzero(area < min_area_m2)]


@dataclass
class ContourProbe:
    open_gap_m: float   # distance between the last and first contour point
    touching: int       # non-adjacent contour points closer than 1e-6 m


def contour_probe(contour) -> ContourProbe:
    """Closure and self-contact of a trim contour (k, 3)."""
    c = None if contour is None else np.asarray(contour, float)
    if c is None or len(c) < 4:
        return ContourProbe(0.0, 0)
    seg = np.linalg.norm(np.diff(c, axis=0), axis=1)
    gap = float(np.linalg.norm(c[-1] - c[0]))
    # a closed ring's end gap is about one segment; report the excess over that
    open_gap = max(0.0, gap - float(np.median(seg)))
    pairs = cKDTree(c).query_pairs(1e-6, output_type="ndarray")
    n = len(c)
    touching = int(sum(1 for i, j in pairs if (j - i) > 1 and (j - i) < n - 1))
    return ContourProbe(open_gap, touching)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_diag_probes.py`
Expected: 4 passed. If the closed-ring assertion `open_gap_m < 0.5` fails, note a 40-point unit ring has segment ≈ 0.157, end gap ≈ 0.157, so excess ≈ 0.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/probes.py tests/test_diag_probes.py
git commit -m "feat(diagnose): source-geometry probes (duplicates, degenerate, contour)" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Findings and rules

**Files:**
- Create: `packages/ocx-diagnose/src/ocx_diagnose/advice.py`
- Test: `tests/test_diag_advice.py`

- [ ] **Step 1: Write the failing tests**

```python
from types import SimpleNamespace as NS

from ocx_diagnose.advice import Finding, panel_findings, plate_findings
from ocx_diagnose.probes import ContourProbe


def _plate(**kw):
    base = dict(plate_id="p1", route="mesh-trim", trim_reject=None, snap_m=0.0,
                max_snap_m=1.5, dev_max_m=0.0, overlap_faces=0, gap_vertices=0,
                max_gap_m=0.0, flipped_frac=None, spread_max=None,
                health={"boundary_edges": 4, "non_manifold_edges": 0})
    base.update(kw)
    return NS(**base)


def _ids(fs):
    return {f.id for f in fs}


def test_healthy_plate_has_no_findings():
    assert plate_findings(_plate(), ContourProbe(0.0, 0), [], 0.05) == []


def test_overlap_without_probe_is_likely_and_with_probe_confirmed():
    p = _plate(overlap_faces=30000)
    f = {x.id: x for x in plate_findings(p, ContourProbe(0, 0), [], 0.05)}["overlap"]
    assert f.status == "likely" and f.severity == "high"
    assert "30000" in f.evidence and f.source_steps and f.mesh_steps
    g = {x.id: x for x in plate_findings(p, ContourProbe(0, 0), [(3, 7, 6)], 0.05)}["overlap"]
    assert g.status == "confirmed" and "3" in g.evidence and "7" in g.evidence


def test_each_plate_rule_fires():
    tol = 0.05
    cases = {
        "trim-reject": _plate(trim_reject="snap too large"),
        "snap": _plate(snap_m=1.0, max_snap_m=1.5),
        "chart-distortion": _plate(route="lscm", flipped_frac=0.02, spread_max=3.0),
        "deviation": _plate(dev_max_m=0.2),
        "non-manifold": _plate(health={"boundary_edges": 4, "non_manifold_edges": 5}),
        "gaps": _plate(gap_vertices=10, max_gap_m=0.02),
    }
    for fid, plate in cases.items():
        assert fid in _ids(plate_findings(plate, ContourProbe(0, 0), [], tol)), fid
    assert "open-contour" in _ids(plate_findings(_plate(), ContourProbe(2.0, 0), [], tol))
    assert "self-touching-contour" in _ids(plate_findings(_plate(), ContourProbe(0, 3), [], tol))


def test_panel_findings_and_ranking():
    chart = NS(n_members=10, boundary_edges_before_stitch=100, boundary_edges_after_stitch=60)
    fs = panel_findings("pan", chart, duplicates=[(1, 2, 6)], degenerate=[4])
    assert _ids(fs) == {"duplicate-members", "degenerate-members", "seam-gaps"}
    assert fs[0].severity == "high"          # ranked high -> medium -> low
    assert all(isinstance(f, Finding) and f.scope == "panel" for f in fs)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_diag_advice.py`
Expected: FAIL — `ModuleNotFoundError: ocx_diagnose.advice`.

- [ ] **Step 3: Implement `advice.py`**

```python
"""Rule-based findings: metric/probe evidence -> root cause -> remedies."""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from ocx_diagnose.probes import (
    ContourProbe,
    contour_probe,
    degenerate_members,
    duplicate_members,
)

_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str            # high | medium | low
    scope: str               # panel | plate
    subject: str             # panel id or plate id
    status: str              # likely (metrics only) | confirmed (probe evidence)
    title: str
    evidence: str
    cause: str
    mesh_steps: tuple[str, ...] = ()     # what to change in the diagnose/render settings
    source_steps: tuple[str, ...] = ()   # what to fix in the OCX source NURBS


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (_RANK[f.severity], f.id, f.subject))


def _pairs_text(pairs) -> str:
    return ", ".join(f"#{a}/#{b} ({n} samples)" for a, b, n in pairs[:5])


def _overlap(p, tol_m, cp, dups):
    if p.overlap_faces < 50:
        return None
    confirmed = bool(dups)
    ev = f"{p.overlap_faces} faces lie on another plate's surface."
    if confirmed:
        ev += f" Coincident source members: {_pairs_text(dups)}."
    return Finding(
        "overlap", "high", "plate", p.plate_id, "confirmed" if confirmed else "likely",
        "Plate overlaps neighbouring plates", ev,
        "Two or more plates (or the NURBS members behind them) cover the same part of "
        "the hull, so the shell is double-skinned there.",
        ("Overlap is geometric, not a meshing artefact; a finer tolerance will not remove it.",),
        ("Delete or merge duplicate NURBS members/plates in the OCX source.",
         "Trim each plate so adjacent plates share only an edge, not an area.",
         "Check that one plate is not modelled on both sides of the same surface."))


def _trim_reject(p, tol_m, cp, dups):
    if not p.trim_reject:
        return None
    return Finding(
        "trim-reject", "medium", "plate", p.plate_id, "likely",
        "Mesh-trim route was rejected", f"Reason: {p.trim_reject}.",
        "The plate contour could not be cut from the panel mesh, so a slower or less "
        "accurate fallback route was used.",
        ("Increase --tolerance slightly so the panel mesh is coarser at the seams.",),
        ("Make the plate contour curves lie on the NURBS surface (within 1 mm).",
         "Close the contour: end point equals start point."))


def _snap(p, tol_m, cp, dups):
    if p.snap_m is None or not p.max_snap_m or p.snap_m < 0.5 * p.max_snap_m:
        return None
    return Finding(
        "snap", "medium", "plate", p.plate_id, "likely", "Contour snaps far from the mesh",
        f"Worst snap {p.snap_m:.3g} m of allowed {p.max_snap_m:.3g} m.",
        "The plate contour does not lie on the surface the plate is cut from.",
        ("Lower --tolerance so the mesh follows the surface more closely.",),
        ("Re-project the contour curves onto the NURBS surface.",
         "Check the contour belongs to this panel's surface, not a neighbouring one."))


def _chart_distortion(p, tol_m, cp, dups):
    flipped = p.flipped_frac or 0.0
    if flipped <= 0 and (p.spread_max or 0.0) < 20:
        return None
    return Finding(
        "chart-distortion", "medium", "plate", p.plate_id, "likely",
        "Flattened chart is distorted",
        f"Flipped area {flipped:.2%}, max scale spread {p.spread_max or 0:.3g}.",
        "The surface is strongly curved or folded, so its 2-D unfolding stretches or flips.",
        ("Lower --tolerance to add triangles in high-curvature areas.",),
        ("Split the NURBS patch along the fold or ridge line.",
         "Remove near-singular corners (collapsed edges) from the patch."))


def _deviation(p, tol_m, cp, dups):
    if p.dev_max_m is None or p.dev_max_m <= tol_m:
        return None
    return Finding(
        "deviation", "medium", "plate", p.plate_id, "likely", "Mesh deviates from the surface",
        f"Max deviation {p.dev_max_m:.3g} m exceeds tolerance {tol_m:.3g} m.",
        "Triangles are too coarse for the surface curvature, or the nearest exact surface "
        "is a different member than the one meshed.",
        (f"Re-run with --tolerance below {tol_m * 1000:.0f} (mm).",),
        ("If deviation stays high at small tolerance, look for overlapping members.",))


def _non_manifold(p, tol_m, cp, dups):
    n = p.health.get("non_manifold_edges", 0)
    if n <= 0:
        return None
    return Finding(
        "non-manifold", "high", "plate", p.plate_id, "likely", "Non-manifold mesh edges",
        f"{n} edges are shared by more than two triangles.",
        "Overlapping or T-junction seams between members produce edges with 3+ faces.",
        ("Not fixable by tolerance alone.",),
        ("Make adjacent NURBS members meet along identical edge curves.",
         "Remove duplicate members covering the same area."))


def _gaps(p, tol_m, cp, dups):
    if p.gap_vertices <= 0:
        return None
    return Finding(
        "gaps", "low", "plate", p.plate_id, "likely", "Small gaps to neighbouring plates",
        f"{p.gap_vertices} boundary vertices are up to {p.max_gap_m:.3g} m from a neighbour.",
        "Neighbouring plates nearly, but not exactly, share their edges.",
        ("Gaps below the tolerance are cosmetic.",),
        ("Snap neighbouring plate contours to common edge curves.",))


def _open_contour(p, tol_m, cp, dups):
    if cp is None or cp.open_gap_m <= 10 * tol_m:
        return None
    return Finding(
        "open-contour", "high", "plate", p.plate_id, "confirmed", "Trim contour is not closed",
        f"Contour end points are {cp.open_gap_m:.3g} m apart (beyond one segment).",
        "An open contour cannot enclose an area, so trimming is unreliable.",
        (), ("Close the contour curve in the OCX source (last point = first point).",))


def _touching_contour(p, tol_m, cp, dups):
    if cp is None or cp.touching <= 0:
        return None
    return Finding(
        "self-touching-contour", "medium", "plate", p.plate_id, "confirmed",
        "Trim contour touches itself", f"{cp.touching} contour point pairs coincide.",
        "A pinched or figure-eight contour splits the plate into ambiguous regions.",
        (), ("Remove the repeated vertices or split the plate at the pinch point.",))


_PLATE_RULES = (_overlap, _trim_reject, _snap, _chart_distortion, _deviation, _non_manifold,
                _gaps, _open_contour, _touching_contour)


def plate_findings(plate, cprobe: ContourProbe | None, duplicates, tol_m: float) -> list[Finding]:
    """Findings for one plate; a failing rule is logged and skipped."""
    out = []
    for rule in _PLATE_RULES:
        try:
            f = rule(plate, tol_m, cprobe, duplicates)
        except Exception as exc:  # noqa: BLE001 — advice must never break the report
            logger.warning("advice rule {} failed on {}: {}", rule.__name__, plate.plate_id, exc)
            continue
        if f:
            out.append(f)
    return rank(out)


def panel_findings(panel_id: str, chart, duplicates, degenerate) -> list[Finding]:
    """Panel-level findings from the chart statistics and probes."""
    out = []
    if duplicates:
        out.append(Finding(
            "duplicate-members", "high", "panel", panel_id, "confirmed",
            "Duplicate NURBS members",
            f"{len(duplicates)} member pairs coincide: {_pairs_text(duplicates)}.",
            "The panel contains surfaces lying on top of each other.",
            ("Meshing cannot fix this.",),
            ("Delete the redundant member in the OCX source (keep one per area).",
             "Check the model export for repeated surfaces.")))
    if degenerate:
        out.append(Finding(
            "degenerate-members", "low", "panel", panel_id, "confirmed",
            "Degenerate NURBS members",
            f"{len(degenerate)} members have no area or no faces: "
            f"{', '.join('#' + str(i) for i in degenerate[:10])}.",
            "Collapsed or empty patches add cost and can destabilise stitching.",
            (), ("Remove zero-area members from the OCX source.",)))
    if chart is not None and chart.boundary_edges_after_stitch > 0.2 * max(
            chart.boundary_edges_before_stitch, 1):
        out.append(Finding(
            "seam-gaps", "medium", "panel", panel_id, "likely", "Seams between members stay open",
            f"{chart.boundary_edges_after_stitch} of {chart.boundary_edges_before_stitch} "
            "member boundary edges remain unstitched.",
            "Adjacent members do not share edges within the weld distance.",
            ("A coarser --tolerance widens the weld distance and may close small seams.",),
            ("Make neighbouring NURBS members share edge curves exactly.",)))
    return rank(out)


def advise_panel(panel) -> None:
    """Fill ``panel.findings`` and each plate's ``findings`` (probe failures are skipped)."""
    chart = panel.chart
    members = panel.plates[0].diag.candidates if panel.plates else []
    try:
        dups = duplicate_members(chart, members)
    except Exception as exc:  # noqa: BLE001
        logger.warning("duplicate probe failed on {}: {}", panel.panel_id, exc)
        dups = []
    try:
        degen = degenerate_members(chart)
    except Exception as exc:  # noqa: BLE001
        logger.warning("degenerate probe failed on {}: {}", panel.panel_id, exc)
        degen = []
    panel.findings = panel_findings(panel.panel_id, chart, dups, degen)
    for p in panel.plates:
        try:
            cp = contour_probe(p.diag.contour)
        except Exception as exc:  # noqa: BLE001
            logger.warning("contour probe failed on {}: {}", p.plate_id, exc)
            cp = None
        p.findings = plate_findings(p, cp, dups, panel.tol_m)
    logger.debug("advice {}: {} panel / {} plate findings", panel.panel_id,
                 len(panel.findings), sum(len(p.findings) for p in panel.plates))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_diag_advice.py`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/advice.py tests/test_diag_advice.py
git commit -m "feat(diagnose): rule-based findings with mesh and OCX-source remedies" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Wire advice into the analysis

**Files:**
- Modify: `packages/ocx-diagnose/src/ocx_diagnose/analyse.py` (`PlateResult`, `PanelResult`, `analyse_model`)
- Test: `tests/test_diag_advice.py` (append)

- [ ] **Step 1: Append the failing test**

```python
def test_analyse_model_attaches_findings():
    from ocx_diagnose.analyse import analyse_model
    from tests.test_render_model import make_vessel
    panels = analyse_model(make_vessel(), {"pan1"}, 50.0, [])
    assert isinstance(panels[0].findings, list)
    assert all(isinstance(p.findings, list) for p in panels[0].plates)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_diag_advice.py::test_analyse_model_attaches_findings`
Expected: FAIL — `AttributeError: 'PanelResult' object has no attribute 'findings'`.

- [ ] **Step 3: Implement**

In `analyse.py`: add `from ocx_diagnose.advice import Finding, advise_panel` to the imports; add to `PlateResult` after `score: float`:

```python
    findings: list[Finding] = field(default_factory=list)
```

add to `PanelResult` after `tol_m: float = 0.05`:

```python
    findings: list[Finding] = field(default_factory=list)
```

In `analyse_model`, replace `panels.append(PanelResult(...))` with:

```python
        panel = PanelResult(
            panel_id=panel_id, chart=sink.charts.get(panel_id), plates=plates,
            skipped={k: v for k, v in skips.items() if k.split("/")[0] in plate_ids},
            sweep=run_sweep(vessel, {panel_id}, sweep_mm) if sweep_mm else [],
            seconds=sum(p.seconds for p in plates), tol_m=tol_m)
        t_adv = time.perf_counter()
        advise_panel(panel)
        logger.info("Advice for {}: {} findings in {:.1f}s", panel_id,
                    len(panel.findings) + sum(len(p.findings) for p in plates),
                    time.perf_counter() - t_adv)
        panels.append(panel)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_diag_advice.py tests/test_diag_checks.py tests/test_diag_cli.py`
Expected: all pass. (`advice.py` imports `probes.py`, which imports `checks.py` — no cycle with `analyse.py`.)

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/analyse.py tests/test_diag_advice.py
git commit -m "feat(diagnose): attach findings to panel and plate results" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Report boxes, summary column, JSON

**Files:**
- Modify: `packages/ocx-diagnose/src/ocx_diagnose/report.py`
- Test: `tests/test_diag_report.py` (append)

- [ ] **Step 1: Append the failing test**

```python
def test_report_and_json_include_findings(tmp_path):
    from ocx_diagnose.advice import Finding

    res = analyse_model(make_vessel(), {"pan1"}, 50.0, [])
    f = Finding("overlap", "high", "plate", "pl1", "likely", "Plate overlaps",
                "30000 faces", "double skin", ("mesh step",), ("source step",))
    g = Finding("duplicate-members", "high", "panel", "pan1", "confirmed", "Duplicates",
                "pairs #1/#2", "stacked", (), ("delete one",))
    res[0].plates[0].findings = [f]
    res[0].findings = [g]
    html = tmp_path / "r.html"
    js = tmp_path / "r.json"
    write_report(res, html, max_plates=5, title="t")
    write_json(res, js)
    text = html.read_text(encoding="utf-8")
    assert "Findings" in text and "Duplicates" in text and "delete one" in text
    assert "Diagnosis" in text and "Improve the OCX source" in text and "mesh step" in text
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["pan1"]["findings"][0]["id"] == "duplicate-members"
    assert data["pan1"]["plates"]["pl1"]["findings"][0]["id"] == "overlap"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q tests/test_diag_report.py::test_report_and_json_include_findings`
Expected: FAIL — `"Findings"` not in text.

- [ ] **Step 3: Implement in `report.py`**

Add helper after `_table`:

```python
_SEV_COLOUR = {"high": "#c0392b", "medium": "#e67e22", "low": "#7f8c8d"}


def _finding_html(f) -> str:
    def steps(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{_html.escape(s)}</li>" for s in items)
        return f"<b>{title}</b><ul>{lis}</ul>"

    colour = _SEV_COLOUR.get(f.severity, "#555")
    return (f'<div class="finding" style="border-left:4px solid {colour}">'
            f"<b>[{_html.escape(f.severity.upper())}] {_html.escape(f.title)}</b> "
            f"<i>({_html.escape(f.status)})</i>"
            f"<div><b>Evidence:</b> {_html.escape(f.evidence)}</div>"
            f"<div><b>Likely cause:</b> {_html.escape(f.cause)}</div>"
            f"{steps('Improve the meshing', f.mesh_steps)}"
            f"{steps('Improve the OCX source', f.source_steps)}</div>")


def _findings_box(title: str, findings) -> str:
    if not findings:
        return ""
    return f"<h3>{title}</h3>" + "".join(_finding_html(f) for f in findings)
```

Add to `_CSS` string: `".finding{margin:.4em 0;padding:.3em .6em;background:#fafafa;font-size:13px}"` (append before the closing of the last literal, keeping the parentheses balanced).

In `plate_section`, replace the final two lines with:

```python
    body = _findings_box("Diagnosis", pr.findings) + "".join(_fig_html(f) for f in figs)
    n = len(pr.findings)
    label = f"{pr.plate_id} (score {pr.score:.3g}, route {pr.route}, {n} findings)"
    return f"<details><summary>{_html.escape(label)}</summary>{body}</details>"
```

In `panel_section`, directly after `parts = [f"<h2>...</h2>"]` add:

```python
    parts.append(_findings_box("Findings", panel.findings))
```

In `_summary_row` change the return to append a findings count, and update the header tuple in `write_report` accordingly:

```python
    n_find = len(panel.findings) + sum(len(p.findings) for p in panel.plates)
    return (panel.panel_id, len(panel.plates), routes,
            max((p.score for p in panel.plates), default=None),
            max(devs, default=None), "yes" if panel.sweep else "no", n_find)
```

and in `write_report`: `("panel", "plates", "routes", "worst score", "max dev m", "sweep", "findings")`.

In `write_json`, inside the per-panel dict add `"findings": [asdict(f) for f in panel.findings],` and inside each plate dict, after `"health": p.health`, add `, "findings": [asdict(f) for f in p.findings]`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q tests/test_diag_report.py tests/test_diag_cli.py`
Expected: all pass. The earlier assertion `"<script src=" not in text` must still hold.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-diagnose/src/ocx_diagnose/report.py tests/test_diag_report.py
git commit -m "feat(diagnose): findings boxes, summary column and JSON in report" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Real-model check, docs, full suite

**Files:**
- Modify: `README.md` (ocx-diagnose section)

- [ ] **Step 1: Run on the cadhu model and check timing and content**

Run: `uv run ocx-diagnose .\models\TR05\tr05_tc14a_cadhu_outer_shell.3docx --report $env:TEMP\adv.html --json $env:TEMP\adv.json`
Expected: finishes in roughly 2–3 minutes (previous ~110 s plus the duplicate probe); log shows `Advice for _hullgroup3_layer3panel: N findings in X s`. If the advice step exceeds ~60 s, lower `_SAMPLES_PER_MEMBER` in `probes.py` and re-run.
Then check the JSON: `uv run python -c "import json,os;d=json.load(open(os.environ['TEMP']+'/adv.json'));[print(k,[f['id'] for f in v['findings']]) for k,v in d.items()]"`
Expected: `_hullgroup3_layer3panel` lists `duplicate-members` if the overlaps come from coincident members, otherwise the plates list `overlap` as `likely`. Record which in the commit message.

- [ ] **Step 2: Document in README**

Add a short "Advice" paragraph to the ocx-diagnose section of `README.md`: the report now contains ranked *Findings* per panel and a *Diagnosis* box per worst plate, each with evidence, likely cause, "Improve the meshing" steps and "Improve the OCX source" steps; status `confirmed` means a probe proved it, `likely` means inferred from metrics; findings also appear in the JSON output.

- [ ] **Step 3: Full suite and lint**

Run: `uv run pytest -q` then `uv run ruff check packages tests --output-format concise`
Expected: all tests pass; ruff shows no new errors in `advice.py`, `probes.py`, `analyse.py`, `report.py`, the new tests (3 pre-existing errors in `surfaces.py` and `test_diag_hooks.py` are known).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe ocx-diagnose advice" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
