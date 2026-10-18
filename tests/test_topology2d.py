"""Tests for shapely-based 2-D topology helpers."""
from __future__ import annotations

import numpy as np
from ocx_geometry.topology2d import (
    point_polyline_distance,
    polygon_ok,
    region_count,
)

_SQ = np.array([[0, 0], [4, 0], [4, 4], [0, 4]], dtype=float)


class TestPolygonOk:
    def test_valid_square(self):
        assert polygon_ok(_SQ) is None

    def test_self_intersecting_bowtie(self):
        bowtie = np.array([[0, 0], [2, 2], [2, 0], [0, 2]], dtype=float)
        assert polygon_ok(bowtie) is not None

    def test_degenerate(self):
        assert polygon_ok(np.array([[0, 0], [1, 1]], dtype=float)) is not None


class TestRegionCount:
    def test_no_cuts_is_one_region(self):
        assert region_count(_SQ, []) == 1

    def test_full_cut_splits_in_two(self):
        cut = np.array([[2, -1], [2, 5]], dtype=float)
        assert region_count(_SQ, [cut]) == 2

    def test_partial_cut_does_not_split(self):
        cut = np.array([[2, 1], [2, 3]], dtype=float)
        assert region_count(_SQ, [cut]) == 1

    def test_two_crossing_cuts_make_four(self):
        cuts = [np.array([[2, -1], [2, 5]], dtype=float),
                np.array([[-1, 2], [5, 2]], dtype=float)]
        assert region_count(_SQ, cuts) == 4

    def test_invalid_outer_returns_one(self):
        bowtie = np.array([[0, 0], [2, 2], [2, 0], [0, 2]], dtype=float)
        assert region_count(bowtie, []) == 1


class TestPointPolylineDistance:
    def test_on_segment(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        assert point_polyline_distance(np.array([5.0, 0, 0]), pl) < 1e-12

    def test_off_segment(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        d = point_polyline_distance(np.array([5.0, 3.0, 0]), pl)
        assert abs(d - 3.0) < 1e-12

    def test_beyond_endpoint(self):
        pl = np.array([[0, 0, 0], [10, 0, 0]], dtype=float)
        d = point_polyline_distance(np.array([13.0, 4.0, 0]), pl)
        assert abs(d - 5.0) < 1e-12
