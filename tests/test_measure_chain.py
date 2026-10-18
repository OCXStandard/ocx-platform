"""Tests for polyline chaining / gap measurement in ocx_geometry.measure."""
from __future__ import annotations

import numpy as np
from ocx_geometry.measure import chain_polylines, ordered_junction_gaps


def _seg(a, b):
    return np.array([a, b], dtype=float)


# Four sides of the unit square in scrambled order and orientation.
_SQ = [
    _seg([0, 0, 0], [1, 0, 0]),
    _seg([1, 1, 0], [1, 0, 0]),   # reversed
    _seg([0, 1, 0], [1, 1, 0]),
    _seg([0, 0, 0], [0, 1, 0]),   # reversed
]


class TestChainPolylines:
    def test_closed_square_has_zero_gaps(self):
        ring, gaps = chain_polylines(_SQ)
        assert ring is not None and len(ring) >= 4
        assert len(gaps) == 4          # 3 junctions + closure
        assert max(gaps) < 1e-12

    def test_open_square_reports_closure_gap(self):
        open_sq = [s.copy() for s in _SQ]
        open_sq[3][0] = [0.005, 0.0, 0.0]   # pull one corner 5 mm away
        ring, gaps = chain_polylines(open_sq)
        assert ring is not None
        assert abs(max(gaps) - 0.005) < 1e-9

    def test_single_closed_polyline(self):
        ring = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]],
                        dtype=float)
        chained, gaps = chain_polylines([ring])
        assert chained is not None
        assert max(gaps) < 1e-12

    def test_empty_input_returns_none(self):
        ring, gaps = chain_polylines([])
        assert ring is None and gaps == []


class TestOrderedJunctionGaps:
    def test_continuous_in_declared_order(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1, 0, 0], [1, 1, 0]),
                _seg([1, 1, 0], [0, 1, 0])]
        gaps = ordered_junction_gaps(segs)
        assert len(gaps) == 2 and max(gaps) < 1e-12

    def test_reversed_segment_still_continuous(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1, 1, 0], [1, 0, 0])]     # reversed second segment
        gaps = ordered_junction_gaps(segs)
        assert len(gaps) == 1 and gaps[0] < 1e-12

    def test_gap_reported(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1.002, 0, 0], [2, 0, 0])]
        gaps = ordered_junction_gaps(segs)
        assert abs(gaps[0] - 0.002) < 1e-9

    def test_fewer_than_two_segments(self):
        assert ordered_junction_gaps([_seg([0, 0, 0], [1, 0, 0])]) == []
