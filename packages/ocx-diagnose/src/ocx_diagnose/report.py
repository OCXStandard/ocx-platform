"""Assemble the interactive HTML report and the JSON stats."""
from __future__ import annotations

import base64
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
        "details{margin:.5em 0}summary{cursor:pointer}"
        ".finding{margin:.4em 0;padding:.3em .6em;background:#fafafa;font-size:13px}")
_fig_seq = 0
_VENDOR = Path(__file__).parent / "vendor"
_PALETTE = ("#4c78a8", "#59a14f", "#b8a04a", "#8e6bb0", "#46a6a6", "#a07850")
_JS = ("function sync(){document.querySelectorAll('.lz').forEach(g=>{"
       "const vis=g.offsetParent!==null&&!g.closest('details:not([open])');"
       "if(vis&&!g.dataset.done){const d=JSON.parse(document.getElementById(g.id+'j')"
       ".textContent);Plotly.newPlot(g,d.data,d.layout,{responsive:true});g.dataset.done=1;}"
       "else if(!vis&&g.dataset.done){g.querySelectorAll('canvas').forEach(c=>{"
       "const x=c.getContext('webgl')||c.getContext('webgl2');"
       "const l=x&&x.getExtension('WEBGL_lose_context');if(l)l.loseContext();});"
       "Plotly.purge(g);g.dataset.done='';}});}"
       "function show(id){document.querySelectorAll('.tab').forEach(e=>"
       "e.classList.toggle('on',e.id===id));document.querySelectorAll('button.tb')"
       "       .forEach(b=>b.classList.toggle('on',b.dataset.t===id));sync();"
              "if(id==='tabmodel')initViewer();}"
              "function focusPlate(p,zoom){const f=p||null;show('tabmodel');viewerFocus(f,zoom!==false&&!!f);"
              "const h=document.getElementById('hl');h.textContent=f?'Highlighted: '+f+' ':'';"
       "const d=f&&[...document.querySelectorAll('details[data-plate]')].find(x=>x.dataset.plate===f);"
       "if(d){const a=document.createElement('a');a.href='#';a.textContent='open its diagnosis';"
       "a.onclick=()=>{show(d.closest('.tab').id);d.open=true;sync();d.scrollIntoView();return false;};"
       "h.appendChild(a);}}"
       "document.addEventListener('toggle',sync,true);")

_PLATE_SCALARS = ("route", "trim_reject", "snap_m", "max_snap_m", "chart_stage", "seconds",
                  "dev_mean_m", "dev_max_m", "overlap_faces", "gap_vertices", "max_gap_m",
                  "bbox_delta_m", "flipped_frac", "spread_max", "score")
_MAX_DEV_POINTS = 3000


def _fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _fig_html(fig) -> str:
    """Figure placeholder; _JS draws it lazily, since browsers cap live WebGL contexts."""
    global _fig_seq
    _fig_seq += 1
    data = fig.to_json().replace("</", "<\\/")
    return (f'<div class="lz" id="fig{_fig_seq}" style="width:100%;height:450px"></div>'
            f'<script type="application/json" id="fig{_fig_seq}j">{data}</script>')


def _b64(a, dtype) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def model_section(results) -> str:
    """3-D model tab: every plate as binary buffers for the embedded three.js viewer."""
    colours: dict[str, str] = {}
    plates = []
    for panel in results:
        col = colours.setdefault(panel.panel_id, _PALETTE[len(colours) % len(_PALETTE)])
        for p in panel.plates:
            if len(p.mesh.triangles):
                plates.append({"id": p.plate_id, "panel": panel.panel_id, "color": col,
                               "info": {"route": p.route, "score": round(float(p.score), 3),
                                        "findings": [[f.severity, f.title] for f in p.findings]},
                               "v": _b64(p.mesh.vertices, np.float32),
                               "f": _b64(p.mesh.triangles, np.uint32)})
    data = json.dumps({"plates": plates}, separators=(",", ":"))
    return ("<h2>Rendered model</h2><p>Click a plate to highlight it; drag to orbit, "
            "wheel to zoom, right-drag to pan. "
            '<span id="hl"></span> <button onclick="focusPlate(null)">Clear highlight</button></p>'
            '<div id="v3d" style="width:100%;height:720px;background:#f4f6fa"></div>'
            f'<script type="application/json" id="v3dj">{data}</script>')


