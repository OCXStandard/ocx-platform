"""Integration: render the TR04 cutout reference model (needs models/TR04)."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

MODEL = Path(__file__).resolve().parents[1] / "models" / "TR04" / "tr04_tc13_nast.3docx"

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
