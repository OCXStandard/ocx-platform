"""Geometry topology checks (OCX-TOP-001 through 005, 008 and 009)."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger
from ocx_geometry.holes import parametric_profile, place_hole
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps
from ocx_geometry.topology2d import (
    point_polyline_distance,
    polygon_ok,
    region_count,
)
from ocx_model_core.model.ir.base import ParentKind
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


def _resolve_catalogue_hole(vessel, ref):
    """IrHole2D behind a hole Ref (by local id, then by GUID), or None."""
    catalogue = vessel.hole_shape_catalogue
    if catalogue is None or ref is None:
        return None
    hole = catalogue.holes.get(ref.local_ref)
    if hole is None and ref.guidref:
        for candidate in catalogue.holes.values():
            if candidate.guidref == ref.guidref:
                return candidate
    return hole


def _open_ring(pts: np.ndarray) -> np.ndarray:
    """Drop an exactly-repeated closing point.

    Shapely's ``split`` treats an exactly-closed interior ring as a splitter
    (inner disk + remainder), which would flag every normal hole. Open rings
    keep interior holes as one region while a ring crossing the plate
    outline still splits it.
    """
    if len(pts) > 3 and np.linalg.norm(pts[0] - pts[-1]) < 1e-12:
        return pts[:-1]
    return pts


def _placed_hole_outlines(context, cut_by_holes, cut_by_contours,
                          tol_m=_SAMPLE_TOL_M):
    """3D hole outlines in metres from CutBy data -> (outlines, n_skipped).

    Catalogue holes (``IrHole2DContour``) are profiled (parametric or
    sampled contour) and mapped through their placement frame; inline
    cut-by contours are already in model space and only sampled.
    """
    geo = context.geometry
    outlines: list[np.ndarray] = []
    skipped = 0
    for hc in cut_by_holes:
        hole = _resolve_catalogue_hole(context.vessel, hc.hole_ref)
        profile = None
        if hole is not None:
            if hole.parametric is not None:
                profile = parametric_profile(hole.parametric, geo.length, tol_m)
            elif hole.contour is not None:
                profile = geo.sample(hole.contour, tol_m)
        placed = None
        if profile is not None and len(profile) >= 3:
            placed = place_hole(np.asarray(profile, dtype=float),
                                hc.transformation, geo.length)
        if placed is None:
            skipped += 1
        else:
            outlines.append(_open_ring(placed))
    for contour in cut_by_contours:
        pts = geo.sample(contour, tol_m)
        if pts is None or len(pts) < 3:
            skipped += 1
        else:
            outlines.append(_open_ring(pts))
    return outlines, skipped


def hole_not_splitting_plate(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-004: a hole must not split a plate into disjoint regions."""
    findings: list[Finding] = []
    geo = context.geometry
    vessel = context.vessel
    for pid, plate in vessel.plates.items():
        if not plate.cut_by_holes and not plate.cut_by_contours:
            continue
        panel = None
        pr = plate.parent_ref
        if pr is not None and pr.kind == ParentKind.PANEL:
            panel = vessel.panels.get(pr.id)
        if panel is None:
            logger.debug("TOP-004: plate {} skipped (no owning panel)", pid)
            continue
        param = geo.surface_param(geo.panel_surface(panel))
        if param is None:
            logger.debug("TOP-004: plate {} skipped (no buildable panel "
                         "surface)", pid)
            continue
        if param.periodic_u:
            logger.debug("TOP-004: plate {} skipped (periodic surface, "
                         "ambiguous UV mapping)", pid)
            continue
        outline = geo.sample(plate.outer_contour)
        if outline is None or len(outline) < 3:
            logger.debug("TOP-004: plate {} skipped (unsampleable outer "
                         "contour)", pid)
            continue
        holes_3d, skipped = _placed_hole_outlines(
            context, plate.cut_by_holes, plate.cut_by_contours)
        if skipped:
            logger.debug("TOP-004: plate {}: {} hole(s) could not be "
                         "placed; skipped", pid, skipped)
        if not holes_3d:
            continue
        try:
            outline_uv = np.asarray(param.inverse(outline), dtype=float)
            cuts_uv = [np.asarray(param.inverse(h), dtype=float)
                       for h in holes_3d]
        except Exception as exc:  # noqa: BLE001 — lean-pass on UV failure
            logger.debug("TOP-004: plate {} skipped (UV mapping failed: {})",
                         pid, exc)
            continue
        n = region_count(outline_uv, cuts_uv)
        if n > 1:
            findings.append(Finding(
                message=f"Hole splits plate into {n} regions",
                element_id=pid, guid=plate.guidref))
    return findings


