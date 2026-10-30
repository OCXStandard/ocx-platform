"""ocx_render — GLB/HTML rendering of OCX models.

``render_model(vessel, options)`` tessellates an ``IrVessel`` into
``PartMesh`` objects; ``gltf_writer``/``html_viewer`` export them.
"""
from importlib.metadata import version

from ocx_geometry.backend import RenderResult, TessellationOptions
from ocx_geometry.mesh import PartMesh

from ocx_render.render import render_model

__version__ = version("ocx-render")

__all__ = ["PartMesh", "RenderResult", "TessellationOptions", "render_model"]
