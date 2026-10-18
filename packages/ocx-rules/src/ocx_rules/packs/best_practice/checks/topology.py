"""Geometry topology checks (OCX-TOP-001/002/003, later 004/005/008/009)."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger
from ocx_geometry.holes import parametric_profile
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps
from ocx_geometry.topology2d import polygon_ok
from ocx_model_core.model.ir.geometry import IrCompositeCurve3D

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


def panel_limited_by_closed(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-001: panel LimitedBy must form a closed contour."""
    tol_m = float(params.get("tolerance_mm", 1.0)) / 1000.0
    findings: list[Finding] = []
    for pid, panel in context.vessel.panels.items():
        if not panel.limited_by:
            continue
        samples, skipped = _panel_boundary_samples(context, panel)
        if skipped:
            logger.debug("TOP-001: panel {} skipped ({} unresolved refs)",
                         pid, skipped)
            continue
        if not samples:
            logger.debug("TOP-001: panel {} skipped (no sampleable boundary)",
                         pid)
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


def _composite_curves(context) -> list[tuple[str, str | None, IrCompositeCurve3D]]:
    """All IrCompositeCurve3D objects in the model as (owner_id, guid, curve).

    Collected from panel boundary curves (resolved + inline LimitedBy
    curves), seam trace lines, stiffener/pillar traces, plate outer
    contours and catalogue hole contours. De-duplicated by object identity
    so a curve reachable via two paths is reported once.
    """
    vessel = context.vessel
    seen: set[int] = set()
    found: list[tuple[str, str | None, IrCompositeCurve3D]] = []

    def add(owner_id: str, guid: str | None, curve) -> None:
        if isinstance(curve, IrCompositeCurve3D) and id(curve) not in seen:
            seen.add(id(curve))
            found.append((owner_id, guid, curve))

    for pid, panel in vessel.panels.items():
        curves, _ = context.geometry.boundary_curves(panel)
        for c in curves:
            add(pid, panel.guidref, c)
        for ref in panel.limited_by:
            add(pid, panel.guidref, getattr(ref, "curve", None))
    for sid, seam in vessel.seams.items():
        add(sid, seam.guidref, seam.trace_line)
    for stid, stiffener in vessel.stiffeners.items():
        add(stid, stiffener.guidref, stiffener.trace)
    for plid, pillar in vessel.pillars.items():
        add(plid, pillar.guidref, pillar.trace)
    for plid, plate in vessel.plates.items():
        add(plid, plate.guidref, plate.outer_contour)
    catalogue = vessel.hole_shape_catalogue
    if catalogue is not None:
        for hid, hole in catalogue.holes.items():
            add(hid, hole.guidref, hole.contour)
    return found


def composite_curve_continuous(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-002: CompositeCurve3D segments must join end-to-end."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    findings: list[Finding] = []
    for owner_id, guid, curve in _composite_curves(context):
        samples = []
        for seg in curve.segments:
            pts = context.geometry.sample(seg)
            if pts is None or len(pts) < 2:
                logger.debug("TOP-002: composite curve on {} skipped "
                             "(unsampleable segment)", owner_id)
                samples = None
                break
            samples.append(pts)
        if samples is None or len(samples) < 2:
            continue
        gaps = ordered_junction_gaps(samples)
        bad = [g for g in gaps if g > tol_m]
        if bad:
            findings.append(Finding(
                message=(f"Composite curve segments are not continuous: "
                         f"worst junction gap {max(bad) * 1000:.2f} mm "
                         f"exceeds {tol_m * 1000:.2f} mm"),
                element_id=owner_id, guid=guid))
    return findings


def hole_contours_closed(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-003: hole/opening contours must be closed."""
    tol_m = float(params.get("tolerance_mm", 0.1)) / 1000.0
    catalogue = context.vessel.hole_shape_catalogue
    if catalogue is None:
        return []
    findings: list[Finding] = []
    for hid, hole in catalogue.holes.items():
        if hole.parametric is not None:
            ring = parametric_profile(hole.parametric, context.geometry.length,
                                      _SAMPLE_TOL_M)
            if ring is None:
                logger.debug("TOP-003: hole {} parametric profile could not "
                             "be built; skipped", hid)
                continue
            reason = polygon_ok(ring)
            if reason is not None:
                findings.append(Finding(
                    message=(f"Parametric hole profile is not a valid "
                             f"closed polygon: {reason}"),
                    element_id=hid, guid=hole.guidref))
            continue
        if hole.contour is None:
            continue
        pts = context.geometry.sample(hole.contour)
        if pts is None or len(pts) < 2:
            logger.debug("TOP-003: hole {} contour unsampleable; skipped", hid)
            continue
        gap = float(np.linalg.norm(pts[0] - pts[-1]))
        if gap > tol_m:
            findings.append(Finding(
                message=(f"Hole contour is not closed: closure gap "
                         f"{gap * 1000:.2f} mm exceeds "
                         f"{tol_m * 1000:.2f} mm"),
                element_id=hid, guid=hole.guidref))
    return findings
