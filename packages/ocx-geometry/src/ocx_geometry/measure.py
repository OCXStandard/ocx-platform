"""Length, area and closure measurements on IR geometry."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from loguru import logger
from ocx_model_core.model.ir.base import IrUnit, Quantity
from ocx_model_core.model.ir.geometry import IrPoint3D


def polyline_length(points: Sequence[IrPoint3D]) -> float:
    """Total length of the polyline through *points*, in the points' own units."""
    if len(points) < 2:
        return 0.0
    coords = np.array([(p.x, p.y, p.z) for p in points], dtype=float)
    return float(np.linalg.norm(np.diff(coords, axis=0), axis=1).sum())


# Fallback factors for models without a usable unit registry (bare fragments).
_FALLBACK_TO_M = {"Um": 1.0, "Umm": 1e-3, "Ucm": 1e-2, "Udm": 0.1, "Ukm": 1e3}


class LengthResolver:
    """Resolve OCX unit ids to metres, with graceful fallbacks."""

    def __init__(self, registry: dict[str, IrUnit] | None) -> None:
        self._registry = registry or {}
        self._warned: set[str] = set()

    def to_m(self, value: float, unit_id: str) -> float:
        unit = self._registry.get(unit_id)
        if unit is not None:
            return value * unit.to_si_factor
        factor = _FALLBACK_TO_M.get(unit_id)
        if factor is not None:
            return value * factor
        if unit_id not in self._warned:
            self._warned.add(unit_id)
            logger.warning("Unknown length unit id {!r}; assuming metres", unit_id)
        return value

    def point(self, p: IrPoint3D) -> np.ndarray:
        return np.array([self.to_m(p.x, p.unit),
                         self.to_m(p.y, p.unit),
                         self.to_m(p.z, p.unit)], dtype=np.float64)

    def qty(self, q: Quantity | None) -> float | None:
        if q is None:
            return None
        return self.to_m(q.value, q.unit)
