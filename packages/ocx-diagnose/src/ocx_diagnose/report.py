"""Assemble the interactive HTML report and the JSON stats."""
from __future__ import annotations

import html as _html
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import plotly.offline
from loguru import logger

from ocx_diagnose import figures as fg
from ocx_diagnose.checks import chart_distortion, surface_deviation

_CSS = ("body{font-family:sans-serif;margin:1em}table{border-collapse:collapse;margin:.5em 0}"
        "td,th{border:1px solid #ccc;padding:2px 6px;font-size:12px}"
        ".tab{display:none}.tab.on{display:block}button.on{font-weight:bold}"
        "details{margin:.5em 0}summary{cursor:pointer}")
_JS = ("function show(id){document.querySelectorAll('.tab').forEach(e=>"
       "e.classList.toggle('on',e.id===id));document.querySelectorAll('button.tb')"
       ".forEach(b=>b.classList.toggle('on',b.dataset.t===id));"
       "window.dispatchEvent(new Event('resize'));}")

_PLATE_SCALARS = ("route", "trim_reject", "snap_m", "max_snap_m", "chart_stage", "seconds",
                  "dev_mean_m", "dev_max_m", "overlap_faces", "gap_vertices", "max_gap_m",
                  "bbox_delta_m", "flipped_frac", "spread_max", "score")
_MAX_DEV_POINTS = 3000


def _fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_html.escape(_fmt(c))}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _chart_counts(chart) -> dict:
    if chart is None:
        return {}
    return {
        "n_members": chart.n_members,
        "members_used": len(chart.members_used),
        "verts_before_weld": chart.verts_before_weld,
        "verts_after_weld": chart.verts_after_weld,
        "boundary_edges_before_stitch": chart.boundary_edges_before_stitch,
        "boundary_edges_after_stitch": chart.boundary_edges_after_stitch,
        "build_s": chart.build_s,
    }


def _route_counts(panel) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in panel.plates:
        counts[p.route] = counts.get(p.route, 0) + 1
    return counts


def plate_section(pr, tol_m: float) -> str:
    """<details> block with the per-plate figures."""
    m, pd = pr.mesh, pr.diag
    V, F = m.vertices, m.triangles
    figs = []
    if pd.contour is not None and len(V):
        figs.append(fg.ring_fig(V, F, pd.contour, f"{pr.plate_id}: contour and snap"))
    if len(F) and pd.candidates:
        pts = V[F].mean(axis=1)
        if len(pts) > _MAX_DEV_POINTS:
            pts = pts[np.linspace(0, len(pts) - 1, _MAX_DEV_POINTS).astype(int)]
        figs.append(fg.deviation_fig(
            pts, surface_deviation(pts, pd.candidates, max_samples=len(pts),
                              chart=pd.chart), tol_m))
    if len(F):
        figs.append(fg.edges_fig(V, F))
    if pr.route == "lscm" and pd.local_param is not None:
        Vc, Fc, uv = pd.local_param.chart
        d = chart_distortion(Vc, Fc, uv)
        figs.append(fg.chart_mesh_fig(Vc, Fc, d.spread, f"{pr.plate_id}: scale spread",
                                      flipped=d.flipped))
        figs.append(fg.uv_layout_fig(uv, Fc, d.flipped))
    body = "".join(_fig_html(f) for f in figs)
    label = f"{pr.plate_id} (score {pr.score:.3g}, route {pr.route})"
    return f"<details><summary>{_html.escape(label)}</summary>{body}</details>"


