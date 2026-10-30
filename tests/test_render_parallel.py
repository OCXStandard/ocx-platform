"""Parallel plate tessellation: same result as serial, robust fallbacks."""
from concurrent.futures import Future
from pathlib import Path

import ocx_render.render as render_mod
import pytest
from loguru import logger
from ocx_geometry.backend import TessellationOptions
from ocx_geometry.diagnostics import DiagSink
from ocx_model_core.model.ir.base import IrVector3D, ParentKind, ParentRef
from ocx_model_core.model.ir.geometry import IrPlane3D, IrPolyLine3D, IrUnboundedGeometry
from ocx_model_core.model.ir.structural import IrPanel, IrPlate
from ocx_render.render import render_model

from tests.test_render_model import TestCutByHoles, pt


def _multi_panel_vessel():
    """pan1 (pl1, broken panel hole) + pan2 (pl2, pl3) + an unparented plate."""
    vessel = TestCutByHoles()._vessel_with_hole(with_transformation=False)
    vessel.panels["pan2"] = IrPanel(
        id="pan2", name="Bulkhead", plate_ids=["pl2", "pl3"],
        unbounded_geometry=IrUnboundedGeometry(surface=IrPlane3D(
            id="s2", point_on_surface=pt(0, 0, 0), normal=IrVector3D(1, 0, 0))))
    for pid, y0 in (("pl2", 0), ("pl3", 2)):
        vessel.plates[pid] = IrPlate(
            id=pid, parent_ref=ParentRef(ParentKind.PANEL, "pan2"), name=pid,
            outer_contour=IrPolyLine3D(None, vertices=[
                pt(0, y0, 0), pt(0, y0 + 2, 0), pt(0, y0 + 2, 3),
                pt(0, y0, 3), pt(0, y0, 0)]))
    vessel.plates["orphan"] = IrPlate(
        id="orphan", parent_ref=ParentRef(ParentKind.VESSEL, "v"), name="orphan")
    return vessel


def _signature(result):
    return ([(m.part_id, m.kind, m.vertices.tobytes(), m.triangles.tobytes(),
              None if m.normals is None else m.normals.tobytes(), m.color,
              m.extras) for m in result.meshes],
            dict(result.skipped), dict(result.hole_failures))


class TestParallelMatchesSerial:
    def test_two_workers_give_identical_result(self):
        serial = render_model(_multi_panel_vessel(), TessellationOptions(workers=1))
        parallel = render_model(_multi_panel_vessel(), TessellationOptions(workers=2))
        assert [m.part_id for m in serial.meshes][:3] == ["pl1", "pl2", "pl3"]
        assert _signature(parallel) == _signature(serial)

    def test_worker_warnings_are_logged_in_parent(self):
        messages = []
        sink = logger.add(lambda m: messages.append(m.record["message"]),
                          level="WARNING")
        try:
            render_model(_multi_panel_vessel(), TessellationOptions(workers=2))
        finally:
            logger.remove(sink)
        assert any("pan1/hole:hc1" in m for m in messages)


class _FailingPool:
    """Stands in for ProcessPoolExecutor: every task fails."""
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        fut = Future()
        fut.set_exception(RuntimeError("worker died"))
        return fut


class TestFallbacks:
    def test_failed_worker_panels_are_rendered_serially(self, monkeypatch):
        expected = _signature(render_model(_multi_panel_vessel()))
        monkeypatch.setattr(render_mod, "ProcessPoolExecutor", _FailingPool)
        result = render_model(_multi_panel_vessel(), TessellationOptions(workers=4))
        assert _signature(result) == expected

    def test_diagnostics_force_serial(self, monkeypatch):
        def no_pool(*args, **kwargs):
            raise AssertionError("pool must not be used with diag")

        monkeypatch.setattr(render_mod, "ProcessPoolExecutor", no_pool)
        sink = DiagSink()
        result = render_model(_multi_panel_vessel(),
                              TessellationOptions(workers=4, diag=sink))
        assert {"pl1", "pl2", "pl3"} <= set(sink.plates)
        assert len([m for m in result.meshes if m.kind == "plate"]) == 3

    def test_single_panel_does_not_start_a_pool(self, monkeypatch):
        from tests.test_render_model import make_vessel

        def no_pool(*args, **kwargs):
            raise AssertionError("pool not needed for one panel")

        monkeypatch.setattr(render_mod, "ProcessPoolExecutor", no_pool)
        result = render_model(make_vessel(), TessellationOptions(workers=4))
        assert any(m.kind == "plate" for m in result.meshes)


class TestCliWorkers:
    def _run(self, tmp_path, monkeypatch, *args):
        import ocx_render.cli as cli_mod
        from ocx_render.cli import app
        from typer.testing import CliRunner

        seen = {}
        real = render_mod.render_model

        def spy(vessel, options):
            seen["workers"] = options.workers
            return real(vessel, TessellationOptions(tolerance_m=options.tolerance_m))

        monkeypatch.setattr(cli_mod, "_load_vessel", lambda m: _multi_panel_vessel())
        monkeypatch.setattr(render_mod, "render_model", spy)
        dummy = tmp_path / "m.3docx"
        dummy.write_text("<x/>", encoding="utf-8")
        result = CliRunner().invoke(
            app, [str(dummy), "-d", str(tmp_path / "o.glb"), "--no-html", *args])
        return result, seen

    def test_default_uses_all_cores(self, tmp_path, monkeypatch):
        import os
        result, seen = self._run(tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        assert seen["workers"] == (os.cpu_count() or 1)

    def test_explicit_workers(self, tmp_path, monkeypatch):
        result, seen = self._run(tmp_path, monkeypatch, "--workers", "1")
        assert result.exit_code == 0, result.output
        assert seen["workers"] == 1

    def test_negative_workers_rejected(self, tmp_path, monkeypatch):
        result, _ = self._run(tmp_path, monkeypatch, "--workers", "-1")
        assert result.exit_code == 2


class _BrokenPool(_FailingPool):
    """Pool that breaks while starting workers (e.g. unguarded __main__)."""
    def submit(self, fn, *args):
        raise BrokenPipeError("worker bootstrap failed")


def test_pool_that_breaks_on_submit_falls_back_to_serial(monkeypatch):
    expected = _signature(render_model(_multi_panel_vessel()))
    monkeypatch.setattr(render_mod, "ProcessPoolExecutor", _BrokenPool)
    result = render_model(_multi_panel_vessel(), TessellationOptions(workers=4))
    assert _signature(result) == expected


_HULL = (Path(__file__).parent.parent / "models" / "TR05"
         / "tr05_tc09_nast_hull.3docx")


@pytest.mark.skipif(not _HULL.exists(), reason="tr05 hull test model not present")
def test_chunked_charted_panel_matches_serial():
    """One charted panel of 25 plates is split into chunks across workers."""
    from ocx_render.cli import _load_vessel

    vessel = _load_vessel(_HULL)
    serial = render_model(vessel, TessellationOptions(workers=1))
    parallel = render_model(vessel, TessellationOptions(workers=3))
    assert len(serial.meshes) >= 25 and not serial.skipped
    assert _signature(parallel) == _signature(serial)
