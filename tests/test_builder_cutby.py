"""Builder coverage for CutBy openings and parametric hole dimensions."""
from types import SimpleNamespace as NS

from ocx_model_core.builders.v3_builder import OcxV3Builder
from ocx_model_core.model.ir import IrVessel


def _b() -> OcxV3Builder:
    return OcxV3Builder()


def _qty(value, unit="Um"):
    return NS(numericvalue=value, unit=unit)


def _hole2d(hid, **variants):
    base = dict(id=hid, name=None, guidref=f"guid-{hid}", contour=None,
                ellipse=None, rectangular_mickey_mouse_ears=None,
                rectangular_hole=None, super_elliptical=None,
                symmetrical_hole=None, parametric_circle=None)
    base.update(variants)
    return NS(**base)


class TestParametricDimensions:
    def test_rectangular_hole_dims(self):
        cat = NS(id="HC", name=None, hole2_d=[_hole2d(
            "H1", rectangular_hole=NS(height=_qty(0.8), width=_qty(0.6),
                                      fillet_radius=_qty(0.15)))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        p = ir.hole_shape_catalogue.holes["H1"].parametric
        assert p.variant == "rectangular_hole"
        assert p.height.value == 0.8 and p.width.value == 0.6
        assert p.fillet_radius.value == 0.15
        assert p.diameter is None

    def test_circle_and_superellipse_dims(self):
        cat = NS(id="HC", name=None, hole2_d=[
            _hole2d("H2", parametric_circle=NS(diameter=_qty(0.5))),
            _hole2d("H3", super_elliptical=NS(major_diameter=_qty(1.2),
                                              minor_diameter=_qty(0.6),
                                              exponent=2.5))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        assert ir.hole_shape_catalogue.holes["H2"].parametric.diameter.value == 0.5
        p3 = ir.hole_shape_catalogue.holes["H3"].parametric
        assert p3.variant == "super_elliptical" and p3.exponent.value == 2.5
        assert p3.exponent.unit == ""

    def test_superellipse_quantity_shaped_exponent(self):
        # Older/stub bindings may wrap the exponent as a quantity.
        cat = NS(id="HC", name=None, hole2_d=[
            _hole2d("H4", super_elliptical=NS(major_diameter=_qty(1.2),
                                              minor_diameter=_qty(0.6),
                                              exponent=_qty(2.5, "UDimless")))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        p4 = ir.hole_shape_catalogue.holes["H4"].parametric
        assert p4.exponent.value == 2.5 and p4.exponent.unit == "UDimless"


def _transformation():
    return NS(origin=NS(coordinates=[8.5, 10.0, 9.9], unit="Um"),
              primary_axis=NS(direction=[0.0, 0.0, -1.0]),
              secondary_axis=NS(direction=[1.0, 0.0, 0.0]))


def _hole2d_contour(cid, ref):
    return NS(id=cid, name=None, guidref=f"guid-{cid}",
              hole_ref=NS(local_ref=ref, guidref=f"guid-{ref}", ref_type="ocx:Hole2D",
                          offset=None, offset_direction=None),
              transformation=_transformation())


class TestCutByParsing:
    def test_panel_cut_by_holes(self):
        raw = NS(id="pan1", name="P", guidref=None, function_type=None,
                 tightness=None, point_on_surface=None,
                 composed_of=None, stiffened_by=None, limited_by=None,
                 unbounded_geometry=None,
                 cut_by=NS(hole2_dcontour=[_hole2d_contour("hc1", "H1"),
                                           _hole2d_contour("hc2", "H2")],
                           inner_contour=[]))
        ir = IrVessel(id="v1")
        panel = _b()._build_panel(raw, ir, "v1")
        assert len(panel.cut_by_holes) == 2
        hc = panel.cut_by_holes[0]
        assert hc.id == "hc1"
        assert hc.hole_ref.local_ref == "H1"
        assert hc.transformation.origin.x == 8.5
        assert hc.transformation.primary_axis.z == -1.0
        assert hc.transformation.secondary_axis.x == 1.0

    def test_panel_without_cut_by_is_empty(self):
        raw = NS(id="pan2", name=None, guidref=None, function_type=None,
                 tightness=None, point_on_surface=None, composed_of=None,
                 stiffened_by=None, limited_by=None, unbounded_geometry=None)
        ir = IrVessel(id="v1")
        panel = _b()._build_panel(raw, ir, "v1")
        assert panel.cut_by_holes == [] and panel.cut_by_contours == []

    def test_plate_cut_by_holes_from_plate_cut_by(self):
        from ocx_model_core.model.ir.base import ParentKind, ParentRef
        raw = NS(id="pl1", name=None, guidref=None, plate_material=None,
                 net_area=None, function_type=None, outer_contour=None,
                 point_on_surface=None,
                 plate_cut_by=NS(hole2_dcontour=[_hole2d_contour("hc3", "H3")],
                                 inner_contour=[], slot_contour=[]))
        plate = _b()._build_plate(raw, ParentRef(ParentKind.PANEL, "pan1"))
        assert len(plate.cut_by_holes) == 1
        assert plate.cut_by_holes[0].hole_ref.local_ref == "H3"

    def test_missing_transformation_is_none(self):
        hc = _hole2d_contour("hc4", "H4")
        hc.transformation = None
        raw_cut_by = NS(hole2_dcontour=[hc], inner_contour=[])
        out = _b()._build_hole2d_contours(raw_cut_by)
        assert out[0].transformation is None