def panel_section(panel, max_plates: int, tol_m: float) -> str:
    """Contents of one panel tab."""
    parts = [f"<h2>{_html.escape(panel.panel_id)}</h2>"]
    counts = _chart_counts(panel.chart)
    if counts:
        parts.append("<h3>Chart mesh</h3>")
        parts.append(_table(counts.keys(), [counts.values()]))
        c = panel.chart
        if c.V is not None and c.F is not None and c.tri_member is not None and len(c.F):
            parts.append(_fig_html(fg.chart_mesh_fig(
                c.V, c.F, c.tri_member, "Chart mesh by member", colorscale="Rainbow")))
    if panel.sweep:
        parts.append(_fig_html(fg.sweep_fig(
            [s.tol_mm for s in panel.sweep], [s.dev_max_m for s in panel.sweep],
            [s.triangles for s in panel.sweep])))
        parts.append(_table(
            ("tol mm", "seconds", "triangles", "parts", "skipped", "dev mean m", "dev max m"),
            [(s.tol_mm, s.seconds, s.triangles, s.parts, s.skipped, s.dev_mean_m, s.dev_max_m)
             for s in panel.sweep]))
    parts.append("<h3>Plates</h3>")
    parts.append(_table(
        ("plate", "route", "snap/max m", "reject", "dev max m", "overlaps", "gaps",
         "flipped", "boundary", "non-manifold", "score"),
        [(p.plate_id, p.route,
          "-" if p.snap_m is None else f"{p.snap_m:.3g}/{_fmt(p.max_snap_m)}",
          p.trim_reject, p.dev_max_m, p.overlap_faces, p.gap_vertices, p.flipped_frac,
          p.health.get("boundary_edges"), p.health.get("non_manifold_edges"), p.score)
         for p in panel.plates]))
    if panel.skipped:
        parts.append("<h3>Skipped</h3>" + _table(
            ("plate", "reason"), sorted(panel.skipped.items())))
    worst = sorted(panel.plates, key=lambda p: p.score, reverse=True)[:max_plates]
    parts.append(f"<h3>Worst {len(worst)} plates</h3>")
    parts.extend(plate_section(p, tol_m) for p in worst)
    return "".join(parts)


def _summary_row(panel) -> tuple:
    routes = ", ".join(f"{k}:{v}" for k, v in sorted(_route_counts(panel).items()))
    devs = [p.dev_max_m for p in panel.plates if p.dev_max_m is not None]
    return (panel.panel_id, len(panel.plates), routes,
            max((p.score for p in panel.plates), default=None),
            max(devs, default=None), "yes" if panel.sweep else "no")


def write_report(results, path, max_plates: int, title: str) -> None:
    """Write one self-contained HTML file with plotly.js embedded once."""
    tabs = [(f"tab{i}", p) for i, p in enumerate(results)]
    buttons = "".join(
        f'<button class="tb" data-t="{tid}" onclick="show(\'{tid}\')">'
        f"{_html.escape(p.panel_id)}</button> " for tid, p in tabs)
    sections = "".join(
        f'<div class="tab" id="{tid}">{panel_section(p, max_plates, p.tol_m)}</div>'
        for tid, p in tabs)
    summary = _table(("panel", "plates", "routes", "worst score", "max dev m", "sweep"),
                     [_summary_row(p) for p in results])
    first = f"show('{tabs[0][0]}');" if tabs else ""
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(title)}</title><style>{_CSS}</style>"
            f"<script>{plotly.offline.get_plotlyjs()}</script></head><body>"
            f"<h1>{_html.escape(title)}</h1>{summary}<div>{buttons}</div>{sections}"
            f"<script>{_JS}{first}</script></body></html>")
    Path(path).write_text(page, encoding="utf-8")
    logger.info("Wrote report {} ({:.1f} MB)", path, len(page) / 1e6)


def write_json(results, path) -> None:
    """Write per-panel stats (no arrays, meshes or collectors)."""
    data = {}
    for panel in results:
        data[panel.panel_id] = {
            "chart": _chart_counts(panel.chart),
            "plates": {p.plate_id: {**{k: getattr(p, k) for k in _PLATE_SCALARS},
                                    "health": p.health}
                       for p in panel.plates},
            "sweep": [asdict(s) for s in panel.sweep],
        }
    Path(path).write_text(json.dumps(data, indent=2, default=float), encoding="utf-8")