def _viewer_js() -> str:
    return "".join((_VENDOR / n).read_text(encoding="utf-8")
                   for n in ("three.min.js", "OrbitControls.js", "viewer.js"))


def _table(headers, rows) -> str:
    head = "".join(f"<th>{_html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{_html.escape(_fmt(c))}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


_SEV_COLOUR = {"high": "#c0392b", "medium": "#e67e22", "low": "#7f8c8d"}


def _finding_html(f) -> str:
    def steps(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{_html.escape(s)}</li>" for s in items)
        return f"<b>{title}</b><ul>{lis}</ul>"

    colour = _SEV_COLOUR.get(f.severity, "#555")
    return (f'<div class="finding" style="border-left:4px solid {colour}">'
            f"<b>[{_html.escape(f.severity.upper())}] {_html.escape(f.title)}</b> "
            f"<i>({_html.escape(f.status)})</i>"
            f"<div><b>Evidence:</b> {_html.escape(f.evidence)}</div>"
            f"<div><b>Likely cause:</b> {_html.escape(f.cause)}</div>"
            f"{steps('Improve the meshing', f.mesh_steps)}"
            f"{steps('Improve the OCX source', f.source_steps)}</div>")


def _findings_box(title: str, findings) -> str:
    if not findings:
        return ""
    return f"<h3>{title}</h3>" + "".join(_finding_html(f) for f in findings)


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
    link = (f'<p><a href="#" data-p="{_html.escape(pr.plate_id, quote=True)}" '
            'onclick="focusPlate(this.dataset.p);return false">View in 3D model</a></p>')
    body = link + _findings_box("Diagnosis", pr.findings) + "".join(_fig_html(f) for f in figs)
    n = len(pr.findings)
    label = f"{pr.plate_id} (score {pr.score:.3g}, route {pr.route}, {n} findings)"
    return (f'<details data-plate="{_html.escape(pr.plate_id, quote=True)}">'
            f"<summary>{_html.escape(label)}</summary>{body}</details>")


def panel_section(panel, max_plates: int, tol_m: float) -> str:
    """Contents of one panel tab."""
    parts = [f"<h2>{_html.escape(panel.panel_id)}</h2>"]
    parts.append(_findings_box("Findings", panel.findings))
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
    n_find = len(panel.findings) + sum(len(p.findings) for p in panel.plates)
    return (panel.panel_id, len(panel.plates), routes,
            max((p.score for p in panel.plates), default=None),
            max(devs, default=None), "yes" if panel.sweep else "no", n_find)


_EXPLAIN = (
    "<h3>How to read this report</h3><ul style='margin:0;padding-left:1.2em;font-size:12px'>"
    "<li><b>Route</b>: how a plate was meshed. <i>single</i> = one surface; <i>mesh-trim</i> = "
    "cut from the panel's shared chart mesh (best); <i>lscm</i> = local flattening fallback; "
    "<i>best-member</i> = trimmed on the closest member surface (last resort).</li>"
    "<li><b>Score</b>: weighted badness (higher is worse): deviation/tolerance, snap/max snap, "
    "flipped UV triangles, non-manifold edges, overlaps, gaps, bounding-box offset, and a "
    "penalty for fallback routes.</li>"
    "<li><b>dev max m</b>: largest distance from the plate mesh to the true surface; "
    "<b>snap</b>: how far the trim contour was moved onto the mesh.</li>"
    "<li><b>overlaps / gaps</b>: faces overlapping neighbouring plates / vertices with no "
    "neighbour within tolerance. <b>boundary / non-manifold</b>: open and over-shared mesh edges.</li>"
    "<li><b>Charts</b>: <i>contour and snap</i> = trim ring on the mesh; <i>Deviation</i> = "
    "colour by distance to surface; <i>Boundary / non-manifold edges</i> = mesh defects; "
    "<i>scale spread</i> and <i>UV layout</i> (lscm) = flattening distortion and flipped "
    "triangles; <i>Chart mesh by member</i> = which source surface each face came from; "
    "<i>Tolerance sweep</i> = deviation and triangle count vs tolerance.</li>"
    "<li><b>Findings</b>: rule-based diagnoses, <i>confirmed</i> if backed by a probe, "
    "<i>likely</i> if inferred from metrics.</li></ul>")


def header_html(header) -> str:
    """Two-column table of the OCX <Header> metadata (empty string when absent)."""
    if header is None:
        return ""
    rows = [(label, getattr(header, attr, None)) for label, attr in (
        ("Name", "name"), ("Author", "author"), ("Organization", "organization"),
        ("Originating system", "originating_system"),
        ("Application version", "application_version"),
        ("Time stamp", "time_stamp"), ("Documentation", "documentation"))]
    body = "".join(f"<tr><th style='text-align:left'>{_html.escape(k)}</th>"
                   f"<td>{_html.escape(str(v))}</td></tr>" for k, v in rows if v)
    return f"<h3>OCX header</h3><table>{body}</table>" if body else ""


def intro_html(header) -> str:
    """OCX header on the left, static legend on the right."""
    return (f"<div style='display:flex;gap:2em;align-items:flex-start'>"
            f"<div>{header_html(header)}</div><div style='flex:1'>{_EXPLAIN}</div></div>")


def write_report(results, path, max_plates: int, title: str, header=None) -> None:
    """Write one self-contained HTML file with plotly.js embedded once."""
    tabs = [(f"tab{i}", p) for i, p in enumerate(results)]
    buttons = "".join(
        f'<button class="tb" data-t="{tid}" onclick="show(\'{tid}\')">'
        f"{_html.escape(p.panel_id)}</button> " for tid, p in tabs)
    sections = "".join(
        f'<div class="tab" id="{tid}">{panel_section(p, max_plates, p.tol_m)}</div>'
        for tid, p in tabs)
    buttons += ('<button class="tb" data-t="tabmodel" onclick="show(\'tabmodel\')">'
                "3D model</button> ")
    sections += f'<div class="tab" id="tabmodel">{model_section(results)}</div>'
    summary = _table(("panel", "plates", "routes", "worst score",     "max dev m", "sweep",
                          "findings"),
                         [_summary_row(p) for p in results])
    first = f"show('{tabs[0][0]}');" if tabs else ""
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{_html.escape(title)}</title><style>{_CSS}</style>"
            f"<script>{plotly.offline.get_plotlyjs()}</script></head><body>"
            f"<h1>{_html.escape(title)}</h1>{intro_html(header)}{summary}"
            f"<div>{buttons}</div>{sections}"
            f"<script>{_viewer_js()}</script><script>{_JS}{first}</script></body></html>")
    Path(path).write_text(page, encoding="utf-8")
    logger.info("Wrote report {} ({:.1f} MB)", path, len(page) / 1e6)


def write_json(results, path) -> None:
    """Write per-panel stats (no arrays, meshes or collectors)."""
    data = {}
    for panel in results:
        data[panel.panel_id] = {
            "chart": _chart_counts(panel.chart),
            "plates": {p.plate_id: {**{k: getattr(p, k) for k in _PLATE_SCALARS},
                                    "health": p.health,
                                    "findings": [asdict(f) for f in p.findings]}
                       for p in panel.plates},
            "findings": [asdict(f) for f in panel.findings],
            "sweep": [asdict(s) for s in panel.sweep],
        }
    Path(path).write_text(json.dumps(data, indent=2, default=float), encoding="utf-8")

