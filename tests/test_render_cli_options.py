"""ocx-render CLI: --tolerance validation, --panel filter, package version."""
from importlib.metadata import version

import ocx_render.cli as cli_mod
import ocx_render.render as render_mod
from ocx_render.cli import app
from typer.testing import CliRunner

from tests.test_render_parallel import _multi_panel_vessel


def _run(tmp_path, monkeypatch, *args):
    seen = {}
    real = render_mod.render_model

    def spy(vessel, options):
        seen["options"] = options
        return real(vessel, options)

    monkeypatch.setattr(cli_mod, "_load_vessel", lambda m: _multi_panel_vessel())
    monkeypatch.setattr(render_mod, "render_model", spy)
    dummy = tmp_path / "m.3docx"
    dummy.write_text("<x/>", encoding="utf-8")
    glb = tmp_path / "o.glb"
    result = CliRunner().invoke(
        app, [str(dummy), "-d", str(glb), "--no-html", "-j", "1", *args])
    return result, seen.get("options"), glb


class TestTolerance:
    def test_zero_tolerance_rejected(self, tmp_path, monkeypatch):
        result, options, glb = _run(tmp_path, monkeypatch, "--tolerance", "0")
        assert result.exit_code == 2 and options is None and not glb.exists()

    def test_negative_tolerance_rejected(self, tmp_path, monkeypatch):
        result, _, _ = _run(tmp_path, monkeypatch, "--tolerance", "-5")
        assert result.exit_code == 2

    def test_positive_tolerance_converted_to_metres(self, tmp_path, monkeypatch):
        result, options, _ = _run(tmp_path, monkeypatch, "--tolerance", "20")
        assert result.exit_code == 0, result.output
        assert options.tolerance_m == 0.02


class TestPanelFilter:
    def test_default_renders_all_panels(self, tmp_path, monkeypatch):
        result, options, _ = _run(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        assert options.only_panels is None

    def test_repeated_panel_option_restricts_render(self, tmp_path, monkeypatch):
        result, options, _ = _run(tmp_path, monkeypatch,
                                  "--panel", "pan2", "-p", "pan1")
        assert result.exit_code == 0, result.output
        assert options.only_panels == frozenset({"pan1", "pan2"})
        assert "4 parts" in result.output   # pl1 + st1 on pan1, pl2 + pl3 on pan2

    def test_unknown_panel_ids_are_reported(self, tmp_path, monkeypatch):
        result, _, _ = _run(tmp_path, monkeypatch, "--panel", "pan2",
                            "--panel", "nope")
        assert result.exit_code == 0, result.output
        assert "nope" in result.output

    def test_only_unknown_panels_renders_nothing(self, tmp_path, monkeypatch):
        result, _, glb = _run(tmp_path, monkeypatch, "--panel", "nope")
        assert result.exit_code == 1 and not glb.exists()


def test_version_comes_from_package_metadata():
    import ocx_render
    assert ocx_render.__version__ == version("ocx-render")
