"""Canonicalisation tests: quantizer, geometry, records, invariance (ocx-hash/1)."""

from __future__ import annotations

import decimal
from decimal import Decimal

from ocx_integrity.canon_geom import _reverse_seg, curve_record
from ocx_integrity.jsonutil import prune, sort_jcs, type_name
from ocx_integrity.quantize import Quantizer, fmt_decimal
from ocx_model_core.model.ir import (
    IrCompositeCurve3D,
    IrCurve3D,
    IrLine3D,
    IrPoint3D,
    IrPolyLine3D,
    IrVector3D,
    Quantity,
)

from tests.integrity_fixtures import registry, square


def _quantizer() -> tuple[Quantizer, list[str]]:
    warnings: list[str] = []
    return Quantizer(registry(), warnings.append), warnings


def test_fmt_decimal_rounds_half_even():
    assert fmt_decimal(Decimal("0.0000005"), 6) == "0.000000"
    assert fmt_decimal(Decimal("0.0000015"), 6) == "0.000002"


def test_fmt_decimal_normalises_negative_zero():
    assert fmt_decimal(-0.0000001, 6) == "0.000000"
    assert fmt_decimal(-0.0, 0) == "0"


def test_fmt_decimal_non_finite():
    assert fmt_decimal(float("nan"), 6) == "NaN"
    assert fmt_decimal(float("inf"), 6) == "Infinity"
    assert fmt_decimal(float("-inf"), 6) == "-Infinity"


def test_fmt_decimal_large_finite_values():
    assert fmt_decimal(1e22, 6) == "10000000000000000000000.000000"
    assert fmt_decimal(1e19, 9) == "10000000000000000000.000000000"
    assert fmt_decimal(1e300, 6) == "1" + "0" * 300 + ".000000"


def test_quantize_independent_of_global_decimal_context():
    q, _ = _quantizer()
    expected = (fmt_decimal(Decimal("123.4567885"), 6), q.quantity(Quantity(1234.5, "Ucm4")))
    with decimal.localcontext() as ctx:
        ctx.prec = 5
        ctx.rounding = decimal.ROUND_DOWN
        actual = (fmt_decimal(Decimal("123.4567885"), 6), q.quantity(Quantity(1234.5, "Ucm4")))
    assert actual == expected == ("123.456788", "0.000012345")


def test_quantity_mm_and_m_are_identical():
    q, _ = _quantizer()
    assert q.quantity(Quantity(12.5, "Umm")) == q.quantity(Quantity(0.0125, "Um")) == "0.012500"


def test_quantity_precision_per_si_symbol():
    q, _ = _quantizer()
    assert q.quantity(Quantity(355.0, "UNOvermm2")) == "355000000"
    assert q.quantity(Quantity(1.8, "Ut")) == "1800.000"
    assert q.quantity(Quantity(1234.5, "Ucm4")) == "0.000012345"
    assert q.quantity(Quantity(0.3, "UDimless")) == "0.300000"


def test_unknown_unit_kept_raw_with_warning():
    q, warnings = _quantizer()
    assert q.quantity(Quantity(1.5, "Ufoo")) == {"value": "1.500000", "unit": "Ufoo"}
    assert q.point(IrPoint3D(1.0, 2.0, 3.0, "Ufoo")) == ["1.000000", "2.000000", "3.000000", "Ufoo"]
    assert warnings == ["unknown unit 'Ufoo'", "unknown unit 'Ufoo'"]


def test_point_and_vector():
    q, _ = _quantizer()
    assert q.point(IrPoint3D(1000.0, 0.0, -0.0000001, "Umm")) == [
        "1.000000",
        "0.000000",
        "0.000000",
    ]
    assert q.vector(IrVector3D(0.0, 0.0, 1.0)) == ["0.000000", "0.000000", "1.000000"]


def _geom_canon():
    q, _ = _quantizer()

    def canon(v):
        if isinstance(v, IrPoint3D):
            return q.point(v)
        if isinstance(v, IrVector3D):
            return q.vector(v)
        if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
            return v
        if isinstance(v, float):
            return q.scalar(v)
        if isinstance(v, Quantity):
            return q.quantity(v)
        if isinstance(v, IrCurve3D):
            return curve_record(v, canon)
        if isinstance(v, list):
            return [canon(x) for x in v]
        raise TypeError(type(v))

    return canon


