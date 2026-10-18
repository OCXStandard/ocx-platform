"""Lazily-built geometry facade over an IrVessel for rule checks.

All methods degrade to None/empty instead of raising, matching the checks'
lean-pass policy. Units: everything returned is SI metres / kg.
"""
from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from ocx_geometry.curves import sample_curve
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import SurfaceParam, make_param

if TYPE_CHECKING:
    from ocx_model_core.model.ir import (
        IrCurve3D,
        IrPanel,
        IrSurface3D,
        IrVessel,
        Quantity,
    )


class GeometryContext:
    """Shared geometry services for geometry-dependent rule checks."""

    def __init__(self, vessel: "IrVessel") -> None:
        self.vessel = vessel

    @cached_property
    def length(self) -> LengthResolver:
        return LengthResolver(self.vessel.unit_registry)

    def to_si(self, q: "Quantity | None") -> float | None:
        """Any Quantity → SI float via the model's unit registry."""
        if q is None or q.value is None:
            return None
        unit = self.vessel.unit_registry.get(q.unit) if q.unit else None
        if unit is not None and unit.to_si_factor is not None:
            return float(q.value) * float(unit.to_si_factor)
        if q.unit:
            logger.debug("Unknown unit {!r}; treating value as SI", q.unit)
        return float(q.value)

    def sample(self, curve: "IrCurve3D | None",
               tol_m: float = 0.001) -> np.ndarray | None:
        """Sample a curve to an (N, 3) polyline in metres, or None."""
        if curve is None:
            return None
        try:
            return sample_curve(curve, self.length, tol_m)
        except Exception as exc:
            logger.debug("curve sampling failed: {}", exc)
            return None

    def surface_param(self, surface: "IrSurface3D | None",
                      tol_m: float = 0.001) -> SurfaceParam | None:
        """Build a parametrization for a surface, or None if unsupported."""
        if surface is None:
            return None
        try:
            return make_param(surface, self.length, tol_m)
        except Exception as exc:
            logger.debug("surface param failed: {}", exc)
            return None

    def panel_surface(self, panel: "IrPanel") -> "IrSurface3D | None":
        """Resolve a panel's support surface geometry, or None."""
        ug = panel.unbounded_geometry
        if ug is None:
            return None
        if ug.surface is not None:
            return ug.surface
        v = self.vessel
        if ug.surface_ref is not None:
            s = v.surfaces.get(ug.surface_ref)
            if s is not None:
                return s.geometry
            coll = v.surface_collections.get(ug.surface_ref)
            if coll is not None and len(coll.surfaces) == 1:
                return coll.surfaces[0].geometry
        if ug.grid_ref is not None:
            rp = v.ref_planes.get(ug.grid_ref)
            if rp is not None:
                return rp.reference_plane
        return None

    def boundary_curves(self, panel: "IrPanel") -> tuple[list, int]:
        """Explicit boundary curves of a panel + count of unresolvable refs.

        FreeEdgeCurve3D -> inline curve; SeamRef -> seam trace_line;
        StiffenerRef -> stiffener trace. Other ref types carry no explicit
        curve -> unresolvable.
        """
        v = self.vessel
        curves = []
        unresolved = 0
        for ref in panel.limited_by:
            curve = None
            if ref.ref_type == "FreeEdgeCurve3D":
                curve = ref.curve
            elif ref.ref_type == "SeamRef":
                seam = v.seams.get(ref.local_ref)
                curve = seam.trace_line if seam else None
            elif ref.ref_type == "StiffenerRef":
                stf = v.stiffeners.get(ref.local_ref)
                curve = stf.trace if stf else None
            if curve is not None:
                curves.append(curve)
            else:
                unresolved += 1
        return curves, unresolved
