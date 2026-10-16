from types import SimpleNamespace as NS

from ocx_diagnose.advice import Finding, panel_findings, plate_findings
from ocx_diagnose.probes import ContourProbe


def _plate(**kw):
    base = dict(plate_id="p1", route="mesh-trim", trim_reject=None, snap_m=0.0,
                max_snap_m=1.5, dev_max_m=0.0, overlap_faces=0, gap_vertices=0,
                max_gap_m=0.0, flipped_frac=None, spread_max=None,
                health={"boundary_edges": 4, "non_manifold_edges": 0})
    base.update(kw)
    return NS(**base)


def _ids(fs):
    return {f.id for f in fs}


def test_healthy_plate_has_no_findings():
    assert plate_findings(_plate(), ContourProbe(0.0, 0), [], 0.05) == []


def test_overlap_without_probe_is_likely_and_with_probe_confirmed():
    p = _plate(overlap_faces=30000)
    f = {x.id: x for x in plate_findings(p, ContourProbe(0, 0), [], 0.05)}["overlap"]
    assert f.status == "likely" and f.severity == "high"
    assert "30000" in f.evidence and f.source_steps and f.mesh_steps
    g = {x.id: x for x in plate_findings(p, ContourProbe(0, 0), [(3, 7, 6)], 0.05)}["overlap"]
    assert g.status == "confirmed" and "3" in g.evidence and "7" in g.evidence


def test_each_plate_rule_fires():
    tol = 0.05
    cases = {
        "trim-reject": _plate(trim_reject="snap too large"),
        "snap": _plate(snap_m=1.0, max_snap_m=1.5),
        "chart-distortion": _plate(route="lscm", flipped_frac=0.02, spread_max=3.0),
        "deviation": _plate(dev_max_m=0.2),
        "non-manifold": _plate(health={"boundary_edges": 4, "non_manifold_edges": 5}),
        "gaps": _plate(gap_vertices=10, max_gap_m=0.02),
    }
    for fid, plate in cases.items():
        assert fid in _ids(plate_findings(plate, ContourProbe(0, 0), [], tol)), fid
    assert "open-contour" in _ids(plate_findings(_plate(), ContourProbe(2.0, 0), [], tol))
    assert "self-touching-contour" in _ids(plate_findings(_plate(), ContourProbe(0, 3), [], tol))


def test_panel_findings_and_ranking():
    chart = NS(n_members=10, boundary_edges_before_stitch=100, boundary_edges_after_stitch=60)
    fs = panel_findings("pan", chart, duplicates=[(1, 2, 6)], degenerate=[4])
    assert _ids(fs) == {"duplicate-members", "degenerate-members", "seam-gaps"}
    assert fs[0].severity == "high"          # ranked high -> medium -> low
    assert all(isinstance(f, Finding) and f.scope == "panel" for f in fs)


def test_analyse_model_attaches_findings():
    from ocx_diagnose.analyse import analyse_model

    from tests.test_render_model import make_vessel
    panels = analyse_model(make_vessel(), {"pan1"}, 50.0, [])
    assert isinstance(panels[0].findings, list)
    assert all(isinstance(p.findings, list) for p in panels[0].plates)
