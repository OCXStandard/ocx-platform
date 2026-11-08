"""Canonicalisation tests: quantizer, geometry, records, invariance (ocx-hash/1)."""

from __future__ import annotations

import decimal
from decimal import Decimal

from ocx_integrity.quantize import Quantizer, fmt_decimal
from ocx_model_core.model.ir import IrPoint3D, IrVector3D, Quantity

from tests.integrity_fixtures import registry


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
