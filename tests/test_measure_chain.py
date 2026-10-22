"""Tests for polyline chaining / gap measurement in ocx_geometry.measure."""
from __future__ import annotations

import numpy as np
from ocx_geometry.measure import (
    chain_gap_details,
    chain_polylines,
    chained_junction_gaps,
)


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


class TestChainGapDetails:
    def test_square_with_one_gap(self):
        # Three sides of a unit square + a short fourth side leaving a gap.
        a = np.array([[0, 0, 0], [1, 0, 0]], float)
        b = np.array([[1, 0, 0], [1, 1, 0]], float)
        c = np.array([[1, 1, 0], [0, 1, 0]], float)
        d = np.array([[0, 1, 0], [0, 0.4, 0]], float)  # stops 0.4 short
        details = chain_gap_details([a, b, c, d])
        # 3 junctions + 1 closure entry
        assert len(details) == 4
        gaps = [g for _, _, g in details]
        assert max(gaps[:3]) < 1e-12          # junctions touch exactly
        assert abs(gaps[3] - 0.4) < 1e-12     # closure gap
        pa, pb, _ = details[3]
        np.testing.assert_allclose(pa, [0, 0.4, 0])
        np.testing.assert_allclose(pb, [0, 0, 0])
        # Gap distances must match chain_polylines for the same input.
        _, ref_gaps = chain_polylines([a, b, c, d])
        np.testing.assert_allclose(gaps, ref_gaps)

    def test_empty_and_single(self):
        assert chain_gap_details([]) == []
        one = np.array([[0, 0, 0], [1, 0, 0]], float)
        details = chain_gap_details([one])
        assert len(details) == 1              # closure gap only
        assert abs(details[0][2] - 1.0) < 1e-12


class TestChainedJunctionGaps:
    def test_out_of_order_scrambled_square_has_zero_gaps(self):
        gaps = chained_junction_gaps(_SQ)
        assert len(gaps) == 3           # junctions only, no closure gap
        assert max(gaps) < 1e-12

    def test_open_polyline_out_of_order(self):
        # L-shape declared middle-last: chainable only via both-end growth.
        segs = [_seg([1, 0, 0], [1, 1, 0]),
                _seg([1, 1, 0], [0, 1, 0]),
                _seg([0, 0, 0], [1, 0, 0])]
        gaps = chained_junction_gaps(segs)
        assert len(gaps) == 2 and max(gaps) < 1e-12

    def test_genuine_gap_reported(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([1.057, 0, 0], [2, 0, 0])]
        gaps = chained_junction_gaps(segs)
        assert abs(gaps[0] - 0.057) < 1e-9

    def test_reversed_segment_chains(self):
        segs = [_seg([0, 0, 0], [1, 0, 0]),
                _seg([2, 0, 0], [1, 0, 0])]    # reversed
        gaps = chained_junction_gaps(segs)
        assert len(gaps) == 1 and gaps[0] < 1e-12

    def test_fewer_than_two_segments(self):
        assert chained_junction_gaps([]) == []
        assert chained_junction_gaps([_seg([0, 0, 0], [1, 0, 0])]) == []
        assert chained_junction_gaps([None]) == []
