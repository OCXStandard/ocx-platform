"""OCX-TOP-001 helpers: boundary-ref reason fragments and the arrangement
path for panels bounded by GridRefs."""
from __future__ import annotations

from collections import Counter


def boundary_reasons(dangling: Counter[str], no_curve: Counter[str],
                     unsampleable: int) -> list[str]:
    """Reason fragments for LimitedBy refs that cannot be evaluated."""
    def by_type(counts: Counter[str]) -> str:
        return ", ".join(f"{t}×{n}" for t, n in sorted(counts.items()))

    reasons = []
    if dangling:
        reasons.append(f"{dangling.total()} dangling boundary ref(s) "
                       f"({by_type(dangling)})")
    if no_curve:
        reasons.append(f"{no_curve.total()} boundary ref(s) without explicit "
                       f"curve ({by_type(no_curve)})")
    if unsampleable:
        reasons.append(f"{unsampleable} unsampleable boundary curve(s)")
    return reasons
