import pytest
from ocx_diagnose.cli import app
from typer.testing import CliRunner


def test_help_lists_options():
    r = CliRunner().invoke(app, ["diagnose", "--help"])
    assert r.exit_code == 0
    for opt in ("--panel", "--tolerance-sweep", "--report", "--json", "--max-plates"):
        assert opt in r.output


def test_bad_sweep_value_is_rejected():
    r = CliRunner().invoke(app, ["diagnose", "x.3docx", "--tolerance-sweep", "10,abc"])
    assert r.exit_code != 0


@pytest.mark.integration
def test_tr04_smoke(tmp_path):
    out = tmp_path / "r.html"
    r = CliRunner().invoke(app, [
        "diagnose",
        "models/tr04/tr04_tc14A_outer_shell.3docx", "--report", str(out),
        "--json", str(tmp_path / "r.json"), "--max-plates", "3"])
    assert r.exit_code == 0, r.output
    assert out.stat().st_size > 100_000
