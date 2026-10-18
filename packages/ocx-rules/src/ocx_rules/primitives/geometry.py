"""Geometry primitives. Step 1: stubs only.

Implementations (step 2) must import ocx_geometry INSIDE the function body so
that content-only validation never loads the numpy stack.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def closed_contour(context, params: dict) -> list[Finding]:
    """The contour named by ``target`` is closed within ``tolerance_mm``."""
    raise CheckNotImplemented("closed_contour is not implemented yet")


def normals_consistent(context, params: dict) -> list[Finding]:
    """Normals over ``target`` are consistently oriented within ``angle_tolerance_deg``."""
    raise CheckNotImplemented("normals_consistent is not implemented yet")
