"""Surface/plane intersection in metres (IR-independent)."""
from __future__ import annotations

import numpy as np


def offset_plane(point, normal,
                 offset_m: float) -> tuple[np.ndarray, np.ndarray]:
    """``(point shifted offset_m along the unit normal, unit normal)``."""
    n = np.asarray(normal, dtype=float)
    length = float(np.linalg.norm(n))
    if length < 1e-12:
        raise ValueError("plane normal must be non-zero")
    n = n / length
    return np.asarray(point, dtype=float) + float(offset_m) * n, n
