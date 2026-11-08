"""Quantities, points and vectors → fixed-precision SI decimal strings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import ROUND_HALF_EVEN, Decimal

from ocx_model_core.model.ir import IrUnit, IrVector3D, Quantity

from ocx_integrity.profile import DEFAULT_DECIMALS, decimals_for


def _dec(value: float | Decimal) -> Decimal:
    # repr() gives the shortest round-tripping string, so 0.001 stays exactly 0.001.
    return value if isinstance(value, Decimal) else Decimal(repr(float(value)))


def fmt_decimal(value: float | Decimal, decimals: int) -> str:
    """Round half-even to ``decimals`` places; ``-0`` becomes ``0``; never a float."""
    d = _dec(value)
    if d.is_nan():
        return "NaN"
    if d.is_infinite():
        return "-Infinity" if d < 0 else "Infinity"
    q = d.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN)
    if q == 0:
        q = q.copy_abs()
    return format(q, "f")


class Quantizer:
    """Convert IR values to SI decimal strings using a vessel's unit registry."""

    def __init__(self, registry: Mapping[str, IrUnit], warn: Callable[[str], None]) -> None:
        self._registry = registry
        self._warn = warn

    def quantity(self, q: Quantity) -> str | dict[str, str]:
        unit = self._registry.get(q.unit)
        if unit is None:
            self._warn(f"unknown unit {q.unit!r}")
            return {"value": fmt_decimal(q.value, DEFAULT_DECIMALS), "unit": q.unit}
        return fmt_decimal(_dec(q.value) * _dec(unit.to_si_factor), decimals_for(unit.si_symbol))

    def point(self, p) -> list[str]:
        """``IrPoint3D`` or ``IrCog`` → ``[x, y, z]`` (``[x, y, z, unit]`` if unit unknown)."""
        coords = (p.x, p.y, p.z)
        unit = self._registry.get(p.unit)
        if unit is None:
            self._warn(f"unknown unit {p.unit!r}")
            return [fmt_decimal(c, DEFAULT_DECIMALS) for c in coords] + [p.unit]
        factor = _dec(unit.to_si_factor)
        decimals = decimals_for(unit.si_symbol)
        return [fmt_decimal(_dec(c) * factor, decimals) for c in coords]

    def scalar(self, value: float) -> str:
        return fmt_decimal(value, DEFAULT_DECIMALS)

    def vector(self, v: IrVector3D) -> list[str]:
        return [self.scalar(c) for c in (v.x, v.y, v.z)]
