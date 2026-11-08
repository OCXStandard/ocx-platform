"""Plate → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrPlate

from ocx_integrity.jsonutil import sort_jcs
from ocx_integrity.records.common import (
    Context,
    curve_lengths,
    hole_placement,
    identity,
    make_record,
    material_aspect,
)

KIND = "plate"


def extract(plate: IrPlate, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND, plate, ctx, function_type=plate.function_type, parent=ctx.parent(plate.parent_ref)
        ),
        "material": material_aspect(KIND, plate.material_ref, ctx),
        "scantlings": make_record(
            KIND,
            thickness=c(plate.thickness),
            renewal_thickness=c(plate.renewal_thickness),
            voluntary_thickness_addition=c(plate.voluntary_thickness_addition),
        ),
        "geometry": make_record(
            KIND,
            outer_contour=c(plate.outer_contour),
            cut_by_contours=ctx.canon_set(plate.cut_by_contours),
            cut_by_holes=sort_jcs(hole_placement(h, ctx) for h in plate.cut_by_holes),
            point_on_surface=c(plate.point_on_surface),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(plate.mass_properties),
            net_area=c(plate.net_area),
            curve_lengths=curve_lengths(
                ctx, outer_contour=plate.outer_contour, cut_by_contours=plate.cut_by_contours
            ),
        ),
    }
