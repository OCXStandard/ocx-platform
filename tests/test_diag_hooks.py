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
