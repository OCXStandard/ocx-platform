"""Exporter plausibility checks (OCX-TOP-010..012, OCX-PROP-005/006).

These rules catch data that is well-formed but physically implausible —
typically exporter bugs that copy one value onto many parts: inclination
positions off the trace, web directions that disagree with the panel
surface normal, COGs outside the part, and values shared by many parts.
"""
from __future__ import annotations

import math
import weakref
from collections import defaultdict
from itertools import chain
from typing import Any

import numpy as np
from loguru import logger
from ocx_model_core.model.ir.base import ParentKind

from ocx_rules.model import Finding
from ocx_rules.packs.best_practice.checks.properties import _cog_m
from ocx_rules.packs.best_practice.checks.topology import _inclination_positions


def _nearest_on_polyline(poly: np.ndarray,
                         p: np.ndarray) -> tuple[np.ndarray, float]:
    """Closest point on an (N, 3) polyline to ``p`` and its distance."""
    if len(poly) == 1:
        return poly[0], float(np.linalg.norm(p - poly[0]))
    a, b = poly[:-1], poly[1:]
    ab = b - a
    denom = np.einsum("ij,ij->i", ab, ab)
    t = np.einsum("ij,ij->i", p - a, ab) / np.where(denom > 1e-30, denom, 1.0)
    q = a + np.clip(t, 0.0, 1.0)[:, None] * ab
    d = np.linalg.norm(q - p, axis=1)
    i = int(np.argmin(d))
    return q[i], float(d[i])


# A stiffener farther than this from every panel surface is free-standing;
# its web is not compared with a surface normal.
_SURFACE_GAP_M = 0.05


def _normalize(vec: np.ndarray) -> np.ndarray | None:
    """Unit copy of ``vec``, or None when zero/non-finite."""
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(vec).all() or norm < 1e-12:
        return None
    return vec / norm


def _unit_vector(v) -> np.ndarray | None:
    """IrVector3D -> unit (3,) array, or None when missing/zero/non-finite."""
    if v is None:
        return None
    return _normalize(np.array([v.x, v.y, v.z], dtype=float))


def _panel_surface_params(geo, panel) -> list:
    """SurfaceParams for every support surface of a panel.

    Uses every inline patch (``UnboundedGeometry.surfaces``) and falls back
    to ``GeometryContext.panel_surface`` (inline surface, SurfaceRef, GridRef).
    """
    ug = panel.unbounded_geometry
    surfaces = list(ug.surfaces) if ug is not None and ug.surfaces else []
    if not surfaces:
        single = geo.panel_surface(panel)
        surfaces = [single] if single is not None else []
    params = (geo.surface_param(s) for s in surfaces)
    return [p for p in params if p is not None]


def _surface_normal_at(params: list, point: np.ndarray) -> np.ndarray | None:
    """Unit normal of the surface nearest ``point`` (None beyond the gap)."""
    best: tuple[float, Any, np.ndarray] | None = None
    for sp in params:
        uv = sp.inverse(point[None, :])
        dist = float(np.linalg.norm(sp.evaluate(uv)[0] - point))
        if best is None or dist < best[0]:
            best = (dist, sp, uv)
    if best is None or best[0] > _SURFACE_GAP_M:
        return None
    return _normalize(best[1].normals(best[2])[0])


_WEB_ANGLES_CACHE: "weakref.WeakKeyDictionary[Any, list[tuple[Any, int, float]]]" = (
    weakref.WeakKeyDictionary())


def _web_angles(context) -> list[tuple[Any, int, float]]:
    """Memoized ``_compute_web_angles`` per GeometryContext (TOP-011/012)."""
    geo = context.geometry
    cached = _WEB_ANGLES_CACHE.get(geo)
    if cached is None:
        cached = _compute_web_angles(context)
        _WEB_ANGLES_CACHE[geo] = cached
    return cached


