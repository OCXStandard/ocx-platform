"""Integration: render the TR04 cutout reference model (needs models/TR04)."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

MODEL = Path(__file__).resolve().parents[1] / "models" / "TR04" / "tr04_tc13_nast.3docx"
MODEL_AI3DX = MODEL.with_name("tr04_tc13_ai3dx.3docx")
MODEL_SHELL = MODEL.with_name("tr04_tc14a_outer_shell.3docx")

pytestmark = pytest.mark.integration


def _plate_area(meshes) -> float:
    total = 0.0
    for m in meshes:
        if m.kind != "plate":
            continue
        v, t = m.vertices, m.triangles
        a = v[t[:, 1]] - v[t[:, 0]]
        b = v[t[:, 2]] - v[t[:, 0]]
        total += 0.5 * float(np.linalg.norm(np.cross(a, b), axis=1).sum())
    return total


@pytest.mark.skipif(not MODEL.exists(), reason="reference model not present")
def test_tr04_tc13_renders_with_cutouts():
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser
    from ocx_render.render import TessellationOptions, render_model

    root = OcxParser().parse(str(MODEL))
    vessel = get_builder(root.schema_version).build(root)

    # Builder captured the catalogue and all 9 panel-level hole placements.
    assert vessel.hole_shape_catalogue is not None
    assert len(vessel.hole_shape_catalogue.holes) == 7
    panel = next(iter(vessel.panels.values()))
    assert len(panel.cut_by_holes) == 9

    result = render_model(vessel, TessellationOptions())
    assert any(m.kind == "plate" for m in result.meshes)
    hole_failures = {k: v for k, v in result.skipped.items() if "/hole:" in k}
    assert hole_failures == {}
    area_holed = _plate_area(result.meshes)

    # Rendering with the holes stripped must give a measurably larger area.
    for key, p in list(vessel.panels.items()):
        vessel.panels[key] = dataclasses.replace(
            p, cut_by_holes=[], cut_by_contours=[]
        )
    for key, pl in list(vessel.plates.items()):
        vessel.plates[key] = dataclasses.replace(
            pl, cut_by_holes=[], cut_by_contours=[]
        )
    area_full = _plate_area(render_model(vessel, TessellationOptions()).meshes)
    assert area_holed < area_full * 0.995


@pytest.mark.skipif(not MODEL_SHELL.exists(), reason="reference model not present")
def test_tr04_tc14a_outer_shell_renders_all_plates():
    """Outer-shell plates spanning a 2-D NURBS patch grid must all render,
    and each plate's mesh boundary must track its sampled outer contour.

    Regression for distorted/missing shell plates: composite charts over
    patch-grid surface collections mis-routed points to patches from the
    wrong spine band and lost contour points whose own patch had too few
    contour samples to fit an affine chart.
    """
    from ocx_geometry.curves import sample_contour
    from ocx_geometry.measure import LengthResolver
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser
    from ocx_render.render import TessellationOptions, render_model

    root = OcxParser().parse(str(MODEL_SHELL))
    vessel = get_builder(root.schema_version).build(root)
    assert len(vessel.plates) == 24

    options = TessellationOptions()
    result = render_model(vessel, options)
    assert result.skipped == {}, result.skipped
    plate_meshes = {m.part_id: m for m in result.meshes if m.kind == "plate"}
    assert len(plate_meshes) == 24

    length = LengthResolver(vessel.unit_registry)
    for plate in vessel.plates.values():
        contour = sample_contour(plate.outer_contour, length,
                                 options.tolerance_m, options.snap_tolerance_m)
        verts = plate_meshes[plate.id].vertices
        # every sampled contour point must be close to some mesh vertex
        d = np.linalg.norm(contour[:, None, :] - verts[None, :, :], axis=2)
        worst = float(d.min(axis=1).max())
        assert worst < 0.1, (f"{plate.name}: contour point {worst:.3f} m "
                             "away from the rendered mesh")


@pytest.mark.skipif(not MODEL_AI3DX.exists(), reason="reference model not present")
def test_tr04_tc13_ai3dx_contour_holes_are_cut():
    """ai3dx authors holes as multi-segment 3D contours (XZ plane)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser
    from ocx_render.render import TessellationOptions, render_model

    root = OcxParser().parse(str(MODEL_AI3DX))
    vessel = get_builder(root.schema_version).build(root)

    assert vessel.hole_shape_catalogue is not None
    assert len(vessel.hole_shape_catalogue.holes) == 9
    panel = next(iter(vessel.panels.values()))
    assert len(panel.cut_by_holes) == 9

    result = render_model(vessel, TessellationOptions())
    assert any(m.kind == "plate" for m in result.meshes)
    hole_failures = {k: v for k, v in result.skipped.items() if "/hole:" in k}
    assert hole_failures == {}
    area_holed = _plate_area(result.meshes)

    for key, p in list(vessel.panels.items()):
        vessel.panels[key] = dataclasses.replace(
            p, cut_by_holes=[], cut_by_contours=[]
        )
    for key, pl in list(vessel.plates.items()):
        vessel.plates[key] = dataclasses.replace(
            pl, cut_by_holes=[], cut_by_contours=[]
        )
    area_full = _plate_area(render_model(vessel, TessellationOptions()).meshes)
    assert area_holed < area_full * 0.995
