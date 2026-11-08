"""Per-kind canonical record extractors (profile ocx-hash/1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.profile import ASPECTS
from ocx_integrity.records import (
    bracket,
    compartment,
    edge_reinforcement,
    panel,
    pillar,
    plate,
    seam,
    stiffener,
)
from ocx_integrity.records import vessel as vessel_records
from ocx_integrity.records.common import Context, part_id, vessel_part_id

Extractor = Callable[[Any, Context], dict[str, Any]]

EXTRACTORS: dict[str, Extractor] = {
    "vessel": vessel_records.extract,
    "plate": plate.extract,
    "stiffener": stiffener.extract,
    "bracket": bracket.extract,
    "pillar": pillar.extract,
    "edge_reinforcement": edge_reinforcement.extract,
    "panel": panel.extract,
    "seam": seam.extract,
    "compartment": compartment.extract,
}

# (kind, IrVessel attribute) for every part kind except the vessel itself.
_TABLES: tuple[tuple[str, str], ...] = (
    ("plate", "plates"),
    ("stiffener", "stiffeners"),
    ("bracket", "brackets"),
    ("pillar", "pillars"),
    ("edge_reinforcement", "edge_reinforcements"),
    ("panel", "panels"),
    ("seam", "seams"),
    ("compartment", "compartments"),
)


@dataclass(frozen=True)
class PartRecords:
    kind: str
    part_id: str
    id_source: str
    aspects: dict[str, dict[str, Any]]  # present aspects only, in ASPECTS order


def _present(aspects: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a: aspects[a] for a in ASPECTS if aspects.get(a)}


def iter_parts(vessel: IrVessel, ctx: Context) -> Iterator[PartRecords]:
    """Yield the vessel metadata part, then every structural/arrangement part."""
    vid = vessel_part_id(vessel)
    ctx.current = vid
    yield PartRecords("vessel", vid, "vessel", _present(EXTRACTORS["vessel"](vessel, ctx)))
    for kind, attr in _TABLES:
        for obj in getattr(vessel, attr).values():
            pid, source = part_id(obj)
            ctx.current = f"{kind} {pid}"
            yield PartRecords(kind, pid, source, _present(EXTRACTORS[kind](obj, ctx)))
