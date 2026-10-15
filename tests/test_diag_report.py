import numpy as np
from ocx_diagnose import figures as fg


def _tri():
    V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    return V, np.array([[0, 1, 2], [0, 2, 3]])


def test_each_builder_returns_figure_with_traces():
    V, F = _tri()
    uv = V[:, :2]
    assert len(fg.chart_mesh_fig(V, F, np.array([0, 1]), "members").data) >= 1
    assert len(fg.uv_layout_fig(uv, F, np.array([False, True])).data) >= 1
    assert len(fg.ring_fig(V, F, V[:3] + [0, 0, 0.1], "ring").data) >= 2
    assert len(fg.deviation_fig(V, V[:, 2] + 0.01, 0.05).data) >= 1
    assert len(fg.edges_fig(V, F).data) >= 1
    assert len(fg.sweep_fig([10.0, 50.0], [0.003, 0.02], [4000, 900]).data) >= 2
