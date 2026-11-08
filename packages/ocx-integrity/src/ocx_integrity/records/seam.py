"""Seam → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrSeam

from ocx_integrity.records.common import Context, curve_lengths, identity, make_record

KIND = "seam"


def extract(seam: IrSeam, ctx: Context) -> dict[str, Any]:
    return {
        "identity": identity(KIND, seam, ctx),
        "geometry": make_record(
            KIND,
            trace_line=ctx.canon(seam.trace_line),
            trace_refs=ctx.canon_set(seam.trace_refs),
        ),
        "physical": make_record(KIND, curve_lengths=curve_lengths(ctx, trace_line=seam.trace_line)),
    }
