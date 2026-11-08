"""Profile ocx-hash/1 constants: aspect order, part kinds, quantisation precision."""

from __future__ import annotations

PROFILE = "ocx-hash/1"

ASPECTS: tuple[str, ...] = ("identity", "material", "scantlings", "geometry", "physical")

KINDS: tuple[str, ...] = (
    "vessel",
    "plate",
    "stiffener",
    "bracket",
    "pillar",
    "edge_reinforcement",
    "panel",
    "seam",
    "compartment",
)

DEFAULT_DECIMALS = 6

# Keyed on IrUnit.si_symbol (see ocx_model_core.model.units._DIM_TO_SI_SYMBOL).
DECIMALS_BY_SI_SYMBOL: dict[str, int] = {
    "m": 6,
    "m²": 6,
    "m³": 6,
    "m⁴": 9,
    "Pa": 0,
    "kg": 3,
    "kg/m³": 3,
    "m/s": 6,
    "N·m": 3,
}


def decimals_for(si_symbol: str) -> int:
    return DECIMALS_BY_SI_SYMBOL.get(si_symbol, DEFAULT_DECIMALS)
