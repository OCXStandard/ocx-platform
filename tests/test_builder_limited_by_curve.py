"""FreeEdgeCurve3D boundary geometry must survive into IrLimitedByRef.curve."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from ocx_model_core.builders.v3_builder import OcxV3Builder
from ocx_model_core.model.ir import IrVessel
from ocx_model_core.model.ir.geometry import IrCompositeCurve3D, IrCurve3D, IrLine3D

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


class TestMultiSegmentFreeEdgeCurve:
    def test_two_line_segments_build_composite_curve(self):
        """A FreeEdgeCurve3D with several curve children must keep every
        segment, wrapped in an IrCompositeCurve3D — not just the first one."""
        def _pt(x, y, z):
            return NS(coordinates=[x, y, z], unit="Um")

        class Line3D(NS):
            pass

        fec = NS(
            guidref="fec-guid-1",
            name="FEC1",
            line3_d=[
                Line3D(start_point=_pt(0.0, 0.0, 0.0), end_point=_pt(1.0, 0.0, 0.0),
                       curve_length=None, id="L1"),
                Line3D(start_point=_pt(1.0, 0.0, 0.0), end_point=_pt(1.0, 1.0, 0.0),
                       curve_length=None, id="L2"),
            ],
        )
        raw_panel = NS(id="P1", limited_by=NS(free_edge_curve3_d=[fec]))
        ir = IrVessel(id="V1")

        panel = OcxV3Builder()._build_panel(raw_panel, ir, "V1")

        assert panel is not None
        fec_refs = [r for r in panel.limited_by if r.ref_type == "FreeEdgeCurve3D"]
        assert len(fec_refs) == 1
        curve = fec_refs[0].curve
        assert isinstance(curve, IrCompositeCurve3D)
        assert len(curve.segments) == 2
        assert all(isinstance(s, IrLine3D) for s in curve.segments)