def seam_topology(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-005: seam endpoints must not land on hole contours."""
    tol_m = float(params.get("tolerance_mm", 5.0)) / 1000.0
    findings: list[Finding] = []
    geo = context.geometry
    vessel = context.vessel
    for pid, panel in vessel.panels.items():
        seams = [(sid, vessel.seams[sid]) for sid in panel.seam_ids
                 if sid in vessel.seams]
        if not seams:
            continue
        boundary, _ = _panel_boundary_samples(context, panel)
        cut_holes = list(panel.cut_by_holes)
        cut_contours = list(panel.cut_by_contours)
        for plate_id in panel.plate_ids:
            plate = vessel.plates.get(plate_id)
            if plate is not None:
                cut_holes += plate.cut_by_holes
                cut_contours += plate.cut_by_contours
        hole_outlines, _ = _placed_hole_outlines(context, cut_holes,
                                                 cut_contours)
        seam_samples: dict[str, np.ndarray] = {}
        for sid, seam in seams:
            pts = geo.sample(seam.trace_line)
            if pts is None or len(pts) < 2:
                logger.debug("TOP-005: seam {} on panel {} skipped "
                             "(unsampleable trace)", sid, pid)
                continue
            seam_samples[sid] = pts
        if not hole_outlines:
            continue
        for sid, pts in seam_samples.items():
            seam = vessel.seams[sid]
            non_hole = boundary + [p for osid, p in seam_samples.items()
                                   if osid != sid]
            for label, endpoint in (("start", pts[0]), ("end", pts[-1])):
                d_hole = min((point_polyline_distance(endpoint, h)
                              for h in hole_outlines), default=float("inf"))
                d_other = min((point_polyline_distance(endpoint, c)
                               for c in non_hole), default=float("inf"))
                if d_hole <= tol_m and d_hole < d_other:
                    findings.append(Finding(
                        message=(f"Seam {label} endpoint lies on a hole "
                                 f"contour ({d_hole * 1000:.2f} mm away, "
                                 f"tolerance {tol_m * 1000:.2f} mm)"),
                        element_id=sid, guid=seam.guidref))
    return findings


_ADJACENCY_TOL_M = 0.001   # boundary proximity that makes two members adjacent
_MAX_SHARED_SAMPLES = 5    # normal evaluations per adjacent member pair


def _normal_at(param, point: np.ndarray) -> np.ndarray | None:
    """Unit surface normal of ``param`` at the UV nearest ``point``, or None."""
    uv = np.asarray(param.inverse(np.asarray([point], dtype=float)), dtype=float)
    du, dv = param.first_derivs(uv)
    n = np.cross(du[0], dv[0])
    norm = float(np.linalg.norm(n))
    if not np.isfinite(norm) or norm < 1e-12:
        return None
    return n / norm


def surface_normals_and_boundaries(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-008: normals must be consistent across a surface collection."""
    tol_deg = float(params.get("angle_tolerance_deg", 90.0))
    findings: list[Finding] = []
    geo = context.geometry
    for cid, coll in context.vessel.surface_collections.items():
        members = []
        for surf in coll.surfaces:
            geom = surf.geometry
            boundary = geo.sample(getattr(geom, "face_boundary_curve", None))
            param = geo.surface_param(geom)
            if param is None or boundary is None or len(boundary) < 2:
                logger.debug("TOP-008: member {} of collection {} skipped "
                             "(no buildable surface or boundary)", surf.id, cid)
                continue
            members.append((surf, param, boundary))
        if len(members) < 2:
            logger.debug("TOP-008: collection {} skipped "
                         "(fewer than 2 buildable members)", cid)
            continue
        for i in range(len(members)):
            surf_a, param_a, bnd_a = members[i]
            for surf_b, param_b, bnd_b in members[i + 1:]:
                try:
                    # Symmetric point-to-segment proximity: vertices of one
                    # boundary may lie on the interior of the other's
                    # segments (e.g. T-configurations without shared
                    # corners), so check both directions.
                    cand = (
                        [(point_polyline_distance(p, bnd_b), p) for p in bnd_a]
                        + [(point_polyline_distance(p, bnd_a), p) for p in bnd_b]
                    )
                except Exception as exc:  # noqa: BLE001 — lean-pass per pair
                    logger.debug("TOP-008: pair {}/{} skipped ({})",
                                 surf_a.id, surf_b.id, exc)
                    continue
                close = sorted((c for c in cand if c[0] <= _ADJACENCY_TOL_M),
                               key=lambda c: c[0])
                if not close:
                    continue  # not adjacent
                angles = []
                for _, p in close[:_MAX_SHARED_SAMPLES]:
                    try:
                        na = _normal_at(param_a, p)
                        nb = _normal_at(param_b, p)
                    except Exception as exc:  # noqa: BLE001 — skip sample
                        logger.debug("TOP-008: normal evaluation failed for "
                                     "{}/{}: {}", surf_a.id, surf_b.id, exc)
                        continue
                    if na is None or nb is None:
                        continue
                    dot = float(np.clip(na @ nb, -1.0, 1.0))
                    angles.append(np.degrees(np.arccos(dot)))
                if not angles:
                    logger.debug("TOP-008: pair {}/{} skipped (no evaluable "
                                 "shared boundary samples)", surf_a.id, surf_b.id)
                    continue
                angle = float(np.median(angles))
                if angle > tol_deg:
                    findings.append(Finding(
                        message=(f"Surface normals deviate across the shared "
                                 f"boundary with member {surf_b.id} in "
                                 f"collection {cid}: {angle:.1f} deg exceeds "
                                 f"{tol_deg:.1f} deg"),
                        element_id=surf_a.id, guid=surf_a.guidref))
    return findings


_DUP_POSITION_TOL_M = 1e-6


def _inclination_positions(geo, entries) -> list[np.ndarray | None]:
    """Inclination positions in metres (None where missing/unparseable)."""
    out: list[np.ndarray | None] = []
    for entry in entries:
        pos = getattr(entry, "position", None)
        if pos is None:
            out.append(None)
            continue
        try:
            out.append(np.asarray(geo.length.point(pos), dtype=float))
        except Exception as exc:  # noqa: BLE001 — skip entry
            logger.debug("TOP-009: unparseable inclination position: {}", exc)
            out.append(None)
    return out


def _direction_flip(entries, field: str) -> tuple[int, int] | None:
    """First consecutive pair of inclination entries whose ``field`` vectors
    have a negative dot product (entries without the vector are skipped)."""
    prev_idx: int | None = None
    prev_vec: np.ndarray | None = None
    for i, entry in enumerate(entries):
        v = getattr(entry, field, None)
        if v is None:
            continue
        vec = np.array([v.x, v.y, v.z], dtype=float)
        if not np.isfinite(vec).all() or np.linalg.norm(vec) < 1e-12:
            continue
        if prev_vec is not None and float(prev_vec @ vec) < 0.0:
            return prev_idx, i
        prev_idx, prev_vec = i, vec
    return None


def stiffener_inclinations(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-009: inclination series must be duplicate-free and smooth."""
    findings: list[Finding] = []
    geo = context.geometry
    vessel = context.vessel
    members = list(vessel.stiffeners.items()) + list(vessel.pillars.items())
    for mid, member in members:
        entries = getattr(member, "inclinations", None) or []
        if len(entries) < 2:
            continue
        positions = _inclination_positions(geo, entries)
        dup = next(((i, j)
                    for i in range(len(positions))
                    for j in range(i + 1, len(positions))
                    if positions[i] is not None and positions[j] is not None
                    and np.linalg.norm(positions[i] - positions[j])
                    < _DUP_POSITION_TOL_M), None)
        if dup is not None:
            findings.append(Finding(
                message=(f"Duplicate inclination position: entries {dup[0]} "
                         f"and {dup[1]} are less than "
                         f"{_DUP_POSITION_TOL_M:g} m apart"),
                element_id=mid, guid=member.guidref))
        for field, label in (("web_direction", "Web"),
                             ("flange_direction", "Flange")):
            flip = _direction_flip(entries, field)
            if flip is not None:
                findings.append(Finding(
                    message=(f"{label} direction flips between inclination "
                             f"entries {flip[0]} and {flip[1]} "
                             f"(negative dot product)"),
                    element_id=mid, guid=member.guidref))
    return findings
