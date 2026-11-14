"""Grid reference planes: an axis-aligned plane from an axis and a location."""
from __future__ import annotations

import numpy as np

_AXES = {"x": 0, "y": 1, "z": 2}


def grid_plane(axis: str, location: float) -> tuple[np.ndarray, np.ndarray]:
    """``(point, unit_normal)`` of the grid plane ``axis = location``.

    The normal is the positive axis (the ocx-render convention); the point
    is ``location`` along it, in the same length unit as ``location``.
    """
    try:
        k = _AXES[axis]
    except KeyError:
        raise ValueError(
            f"unknown grid axis {axis!r}; expected 'x', 'y' or 'z'") from None
    normal = np.zeros(3)
    normal[k] = 1.0
    return float(location) * normal, normal
