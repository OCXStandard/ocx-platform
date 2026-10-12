"""CLI tests for the `ocx-render` single-command app."""
from ocx_render.cli import app
from typer.testing import CliRunner

runner = CliRunner()


class TestRenderCommand:
    def test_unparseable_file_exits_2(self, tmp_path):
        bad = tmp_path / "bad.3docx"
        bad.write_text("this is not xml", encoding="utf-8")
        result = runner.invoke(app, [str(bad)])
        assert result.exit_code == 2

    def test_model_without_renderable_geometry_exits_1(self, tmp_path, monkeypatch):
        import ocx_render.cli as cli_mod
        from ocx_model_core.model.ir import IrVessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: IrVessel(id="V1"))
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        result = runner.invoke(app, [str(dummy)])
        assert result.exit_code == 1

    def test_synthetic_model_renders(self, tmp_path, monkeypatch):
        """Patch the load step to return a renderable vessel and check outputs."""
        import ocx_render.cli as cli_mod

        from tests.test_render_model import make_vessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        glb = tmp_path / "out.glb"
        result = runner.invoke(
            app, [str(dummy), "--destination", str(glb)])
        assert result.exit_code == 0, result.output
        assert glb.exists()
        assert glb.with_suffix(".html").exists()

    def test_no_html_flag(self, tmp_path, monkeypatch):
        import ocx_render.cli as cli_mod

        from tests.test_render_model import make_vessel

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        glb = tmp_path / "out.glb"
        result = runner.invoke(
            app, [str(dummy), "--destination", str(glb), "--no-html"])
        assert result.exit_code == 0, result.output
        assert glb.exists()
        assert not glb.with_suffix(".html").exists()
