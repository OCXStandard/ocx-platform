"""JSON-shape helpers shared by geometry and record canonicalisation."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from typing import Any

import rfc8785

# Exporter-local ids are never hashed; curve lengths are committed under "physical".
SKIP_FIELDS = frozenset({"id", "guidref", "curve_length"})


def _is_empty(value: Any) -> bool:
    if value is None or value is False:
        return True
    return isinstance(value, (str, list, dict)) and len(value) == 0


def prune(value: Any) -> Any:
    """Recursively drop dict entries that are None, '', False, [] or {}."""
    if isinstance(value, dict):
        out = {k: prune(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if not _is_empty(v)}
    if isinstance(value, list):
        return [prune(v) for v in value]
    return value


def type_name(obj: Any) -> str:
    """``IrPolyLine3D`` → ``"polyline3d"``."""
    name = type(obj).__name__
    return (name[2:] if name.startswith("Ir") else name).lower()


def sort_jcs(items: Iterable[Any]) -> list[Any]:
    """Sort an unordered collection by the JCS bytes of each item."""
    return sorted(items, key=rfc8785.dumps)


def dataclass_dict(
    obj: Any, canon: Callable[[Any], Any], skip: frozenset[str] = SKIP_FIELDS
) -> dict[str, Any]:
    """Generic canonical dict for an IR dataclass: ``{"type": ..., field: canon(value)}``."""
    out: dict[str, Any] = {"type": type_name(obj)}
    for f in dataclasses.fields(obj):
        if f.name not in skip:
            out[f.name] = canon(getattr(obj, f.name))
    return prune(out)
