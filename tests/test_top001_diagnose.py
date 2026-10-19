"""TOP-001 diagnosis assembly (ocx_diagnose.top001)."""
import numpy as np
from ocx_diagnose.top001 import diagnose_panel, select_panels
from ocx_model_core.model.ir import (
    IrLimitedByRef,
    IrLine3D,
    IrPanel,
    IrPoint3D,
    IrSeam,
    IrVessel,
)
from ocx_rules.geometry_context import GeometryContext

M = "Um"  # metres (maps to 1.0 in measure._FALLBACK_TO_M)


def _pt(x, y, z):
    return IrPoint3D(x=x, y=y, z=z, unit=M)


def _line(a, b):
    return IrLine3D(curve_length=None, start=_pt(*a), end=_pt(*b))


def _seam(vessel, sid, a, b):
    vessel.seams[sid] = IrSeam(id=sid, trace_line=_line(a, b))


def _open_square_panel():
    """Panel whose LimitedBy traces three sides of a unit square (1 m gap)."""
    v = IrVessel(id="V1")
    _seam(v, "s1", (0, 0, 0), (1, 0, 0))
    _seam(v, "s2", (1, 0, 0), (1, 1, 0))
    _seam(v, "s3", (1, 1, 0), (0, 1, 0))
    panel = IrPanel(id="p1", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref="s1"),
        IrLimitedByRef(ref_type="SeamRef", local_ref="s2"),
        IrLimitedByRef(ref_type="SeamRef", local_ref="s3",
                       contour_start=_pt(1, 1, 0), contour_end=_pt(0, 1, 0)),
        IrLimitedByRef(ref_type="GridRef", local_ref="missing",
                       contour_start=_pt(0, 1, 0), contour_end=_pt(0, 0, 0)),
    ])
    v.panels["p1"] = panel
    return v, panel


def test_segments_in_document_order_with_bounds():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    assert [s.seq for s in diag.segments] == [1, 2, 3, 4]
    assert diag.segments[0].ref_type == "SeamRef"
    assert diag.segments[0].polyline is not None
    np.testing.assert_allclose(diag.segments[2].start, [1, 1, 0])
    np.testing.assert_allclose(diag.segments[2].end, [0, 1, 0])


def test_unresolvable_segment_flagged():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    assert diag.segments[3].polyline is None
    assert diag.unresolved_count == 1
    np.testing.assert_allclose(diag.segments[3].start, [0, 1, 0])


def test_gap_detected_above_tolerance():
    v, panel = _open_square_panel()
    diag = diagnose_panel(GeometryContext(v), panel, tol_m=0.001)
    # three chained sides leave one closure gap of 1 m
    assert diag.worst_gap_m > 0.9
    assert len(diag.gaps) == 1
    assert abs(diag.gaps[0].distance_m - 1.0) < 1e-9


def test_closed_panel_has_no_gaps():
    v, panel = _open_square_panel()
    _seam(v, "s4", (0, 1, 0), (0, 0, 0))
    closed = IrPanel(id="p2", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref=s)
        for s in ("s1", "s2", "s3", "s4")])
    v.panels["p2"] = closed
    diag = diagnose_panel(GeometryContext(v), closed, tol_m=0.001)
    assert diag.gaps == [] and diag.worst_gap_m <= 0.001


def test_select_panels_failing_by_default():
    v, _ = _open_square_panel()
    geo = GeometryContext(v)
    selected = select_panels(geo, panel_ids=None, tol_m=0.001)
    assert [p.panel_id for p in selected] == ["p1"]
    forced = select_panels(geo, panel_ids=["p1"], tol_m=0.001)
    assert [p.panel_id for p in forced] == ["p1"]
