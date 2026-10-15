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
