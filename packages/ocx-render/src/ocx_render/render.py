"""Tessellated 3D renderer — public API.

``render_model(vessel, options)`` tessellates all renderable parts of an
``IrVessel`` into ``PartMesh`` objects.  Single-part failures are recorded
in ``RenderResult.skipped`` and never abort the render.
"""
from __future__ import annotations

import time

import numpy as np
from loguru import logger
from ocx_geometry.backend import (
    ITessellator,
    RenderResult,
    TessellationOptions,
)
from ocx_geometry.curves import sample_contour, sample_curve
from ocx_geometry.diagnostics import ChartDiag, PlateDiag
from ocx_geometry.holes import parametric_profile, place_hole
from ocx_geometry.lscm import make_lscm_chart
from ocx_geometry.measure import LengthResolver
from ocx_geometry.mesh import PartMesh
from ocx_geometry.mesh_trim import MeshTrimmer
from ocx_geometry.sections_2d import fallback_polygon, section_polygon
from ocx_geometry.surfaces import (
    SurfaceParam,
    make_param,
)
from ocx_geometry.sweep import (
    insert_trace_points,
    resolve_web_dirs,
    sweep_profile,
)
from ocx_geometry.uv_tessellator import UvTessellator
from ocx_model_core.model.ir.base import IrVector3D, ParentKind
from ocx_model_core.model.ir.geometry import IrPlane3D, IrPoint3D, IrRefPlane
from ocx_model_core.model.ir.structural import IrPanel, IrVessel

__all__ = ["render_model", "RenderResult", "TessellationOptions", "PartMesh"]


_AXIS_VECTORS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _plane_from_ref_plane(rp: IrRefPlane, vessel: IrVessel) -> IrPlane3D | None:
    """Synthesize a plane from a grid ref plane's axis + scalar location."""
    if rp.location is None:
        return None
    axis = None
    for cs in vessel.coordinate_systems.values():
        if rp.id in cs.x_ref_plane_ids:
            axis = "x"
        elif rp.id in cs.y_ref_plane_ids:
            axis = "y"
        elif rp.id in cs.z_ref_plane_ids:
            axis = "z"
        if axis:
            break
    if axis is None:
        return None
    nx, ny, nz = _AXIS_VECTORS[axis]
    loc = rp.location.value
    return IrPlane3D(
        id=rp.id,
        point_on_surface=IrPoint3D(nx * loc, ny * loc, nz * loc,
                                   rp.location.unit),
        normal=IrVector3D(nx, ny, nz))


def _resolve_panel_surfaces(panel: IrPanel, vessel: IrVessel) -> list:
    """All candidate surface geometries for a panel (usually exactly one)."""
    ug = panel.unbounded_geometry
    if ug is None:
        return []
    if ug.surface is not None:
        return [ug.surface]
    if ug.surface_ref:
        s = vessel.surfaces.get(ug.surface_ref)
        if s is not None and s.geometry is not None:
            return [s.geometry]
        coll = vessel.surface_collections.get(ug.surface_ref)
        if coll is not None:
            return [m.geometry for m in coll.surfaces if m.geometry is not None]
        for coll in vessel.surface_collections.values():
            for member in coll.surfaces:
                if member.id == ug.surface_ref and member.geometry is not None:
                    return [member.geometry]
        return []
    if ug.grid_ref:
        rp = vessel.ref_planes.get(ug.grid_ref)
        if rp is not None:
            if rp.reference_plane is not None:
                return [rp.reference_plane]
            plane = _plane_from_ref_plane(rp, vessel)
            return [plane] if plane is not None else []
    return []


