"""ocx_geometry — geometry evaluation kernel for the OCX IR.

Pure computation on ``ocx_model_core`` IR geometry: curve/surface evaluation,
length and area measurement, contour-closure checks and tessellation into
plain numpy mesh arrays. No display or rendering stack.
"""
from ocx_geometry.measure import polyline_length

__version__ = "0.1.0"

__all__ = ["polyline_length"]
