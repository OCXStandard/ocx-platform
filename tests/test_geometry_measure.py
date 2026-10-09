"""Seed tests for the ocx-geometry evaluation kernel."""
from ocx_geometry import polyline_length
from ocx_model_core.model.ir.geometry import IrPoint3D


def _pt(x: float, y: float, z: float) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def test_polyline_length_empty_and_single_point():
    assert polyline_length([]) == 0.0
    assert polyline_length([_pt(1, 2, 3)]) == 0.0


def test_polyline_length_two_segments():
    pts = [_pt(0, 0, 0), _pt(3, 4, 0), _pt(3, 4, 12)]
    assert polyline_length(pts) == 17.0
