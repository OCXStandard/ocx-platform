"""Vessel metadata → canonical identity record (IrHeader is deliberately not hashed)."""

from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.records.common import Context, make_record

KIND = "vessel"


def extract(vessel: IrVessel, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": make_record(
            KIND,
            id_source="vessel",
            name=vessel.name,
            ship_designation=c(vessel.ship_designation),
            principal_particulars=c(vessel.principal_particulars),
            builder_info=c(vessel.builder_info),
            statutory_data=c(vessel.statutory_data),
            tonnage_data=c(vessel.tonnage_data),
        ),
    }
