"""Length, area and closure measurements on IR geometry."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from ocx_model_core.model.ir.geometry import IrPoint3D


def polyline_length(points: Sequence[IrPoint3D]) -> float:
    """Total length of the polyline through *points*, in the points' own units."""
    if len(points) < 2:
        return 0.0
    coords = np.array([(p.x, p.y, p.z) for p in points], dtype=float)
    return float(np.linalg.norm(np.diff(coords, axis=0), axis=1).sum())
