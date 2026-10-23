"""PartMesh — the tessellated output unit — and per-part color assignment."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Base colors per part kind (RGB 0-255).
KIND_COLORS: dict[str, tuple[int, int, int]] = {
    "plate": (140, 145, 150),      # steel grey
    "stiffener": (70, 110, 200),   # blue
    "pillar": (80, 170, 110),      # green
    "bracket": (200, 140, 60),     # orange
    "panel": (205, 170, 125),      # tan (reserved; panels are not tessellated in v1)
}


def part_color(kind: str, part_id: str) -> tuple[int, int, int]:
    """Deterministic per-part color: kind base color + per-id hue jitter."""
    base = KIND_COLORS.get(kind, (180, 180, 180))
    digest = hashlib.md5(part_id.encode("utf-8")).digest()
    # three independent jitters in [-18, +18]
    return tuple(
        int(np.clip(base[i] + (digest[i] % 37) - 18, 0, 255)) for i in range(3)
    )


@dataclass
class PartMesh:
    """A single tessellated part, in metres."""
    part_id: str
    name: str
    kind: str                                  # "plate" | "stiffener" | "pillar" | "bracket" | "panel"
    vertices: np.ndarray                       # (N, 3) float64, metres
    triangles: np.ndarray                      # (M, 3) int
    normals: np.ndarray | None = None          # (N, 3) float64 or None
    color: tuple[int, int, int] | None = None  # filled from part_color if None
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = part_color(self.kind, self.part_id)
