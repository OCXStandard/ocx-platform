"""Tessellation backend interface and option/result types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ocx_geometry.mesh import PartMesh


@dataclass(frozen=True)
class TessellationOptions:
    """Controls tessellation density and contour repair."""
    tolerance_m: float = 0.05        # linear deflection (metres); default 50 mm
    snap_tolerance_m: float = 0.01   # max contour gap snapped shut (metres)
    diag: Any = None                 # optional ocx_geometry.diagnostics.DiagSink
    # Render only parts parented to these panels (plates, stiffeners,
    # brackets, pillars); parts not under a panel are then left out.
    only_panels: frozenset[str] | None = None
    # Processes for plate tessellation (1 = serial); serial whenever diag
    # is set, since diagnostics are recorded into the caller's sink.  With
    # >1, scripts must guard their entry point (``if __name__ ==
    # "__main__":``) as for any process pool under the spawn start method.
    workers: int = 1


@dataclass
class RenderResult:
    """Outcome of a render: meshes plus a skip log (part id → reason).

    ``hole_failures`` (``<plate_or_panel_id>/hole:<id>`` → reason) records CutBy
    holes that could not be applied; the plate itself still rendered.
    """
    meshes: list[PartMesh] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    hole_failures: dict[str, str] = field(default_factory=dict)

    @property
    def rendered_count(self) -> int:
        return len(self.meshes)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ITessellator(ABC):
    """Backend interface for trimming+triangulating a surface patch.

    Backends receive geometry already resolved to numpy arrays in metres
    (the orchestrator does IR resolution), so alternative backends (e.g. a
    future OpenCASCADE one) only re-implement the geometric core.
    """

    @abstractmethod
    def tessellate_trimmed_surface(
        self,
        part_id: str,
        name: str,
        kind: str,
        contour_pts: np.ndarray,            # (N, 3) closed boundary polyline, metres
        hole_pts: list[np.ndarray],         # list of (K, 3) closed hole polylines
        surface_param,                       # surfaces.SurfaceParam
        options: TessellationOptions,
    ) -> PartMesh | None:
        """Return the tessellated part, or None if this part cannot be meshed."""