def _compute_web_angles(context) -> list[tuple[Any, int, float]]:
    """(stiffener, inclination index, web-to-surface-normal angle in degrees).

    Shared by OCX-TOP-011/012. Evaluated at the trace point nearest the
    inclination position (trace start when it has none). Stiffeners without
    a panel, a resolvable surface, or within 50 mm of it are skipped.
    """
    geo = context.geometry
    vessel = context.vessel
    surface_cache: dict[str, list] = {}
    out: list[tuple[Any, int, float]] = []
    for stiffener in vessel.stiffeners.values():
        parent = stiffener.parent_ref
        if (not stiffener.inclinations or parent is None
                or parent.kind is not ParentKind.PANEL):
            continue
        panel = vessel.panels.get(parent.id)
        if panel is None:
            continue
        try:
            if panel.id not in surface_cache:
                surface_cache[panel.id] = _panel_surface_params(geo, panel)
            params = surface_cache[panel.id]
            if not params:
                continue
            poly = geo.sample(stiffener.trace)
            if poly is None or len(poly) == 0:
                continue
            positions = _inclination_positions(geo, stiffener.inclinations)
            angles: list[tuple[Any, int, float]] = []
            for i, (entry, pos) in enumerate(zip(stiffener.inclinations,
                                                 positions, strict=True)):
                web = _unit_vector(entry.web_direction)
                if web is None:
                    continue
                point = poly[0] if pos is None else _nearest_on_polyline(poly, pos)[0]
                normal = _surface_normal_at(params, point)
                if normal is None:
                    continue
                cos = min(abs(float(web @ normal)), 1.0)
                angles.append((stiffener, i, math.degrees(math.acos(cos))))
            out.extend(angles)
        except Exception as exc:  # noqa: BLE001 — skip stiffener
            logger.debug("TOP-011/012: stiffener {} skipped: {}",
                         stiffener.id, exc)
    return out


