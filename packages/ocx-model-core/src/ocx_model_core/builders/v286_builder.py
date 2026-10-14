"""Ocx286Builder — translates OCX schema v2.8.x dataclasses into IR types.

The 2.8.6 element vocabulary is close enough to 3.1.0 that the inherited
``OcxV3Builder`` logic (which reads the newest field name first and falls
back to older names, all via ``getattr``) handles it directly.  Two real
structural differences remain:

1. The 2.8.6 xsdata bindings declare many fields as ``List[...]`` where the
   3.x bindings have scalars (e.g. ``OcxXml.vessel``, ``Plate.plate_material``,
   ``Material.density`` — ~60 fields in total).  ``build`` therefore first
   runs a generic in-place normalisation pass that unwraps any field that is
   a list in the 2.8.6 bindings but a scalar in the 3.1.0 bindings, then
   delegates to the inherited v3 build.
2. 2.8.6 nests the frame-table plane groups inside a ``FrameTables`` wrapper
   on ``CoordinateSystem`` (3.x has ``XRefPlanes``/… directly on it); a small
   adapter re-exposes them under the 3.x field names.
"""
from __future__ import annotations

import dataclasses
import typing

from loguru import logger

from ocx_model_core.parsers.dynamic_loader import DeclarationOfOcxImport, DynamicLoader

from .v3_builder import OcxV3Builder, _first


class _FrameTableCs:
    """Adapter presenting a 2.8.6 CoordinateSystem/FrameTables pair with 3.x field names."""

    def __init__(self, cs, ft) -> None:
        self.id = getattr(cs, "id", None)
        self.name = getattr(cs, "name", None)
        self.is_global = getattr(cs, "is_global", False)
        self.local_cartesian = getattr(cs, "local_cartesian", None)
        self.xref_planes = _first(getattr(ft, "xref_planes", None))
        self.yref_planes = _first(getattr(ft, "yref_planes", None))
        self.zref_planes = _first(getattr(ft, "zref_planes", None))


class Ocx286Builder(OcxV3Builder):
    """Builds an ``IrVessel`` from an OCX v2.8.x root dataclass."""

    #: lazily-built cache: 2.8.6 class name → field names to unwrap
    _unwrap_map: typing.ClassVar[dict[str, set[str]] | None] = None

    def supported_versions(self) -> list[tuple[int, int]]:
        return [(2, 8)]

    def build(self, root):
        """Normalise the raw 2.8.6 tree in place, then run the v3 build."""
        self._normalize(root, set())
        return super().build(root)

    # ------------------------------------------------------------------
    # Generic list→scalar normalisation (guided by the 3.1.0 bindings)
    # ------------------------------------------------------------------

    @classmethod
    def _reference_module(cls):
        """The 3.1.0 bindings module, used as the shape reference."""
        return DynamicLoader.import_module(DeclarationOfOcxImport("ocx", "3.1.0"))

    @classmethod
    def _fields_to_unwrap(cls, node) -> set[str]:
        """Fields of *node*'s class that are lists in 2.8.6 but scalars in 3.1.0."""
        name = type(node).__name__
        if cls._unwrap_map is None:
            cls._unwrap_map = {}
        if name in cls._unwrap_map:
            return cls._unwrap_map[name]
        fields: set[str] = set()
        ref_cls = getattr(cls._reference_module(), name, None)
        if ref_cls is not None and dataclasses.is_dataclass(ref_cls):
            try:
                here = typing.get_type_hints(type(node))
                there = typing.get_type_hints(ref_cls)
            except Exception:  # pragma: no cover — defensive
                here, there = {}, {}
            for f in dataclasses.fields(node):
                if (
                    typing.get_origin(here.get(f.name)) is list
                    and f.name in there
                    and typing.get_origin(there.get(f.name)) is not list
                ):
                    fields.add(f.name)
        cls._unwrap_map[name] = fields
        return fields

    def _normalize(self, node, seen: set[int]) -> None:
        """Recursively unwrap singleton lists where 3.x expects scalars."""
        if node is None or id(node) in seen or not dataclasses.is_dataclass(node):
            return
        seen.add(id(node))
        unwrap = self._fields_to_unwrap(node)
        for f in dataclasses.fields(node):
            value = getattr(node, f.name, None)
            if f.name in unwrap and isinstance(value, list):
                if len(value) > 1:
                    logger.warning(
                        f"2.8.6 normalisation: {type(node).__name__}.{f.name} has "
                        f"{len(value)} entries; keeping the first only"
                    )
                value = _first(value)
                setattr(node, f.name, value)
            if isinstance(value, (list, tuple)):
                for item in value:
                    self._normalize(item, seen)
            else:
                self._normalize(value, seen)

    # ------------------------------------------------------------------
    # 2.8.6 structural overrides
    # ------------------------------------------------------------------

    def _build_coordinate_system(self, cs, ir) -> None:
        """2.8.6 wraps the ref-plane groups in <FrameTables>; flatten them."""
        if cs is not None and not isinstance(cs, (list, tuple)):
            ft = _first(getattr(cs, "frame_tables", None))
            if ft is not None and getattr(cs, "xref_planes", None) is None:
                cs = _FrameTableCs(cs, ft)
        super()._build_coordinate_system(cs, ir)
