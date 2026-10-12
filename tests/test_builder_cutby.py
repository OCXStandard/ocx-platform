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
                                              exponent=_qty(2.5, "UDimless")))])
        ir = IrVessel(id="v1")
        _b()._build_hole_catalogue(cat, ir)
        assert ir.hole_shape_catalogue.holes["H2"].parametric.diameter.value == 0.5
        p3 = ir.hole_shape_catalogue.holes["H3"].parametric
        assert p3.variant == "super_elliptical" and p3.exponent.value == 2.5