def web_not_in_plate(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-011: the web must not lie in the plate plane."""
    max_deg = float(params.get("max_angle_deg", 80.0))
    return [
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (lies in the plate plane; limit "
                f"{max_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in _web_angles(context) if angle >= max_deg]


def web_near_normal(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-012: the web should be close to the panel surface normal."""
    warn_deg = float(params.get("warn_angle_deg", 30.0))
    max_deg = float(params.get("max_angle_deg", 80.0))
    return [
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (warning above {warn_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in _web_angles(context) if warn_deg < angle < max_deg]


def inclination_position_on_trace(context,
                                  params: dict[str, Any]) -> list[Finding]:
    """OCX-TOP-010: every inclination Position must lie on the part's trace."""
    tol_mm = float(params.get("position_tolerance_mm", 50.0))
    tol_m = tol_mm / 1000.0
    geo = context.geometry
    vessel = context.vessel
    findings: list[Finding] = []
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        if not part.inclinations:
            continue
        try:
            poly = geo.sample(part.trace)
            if poly is None or len(poly) == 0:
                continue
            positions = _inclination_positions(geo, part.inclinations)
            for i, pos in enumerate(positions):
                if pos is None:
                    continue
                if not np.isfinite(pos).all():
                    findings.append(Finding(
                        f"Inclination {i} position has non-finite "
                        f"coordinates", element_id=part.id, guid=part.guidref))
                    continue
                _, dist = _nearest_on_polyline(poly, pos)
                if dist > tol_m:
                    findings.append(Finding(
                        f"Inclination {i} position is {dist:.3f} m off the "
                        f"trace (tolerance {tol_mm:.0f} mm)",
                        element_id=part.id, guid=part.guidref))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("TOP-010: part {} skipped: {}", part.id, exc)
    return findings


def _parts_with_geometry(vessel):
    """(part, curve) pairs: plate outer contours, stiffener/pillar traces."""
    for plate in vessel.plates.values():
        yield plate, plate.outer_contour
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        yield part, part.trace


def part_cog_within_geometry(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-005: the moulded COG must lie near the part's geometry."""
    margin_mm = float(params.get("margin_mm", 500.0))
    margin_m = margin_mm / 1000.0
    geo = context.geometry
    findings: list[Finding] = []
    for part, curve in _parts_with_geometry(context.vessel):
        mp = part.mass_properties
        cog = mp.moulded_cog if mp is not None else None
        if cog is None or curve is None:
            continue
        try:
            pts = geo.sample(curve)
            if pts is None or len(pts) == 0:
                continue
            c = _cog_m(geo.length, cog)
            if not np.isfinite(c).all():
                findings.append(Finding(
                    "Moulded COG has non-finite coordinates",
                    element_id=part.id, guid=part.guidref))
                continue
            lo = pts.min(axis=0) - margin_m
            hi = pts.max(axis=0) + margin_m
            gap = np.maximum(np.maximum(lo - c, c - hi), 0.0)
            dist = float(np.linalg.norm(gap))
            if dist > 0.0:
                findings.append(Finding(
                    f"Moulded COG ({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f}) m is "
                    f"{dist:.3f} m outside the part's bounding box "
                    f"(margin {margin_mm:.0f} mm)",
                    element_id=part.id, guid=part.guidref))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-005: part {} skipped: {}", part.id, exc)
    return findings


def _grid_key(p: np.ndarray, step_m: float) -> tuple[int, int, int]:
    return tuple(int(round(float(c) / step_m)) for c in p)


class _Pool:
    """Parts grouped by a rounded 3D value (one entry per part per key).

    Non-finite values are ignored (PROP-005/TOP-010 report them).
    """

    def __init__(self, label: str, step_m: float) -> None:
        self.label = label
        self.step_m = step_m
        # Keyed by object identity: duplicate IDs must not merge parts.
        self.parts: dict[tuple, dict[int, Any]] = defaultdict(dict)
        self.values: dict[tuple, np.ndarray] = {}

    def add(self, part, value: np.ndarray) -> None:
        if not np.isfinite(value).all():
            return
        key = _grid_key(value, self.step_m)
        self.parts[key][id(part)] = part
        self.values.setdefault(key, value)

    def findings(self, min_parts: int) -> list[Finding]:
        out: list[Finding] = []
        for key, parts in self.parts.items():
            if len(parts) < min_parts:
                continue
            v = self.values[key]
            msg = (f"{self.label} ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f}) is "
                   f"shared by {len(parts)} parts")
            out.extend(Finding(msg, element_id=p.id, guid=p.guidref)
                       for p in parts.values())
        return out


def shared_positions_and_cogs(context, params: dict[str, Any]) -> list[Finding]:
    """OCX-PROP-006: positions/COGs must not be copied across many parts."""
    tol_mm = float(params.get("tolerance_mm", 1.0))
    if not tol_mm > 0.0:
        raise ValueError(f"OCX-PROP-006: tolerance_mm must be > 0, got {tol_mm}")
    step_m = tol_mm / 1000.0
    min_parts = int(params.get("min_parts", 3))
    geo = context.geometry
    vessel = context.vessel
    positions = _Pool("Inclination position", step_m)
    cogs = _Pool("Moulded COG", step_m)
    for part in chain(vessel.stiffeners.values(), vessel.pillars.values()):
        try:
            for pos in _inclination_positions(geo, part.inclinations):
                if pos is not None:
                    positions.add(part, pos)
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-006: part {} positions skipped: {}", part.id, exc)
    for part in chain(vessel.plates.values(), vessel.stiffeners.values(),
                      vessel.pillars.values()):
        mp = part.mass_properties
        cog = mp.moulded_cog if mp is not None else None
        if cog is None:
            continue
        try:
            cogs.add(part, _cog_m(geo.length, cog))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("PROP-006: part {} COG skipped: {}", part.id, exc)
    return positions.findings(min_parts) + cogs.findings(min_parts)
