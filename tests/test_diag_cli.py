from ocx_diagnose.cli import app
from typer.testing import CliRunner


def test_help_lists_options():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    for opt in ("--panel", "--tolerance-sweep", "--report", "--json", "--max-plates"):
        assert opt in r.output
