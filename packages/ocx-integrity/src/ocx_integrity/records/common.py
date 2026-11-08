"""Shared record machinery: part IDs, reference resolution, canonical values."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from ocx_model_core.model.ir import (
    IrCog,
    IrCurve3D,
    IrHole2DContour,
    IrPoint3D,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)

from ocx_integrity.canon_geom import curve_record
from ocx_integrity.jsonutil import dataclass_dict, prune, sort_jcs, type_name
from ocx_integrity.quantize import Quantizer


def part_id(obj: Any) -> tuple[str, str]:
    """``(part_id, id_source)`` — GUID if present, else the XML id."""
    guid = getattr(obj, "guidref", None)
    if guid:
        return guid, "guid"
    return obj.id, "xml_id"


def vessel_part_id(vessel: IrVessel) -> str:
    return f"vessel:{vessel.id}"


def _raw(ref: Ref) -> str:
    return ref.guidref or ref.local_ref


class Context:
    """Per-vessel extraction state: id index, quantizer, warnings, current part."""

    def __init__(self, vessel: IrVessel) -> None:
        self.vessel = vessel
        self.warnings: list[str] = []
        self.current = f"vessel {vessel.id}"
        self.quant = Quantizer(vessel.unit_registry, self.warn)
        self.holes = vessel.hole_shape_catalogue.holes if vessel.hole_shape_catalogue else {}
        self._by_xml_id: dict[str, str] = {}
        self._guids: set[str] = set()
        tables = (
            vessel.plates,
            vessel.stiffeners,
            vessel.brackets,
            vessel.pillars,
            vessel.edge_reinforcements,
            vessel.panels,
            vessel.seams,
            vessel.compartments,
            vessel.materials,
            vessel.sections,
            vessel.surfaces,
            vessel.ref_planes,
            self.holes,
        )
        for table in tables:
            for obj in table.values():
                pid, _ = part_id(obj)
                self._by_xml_id.setdefault(obj.id, pid)
                if getattr(obj, "guidref", None):
                    self._guids.add(obj.guidref)

    def warn(self, message: str) -> None:
        self.warnings.append(f"{message} on {self.current}")

    def resolve(self, ref: Ref | None) -> Any:
        """Ref → target part ID (or ``{"unresolved": raw}``), keeping any 3.2 offset."""
        if ref is None:
            return None
        if ref.local_ref and ref.local_ref in self._by_xml_id:
            target: Any = self._by_xml_id[ref.local_ref]
        elif ref.guidref and ref.guidref in self._guids:
            target = ref.guidref
        else:
            self.warn(f"unresolved reference {_raw(ref)!r}")
            target = {"unresolved": _raw(ref)}
        if ref.offset is None and ref.offset_direction is None:
            return target
        return prune(
            {
                "ref": target,
                "offset": self.canon(ref.offset),
                "offset_direction": self.canon(ref.offset_direction),
            }
        )

    def lookup(self, ref: Ref | None, table: dict[str, Any], what: str) -> Any:
        """Return the object a ref points to in ``table`` (by id, then GUID), or None."""
        if ref is None:
            return None
        obj = table.get(ref.local_ref)
        if obj is None and ref.guidref:
            obj = next(
                (o for o in table.values() if getattr(o, "guidref", None) == ref.guidref), None
            )
        if obj is None:
            self.warn(f"unresolved {what} reference {_raw(ref)!r}")
        return obj

    def parent(self, parent_ref: ParentRef | None) -> Any:
        if parent_ref is None:
            return None
        if parent_ref.kind == ParentKind.VESSEL:
            return vessel_part_id(self.vessel)
        return self.resolve(Ref(parent_ref.id))

    def canon(self, value: Any) -> Any:
        """Any IR value → canonical JSON value (strings for all numbers except ints)."""
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, float):
            return self.quant.scalar(value)
        if isinstance(value, Quantity):
            return self.quant.quantity(value)
        if isinstance(value, (IrPoint3D, IrCog)):
            return self.quant.point(value)
        if isinstance(value, IrVector3D):
            return self.quant.vector(value)
        if isinstance(value, Ref):
            return self.resolve(value)
        if isinstance(value, IrCurve3D):
            return curve_record(value, self.canon)
        if isinstance(value, (list, tuple)):
            return [self.canon(v) for v in value]
        if isinstance(value, dict):
            # Nested XML ids are exporter-local (e.g. IrGenericSection.extra carries them).
            return {str(k): self.canon(v) for k, v in value.items() if k not in ("id", "guidref")}
        if dataclasses.is_dataclass(value):
            return dataclass_dict(value, self.canon)
        raise TypeError(f"cannot canonicalise {type(value).__name__}")

    def canon_set(self, values: list[Any]) -> list[Any]:
        """Canonicalise an unordered collection and sort it by JCS bytes."""
        return sort_jcs(self.canon(v) for v in values)


def make_record(kind: str, **fields: Any) -> dict[str, Any] | None:
    """Pruned record with ``kind``; ``None`` (aspect absent) when no field has content."""
    body = prune(fields)
    return {"kind": kind, **body} if body else None


def identity(kind: str, obj: Any, ctx: Context, **extra: Any) -> dict[str, Any] | None:
    _, source = part_id(obj)
    return make_record(
        kind, id_source=source, name=obj.name, **{k: ctx.canon(v) for k, v in extra.items()}
    )


def catalogue_record(obj: Any, ctx: Context) -> dict[str, Any]:
    pid, _ = part_id(obj)
    return {"part_id": pid, **ctx.canon(obj)}


def _resolved_catalogue(
    ref: Ref | None, table: dict[str, Any], what: str, ctx: Context
) -> dict[str, Any] | None:
    if ref is None:
        return None
    obj = ctx.lookup(ref, table, what)
    return catalogue_record(obj, ctx) if obj is not None else {"unresolved": _raw(ref)}


def material_aspect(kind: str, ref: Ref | None, ctx: Context) -> dict[str, Any] | None:
    return make_record(
        kind, material=_resolved_catalogue(ref, ctx.vessel.materials, "material", ctx)
    )


def section_value(ref: Ref | None, ctx: Context) -> dict[str, Any] | None:
    return _resolved_catalogue(ref, ctx.vessel.sections, "section", ctx)


def hole_placement(h: IrHole2DContour, ctx: Context) -> dict[str, Any]:
    return prune(
        {
            "type": type_name(h),
            "name": h.name,
            "hole": _resolved_catalogue(h.hole_ref, ctx.holes, "hole shape", ctx),
            "transformation": ctx.canon(h.transformation),
        }
    )


def curve_lengths(ctx: Context, **curves: Any) -> dict[str, Any]:
    """Committed lengths of the given curves (lists are treated as unordered)."""
    out: dict[str, Any] = {}
    for name, value in curves.items():
        if isinstance(value, list):
            out[name] = sort_jcs(
                ctx.canon(c.curve_length)
                for c in value
                if c is not None and c.curve_length is not None
            )
        elif value is not None and value.curve_length is not None:
            out[name] = ctx.canon(value.curve_length)
    return prune(out)
