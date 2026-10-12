"""Assemble PartMeshes into a trimesh Scene and export binary glTF (GLB).

Node naming: ``<kind>_<part_id>`` per part; parts with a ``panel_id`` extra
are parented under a ``Panel_<panel_id>`` grouping node.  Part extras are
attached as mesh metadata (exported into glTF mesh ``extras``).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from loguru import logger
from trimesh.visual.material import PBRMaterial

from ocx_geometry.mesh import PartMesh


def _material(color: tuple[int, int, int]) -> PBRMaterial:
    return PBRMaterial(
        baseColorFactor=[color[0] / 255.0, color[1] / 255.0, color[2] / 255.0, 1.0],
        metallicFactor=0.1,
        roughnessFactor=0.8,
        doubleSided=True,
    )


def write_glb(meshes: list[PartMesh], destination: Path) -> Path:
    """Write all parts to a single .glb file; returns the destination path.

    An empty mesh list writes no file (trimesh cannot export empty scenes);
    callers should check ``destination.exists()``.
    """
    destination = Path(destination)
    if not meshes:
        logger.warning("No meshes to export; skipping GLB write to {}", destination)
        return destination

    scene = trimesh.Scene()
    groups: set[str] = set()

    for pm in meshes:
        tm = trimesh.Trimesh(
            vertices=pm.vertices,
            faces=pm.triangles,
            vertex_normals=pm.normals,
            process=False,
        )
        tm.visual = trimesh.visual.TextureVisuals(material=_material(pm.color))
        tm.metadata.update(pm.extras)

        parent = None
        panel_id = pm.extras.get("panel_id")
        if panel_id:
            parent = f"Panel_{panel_id}"
            if parent not in groups:
                scene.graph.update(
                    frame_to=parent,
                    frame_from=scene.graph.base_frame,
                    matrix=np.eye(4),
                )
                groups.add(parent)

        scene.add_geometry(
            tm,
            node_name=f"{pm.kind}_{pm.part_id}",
            geom_name=pm.name or pm.part_id,
            parent_node_name=parent or scene.graph.base_frame,
        )

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(destination))  # format inferred from .glb suffix
    return destination
