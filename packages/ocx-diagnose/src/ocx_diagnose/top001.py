"""OCX-TOP-001 diagnosis: assemble per-panel LimitedBy contour data.

Coordinates are SI metres throughout (GeometryContext convention).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from ocx_geometry.measure import chain_gap_details

if TYPE_CHECKING:
    from ocx_model_core.model.ir import IrPanel, IrPoint3D
    from ocx_rules.geometry_context import GeometryContext

_SAMPLE_TOL_M = 0.001


@dataclass
class SegmentDiag:
    """One LimitedBy child in document order."""
    seq: int                       # 1-based document position
    ref_type: str                  # e.g. "SeamRef"
    target: str                    # local_ref or guidref ("" when absent)
    polyline: np.ndarray | None    # (N, 3) metres; None when unresolvable
    start: np.ndarray | None = None  # ContourBounds points, metres
    mid: np.ndarray | None = None
    end: np.ndarray | None = None


@dataclass
class GapDiag:
    """A junction/closure gap above tolerance."""
    point_a: np.ndarray            # (3,) metres
    point_b: np.ndarray
    distance_m: float


@dataclass
class PanelTop001Diagnosis:
    panel_id: str
    segments: list[SegmentDiag] = field(default_factory=list)
    gaps: list[GapDiag] = field(default_factory=list)
    outer_contours: list[np.ndarray] = field(default_factory=list)
    worst_gap_m: float = 0.0
    unresolved_count: int = 0


def _bound_point(geo: "GeometryContext",
                 pt: "IrPoint3D | None") -> np.ndarray | None:
    """IrPoint3D -> (3,) metres, or None (lean: never raises)."""
    if pt is None:
        return None
    try:
        return np.asarray(geo.length.point(pt), dtype=float)
    except Exception as exc:  # noqa: BLE001 — lean per point
        logger.debug("TOP-001 diag: unparseable ContourBounds point: {}", exc)
        return None


def diagnose_panel(geo: "GeometryContext", panel: "IrPanel",
                   tol_m: float) -> PanelTop001Diagnosis:
    """Assemble the TOP-001 diagnosis for one panel."""
    segments: list[SegmentDiag] = []
    for seq, ref in enumerate(panel.limited_by, start=1):
        curve = geo.boundary_curve_for_ref(ref)
        pts = geo.sample(curve, _SAMPLE_TOL_M) if curve is not None else None
        if pts is not None and len(pts) < 2:
            pts = None
        segments.append(SegmentDiag(
            seq=seq,
            ref_type=ref.ref_type,
            target=ref.local_ref or ref.guidref or "",
            polyline=pts,
            start=_bound_point(geo, ref.contour_start),
            mid=_bound_point(geo, ref.contour_mid_point),
            end=_bound_point(geo, ref.contour_end),
        ))

    samples = [s.polyline for s in segments if s.polyline is not None]
    gaps: list[GapDiag] = []
    worst = 0.0
    if samples:
        for pa, pb, d in chain_gap_details(samples):
            worst = max(worst, d)
            if d > tol_m:
                gaps.append(GapDiag(point_a=pa, point_b=pb, distance_m=d))

    outers: list[np.ndarray] = []
    for oc in panel.outer_contours:
        opts = geo.sample(oc, _SAMPLE_TOL_M)
        if opts is not None and len(opts) >= 2:
            outers.append(opts)

    return PanelTop001Diagnosis(
        panel_id=panel.id,
        segments=segments,
        gaps=gaps,
        outer_contours=outers,
        worst_gap_m=worst,
        unresolved_count=sum(1 for s in segments if s.polyline is None),
    )


def select_panels(geo: "GeometryContext", panel_ids: list[str] | None,
                  tol_m: float) -> list[PanelTop001Diagnosis]:
    """Diagnose panels: the given ids, or all panels failing TOP-001.

    A panel "fails" when its worst gap exceeds *tol_m* or it has
    unresolvable LimitedBy refs. Panels without LimitedBy are skipped.
    Note: this is a superset of the validator's TOP-001 findings — the
    rule skips panels with unresolved refs, this diagnostic includes them.
    """
    vessel = geo.vessel
    out: list[PanelTop001Diagnosis] = []
    if panel_ids:
        for pid in panel_ids:
            panel = vessel.panels.get(pid)
            if panel is None:
                logger.warning("TOP-001 diag: panel id {} not found", pid)
                continue
            out.append(diagnose_panel(geo, panel, tol_m))
        return out
    for panel in vessel.panels.values():
        if not panel.limited_by:
            continue
        diag = diagnose_panel(geo, panel, tol_m)
        if diag.worst_gap_m > tol_m or diag.unresolved_count:
            out.append(diag)
    return out


def write_top001_report(diags: list[PanelTop001Diagnosis], path,
                        title: str) -> None:
    """Write one self-contained HTML report (plotly.js embedded once)."""
    import html as _html
    from pathlib import Path

    import plotly.offline

    from ocx_diagnose.figures import limitedby_fig

    rows = "".join(
        f"<tr><td>{_html.escape(d.panel_id)}</td><td>{len(d.segments)}</td>"
        f"<td>{d.unresolved_count}</td><td>{d.worst_gap_m * 1000:.2f}</td>"
        f"<td>{'no' if d.gaps or d.unresolved_count else 'yes'}</td></tr>"
        for d in diags)
    summary = ("<table border='1' cellpadding='4' cellspacing='0'>"
               "<tr><th>panel</th><th>segments</th><th>unresolved</th>"
               "<th>worst gap mm</th><th>closed</th></tr>"
               f"{rows}</table>") if diags else "<p>No panels to diagnose.</p>"
    figs = "".join(
        limitedby_fig(d).to_html(full_html=False, include_plotlyjs=False,
                                 default_height="650px")
        for d in diags)
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(title)} — TOP-001</title>"
            f"<script>{plotly.offline.get_plotlyjs()}</script></head><body>"
            f"<h1>TOP-001 LimitedBy diagnosis — {_html.escape(title)}</h1>"
            f"{summary}{figs}</body></html>")
    Path(path).write_text(page, encoding="utf-8")
    logger.info("Wrote TOP-001 report {} ({:.1f} MB)", path, len(page) / 1e6)
