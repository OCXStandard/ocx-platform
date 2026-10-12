"""ocx_geometry — geometry evaluation kernel for the OCX IR.

Pure computation on ``ocx_model_core`` IR geometry: curve/surface evaluation,
length and area measurement, contour-closure checks and tessellation into
plain numpy mesh arrays. No display or rendering stack.
"""
from ocx_geometry.backend import ITessellator, RenderResult, TessellationOptions
from ocx_geometry.measure import LengthResolver, polyline_length
from ocx_geometry.mesh import PartMesh

__version__ = "0.1.0"

__all__ = [
    "ITessellator",
    "LengthResolver",
    "PartMesh",
    "RenderResult",
    "TessellationOptions",
    "polyline_length",
]
