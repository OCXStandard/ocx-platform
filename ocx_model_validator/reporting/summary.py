"""Human-readable load summary for an :class:`IrVessel`."""
from __future__ import annotations

from ocx_model_validator.model.ir import IrVessel

_PART_FIELDS = (
    "panels",
    "plates",
    "stiffeners",
    "brackets",
    "pillars",
    "edge_reinforcements",
    "seams",
    "members",
    "materials",
    "sections",
    "compartments",
)


def model_summary(vessel: IrVessel) -> str:
    """Return a short multi-line summary of a loaded model.

    Includes the OCX header metadata and the part counts of the IR.
    """
    header = vessel.header
    if header is None:
        header_line = "Header: (none)"
    else:
        header_line = (
            f"Header: name={header.name!r} author={header.author!r} "
            f"organization={header.organization!r} "
            f"system={header.originating_system!r} "
            f"application_version={header.application_version!r} "
            f"time_stamp={header.time_stamp!r}"
        )
    counts = " ".join(
        f"{name}={len(getattr(vessel, name))}" for name in _PART_FIELDS
    )
    return "\n".join(
        [
            f"Loaded OCX model {vessel.name!r} (schema {vessel.schema_version})",
            header_line,
            f"Parts: {counts}",
        ]
    )
