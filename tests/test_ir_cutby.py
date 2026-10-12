"""IR types for CutBy openings: IrTransformation, IrHole2DContour, IrParametricHole."""
from ocx_model_core.model.ir import (
    IrHole2D,
    IrHole2DContour,
    IrParametricHole,
    IrTransformation,
)
from ocx_model_core.model.ir.base import Quantity, Ref
from ocx_model_core.model.ir.geometry import IrPoint3D, IrVector3D
from ocx_model_core.model.ir.structural import IrPanel, IrPlate


def test_transformation_defaults():
    t = IrTransformation()
    assert t.origin is None and t.primary_axis is None and t.secondary_axis is None


def test_hole2dcontour_fields():
    t = IrTransformation(origin=IrPoint3D(1, 2, 3, "Um"),
                         primary_axis=IrVector3D(1, 0, 0),
                         secondary_axis=IrVector3D(0, 0, 1))
    hc = IrHole2DContour(id="hc1", hole_ref=Ref("H1"), transformation=t)
    assert hc.hole_ref.local_ref == "H1"
    assert hc.transformation.origin.y == 2
    assert hc.name is None and hc.guidref is None


def test_parametric_hole_defaults_and_hole2d_typing():
    p = IrParametricHole(variant="rectangular_hole",
                         height=Quantity(0.8, "Um"), width=Quantity(0.6, "Um"))
    assert p.fillet_radius is None and p.exponent is None
    h = IrHole2D(id="h1", parametric=p)
    assert h.parametric.variant == "rectangular_hole"


def test_panel_and_plate_cutby_defaults():
    panel = IrPanel(id="p1")
    assert panel.cut_by_holes == [] and panel.cut_by_contours == []
    from ocx_model_core.model.ir.base import ParentKind, ParentRef
    plate = IrPlate(id="pl1", parent_ref=ParentRef(ParentKind.PANEL, "p1"))
    assert plate.cut_by_holes == [] and plate.cut_by_contours == []
