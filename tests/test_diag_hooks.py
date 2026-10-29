from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import ChartDiag, DiagSink, PlateDiag


def test_options_default_has_no_diag_and_no_panel_filter():
    o = TessellationOptions()
    assert o.diag is None and o.only_panels is None


def test_sink_collects_by_id():
    sink = DiagSink()
    sink.plates["P1"] = PlateDiag(plate_id="P1", panel_id="PN1")
    sink.charts["PN1"] = ChartDiag(n_members=3)
    assert sink.plates["P1"].route == "unknown"
    assert sink.charts["PN1"].n_members == 3


from ocx_render.render import render_model

from tests.test_render_model import make_vessel


def test_single_member_plate_is_recorded_with_route_single():
    vessel = make_vessel()
    sink = DiagSink()
    res = render_model(vessel, TessellationOptions(diag=sink))
    assert res.rendered_count >= 1
    pd = sink.plates["pl1"]
    assert pd.route == "single" and pd.panel_id == "pan1"
    assert pd.contour is not None and len(pd.candidates) == 1
    assert pd.seconds > 0


def test_only_panels_filters_plates():
    vessel = make_vessel()
    res = render_model(vessel, TessellationOptions(only_panels=frozenset({"nope"})))
    assert not [m for m in res.meshes if m.kind == "plate"]
    assert "pl1" not in res.skipped


import numpy as np  # noqa: E402
from ocx_geometry.lscm import make_lscm_chart  # noqa: E402
from ocx_geometry.mesh_trim import MeshTrimmer  # noqa: E402

from tests.test_mesh_trim import _grid, _square  # noqa: E402
from tests.test_render_lscm import _bilge_members_and_hints  # noqa: E402


def test_chart_build_fills_chartdiag():
    members, hints = _bilge_members_and_hints()
    cd = ChartDiag()
    chart = make_lscm_chart(members, 0.05, hints, diag=cd)
    assert chart is not None
    assert cd.n_members == 3 and cd.verts_after_weld <= cd.verts_before_weld
    assert cd.boundary_edges_after_stitch <= cd.boundary_edges_before_stitch
    assert cd.F is not None and len(cd.F) == len(chart.mesh[1])


def test_trim_records_snap_and_reject_reason():
    V, F = _grid()
    tr = MeshTrimmer(V, F, 0.05)
    ok = PlateDiag(plate_id="a", panel_id="p")
    assert tr.trim(_square(2.3, 6.7, 3.1, 7.9), [], np.array([4.0, 5.0, 0.16]),
                   diag=ok) is not None
    assert ok.snap_m is not None and ok.trim_reject is None
    bad = PlateDiag(plate_id="b", panel_id="p")
    far = _square(2.3, 6.7, 3.1, 7.9) + np.array([0.0, 0.0, 50.0])
    assert tr.trim(far, [], None, diag=bad) is None
    assert bad.trim_reject == "outer ring unusable"


def test_param_for_sets_last_stage():
    members, hints = _bilge_members_and_hints()
    chart = make_lscm_chart(members, 0.05, hints)
    param = chart.param_for(hints[:10 * 2])
    if param is not None:
        assert chart.last_stage in {"gates", "no-gates", "tutte"}
        V, F, uv = param.chart
        assert len(uv) == len(V)


def test_plate_skips_include_panel_level_hole_failures():
    from ocx_diagnose.sweep import plate_skips
    from ocx_geometry.backend import RenderResult

    vessel = make_vessel()
    res = RenderResult()
    res.hole_failures["pan1/hole:hc1"] = "unresolvable HoleRef"
    res.hole_failures["other/hole:hc9"] = "unresolvable HoleRef"
    assert plate_skips(vessel, res, {"pan1"}) == {
        "pan1/hole:hc1": "unresolvable HoleRef"}
    assert "pan1/hole:hc1" in plate_skips(vessel, res, None)
