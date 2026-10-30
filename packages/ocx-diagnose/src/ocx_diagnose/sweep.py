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


def plate_meshes(result, sink: DiagSink) -> list:
    """Plate meshes only (only_panels also renders the panels' stiffeners)."""
    return [m for m in result.meshes
            if m.extras.get("kind") == "plate" and m.part_id in sink.plates]


def plate_skips(vessel, result, panel_ids: set[str] | None) -> dict[str, str]:
    """Skip-log and hole-failure entries for plates of the analysed panels
    (panel-level hole failures are keyed by the panel id)."""
    ids = {p.id for p in vessel.plates.values()
           if panel_ids is None or getattr(p.parent_ref, "id", None) in panel_ids}
    ids |= set(vessel.panels) if panel_ids is None else set(panel_ids)
    entries = {**result.skipped, **result.hole_failures}
    return {k: v for k, v in entries.items() if k.split("/")[0] in ids}


def deviations(result, sink: DiagSink) -> np.ndarray:
    """Face-centroid distance to the exact surface for all plate meshes."""
    parts = []
    for m in plate_meshes(result, sink):
        if len(m.triangles) == 0:
            continue
        pd = sink.plates[m.part_id]
        d = surface_deviation(m.vertices[m.triangles].mean(axis=1), pd.candidates,
                              chart=pd.chart)
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
        meshes = plate_meshes(res, sink)
        dev = deviations(res, sink)
        points.append(SweepPoint(
            tol_mm=tol, seconds=secs,
            triangles=int(sum(len(m.triangles) for m in meshes)),
            parts=len(meshes), skipped=len(plate_skips(vessel, res, panel_ids)),
            dev_mean_m=float(dev.mean()) if len(dev) else None,
            dev_max_m=float(dev.max()) if len(dev) else None))
        logger.info("Sweep {:.1f} mm: {} tris, {:.1f}s, max dev {}", tol,
                    points[-1].triangles, secs, points[-1].dev_max_m)
    return points
