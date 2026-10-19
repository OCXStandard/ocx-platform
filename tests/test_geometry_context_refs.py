"""GeometryContext.boundary_curve_for_ref resolution per LimitedBy ref type."""
from ocx_model_core.model.ir import (
    IrLimitedByRef,
    IrPanel,
    IrSeam,
    IrStiffener,
    IrVessel,
    ParentKind,
    ParentRef,
)
from ocx_rules.geometry_context import GeometryContext


def _vessel_with_seam():
    v = IrVessel(id="V1")
    # geometry object identity is all we need; type hints aren't enforced
    v.seams["s1"] = IrSeam(id="s1", trace_line="SENTINEL-CURVE")
    return v


def test_seam_ref_resolves_to_trace_line():
    geo = GeometryContext(_vessel_with_seam())
    ref = IrLimitedByRef(ref_type="SeamRef", local_ref="s1")
    assert geo.boundary_curve_for_ref(ref) == "SENTINEL-CURVE"


def test_free_edge_curve_returns_inline_curve():
    geo = GeometryContext(IrVessel(id="V1"))
    ref = IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="",
                         curve="INLINE-CURVE")
    assert geo.boundary_curve_for_ref(ref) == "INLINE-CURVE"


def test_stiffener_ref_resolves_to_trace():
    v = IrVessel(id="V1")
    v.stiffeners["st1"] = IrStiffener(
        id="st1", parent_ref=ParentRef(kind=ParentKind.PANEL, id="p1"),
        trace="STIFF-CURVE")
    geo = GeometryContext(v)
    ref = IrLimitedByRef(ref_type="StiffenerRef", local_ref="st1")
    assert geo.boundary_curve_for_ref(ref) == "STIFF-CURVE"


def test_unresolvable_ref_types_return_none():
    geo = GeometryContext(IrVessel(id="V1"))
    assert geo.boundary_curve_for_ref(
        IrLimitedByRef(ref_type="GridRef", local_ref="g1")) is None
    assert geo.boundary_curve_for_ref(
        IrLimitedByRef(ref_type="SeamRef", local_ref="missing")) is None


def test_boundary_curves_unchanged():
    v = _vessel_with_seam()
    panel = IrPanel(id="p1", limited_by=[
        IrLimitedByRef(ref_type="SeamRef", local_ref="s1"),
        IrLimitedByRef(ref_type="GridRef", local_ref="g1"),
    ])
    curves, unresolved = GeometryContext(v).boundary_curves(panel)
    assert curves == ["SENTINEL-CURVE"] and unresolved == 1
