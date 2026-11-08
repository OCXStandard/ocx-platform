"""Stiffener → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrStiffener

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "stiffener"


def extract(stiffener: IrStiffener, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND,
            stiffener,
            ctx,
            function_type=stiffener.function_type,
            parent=ctx.parent(stiffener.parent_ref),
        ),
        "material": material_aspect(KIND, stiffener.material_ref, ctx),
        "scantlings": bar_scantlings(
            KIND,
            stiffener,
            ctx,
            end_cut_end1=stiffener.end_cut_end1,
            end_cut_end2=stiffener.end_cut_end2,
        ),
        "geometry": make_record(
            KIND,
            trace=c(stiffener.trace),
            trace_refs=ctx.canon_set(stiffener.trace_refs),
            inclinations=c(stiffener.inclinations),
            orientation_rule=stiffener.orientation_rule,
            penetrations=ctx.canon_set(stiffener.penetrations),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(stiffener.mass_properties),
            curve_lengths=curve_lengths(ctx, trace=stiffener.trace),
        ),
    }
