"""Run the render pipeline with a DiagSink and assemble per-panel results."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import ChartDiag, DiagSink, PlateDiag
from ocx_geometry.mesh import PartMesh
from ocx_render.render import render_model

from ocx_diagnose.advice import Finding, advise_panel
from ocx_diagnose.checks import (
    chart_distortion,
    mesh_health,
    neighbour_overlaps_and_gaps,
    surface_deviation,
)
from ocx_diagnose.sweep import SweepPoint, plate_meshes, plate_skips, run_sweep


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
    findings: list[Finding] = field(default_factory=list)


@dataclass
class PanelResult:
    panel_id: str
    chart: ChartDiag | None
    plates: list[PlateResult]
    skipped: dict[str, str]
    sweep: list[SweepPoint] = field(default_factory=list)
    seconds: float = 0.0
    tol_m: float = 0.05
    findings: list[Finding] = field(default_factory=list)


def _plate_result(m: PartMesh, pd: PlateDiag, overlap: dict, tol_m: float) -> PlateResult:
    V, F = m.vertices, m.triangles
    dev = (surface_deviation(V[F].mean(axis=1), pd.candidates, chart=pd.chart)
           if len(F) else np.zeros(0))
    dev = dev[np.isfinite(dev)]
    dev_mean = float(dev.mean()) if len(dev) else None
    dev_max = float(dev.max()) if len(dev) else None

    bbox_delta = 0.0
    if pd.contour is not None and len(V):
        c = pd.contour
        bbox_delta = float(max(np.abs(V.min(0) - c.min(0)).max(),
                               np.abs(V.max(0) - c.max(0)).max()))

    flipped_frac = spread_max = None
    if pd.route == "lscm" and pd.local_param is not None:
        Vc, Fc, uv = pd.local_param.chart
        d = chart_distortion(Vc, Fc, uv)
        flipped_frac, spread_max = d.flipped_frac, d.spread_max

    health = mesh_health(V, F)
    snap = pd.snap_m or 0.0
    max_snap = pd.max_snap_m or 1.0
    score = ((dev_max or 0.0) / tol_m + snap / max_snap + 10 * (flipped_frac or 0.0)
             + (1.0 if pd.route in ("lscm", "best-member") else 0.0)
             + health["non_manifold_edges"] + overlap["overlap_faces"] / 10
             + (1.0 if overlap["gap_vertices"] > 0 else 0.0)
             + bbox_delta / (10 * tol_m))
    return PlateResult(
        plate_id=pd.plate_id, route=pd.route, trim_reject=pd.trim_reject,
        snap_m=pd.snap_m, max_snap_m=pd.max_snap_m, chart_stage=pd.chart_stage,
        seconds=pd.seconds, health=health, dev_mean_m=dev_mean, dev_max_m=dev_max,
        overlap_faces=overlap["overlap_faces"], gap_vertices=overlap["gap_vertices"],
        max_gap_m=overlap["max_gap_m"], bbox_delta_m=bbox_delta,
        flipped_frac=flipped_frac, spread_max=spread_max, mesh=m, diag=pd, score=score)


def analyse_model(vessel, panel_ids: set[str] | None, tolerance_mm: float,
                  sweep_mm: list[float]) -> list[PanelResult]:
    """Render once with a sink, then derive per-panel, per-plate diagnostics."""
    tol_m = tolerance_mm / 1000.0
    sink = DiagSink()
    opts = TessellationOptions(
        tolerance_m=tol_m, diag=sink,
        only_panels=frozenset(panel_ids) if panel_ids else None)
    t0 = time.perf_counter()
    result = render_model(vessel, opts)
    total_s = time.perf_counter() - t0
    logger.info("Diagnose render: {} plates in {:.1f}s", len(sink.plates), total_s)

    skips = plate_skips(vessel, result, panel_ids)
    by_panel: dict[str, list[PartMesh]] = {}
    for m in plate_meshes(result, sink):
        by_panel.setdefault(m.extras["panel_id"], []).append(m)

    panels = []
    for panel_id in sorted(by_panel):
        meshes = by_panel[panel_id]
        ov = neighbour_overlaps_and_gaps(
            {m.part_id: (m.vertices, m.triangles) for m in meshes},
            gap_max_m=max(10 * tol_m, 0.1))
        plates = sorted((_plate_result(m, sink.plates[m.part_id], ov[m.part_id], tol_m)
                         for m in meshes), key=lambda p: p.plate_id)
        plate_ids = {p.id for p in vessel.plates.values()
                     if getattr(p.parent_ref, "id", None) == panel_id}
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
    return panels