def _best_param(candidates: list[SurfaceParam],
                contour: np.ndarray) -> SurfaceParam:
    """Pick the candidate whose surface lies closest to the contour."""
    if len(candidates) == 1:
        return candidates[0]
    sample = contour[:: max(1, len(contour) // 8)]
    best, best_res = candidates[0], float("inf")
    for cand in candidates:
        try:
            uv = cand.inverse(sample)
            res = float(np.linalg.norm(
                np.asarray(cand.evaluate(uv)) - sample, axis=1).mean())
        except Exception:  # noqa: BLE001 — candidate disqualifies itself
            continue
        if res < best_res:
            best, best_res = cand, res
    return best


def _hole_polylines(plate, panel, vessel: IrVessel, length: LengthResolver,
                    options: TessellationOptions
                    ) -> tuple[list[np.ndarray], dict[str, str]]:
    """All hole polylines for one plate: inline contours + resolved CutBy holes.

    Returns (hole polylines in metres, failures keyed
    ``<plate_id>/hole:<id>``).
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
        key = (f"{plate.id}/hole:"
               f"{hc.id or (hc.hole_ref.local_ref if hc.hole_ref else '?')}")
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
            # Keep the full 3D definition-space points: contour holes may
            # be authored in any plane; place_hole maps all three axes.
            profile = sample_contour(shape.contour, length, options.tolerance_m,
                                     options.snap_tolerance_m)
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


def _tessellate_plates(vessel: IrVessel,
                       params: dict[str, list[SurfaceParam]],
                       tess: ITessellator, length: LengthResolver,
                       options: TessellationOptions, result: RenderResult) -> None:
    # Pass 1: sample contours; collect them per panel as hints that bound
    # otherwise-unbounded chart members (planes, cylinders).
    prepared = []
    hints: dict[str, list[np.ndarray]] = {}
    for plate in vessel.plates.values():
        panel_id = (plate.parent_ref.id
                    if plate.parent_ref.kind == ParentKind.PANEL else None)
        if panel_id is None:
            result.skipped[plate.id] = "not parented to a panel"
            continue
        if options.only_panels is not None and panel_id not in options.only_panels:
            continue
        candidates = params.get(panel_id) or []
        if not candidates:
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
        prepared.append((plate, panel_id, candidates, contour))
        hints.setdefault(panel_id, []).append(contour)

    # Pass 2: one LSCM chart mesh per multi-member panel, shared by its
    # plates; each plate flattens only its local submesh (a whole-panel
    # conformal flattening degenerates on doubly-curved panels).
    chart_cache: dict[str, object] = {}
    trim_cache: dict[str, MeshTrimmer] = {}
    n_total = len(prepared)
    t_pass2 = time.perf_counter()
    logger.debug("Timing: pass 1 prepared {} plates ({} panels with charts "
                 "needed)", n_total,
                 sum(1 for p in prepared if len(p[2]) > 1))
    for idx, (plate, panel_id, candidates, contour) in enumerate(prepared, 1):
        t_plate = time.perf_counter()
        sink = options.diag
        pdiag = None
        if sink is not None:
            pdiag = PlateDiag(plate_id=plate.id, panel_id=panel_id,
                              candidates=list(candidates), contour=contour,
                              max_snap_m=max(30.0 * options.tolerance_m, 1.5))
            sink.plates[plate.id] = pdiag
        route = "single"
        local = None
        pm = None
        panel = vessel.panels.get(panel_id)
        holes, hole_failures = _hole_polylines(plate, panel, vessel, length,
                                               options)
        for key, reason in hole_failures.items():
            logger.warning("CutBy hole not applied to {} — {} ({})",
                           plate.id, reason, key)
        result.skipped.update(hole_failures)
        if len(candidates) > 1:
            if panel_id not in chart_cache:
                t_chart = time.perf_counter()
                cdiag = (sink.charts.setdefault(panel_id, ChartDiag())
                         if sink is not None else None)
                chart_cache[panel_id] = make_lscm_chart(
                    candidates, options.tolerance_m,
                    np.vstack(hints[panel_id]), diag=cdiag)
                if cdiag is not None:
                    cdiag.build_s = time.perf_counter() - t_chart
                logger.debug("Timing: LSCM chart for panel {} "
                             "({} members) in {:.2f}s", panel_id,
                             len(candidates), time.perf_counter() - t_chart)
            chart = chart_cache[panel_id]
            if chart is not None:
                if panel_id not in trim_cache:
                    trim_cache[panel_id] = MeshTrimmer(*chart.mesh,
                                                       options.tolerance_m)
                seed = (length.point(plate.point_on_surface)
                        if plate.point_on_surface is not None else None)
                try:
                    out = trim_cache[panel_id].trim(contour, holes, seed,
                                                    diag=pdiag)
                except Exception as exc:  # noqa: BLE001 — fall back below
                    logger.debug("Mesh trim failed for {}: {}", plate.id, exc)
                    if pdiag is not None:
                        pdiag.trim_reject = f"exception: {exc}"
                    out = None
                if out is not None and len(out[1]):
                    pm = PartMesh(part_id=plate.id,
                                  name=plate.name or plate.id, kind="plate",
                                  vertices=out[0], triangles=out[1],
                                  normals=out[2])
                    route = "mesh-trim"
            if pm is None:
                local = chart.param_for(contour) if chart is not None else None
                if pdiag is not None and chart is not None:
                    pdiag.chart_stage = chart.last_stage
                param = local or _best_param(candidates, contour)
                route = "lscm" if local is not None else "best-member"
        else:
            param = candidates[0]
        t_param = time.perf_counter()
        if pm is None:
            pm = tess.tessellate_trimmed_surface(
                plate.id, plate.name or plate.id, "plate", contour, holes,
                param, options)
        if pm is None and local is not None:
            # chart built but this contour would not triangulate on it:
            # retry once on the best single member before giving up
            pm = tess.tessellate_trimmed_surface(
                plate.id, plate.name or plate.id, "plate", contour, holes,
                _best_param(candidates, contour), options)
            route = "best-member"
        if pm is None:
            result.skipped[plate.id] = "triangulation failed"
            continue
        pm.extras.update({"id": plate.id, "guid": plate.guidref,
                          "kind": "plate", "functionType": plate.function_type,
                          "panel_id": panel_id})
        result.meshes.append(pm)
        if pdiag is not None:
            pdiag.route = route
            pdiag.local_param = local
            pdiag.chart = sink.charts.get(panel_id)
            pdiag.seconds = time.perf_counter() - t_plate
        logger.debug("Timing: plate {}/{} {} param {:.2f}s, total {:.2f}s "
                     "(elapsed {:.0f}s)", idx, n_total, plate.id,
                     t_param - t_plate, time.perf_counter() - t_plate,
                     time.perf_counter() - t_pass2)


def _sweep_part(part, kind: str, vessel: IrVessel, length: LengthResolver,
                options: TessellationOptions, result: RenderResult) -> None:
    if part.trace is None:
        result.skipped[part.id] = "no trace"
        return
    pts = sample_curve(part.trace, length, options.tolerance_m)
    if pts is None or len(pts) < 2:
        result.skipped[part.id] = "trace sampling error or open trace"
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
        pts = insert_trace_points(pts, positions)
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
    t_start = time.perf_counter()

    params: dict[str, list[SurfaceParam]] = {}
    for pid, panel in vessel.panels.items():
        if options.only_panels is not None and pid not in options.only_panels:
            continue
        surfs = _resolve_panel_surfaces(panel, vessel)
        built = (make_param(s, length, options.tolerance_m) for s in surfs)
        params[pid] = [p for p in built if p is not None]
    t_params = time.perf_counter()
    logger.debug("Timing: surface params for {} panels in {:.2f}s",
                 len(params), t_params - t_start)

    _tessellate_plates(vessel, params, tess, length, options, result)
    t_plates = time.perf_counter()
    logger.debug("Timing: plates done in {:.2f}s", t_plates - t_params)
    for stiffener in vessel.stiffeners.values():
        _sweep_part(stiffener, "stiffener", vessel, length, options, result)
    t_stiff = time.perf_counter()
    logger.debug("Timing: {} stiffeners in {:.2f}s",
                 len(vessel.stiffeners), t_stiff - t_plates)
    for pillar in vessel.pillars.values():
        _sweep_part(pillar, "pillar", vessel, length, options, result)
    logger.debug("Timing: {} pillars in {:.2f}s", len(vessel.pillars),
                 time.perf_counter() - t_stiff)
    logger.debug("Timing: render_model total {:.2f}s",
                 time.perf_counter() - t_start)

    # Hole failures (keys containing "/hole:") are not skipped parts.
    part_skips = sum(1 for k in result.skipped if "/hole:" not in k)
    logger.info("Render: {} parts tessellated, {} skipped",
                result.rendered_count, part_skips)
    if result.skipped:
        for part_id, reason in result.skipped.items():
            logger.debug("Skipped {}: {}", part_id, reason)
    return result
