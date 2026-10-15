"""Optional collectors the render pipeline fills for diagnostics.

Hooks never change tessellation results; with no sink they cost nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["ChartDiag", "PlateDiag", "DiagSink"]


@dataclass
class ChartDiag:
    """Build statistics of one panel's shared chart mesh."""
    n_members: int = 0
    members_used: list[int] = field(default_factory=list)
    verts_before_weld: int = 0
    verts_after_weld: int = 0
    boundary_edges_before_stitch: int = 0
    boundary_edges_after_stitch: int = 0
    build_s: float = 0.0
    V: np.ndarray | None = None
    F: np.ndarray | None = None
    tri_member: np.ndarray | None = None


@dataclass
class PlateDiag:
    """What happened to one plate."""
    plate_id: str
    panel_id: str
    route: str = "unknown"          # single | mesh-trim | lscm | best-member
    trim_reject: str | None = None  # why mesh-trim was not used
    snap_m: float | None = None     # worst outer-ring snap distance
    max_snap_m: float | None = None
    chart_stage: str | None = None  # gates | no-gates | tutte (route == lscm)
    local_param: Any = None         # LscmParam of the flattened submesh
    candidates: list = field(default_factory=list)  # exact SurfaceParam members
    contour: np.ndarray | None = None
    seconds: float = 0.0


@dataclass
class DiagSink:
    charts: dict[str, ChartDiag] = field(default_factory=dict)
    plates: dict[str, PlateDiag] = field(default_factory=dict)
