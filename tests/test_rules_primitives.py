"""Tests for the check-primitive registry (step 1: signatures + stubs)."""
from __future__ import annotations

import pytest

from ocx_rules.model import CheckNotImplemented
from ocx_rules.primitives import PRIMITIVE_REGISTRY

EXPECTED_PRIMITIVES = {
    "has_attribute",
    "unique",
    "cardinality",
    "value_in_set",
    "sequence",
    "ref_resolves",
    "closed_contour",
    "normals_consistent",
}


class TestPrimitiveRegistry:
    def test_all_expected_primitives_registered(self):
        assert set(PRIMITIVE_REGISTRY) == EXPECTED_PRIMITIVES

    def test_all_primitives_are_callable(self):
        assert all(callable(fn) for fn in PRIMITIVE_REGISTRY.values())

    @pytest.mark.parametrize("name", sorted(EXPECTED_PRIMITIVES))
    def test_stub_raises_check_not_implemented(self, name):
        with pytest.raises(CheckNotImplemented):
            PRIMITIVE_REGISTRY[name](context=None, params={})
