"""Deferred geometry checks — stubs raising CheckNotImplemented.

Only the two compartment checks remain stubbed; all other Phase B
geometry checks are implemented in :mod:`.topology` and :mod:`.properties`.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented


def _stub(summary: str):
    def check(context, params):
        raise CheckNotImplemented(summary)

    check.__doc__ = summary
    return check


compartment_closure = _stub("CompartmentFace/ContourBound curves closed; "
                            "CellBoundary forms a closed volume")
compartments_disjoint = _stub("Compartments do not physically overlap")
