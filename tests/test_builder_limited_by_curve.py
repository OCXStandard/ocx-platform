"""FreeEdgeCurve3D boundary geometry must survive into IrLimitedByRef.curve."""
from __future__ import annotations

from pathlib import Path

import pytest
from ocx_model_core.model.ir.geometry import IrCurve3D

from tests.conftest import _build_session


@pytest.fixture()
def composedof_vessel(stub_dir_310: Path):
    _, ir = _build_session(str(stub_dir_310 / "ocxxml.3docx"))
    return ir


class TestFreeEdgeCurveGeometry:
    def test_free_edge_refs_carry_curves(self, composedof_vessel):
        panels = list(composedof_vessel.panels.values())
        assert panels, "stub model must contain at least one panel"
        fec_refs = [r for p in panels for r in p.limited_by
                    if r.ref_type == "FreeEdgeCurve3D"]
        assert fec_refs, "stub model must contain FreeEdgeCurve3D boundaries"
        for ref in fec_refs:
            assert isinstance(ref.curve, IrCurve3D), (
                f"FreeEdgeCurve3D ref {ref.guidref!r} lost its geometry")

    def test_named_refs_have_no_curve(self, composedof_vessel):
        other = [r for p in composedof_vessel.panels.values()
                 for r in p.limited_by if r.ref_type != "FreeEdgeCurve3D"]
        assert all(r.curve is None for r in other)
