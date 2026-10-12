"""Tests for render/mesh.py, render/backend.py and render/length.py."""
import numpy as np
import pytest
from ocx_geometry.backend import RenderResult, TessellationOptions
from ocx_geometry.measure import LengthResolver
from ocx_geometry.mesh import PartMesh, part_color
from ocx_model_core.model.ir.base import IrUnit, Quantity
from ocx_model_core.model.ir.geometry import IrPoint3D

MM = IrUnit(id="Umm", name="millimeter", symbol="mm",
            dimension_url="D_L", to_si_factor=1e-3, si_symbol="m")
M = IrUnit(id="Um", name="meter", symbol="m",
           dimension_url="D_L", to_si_factor=1.0, si_symbol="m")


class TestLengthResolver:
    def test_to_m_uses_registry_factor(self):
        lr = LengthResolver({"Umm": MM, "Um": M})
        assert lr.to_m(2500.0, "Umm") == pytest.approx(2.5)
        assert lr.to_m(2.5, "Um") == pytest.approx(2.5)

    def test_unknown_unit_falls_back_to_builtin_table(self):
        lr = LengthResolver({})
        assert lr.to_m(1000.0, "Umm") == pytest.approx(1.0)

    def test_completely_unknown_unit_assumes_metres(self):
        lr = LengthResolver({})
        assert lr.to_m(3.0, "Ufurlong") == pytest.approx(3.0)

    def test_point_returns_metre_ndarray(self):
        lr = LengthResolver({"Umm": MM})
        p = lr.point(IrPoint3D(1000.0, 2000.0, 3000.0, "Umm"))
        assert isinstance(p, np.ndarray)
        np.testing.assert_allclose(p, [1.0, 2.0, 3.0])

    def test_qty(self):
        lr = LengthResolver({"Umm": MM})
        assert lr.qty(Quantity(250.0, "Umm")) == pytest.approx(0.25)
        assert lr.qty(None) is None


class TestOptions:
    def test_defaults(self):
        opt = TessellationOptions()
        assert opt.tolerance_m == pytest.approx(0.05)
        assert opt.snap_tolerance_m == pytest.approx(0.01)


class TestPartMesh:
    def test_construction_and_counts(self):
        pm = PartMesh(
            part_id="pl1", name="Plate 1", kind="plate",
            vertices=np.zeros((3, 3)), triangles=np.array([[0, 1, 2]]),
        )
        assert pm.vertices.shape == (3, 3)
        assert pm.triangles.shape == (1, 3)
        assert pm.extras == {}

    def test_part_color_deterministic_and_kind_based(self):
        c1 = part_color("plate", "pl1")
        c2 = part_color("plate", "pl1")
        c3 = part_color("plate", "pl2")
        assert c1 == c2
        assert c1 != c3           # hue jitter differs per id
        assert all(0 <= v <= 255 for v in c1)
        # stiffeners are blueish: blue channel dominates red
        s = part_color("stiffener", "s1")
        assert s[2] > s[0]


class TestRenderResult:
    def test_counts(self):
        res = RenderResult()
        res.meshes.append(PartMesh("a", "a", "plate",
                                   np.zeros((3, 3)), np.array([[0, 1, 2]])))
        res.skipped["b"] = "no contour"
        assert res.rendered_count == 1
        assert res.skipped_count == 1
