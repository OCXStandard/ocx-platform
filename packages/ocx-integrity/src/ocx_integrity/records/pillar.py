"""Pillar → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrPillar

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "pillar"


def extract(pillar: IrPillar, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND,
            pillar,
            ctx,
            function_type=pillar.function_type,
            parent=ctx.parent(pillar.parent_ref),
        ),
        "material": material_aspect(KIND, pillar.material_ref, ctx),
        "scantlings": bar_scantlings(KIND, pillar, ctx),
        "geometry": make_record(
            KIND,
            trace=c(pillar.trace),
            inclinations=c(pillar.inclinations),
            penetrations=ctx.canon_set(pillar.penetrations),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(pillar.mass_properties),
            curve_lengths=curve_lengths(ctx, trace=pillar.trace),
        ),
    }
