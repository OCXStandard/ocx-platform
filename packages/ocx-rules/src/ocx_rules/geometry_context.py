"""Lazily-built geometry facade over an IrVessel for rule checks.

All methods degrade to None/empty instead of raising, matching the checks'
lean-pass policy. Units: everything returned is SI metres / kg.
"""
from __future__ import annotations

from collections.abc import Iterable
from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from ocx_geometry.curves import sample_curve
from ocx_geometry.grid import grid_plane
from ocx_geometry.intersect import offset_plane
from ocx_geometry.measure import LengthResolver
from ocx_geometry.surfaces import SurfaceParam, make_param
from ocx_model_core.model.ir import IrPlane3D, IrPoint3D, IrVector3D

if TYPE_CHECKING:
    from ocx_model_core.model.ir import (
        IrCurve3D,
        IrLimitedByRef,
        IrPanel,
        IrRefPlane,
        IrSurface3D,
        IrVessel,
        Quantity,
    )


class GeometryContext:
    """Shared geometry services for geometry-dependent rule checks."""

    def __init__(self, vessel: "IrVessel") -> None:
        self.vessel = vessel
        self._sample_cache: dict[tuple[int, float],
                                 tuple[object, np.ndarray | None]] = {}

    @cached_property
    def length(self) -> LengthResolver:
        return LengthResolver(self.vessel.unit_registry)

    def to_si(self, q: "Quantity | None") -> float | None:
        """Any Quantity → SI float via the model's unit registry.

        Registry misses for length units delegate to ``LengthResolver`` (which
        knows common fallback factors and warns once per unknown unit); other
        unknown units are treated as SI with a one-time warning.
        """
        if q is None or q.value is None:
            return None
        unit = self.vessel.unit_registry.get(q.unit) if q.unit else None
        if unit is not None and unit.to_si_factor is not None:
            return float(q.value) * float(unit.to_si_factor)
        if q.unit:
            return float(self.length.to_m(float(q.value), q.unit))
        return float(q.value)

    def sample(self, curve: "IrCurve3D | None",
               tol_m: float = 0.001) -> np.ndarray | None:
        """Sample a curve to an (N, 3) polyline in metres, or None.

        Memoized per (curve, tolerance) for the lifetime of this context
        (one validation run over an unchanging IR); callers receive a copy.
        """
        if curve is None:
            return None
        key = (id(curve), float(tol_m))
        entry = self._sample_cache.get(key)
        if entry is not None and entry[0] is curve:
            result = entry[1]
        else:
            try:
                result = sample_curve(curve, self.length, tol_m)
            except Exception as exc:
                logger.debug("curve sampling failed: {}", exc)
                result = None
            # Keep the curve referenced so its id cannot be reused.
            self._sample_cache[key] = (curve, result)
        return None if result is None else result.copy()

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
                return self._ref_plane_geometry(rp)
        return None

    def ref_plane_axis(self, ref_plane_id: str) -> str | None:
        """'x' | 'y' | 'z' — the coordinate-system list holding the plane."""
        for cs in self.vessel.coordinate_systems.values():
            if ref_plane_id in cs.x_ref_plane_ids:
                return "x"
            if ref_plane_id in cs.y_ref_plane_ids:
                return "y"
            if ref_plane_id in cs.z_ref_plane_ids:
                return "z"
        return None

    def _ref_plane_geometry(self, rp: "IrRefPlane") -> IrPlane3D | None:
        """Explicit plane, else one synthesized from axis + location."""
        if rp.reference_plane is not None:
            return rp.reference_plane
        if rp.location is None or rp.location.value is None:
            return None
        axis = self.ref_plane_axis(rp.id)
        if axis is None:
            return None
        point, normal = grid_plane(axis, float(rp.location.value))
        return IrPlane3D(
            id=rp.id,
            point_on_surface=IrPoint3D(*map(float, point),
                                       unit=rp.location.unit),
            normal=IrVector3D(*map(float, normal)))

    def grid_ref_plane(
            self, ref: "IrLimitedByRef",
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """``(point, unit normal)`` in metres of a GridRef's plane with its
        ``Offset`` applied (positive along the normal), or None."""
        rp = self.vessel.ref_planes.get(ref.local_ref)
        plane = self._ref_plane_geometry(rp) if rp is not None else None
        if plane is None or plane.point_on_surface is None \
                or plane.normal is None:
            return None
        n = plane.normal
        try:
            return offset_plane(self.length.point(plane.point_on_surface),
                                [n.x, n.y, n.z],
                                self.to_si(ref.offset) or 0.0)
        except ValueError as exc:
            logger.debug("grid ref plane {} failed: {}", ref.local_ref, exc)
            return None

    def panel_uv_window(
            self, panel: "IrPanel", param: SurfaceParam,
            extra_points: Iterable[np.ndarray] = (),
    ) -> tuple[float, float, float, float] | None:
        """uv window ``(u0, u1, v0, v1)`` around a panel on ``param``.

        Bounding box (in uv) of the OuterContour samples, point_on_surface
        and ``extra_points``, grown on each side by its extent plus 1 m;
        periodic u is capped at one period; clamped to ``param.uv_domain()``.
        """
        chunks = [s for s in (self.sample(c) for c in panel.outer_contours)
                  if s is not None and len(s)]
        if panel.point_on_surface is not None:
            chunks.append(self.length.point(panel.point_on_surface)[None, :])
        chunks += [np.asarray(p, dtype=float).reshape(-1, 3)
                   for p in extra_points if len(p)]
        domain = param.uv_domain()
        if not chunks:
            if domain is not None and np.all(np.isfinite(domain)):
                return tuple(float(x) for x in domain)
            return None
        uv = param.inverse(np.vstack(chunks))
        lo, hi = uv.min(axis=0), uv.max(axis=0)
        su, sv = param.uv_scale()
        grow = (hi - lo) + np.array([1.0 / su, 1.0 / sv])
        lo, hi = lo - grow, hi + grow
        if param.periodic_u and hi[0] - lo[0] > 2.0 * np.pi:
            mid = 0.5 * (lo[0] + hi[0])
            lo[0], hi[0] = mid - np.pi, mid + np.pi
        if domain is not None:
            lo = np.maximum(lo, [domain[0], domain[2]])
            hi = np.minimum(hi, [domain[1], domain[3]])
        if np.any(hi <= lo):
            return None
        return (float(lo[0]), float(hi[0]), float(lo[1]), float(hi[1]))

    def boundary_curve_for_ref(self,
                               ref: "IrLimitedByRef") -> "IrCurve3D | None":
        """Resolve one LimitedBy ref to an explicit boundary curve, or None.

        FreeEdgeCurve3D -> inline curve; SeamRef -> seam trace_line;
        StiffenerRef -> stiffener trace. Other ref types carry no explicit
        curve.
        """
        v = self.vessel
        if ref.ref_type == "FreeEdgeCurve3D":
            return ref.curve
        if ref.ref_type == "SeamRef":
            seam = v.seams.get(ref.local_ref)
            return seam.trace_line if seam else None
        if ref.ref_type == "StiffenerRef":
            stf = v.stiffeners.get(ref.local_ref)
            return stf.trace if stf else None
        return None

    def boundary_curves(self, panel: "IrPanel") -> tuple[list, int]:
        """Explicit boundary curves of a panel + count of unresolvable refs.

        Resolution per ref is delegated to :meth:`boundary_curve_for_ref`;
        refs it cannot resolve are counted as unresolvable.
        """
        curves = []
        unresolved = 0
        for ref in panel.limited_by:
            curve = self.boundary_curve_for_ref(ref)
            if curve is not None:
                curves.append(curve)
            else:
                unresolved += 1
        return curves, unresolved
