"""Tests for ocx_rules.geometry_context.GeometryContext."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from ocx_rules.context import ValidationContext
from ocx_rules.geometry_context import GeometryContext

from tests.conftest import _build_session


@pytest.fixture()
def gctx(stub_dir_310: Path) -> GeometryContext:
    _, vessel = _build_session(str(stub_dir_310 / "ocxxml.3docx"))
    return GeometryContext(vessel)


class TestGeometryContext:
    def test_length_resolver_converts_mm(self, gctx):
        assert abs(gctx.length.to_m(1000.0, "Umm") - 1.0) < 1e-12

    def test_to_si_handles_none(self, gctx):
        assert gctx.to_si(None) is None

    def test_sample_returns_points_or_none(self, gctx):
        for panel in gctx.vessel.panels.values():
            curves, _ = gctx.boundary_curves(panel)
            for c in curves:
                pts = gctx.sample(c, tol_m=0.005)
                assert pts is None or (
                    isinstance(pts, np.ndarray) and pts.shape[1] == 3)

    def test_sample_none_curve_returns_none(self, gctx):
        assert gctx.sample(None) is None

    def test_surface_param_none_returns_none(self, gctx):
        assert gctx.surface_param(None) is None

    def test_boundary_curves_counts_unresolvable(self, gctx):
        panel = next(iter(gctx.vessel.panels.values()))
        curves, unresolved = gctx.boundary_curves(panel)
        assert len(curves) + unresolved == len(panel.limited_by)


class TestValidationContextWiring:
    def test_geometry_is_cached_property(self, stub_dir_310: Path):
        ctx = ValidationContext(model_path=stub_dir_310 / "ocxxml.3docx")
        g1 = ctx.geometry
        assert isinstance(g1, GeometryContext)
        assert ctx.geometry is g1
