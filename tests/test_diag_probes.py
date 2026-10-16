import numpy as np
from ocx_diagnose.probes import (
    contour_probe,
    degenerate_members,
    duplicate_members,
)
from ocx_geometry.diagnostics import ChartDiag
from ocx_geometry.surfaces import PlaneParam


def _grid_chart(offsets):
    """One 1x1 quad (2 faces) per member, member i lying in the plane z=offsets[i]."""
    V, F, tm = [], [], []
    for i, z in enumerate(offsets):
        b = len(V)
        V += [[0, 0, z], [1, 0, z], [1, 1, z], [0, 1, z]]
        F += [[b, b + 1, b + 2], [b, b + 2, b + 3]]
        tm += [i, i]
    return ChartDiag(n_members=len(offsets), members_used=list(range(len(offsets))),
                     V=np.array(V, float), F=np.array(F), tri_member=np.array(tm))


def _planes(offsets):
    return [PlaneParam(np.array([0.0, 0.0, z]), np.array([0.0, 0.0, 1.0])) for z in offsets]


def test_duplicate_members_found_for_coincident_planes():
    chart = _grid_chart([0.0, 0.0, 5.0])
    pairs = duplicate_members(chart, _planes([0.0, 0.0, 5.0]), eps_m=1e-3)
    assert [(a, b) for a, b, _ in pairs] == [(0, 1)]


def test_no_duplicates_for_separate_planes():
    chart = _grid_chart([0.0, 1.0, 5.0])
    assert duplicate_members(chart, _planes([0.0, 1.0, 5.0]), eps_m=1e-3) == []


def test_degenerate_members_by_area_and_missing_faces():
    chart = _grid_chart([0.0, 1.0])
    chart.V[4:8] = chart.V[4:8] * 0.001          # member 1 collapses to 1 mm
    chart.n_members = 3                          # member 2 has no faces at all
    assert degenerate_members(chart, min_area_m2=1e-4) == [1, 2]


def test_contour_probe_touching():
    t = np.linspace(0, 2 * np.pi, 41)[:-1]
    ring = np.c_[np.cos(t), np.sin(t), np.zeros_like(t)]
    assert contour_probe(ring).touching == 0
    pinched = np.vstack([ring, ring[10:11]])     # revisits a point of the ring
    assert contour_probe(pinched).touching >= 1
