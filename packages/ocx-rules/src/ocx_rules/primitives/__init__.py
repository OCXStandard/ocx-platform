"""Check-primitive library.

PRIMITIVE_REGISTRY maps the primitive name used in rule TOML files to the
callable implementing it. All checks share the signature
``(context: ValidationContext, params: dict) -> list[Finding]``.
"""
from __future__ import annotations

from collections.abc import Callable

from ocx_rules.primitives import content, geometry, references

PRIMITIVE_REGISTRY: dict[str, Callable] = {
    "has_attribute": content.has_attribute,
    "unique": content.unique,
    "cardinality": content.cardinality,
    "value_in_set": content.value_in_set,
    "sequence": content.sequence,
    "ref_resolves": references.ref_resolves,
    "closed_contour": geometry.closed_contour,
    "normals_consistent": geometry.normals_consistent,
}
