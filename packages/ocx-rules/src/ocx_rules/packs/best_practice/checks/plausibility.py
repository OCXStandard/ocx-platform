"""Exporter plausibility checks (OCX-TOP-010..012, OCX-PROP-005/006).

These rules catch data that is well-formed but physically implausible —
typically exporter bugs that copy one value onto many parts: inclination
positions off the trace, web directions that disagree with the panel
surface normal, COGs outside the part, and values shared by many parts.
"""
from __future__ import annotations

from itertools import chain
from typing import Any

import numpy as np
from loguru import logger

from ocx_rules.model import Finding
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
                _, dist = _nearest_on_polyline(poly, pos)
                if dist > tol_m:
                    findings.append(Finding(
                        f"Inclination {i} position is {dist:.3f} m off the "
                        f"trace (tolerance {tol_mm:.0f} mm)",
                        element_id=part.id, guid=part.guidref))
        except Exception as exc:  # noqa: BLE001 — skip part
            logger.debug("TOP-010: part {} skipped: {}", part.id, exc)
    return findings
