"""build_compartments_block is public API (consumed by the external ocx-mcp server)."""
from ocx_model_validator.compartments import build_compartments_block

from tests.section_fixtures import make_synthetic_vessel


def test_build_compartments_block_rows_and_warnings():
    rows, warnings = build_compartments_block(make_synthetic_vessel())
    assert isinstance(warnings, list)
    by_name = {r["name"]: r for r in rows}
    assert {"Ballast Tank", "Unclassified Space"} <= set(by_name)
