"""Plotly figure builders for the diagnostic report."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from ocx_diagnose.checks import edge_segments, snap_vectors

_SCENE = dict(aspectmode="data")
_MARGIN = dict(l=0, r=0, t=40, b=0)
_PALETTE = ("#4c78a8", "#59a14f", "#b8a04a", "#8e6bb0", "#46a6a6", "#a07850")


def model_fig(plates, title="Rendered model"):
    """All plates in one scene, one Mesh3d trace per plate (trace name = plate id).

    ``plates`` is an iterable of (plate_id, panel_id, V, F); colour is per panel.
    """
    fig = go.Figure()
    colours: dict[str, str] = {}
    for plate_id, panel_id, V, F in plates:
        if len(F) == 0:
            continue
        col = colours.setdefault(panel_id, _PALETTE[len(colours) % len(_PALETTE)])
        V = np.asarray(V, np.float32)
        fig.add_trace(go.Mesh3d(
            x=V[:, 0], y=V[:, 1], z=V[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
            color=col, name=plate_id, hovertext=f"{plate_id} ({panel_id})", hoverinfo="text",
            flatshading=True, showlegend=False, meta=col))
    fig.update_layout(title=title, scene=_SCENE, margin=_MARGIN)
    return fig


def _lines(segments: np.ndarray):
    """(k, 2, 3) segments -> x, y, z arrays with None separators."""
    if len(segments) == 0:
        return [], [], []
    pad = np.full((len(segments), 1, 3), np.nan)
    flat = np.concatenate([segments, pad], axis=1).reshape(-1, 3)
    return tuple([None if np.isnan(v) else float(v) for v in flat[:, c]] for c in range(3))


def chart_mesh_fig(V, F, face_value, title, colorscale="Turbo", flipped=None):
    """3-D mesh coloured per face; flipped faces (bool mask) drawn red on top."""
    fig = go.Figure(go.Mesh3d(
        x=V[:, 0], y=V[:, 1], z=V[:, 2], i=F[:, 0], j=F[:, 1], k=F[:, 2],
        intensity=np.asarray(face_value, float), intensitymode="cell",
        colorscale=colorscale, showscale=True, flatshading=True))
    if flipped is not None and flipped.any():
        Ff = F[flipped]
        fig.add_trace(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                                i=Ff[:, 0], j=Ff[:, 1], k=Ff[:, 2],
                                color="red", name="flipped"))
    fig.update_layout(title=title, scene=_SCENE, margin=_MARGIN)
    return fig


def uv_layout_fig(uv, F, flipped):
    """2-D UV flattening: edges grey, flipped triangles red."""
    def edges(mask):
        xs, ys = [], []
        for tri in uv[F[mask]]:
            for a, b in ((0, 1), (1, 2), (2, 0)):
                xs += [tri[a, 0], tri[b, 0], None]
                ys += [tri[a, 1], tri[b, 1], None]
        return xs, ys

    fig = go.Figure()
    xs, ys = edges(~flipped)
    fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", name="ok",
                               line=dict(color="#888", width=1)))
    if flipped.any():
        xs, ys = edges(flipped)
        fig.add_trace(go.Scattergl(x=xs, y=ys, mode="lines", name="flipped",
                                   line=dict(color="red", width=2)))
    fig.update_layout(title="UV layout", yaxis=dict(scaleanchor="x"), margin=_MARGIN)
    return fig


def ring_fig(V, F, ring, title):
    """Plate mesh (translucent), contour ring, and ring -> mesh snap vectors."""
    fig = go.Figure(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                              i=F[:, 0], j=F[:, 1], k=F[:, 2],
                              color="lightsteelblue", opacity=0.5, name="plate"))
    closed = np.vstack([ring, ring[:1]])
    fig.add_trace(go.Scatter3d(x=closed[:, 0], y=closed[:, 1], z=closed[:, 2],
                               mode="lines", name="contour",
                               line=dict(color="black", width=4)))
    s, e = snap_vectors(ring, V)
    x, y, z = _lines(np.stack([s, e], axis=1))
    fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode="lines", name="snap",
                               line=dict(color="red", width=3)))
    fig.update_layout(title=title, scene=_SCENE, margin=_MARGIN)
    return fig


def deviation_fig(points, dev, tol_m):
    """Sample points coloured by deviation from the exact surface (m)."""
    ok = np.isfinite(dev)
    fig = go.Figure(go.Scatter3d(
        x=points[ok, 0], y=points[ok, 1], z=points[ok, 2], mode="markers",
        marker=dict(size=2, color=dev[ok], colorscale="Turbo", cmin=0.0,
                    cmax=2.0 * tol_m, colorbar=dict(title="dev (m)"))))
    fig.update_layout(title=f"Deviation (colour max = 2 x tol = {2 * tol_m:.3f} m)",
                      scene=_SCENE, margin=_MARGIN)
    return fig


def edges_fig(V, F):
    """Mesh with boundary edges (orange) and non-manifold edges (red)."""
    fig = go.Figure(go.Mesh3d(x=V[:, 0], y=V[:, 1], z=V[:, 2],
                              i=F[:, 0], j=F[:, 1], k=F[:, 2],
                              color="lightgrey", opacity=0.4, name="plate"))
    for kind, color in (("boundary", "orange"), ("non_manifold", "red")):
        x, y, z = _lines(edge_segments(V, F, kind))
        fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode="lines", name=kind,
                                   line=dict(color=color, width=4)))
    fig.update_layout(title="Boundary / non-manifold edges", scene=_SCENE, margin=_MARGIN)
    return fig


def sweep_fig(tol_mm, dev_max_m, triangles):
    """Max deviation vs tolerance, with the y = x target line, and triangle count."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tol_mm, y=[d * 1000 if d is not None else None for d in dev_max_m],
                             mode="lines+markers", name="max deviation (mm)"))
    fig.add_trace(go.Scatter(x=tol_mm, y=tol_mm, mode="lines", name="target (= tolerance)",
                             line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=tol_mm, y=triangles, mode="lines+markers",
                             name="triangles", yaxis="y2"))
    fig.update_layout(title="Tolerance sweep", xaxis=dict(title="tolerance (mm)", type="log"),
                      yaxis=dict(title="deviation (mm)"),
                      yaxis2=dict(title="triangles", overlaying="y", side="right"),
                      margin=_MARGIN)
    return fig
