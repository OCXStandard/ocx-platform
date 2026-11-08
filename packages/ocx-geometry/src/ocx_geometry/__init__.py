"""ocx_geometry — geometry evaluation kernel for the OCX IR.

Pure computation on ``ocx_model_core`` IR geometry: curve/surface evaluation,
length and area measurement, contour-closure checks, 2-D section outlines,
polygon topology and hole placement. No tessellation or display stack.
"""
from ocx_geometry.measure import LengthResolver, polyline_length

__version__ = "0.2.0"

__all__ = ["LengthResolver", "polyline_length"]
