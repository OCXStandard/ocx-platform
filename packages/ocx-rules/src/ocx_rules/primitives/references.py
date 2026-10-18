"""Cross-reference primitives. Step 1: stubs only."""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def ref_resolves(context, params: dict) -> list[Finding]:
    """Every ``ref_attribute`` value resolves to an element matching ``target_xpath``."""
    raise CheckNotImplemented("ref_resolves is not implemented yet")
