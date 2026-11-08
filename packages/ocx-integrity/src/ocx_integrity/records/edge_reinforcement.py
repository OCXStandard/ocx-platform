"""Edge reinforcement → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrEdgeReinforcement

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    identity,
    make_record,
    material_aspect,
)

KIND = "edge_reinforcement"


def extract(er: IrEdgeReinforcement, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND, er, ctx, function_type=er.function_type, parent=ctx.parent(er.parent_ref)
        ),
        "material": material_aspect(KIND, er.material_ref, ctx),
        "scantlings": bar_scantlings(KIND, er, ctx),
        "geometry": make_record(
            KIND,
            trace_refs=ctx.canon_set(er.trace_refs),
            orientation_rule=er.orientation_rule,
        ),
        "physical": make_record(KIND, mass_properties=c(er.mass_properties)),
    }
