import json

import numpy as np
from ocx_diagnose import figures as fg
from ocx_diagnose.analyse import analyse_model
from ocx_diagnose.report import write_json, write_report

from tests.test_render_model import make_vessel


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


def test_report_and_json_are_written_and_self_contained(tmp_path):
    res = analyse_model(make_vessel(), {"pan1"}, 50.0, [25.0, 100.0])
    html = tmp_path / "r.html"
    js = tmp_path / "r.json"
    write_report(res, html, max_plates=5, title="t")
    write_json(res, js)
    text = html.read_text(encoding="utf-8")
    assert "pan1" in text and "pl1" in text
    assert "<script src=" not in text and "<script charset" not in text  # no CDN reference
    assert text.count("plotly.js v") == 1  # library embedded exactly once
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["pan1"]["plates"]["pl1"]["route"] == "single"
    assert len(data["pan1"]["sweep"]) == 2

