"""Colour schemes: plates/brackets by thickness, sweeps by section."""
import json
import struct

import numpy as np
import pytest
from ocx_geometry.mesh import PartMesh, part_color
from ocx_render.colors import NO_THICKNESS, THICKNESS_PALETTE, apply_color_scheme


def _pm(part_id, kind, **extras):
    return PartMesh(part_id, part_id, kind, np.eye(3), np.array([[0, 1, 2]]),
                    extras={"kind": kind, **extras})


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


class TestThicknessScheme:
    def test_distinct_thicknesses_get_palette_colours_in_value_order(self):
        meshes = [_pm("a", "plate", thickness_mm=12.0),
                  _pm("b", "plate", thickness_mm=10.0),
                  _pm("c", "bracket", thickness_mm=12.0)]
        apply_color_scheme(meshes, "thickness")
        assert _hex(meshes[1].color) == THICKNESS_PALETTE[0]     # 10 mm
        assert _hex(meshes[0].color) == THICKNESS_PALETTE[1]     # 12 mm
        assert meshes[2].color == meshes[0].color                # same thickness

    def test_missing_thickness_is_grey(self):
        meshes = [_pm("a", "plate", thickness_mm=None), _pm("b", "plate")]
        apply_color_scheme(meshes, "thickness")
        assert meshes[0].color == meshes[1].color == NO_THICKNESS

    def test_sweeps_share_a_shade_per_section(self):
        meshes = [_pm("s1", "stiffener", section="HP200"),
                  _pm("s2", "stiffener", section="HP200"),
                  _pm("s3", "stiffener", section="FB100"),
                  _pm("p1", "pillar", section=None)]
        apply_color_scheme(meshes, "thickness")
        assert meshes[0].color == meshes[1].color == part_color("stiffener", "HP200")
        assert meshes[2].color == part_color("stiffener", "FB100")
        assert meshes[3].color == part_color("pillar", "")

    def test_legend_lists_thicknesses_in_order_with_counts(self):
        meshes = [_pm("a", "plate", thickness_mm=12.0),
                  _pm("b", "plate", thickness_mm=10.0),
                  _pm("c", "bracket", thickness_mm=12.0),
                  _pm("d", "plate"),
                  _pm("s", "stiffener", section="X")]
        legend = apply_color_scheme(meshes, "thickness")
        assert legend == [
            {"label": "10 mm", "thickness_mm": 10.0, "color": THICKNESS_PALETTE[0],
             "count": 1},
            {"label": "12 mm", "thickness_mm": 12.0, "color": THICKNESS_PALETTE[1],
             "count": 2},
            {"label": "no thickness", "thickness_mm": None,
             "color": _hex(NO_THICKNESS), "count": 1},
        ]

    def test_more_thicknesses_than_palette_reuses_colours(self):
        n = len(THICKNESS_PALETTE) + 1
        meshes = [_pm(f"p{i}", "plate", thickness_mm=float(i)) for i in range(n)]
        legend = apply_color_scheme(meshes, "thickness")
        assert len(legend) == n
        assert legend[-1]["color"] == THICKNESS_PALETTE[0]

    def test_palette_entries_are_unique_hex(self):
        assert len(set(THICKNESS_PALETTE)) == len(THICKNESS_PALETTE) >= 17


class TestPartScheme:
    def test_part_scheme_keeps_per_part_colours_and_has_no_legend(self):
        meshes = [_pm("a", "plate", thickness_mm=10.0)]
        before = meshes[0].color
        assert apply_color_scheme(meshes, "part") == []
        assert meshes[0].color == before

    def test_unknown_scheme_rejected(self):
        with pytest.raises(ValueError):
            apply_color_scheme([], "rainbow")


class TestRenderExtras:
    def test_plate_thickness_and_stiffener_section_in_extras(self):
        from ocx_model_core.model.ir.base import Quantity
        from ocx_render.render import render_model

        from tests.test_render_model import make_vessel

        vessel = make_vessel()
        vessel.plates["pl1"].thickness = Quantity(0.012, "Um")
        by_id = {m.part_id: m for m in render_model(vessel).meshes}
        assert by_id["pl1"].extras["thickness_mm"] == 12.0
        assert by_id["st1"].extras["section"] == "fb100"

    def test_plate_without_thickness_has_none(self):
        from ocx_render.render import render_model

        from tests.test_render_model import make_vessel

        by_id = {m.part_id: m for m in render_model(make_vessel()).meshes}
        assert by_id["pl1"].extras["thickness_mm"] is None


def _glb_json(path):
    b = path.read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    return json.loads(b[20:20 + n])


class TestGlbWriter:
    def test_same_colour_parts_share_one_material(self, tmp_path):
        from ocx_render.gltf_writer import write_glb

        meshes = [_pm("a", "plate", thickness_mm=10.0),
                  _pm("b", "plate", thickness_mm=10.0)]
        apply_color_scheme(meshes, "thickness")
        j = _glb_json(write_glb(meshes, tmp_path / "m.glb"))
        assert len(j["materials"]) == 1

    def test_legend_written_to_scene_extras(self, tmp_path):
        from ocx_render.gltf_writer import write_glb

        legend = [{"label": "10 mm", "thickness_mm": 10.0, "color": "#ff00ff",
                   "count": 1}]
        j = _glb_json(write_glb([_pm("a", "plate")], tmp_path / "m.glb",
                                legend=legend))
        assert j["scenes"][0]["extras"]["legend"] == legend


class TestCli:
    def _run(self, tmp_path, monkeypatch, *args):
        import ocx_render.cli as cli_mod
        from ocx_render.cli import app
        from typer.testing import CliRunner

        from tests.test_render_model import make_vessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        glb = tmp_path / "out.glb"
        result = CliRunner().invoke(
            app, [str(dummy), "-d", str(glb), "--no-html", *args])
        return result, glb

    def test_default_writes_thickness_legend(self, tmp_path, monkeypatch):
        result, glb = self._run(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        legend = _glb_json(glb)["scenes"][0]["extras"]["legend"]
        assert legend[0]["label"] == "no thickness"

    def test_color_by_part_writes_no_legend(self, tmp_path, monkeypatch):
        result, glb = self._run(tmp_path, monkeypatch, "--color-by", "part")
        assert result.exit_code == 0, result.output
        assert "legend" not in _glb_json(glb)["scenes"][0].get("extras", {})

    def test_unknown_color_scheme_is_a_usage_error(self, tmp_path, monkeypatch):
        result, glb = self._run(tmp_path, monkeypatch, "--color-by", "rainbow")
        assert result.exit_code == 2 and not glb.exists()