def _square_composite(reverse: bool = False, start: int = 0) -> IrCompositeCurve3D:
    c = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
    if reverse:
        c = c[::-1]
    c = c[start:] + c[:start]
    segs = [
        IrLine3D(
            curve_length=None,
            start=IrPoint3D(*c[i], 0.0, "Umm"),
            end=IrPoint3D(*c[(i + 1) % 4], 0.0, "Umm"),
        )
        for i in range(4)
    ]
    return IrCompositeCurve3D(curve_length=None, segments=segs)


def test_prune_drops_empty_values_recursively():
    assert prune(
        {
            "a": None,
            "b": "",
            "c": [],
            "d": {},
            "e": False,
            "f": {"g": None},
            "h": 0,
            "i": True,
            "j": ["x", None],
        }
    ) == {"h": 0, "i": True, "j": ["x", None]}


def test_type_name_strips_ir_prefix():
    assert type_name(IrPolyLine3D(curve_length=None)) == "polyline3d"


def test_sort_jcs_is_deterministic():
    assert sort_jcs([{"b": "2"}, {"a": "1"}]) == [{"a": "1"}, {"b": "2"}]


def test_closed_polyline_canonical_form():
    canon = _geom_canon()
    rec = curve_record(square(), canon)
    assert rec == {
        "type": "polyline3d",
        "is_closed": True,
        "vertices": [
            ["0.000000", "0.000000", "0.000000"],
            ["2.000000", "0.000000", "0.000000"],
            ["2.000000", "2.000000", "0.000000"],
            ["0.000000", "2.000000", "0.000000"],
        ],
    }


def test_closed_polyline_invariant_to_start_orientation_units_and_closure():
    canon = _geom_canon()
    base = curve_record(square(), canon)
    assert curve_record(square(start=2), canon) == base
    assert curve_record(square(reverse=True, start=1), canon) == base
    assert curve_record(square(repeat_first=True), canon) == base
    assert curve_record(square(unit="Um", size=2.0), canon) == base
    assert curve_record(square(size=2000.0000001), canon) == base  # sub-µm noise


def test_open_polyline_keeps_order():
    canon = _geom_canon()
    pts = [IrPoint3D(0.0, 0.0, 0.0, "Umm"), IrPoint3D(1000.0, 0.0, 0.0, "Umm")]
    fwd = curve_record(IrPolyLine3D(curve_length=None, vertices=pts), canon)
    rev = curve_record(IrPolyLine3D(curve_length=None, vertices=pts[::-1]), canon)
    assert fwd != rev
    assert "is_closed" not in fwd


def test_repeated_endpoint_with_different_unknown_unit_is_kept():
    canon = _geom_canon()
    xy = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]

    def ring(last_unit: str) -> IrPolyLine3D:
        units = ["Ufoo"] * 4 + [last_unit]
        pts = [IrPoint3D(x, y, 0.0, u) for (x, y), u in zip(xy, units)]
        return IrPolyLine3D(curve_length=None, vertices=pts)

    assert curve_record(ring("Ufoo"), canon) != curve_record(ring("Ubar"), canon)
    assert curve_record(ring("Ubar"), canon)["vertices"][-1][3] == "Ubar"


def test_closed_composite_invariant_to_start_and_orientation():
    canon = _geom_canon()
    base = curve_record(_square_composite(), canon)
    assert base["segments"][0]["start"] == ["0.000000", "0.000000", "0.000000"]
    assert base["segments"][0]["end"] == ["2.000000", "0.000000", "0.000000"]
    assert curve_record(_square_composite(start=3), canon) == base
    assert curve_record(_square_composite(reverse=True, start=2), canon) == base


def test_reverse_nurbs_segment_mirrors_knots():
    seg = {
        "type": "nurbs3d",
        "control_points": [["0", "0", "0"], ["1", "1", "0"], ["2", "0", "0"]],
        "weights": ["1.000000", "2.000000", "3.000000"],
        "knot_vector": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.300000",
            "1.000000",
            "1.000000",
            "1.000000",
        ],
    }
    rev = _reverse_seg(seg)
    assert rev["control_points"] == [["2", "0", "0"], ["1", "1", "0"], ["0", "0", "0"]]
    assert rev["weights"] == ["3.000000", "2.000000", "1.000000"]
    assert rev["knot_vector"] == [
        "0.000000",
        "0.000000",
        "0.000000",
        "0.700000",
        "1.000000",
        "1.000000",
        "1.000000",
    ]
