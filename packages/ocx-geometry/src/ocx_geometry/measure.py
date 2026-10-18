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


def chain_polylines(
    polylines: list[np.ndarray],
) -> tuple[np.ndarray | None, list[float]]:
    """Greedily chain 3-D polylines end-to-end into one loop.

    Segments are always attached at their nearest endpoints and every junction
    gap is recorded. Returns ``(ring, gaps)`` where ``ring`` is the (N, 3)
    chained polyline (not explicitly closed) and ``gaps`` has one entry per
    junction plus a final entry for the closure gap ring-end -> ring-start.
    Returns ``(None, [])`` when no usable polylines are given. Never raises.

    Intended for inputs that form a closed loop: segments attach only at the
    growing chain tail, so open chains whose first segment is interior will
    report inflated gaps.
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if not parts:
        return None, []
    out = parts[0]
    remaining = parts[1:]
    gaps: list[float] = []
    while remaining:
        tail = out[-1]
        best_i, best_d, best_rev = 0, np.inf, False
        for i, pts in enumerate(remaining):
            d0 = float(np.linalg.norm(pts[0] - tail))
            d1 = float(np.linalg.norm(pts[-1] - tail))
            if d0 < best_d:
                best_i, best_d, best_rev = i, d0, False
            if d1 < best_d:
                best_i, best_d, best_rev = i, d1, True
        pts = remaining.pop(best_i)
        if best_rev:
            pts = pts[::-1]
        gaps.append(best_d)
        out = np.vstack([out, pts])
    gaps.append(float(np.linalg.norm(out[-1] - out[0])))
    return out, gaps


def ordered_junction_gaps(polylines: list[np.ndarray]) -> list[float]:
    """Junction gaps between consecutive polylines in their declared order.

    Each segment may be used reversed; the orientation minimising the gap to
    the current chain end is chosen. Returns one gap per junction (no closure
    gap).
    """
    parts = [np.asarray(p, dtype=float) for p in polylines
             if p is not None and len(p) >= 2]
    if len(parts) < 2:
        return []
    # orient the first segment so its far end best meets segment 2
    first, second = parts[0], parts[1]
    ends_fwd = min(float(np.linalg.norm(first[-1] - second[0])),
                   float(np.linalg.norm(first[-1] - second[-1])))
    ends_rev = min(float(np.linalg.norm(first[0] - second[0])),
                   float(np.linalg.norm(first[0] - second[-1])))
    tail = first[0] if ends_rev < ends_fwd else first[-1]
    gaps: list[float] = []
    for pts in parts[1:]:
        d0 = float(np.linalg.norm(pts[0] - tail))
        d1 = float(np.linalg.norm(pts[-1] - tail))
        if d1 < d0:
            gaps.append(d1)
            tail = pts[0]
        else:
            gaps.append(d0)
            tail = pts[-1]
    return gaps
