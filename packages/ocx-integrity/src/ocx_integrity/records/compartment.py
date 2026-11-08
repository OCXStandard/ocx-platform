"""Compartment → canonical aspect records."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrCompartment

from ocx_integrity.records.common import Context, curve_lengths, identity, make_record

KIND = "compartment"


def extract(comp: IrCompartment, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND,
            comp,
            ctx,
            compartment_purpose=comp.compartment_purpose,
            filling_height=comp.filling_height,
            air_pipe_height=comp.air_pipe_height,
            relief_valve_pressure=comp.relief_valve_pressure,
        ),
        "geometry": make_record(
            KIND,
            face_refs=ctx.canon_set(comp.face_refs),
            face_boundary_curves=ctx.canon_set(comp.face_boundary_curves),
        ),
        "physical": make_record(
            KIND,
            volume=c(comp.volume),
            cog=c(comp.cog),
            curve_lengths=curve_lengths(ctx, face_boundary_curves=comp.face_boundary_curves),
        ),
    }
