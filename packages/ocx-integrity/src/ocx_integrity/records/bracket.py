"""Bracket → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrBracket

from ocx_integrity.records.common import (
    Context,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "bracket"


def extract(bracket: IrBracket, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, bracket, ctx, parent=ctx.parent(bracket.parent_ref)),
        "material": material_aspect(KIND, bracket.material_ref, ctx),
        "scantlings": make_record(
            KIND,
            thickness=c(bracket.thickness),
            renewal_thickness=c(bracket.renewal_thickness),
            voluntary_thickness_addition=c(bracket.voluntary_thickness_addition),
            arm_length_u=c(bracket.arm_length_u),
            arm_length_v=c(bracket.arm_length_v),
            unose=c(bracket.unose),
            vnose=c(bracket.vnose),
            free_edge_radius=c(bracket.free_edge_radius),
            has_edge_reinforcement=bracket.has_edge_reinforcement,
            number_of_supports=bracket.number_of_supports,
            reinforcement_type=bracket.reinforcement_type,
            flange_width=c(bracket.flange_width),
            flange_radius=c(bracket.flange_radius),
            feature_cope=c(bracket.feature_cope),
        ),
        "geometry": make_record(
            KIND,
            origin=c(bracket.origin),
            udirection=c(bracket.udirection),
            vdirection=c(bracket.vdirection),
            outer_contour=c(bracket.outer_contour),
            plane=c(bracket.plane),
            offset=c(bracket.offset),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(bracket.mass_properties),
            curve_lengths=curve_lengths(ctx, outer_contour=bracket.outer_contour),
        ),
    }
