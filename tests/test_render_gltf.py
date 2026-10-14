"""Tests for GLB export — written file must reload with named parts."""
import numpy as np
import pytest
import trimesh
from ocx_geometry.mesh import PartMesh
from ocx_render.gltf_writer import write_glb


def square_mesh(part_id, kind, panel_id=None):
    extras = {"id": part_id, "kind": kind}
    if panel_id:
        extras["panel_id"] = panel_id
    return PartMesh(
        part_id=part_id,
        name=f"Name {part_id}",
        kind=kind,
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        triangles=np.array([[0, 1, 2], [0, 2, 3]]),
        normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        extras=extras,
    )


class TestWriteGlb:
    @pytest.mark.parametrize("panel_id", [None, "pan1"])
    @pytest.mark.parametrize("with_normals", [False, True])
    def test_export_converts_z_up_to_y_up_without_mirroring(
            self, tmp_path, panel_id, with_normals):
        mesh = square_mesh("pl1", "plate", panel_id=panel_id)
        if not with_normals:
            mesh.normals = None
        mesh.vertices[:] += [1, 2, 3]
        vertices = mesh.vertices.copy()
        normals = mesh.normals.copy() if mesh.normals is not None else None
        out = tmp_path / "axes.glb"
        write_glb([mesh], out)
        scene = trimesh.load(str(out), process=False)
        geometry = scene.geometry[mesh.name]

        np.testing.assert_allclose(geometry.vertices, [
            [1, 3, -2], [2, 3, -2], [2, 3, -3], [1, 3, -3],
        ])
        np.testing.assert_allclose(geometry.vertex_normals, [[0, 1, 0]] * 4)
        np.testing.assert_array_equal(geometry.faces, mesh.triangles)
        assert np.all(geometry.face_normals[:, 1] > 0)
        np.testing.assert_array_equal(mesh.vertices, vertices)
        if normals is not None:
            np.testing.assert_array_equal(mesh.normals, normals)
        else:
            assert mesh.normals is None
        transform, _ = scene.graph[f"plate_{mesh.part_id}"]
        np.testing.assert_allclose(transform, np.eye(4))

    def test_roundtrip(self, tmp_path):
        meshes = [
            square_mesh("pl1", "plate", panel_id="pan1"),
            square_mesh("st1", "stiffener", panel_id="pan1"),
            square_mesh("pi1", "pillar"),
        ]
        out = tmp_path / "model.glb"
        write_glb(meshes, out)
        assert out.exists() and out.stat().st_size > 0

        scene = trimesh.load(str(out))
        assert isinstance(scene, trimesh.Scene)
        node_names = set(scene.graph.nodes)
        assert "plate_pl1" in node_names
        assert "stiffener_st1" in node_names
        assert "pillar_pi1" in node_names
        assert "Panel_pan1" in node_names  # grouping node
        # geometry survived
        total_tris = sum(len(g.faces) for g in scene.geometry.values())
        assert total_tris == 6
        # vertices are finite
        for g in scene.geometry.values():
            assert np.all(np.isfinite(g.vertices))

    def test_distinct_part_colors(self, tmp_path):
        meshes = [square_mesh("pl1", "plate"), square_mesh("pl2", "plate")]
        out = tmp_path / "two.glb"
        write_glb(meshes, out)
        scene = trimesh.load(str(out))
        colors = set()
        for g in scene.geometry.values():
            mat = g.visual.material
            colors.add(tuple(np.asarray(mat.baseColorFactor).round(4)))
        assert len(colors) == 2

    def test_empty_mesh_list_does_not_raise(self, tmp_path):
        out = tmp_path / "empty.glb"
        result = write_glb([], out)
        assert result == out
        assert not out.exists()  # nothing written, but no crash
