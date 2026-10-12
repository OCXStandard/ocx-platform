"""Turn IrSection catalogue entries into closed 2D profile polygons.

Convention: columns (s, w).  s = lateral axis, w = web axis with w=0 on the
plate/trace and +w pointing away from it.  All polygons are simple, CCW,
without a repeated last point.  Returns None when required dimensions are
missing; callers fall back to ``fallback_polygon()``.
"""
from __future__ import annotations

import numpy as np

from ocx_model_core.model.ir.sections import (
    IrAngleSection,
    IrBulbFlatSection,
    IrFlatBarSection,
    IrISection,
    IrLSection,
    IrLSectionOvershootFlange,
    IrLSectionOvershootWeb,
    IrRoundSection,
    IrSection,
    IrSquareSection,
    IrTSection,
    IrTubeSection,
    IrUSection,
    IrZSection,
)
from ocx_geometry.measure import LengthResolver

_CIRCLE_SEGS = 16


def _rect(s0, s1, w0, w1) -> np.ndarray:
    return np.array([[s0, w0], [s1, w0], [s1, w1], [s0, w1]], dtype=float)


def _circle(center_s, center_w, r) -> np.ndarray:
    t = np.linspace(0.0, 2 * np.pi, _CIRCLE_SEGS, endpoint=False)
    return np.column_stack([center_s + r * np.cos(t), center_w + r * np.sin(t)])


def fallback_polygon(height: float = 0.1, thickness: float = 0.01) -> np.ndarray:
    """Flat-bar proxy used when a section is unknown or missing dimensions."""
    return _rect(-thickness / 2.0, thickness / 2.0, 0.0, height)


def section_polygon(section: IrSection | None,
                    length: LengthResolver) -> np.ndarray | None:
    """Dispatch to the profile builder for this section type, or None."""
    if section is None:
        return None
    q = length.qty

    if isinstance(section, IrFlatBarSection):
        h, w = q(section.height), q(section.width)
        if h is None or w is None:
            return None
        return _rect(-w / 2.0, w / 2.0, 0.0, h)

    if isinstance(section, IrTSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf], [w / 2, h - tf],
            [w / 2, h], [-w / 2, h], [-w / 2, h - tf], [-tw / 2, h - tf],
        ])

    if isinstance(section, (IrLSection, IrLSectionOvershootFlange,
                            IrLSectionOvershootWeb)):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf],
            [w - tw / 2, h - tf], [w - tw / 2, h], [-tw / 2, h],
        ])

    if isinstance(section, IrBulbFlatSection):
        h, tw = q(section.height), q(section.web_thickness)
        bw = q(section.flange_width)
        if None in (h, tw, bw):
            return None
        bulb_h = min(0.2 * h, h)               # bulb occupies top ~20 % of web
        return np.array([
            [-tw / 2, 0], [tw / 2, 0], [tw / 2, h - bulb_h],
            [bw - tw / 2, h - 0.4 * bulb_h], [bw - tw / 2, h],
            [-tw / 2, h],
        ])

    if isinstance(section, IrAngleSection):
        ll, lt = q(section.leg_length), q(section.leg_thickness)
        if None in (ll, lt):
            return None
        return np.array([
            [-lt / 2, 0], [lt / 2, 0], [lt / 2, ll - lt],
            [ll - lt / 2, ll - lt], [ll - lt / 2, ll], [-lt / 2, ll],
        ])

    if isinstance(section, IrUSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        # channel opening sideways: web vertical, two flanges to +s
        return np.array([
            [-tw / 2, 0], [w - tw / 2, 0], [w - tw / 2, tf], [tw / 2, tf],
            [tw / 2, h - tf], [w - tw / 2, h - tf], [w - tw / 2, h],
            [-tw / 2, h],
        ])

    if isinstance(section, IrISection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-w / 2, 0], [w / 2, 0], [w / 2, tf], [tw / 2, tf],
            [tw / 2, h - tf], [w / 2, h - tf], [w / 2, h], [-w / 2, h],
            [-w / 2, h - tf], [-tw / 2, h - tf], [-tw / 2, tf], [-w / 2, tf],
        ])

    if isinstance(section, IrZSection):
        h, w = q(section.height), q(section.width)
        tw, tf = q(section.web_thickness), q(section.flange_thickness)
        if None in (h, w, tw, tf):
            return None
        return np.array([
            [-w + tw / 2, 0], [tw / 2, 0], [tw / 2, h - tf],
            [w - tw / 2, h - tf], [w - tw / 2, h], [-tw / 2, h],
            [-tw / 2, tf], [-w + tw / 2, tf],
        ])

    if isinstance(section, IrTubeSection):
        d = q(section.diameter)
        if d is None:
            return None
        return _circle(0.0, d / 2.0, d / 2.0)   # tangent to the trace plane

    if isinstance(section, IrRoundSection):
        d = q(section.diameter)
        if d is None:
            return None
        return _circle(0.0, d / 2.0, d / 2.0)

    if isinstance(section, IrSquareSection):
        h = q(section.height)
        if h is None:
            return None
        return _rect(-h / 2.0, h / 2.0, 0.0, h)

    return None
