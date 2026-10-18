"""Geometry topology checks (OCX-TOP-001/002/003, later 004/005/008/009)."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps
from ocx_geometry.topology2d import point_polyline_distance

from ocx_rules.model import Finding

_SAMPLE_TOL_M = 0.001


def _panel_boundary_samples(context, panel, tol_m=_SAMPLE_TOL_M):
    """-> (list of sampled (N, 3) arrays in metres, n_skipped_refs)."""
    geo = context.geometry
    curves, unresolved = geo.boundary_curves(panel)
    samples = []
    for c in curves:
        pts = geo.sample(c, tol_m)
        if pts is None or len(pts) < 2:
            unresolved += 1
        else:
            samples.append(pts)
    return samples, unresolved


def panel_closed_contour(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-001: panel LimitedBy must form a closed contour."""
    tol_m = float(params.get("tolerance_mm", 1.0)) / 1000.0
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if not panel.limited_by:
            continue
        samples, skipped = _panel_boundary_samples(context, panel)
        if skipped or len(samples) < 2:
            logger.debug("TOP-001: panel {} skipped ({} unresolved refs)",
                         pid, skipped)
            continue
        ring, gaps = chain_polylines(samples)
        if ring is None:
            continue
        worst = max(gaps)
        if worst > tol_m:
            findings.append(Finding(
                message=(f"Panel boundary is not closed: largest gap "
                         f"{worst * 1000:.2f} mm exceeds "
                         f"{tol_m * 1000:.2f} mm"),
                element_id=pid, guid=panel.guidref))
    return findings


def boundary_continuity(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-002: consecutive LimitedBy curves must join end-to-end."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if len(panel.limited_by) < 2:
            continue
        samples, skipped = _panel_boundary_samples(context, panel)
        if skipped or len(samples) < 2:
            logger.debug("TOP-002: panel {} skipped ({} unresolved refs)",
                         pid, skipped)
            continue
        gaps = ordered_junction_gaps(samples)
        bad = [g for g in gaps if g > tol_m]
        if bad:
            findings.append(Finding(
                message=(f"{len(bad)} boundary junction(s) exceed "
                         f"{tol_m * 1000:.2f} mm (worst "
                         f"{max(bad) * 1000:.2f} mm)"),
                element_id=pid, guid=panel.guidref))
    return findings


def seam_continuity(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-003: a panel's seams must lie on the panel (within tol)."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    geo = context.geometry
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if not panel.seam_ids:
            continue
        boundary, skipped = _panel_boundary_samples(context, panel)
        surface = geo.surface_param(geo.panel_surface(panel))
        for sid in panel.seam_ids:
            seam = context.vessel.seams.get(sid)
            pts = geo.sample(seam.trace_line) if seam else None
            if pts is None:
                logger.debug("TOP-003: seam {} on panel {} skipped", sid, pid)
                continue
            if surface is not None:
                uv = surface.inverse(pts)
                dist = float(np.max(
                    np.linalg.norm(surface.evaluate(uv) - pts, axis=1)))
            elif boundary and not skipped:
                dist = max(
                    min(point_polyline_distance(p, b) for b in boundary)
                    for p in (pts[0], pts[-1]))
            else:
                logger.debug("TOP-003: panel {} has no usable surface or "
                             "boundary; seam {} skipped", pid, sid)
                continue
            if dist > tol_m:
                findings.append(Finding(
                    message=(f"Seam {sid} deviates {dist * 1000:.2f} mm from "
                             f"panel (tolerance {tol_m * 1000:.2f} mm)"),
                    element_id=pid, guid=panel.guidref))
    return findings
