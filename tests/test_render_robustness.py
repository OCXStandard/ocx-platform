"""render_model never raises per part; CLI maps every failure to an exit code."""
import numpy as np
import ocx_render.render as render_mod
from ocx_geometry.backend import RenderResult
from ocx_geometry.mesh import PartMesh
from ocx_render.cli import app
from ocx_render.render import render_model
from typer.testing import CliRunner

import tests.test_render_brackets as brackets_tests
import tests.test_render_model as model_tests
from tests.test_render_model import make_vessel


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


class TestPerPartIsolation:
    def test_sweep_exception_skips_only_that_part(self, monkeypatch):
        monkeypatch.setattr(render_mod, "sweep_profile", _boom)
        result = render_model(make_vessel())
        assert result.skipped["st1"] == "error: boom"
        assert any(m.kind == "plate" for m in result.meshes)

    def test_plate_tessellation_exception_skips_only_that_plate(self, monkeypatch):
        monkeypatch.setattr(render_mod.UvTessellator,
                            "tessellate_trimmed_surface", _boom)
        result = render_model(make_vessel())
        assert result.skipped["pl1"] == "error: boom"
        assert any(m.kind == "stiffener" for m in result.meshes)

    def test_plate_contour_exception_skips_only_that_plate(self, monkeypatch):
        monkeypatch.setattr(render_mod, "sample_contour", _boom)
        result = render_model(make_vessel())
        assert result.skipped["pl1"] == "error: boom"
        assert any(m.kind == "stiffener" for m in result.meshes)

    def test_bracket_exception_skips_only_that_bracket(self, monkeypatch):
        monkeypatch.setattr(render_mod, "tessellate_bracket", _boom)
        result = render_model(brackets_tests.TestRenderModelBrackets._vessel())
        assert result.skipped["br1"] == "error: boom"
        assert result.skipped["br2"] == "no outer contour"

    def test_panel_surface_exception_skips_its_plates(self, monkeypatch):
        monkeypatch.setattr(render_mod, "make_param", _boom)
        result = render_model(make_vessel())
        assert result.skipped["pl1"] == "no resolvable panel surface"


class TestHoleFailuresSeparated:
    def test_hole_failures_not_in_skipped(self):
        vessel = model_tests.TestCutByHoles()._vessel_with_hole()
        vessel.hole_shape_catalogue.holes.clear()
        result = render_model(vessel)
        assert result.hole_failures == {"pan1/hole:hc1": "unresolvable HoleRef"}
        assert not any("/hole:" in k for k in result.skipped)

    def test_skipped_count_excludes_hole_failures(self):
        res = RenderResult()
        res.skipped["a"] = "no contour"
        res.hole_failures["b/hole:h"] = "unresolvable HoleRef"
        assert res.skipped_count == 1


runner = CliRunner()


def _invoke(tmp_path, monkeypatch, *args):
    import ocx_render.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
    dummy = tmp_path / "m.3docx"
    dummy.write_text("<x/>", encoding="utf-8")
    return runner.invoke(app, [str(dummy), *args])


class TestCliExitCodes:
    def test_destination_without_glb_suffix_is_written_as_glb(
            self, tmp_path, monkeypatch):
        out = tmp_path / "model_out"
        result = _invoke(tmp_path, monkeypatch, "--destination", str(out))
        assert result.exit_code == 0, result.output
        assert out.read_bytes()[:4] == b"glTF"

    def test_non_oserror_write_failure_exits_3(self, tmp_path, monkeypatch):
        import ocx_render.gltf_writer as gw
        monkeypatch.setattr(gw, "write_glb", lambda *a, **k: _boom())
        result = _invoke(tmp_path, monkeypatch)
        assert result.exit_code == 3

    def test_render_model_failure_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(render_mod, "render_model", _boom)
        result = _invoke(tmp_path, monkeypatch)
        assert result.exit_code == 1

    def test_summary_count_excludes_hole_failures(self, tmp_path, monkeypatch):
        res = RenderResult()
        res.meshes.append(PartMesh("p", "p", "plate", np.eye(3),
                                   np.array([[0, 1, 2]])))
        res.hole_failures["p/hole:h"] = "unresolvable HoleRef"
        monkeypatch.setattr(render_mod, "render_model", lambda *a, **k: res)
        result = _invoke(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        assert "1 parts, 0 skipped" in result.output
