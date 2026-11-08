"""Panel → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrLimitedByRef, IrPanel, IrUnboundedGeometry, Ref

from ocx_integrity.jsonutil import prune, sort_jcs
from ocx_integrity.records.common import (
    Context,
    catalogue_record,
    curve_lengths,
    hole_placement,
    identity,
    make_record,
)

KIND = "panel"


def _children(panel: IrPanel, ctx: Context) -> dict[str, list[Any]]:
    groups = {
        "plates": panel.plate_ids,
        "stiffeners": panel.stiffener_ids,
        "brackets": panel.bracket_ids,
        "pillars": panel.pillar_ids,
        "edge_reinforcements": panel.edge_reinforcement_ids,
        "seams": panel.seam_ids,
    }
    return {name: ctx.canon_set([Ref(i) for i in ids]) for name, ids in groups.items()}


def _limit(lb: IrLimitedByRef, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    if lb.ref_type == "FreeEdgeCurve3D":
        target = c(lb.curve)
    else:
        target = ctx.resolve(Ref(lb.local_ref, lb.guidref))
    return prune(
        {
            "ref_type": lb.ref_type,
            "target": target,
            "offset": c(lb.offset),
            "offset_direction": c(lb.offset_direction),
            "contour_start": c(lb.contour_start),
            "contour_end": c(lb.contour_end),
            "contour_mid_point": c(lb.contour_mid_point),
        }
    )


def _unbounded(ug: IrUnboundedGeometry | None, ctx: Context) -> dict[str, Any] | None:
    """Inline the panel's surface: direct, via SurfaceRef, or via GridRef (ref plane)."""
    if ug is None:
        return None
    if ug.surface is not None:
        return {"surface": ctx.canon(ug.surface)}
    if ug.surface_ref:
        surface = ctx.lookup(Ref(ug.surface_ref), ctx.vessel.surfaces, "surface")
        return {
            "surface_ref": catalogue_record(surface, ctx)
            if surface
            else {"unresolved": ug.surface_ref}
        }
    if ug.grid_ref:
        plane = ctx.lookup(Ref(ug.grid_ref), ctx.vessel.ref_planes, "grid")
        return {"grid_ref": catalogue_record(plane, ctx) if plane else {"unresolved": ug.grid_ref}}
    return None


def extract(panel: IrPanel, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND,
            panel,
            ctx,
            function_type=panel.function_type,
            tightness=panel.tightness,
            children=_children(panel, ctx),
        ),
        "geometry": make_record(
            KIND,
            unbounded_geometry=_unbounded(panel.unbounded_geometry, ctx),
            limited_by=sort_jcs(_limit(lb, ctx) for lb in panel.limited_by),
            outer_contours=ctx.canon_set(panel.outer_contours),
            cut_by_contours=ctx.canon_set(panel.cut_by_contours),
            cut_by_holes=sort_jcs(hole_placement(h, ctx) for h in panel.cut_by_holes),
            point_on_surface=c(panel.point_on_surface),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(panel.mass_properties),
            curve_lengths=curve_lengths(
                ctx, outer_contours=panel.outer_contours, cut_by_contours=panel.cut_by_contours
            ),
        ),
    }
