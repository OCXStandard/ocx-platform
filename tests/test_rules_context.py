"""Tests for ValidationContext laziness and caching."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_rules.context import ValidationContext


@pytest.fixture()
def vessel_stub(stub_dir_310: Path) -> Path:
    return stub_dir_310 / "ocxxml.3docx"


class TestValidationContext:
    def test_xml_tree_parses(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        root = ctx.xml_tree.getroot()
        assert root is not None

    def test_xml_tree_cached(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        assert ctx.xml_tree is ctx.xml_tree

    def test_vessel_not_built_for_xml_access(self, vessel_stub: Path, monkeypatch):
        """Accessing xml_tree must never trigger IR parsing/building."""
        import ocx_rules.context as context_mod

        def boom(*a, **k):  # pragma: no cover - should never run
            raise AssertionError("IR build triggered by xml access")

        monkeypatch.setattr(context_mod, "_build_vessel", boom)
        ctx = ValidationContext(vessel_stub)
        _ = ctx.xml_tree  # must not raise

    def test_vessel_builds_ir(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        vessel = ctx.vessel
        assert vessel is ctx.vessel  # cached

    def test_missing_file_raises_on_access_not_init(self, tmp_path: Path):
        ctx = ValidationContext(tmp_path / "nope.3docx")  # no raise here
        with pytest.raises(Exception):
            _ = ctx.xml_tree
