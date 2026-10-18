"""Content-inspection primitives (XML/IR attribute, uniqueness, cardinality...).

Step 1 ships signatures only; every body raises CheckNotImplemented.
Implementations land in step 2.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def has_attribute(context, params: dict) -> list[Finding]:
    """Every element matching ``xpath`` carries ``attribute``."""
    raise CheckNotImplemented("has_attribute is not implemented yet")


def unique(context, params: dict) -> list[Finding]:
    """``key`` values over elements matching ``xpath`` are unique."""
    raise CheckNotImplemented("unique is not implemented yet")


def cardinality(context, params: dict) -> list[Finding]:
    """Each element matching ``xpath`` has between ``min`` and ``max`` ``child`` elements."""
    raise CheckNotImplemented("cardinality is not implemented yet")


def value_in_set(context, params: dict) -> list[Finding]:
    """``key`` values over elements matching ``xpath`` are members of ``allowed``."""
    raise CheckNotImplemented("value_in_set is not implemented yet")


def sequence(context, params: dict) -> list[Finding]:
    """Numeric sequences at ``key`` obey ``order`` (e.g. non_decreasing) / ``max_run``."""
    raise CheckNotImplemented("sequence is not implemented yet")
