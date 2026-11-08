"""Hash a vessel; build, serialise and load the shareable integrity manifest."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.errors import DuplicatePartIdError, IntegrityError, ProfileMismatchError
from ocx_integrity.hashing import aspect_hash
from ocx_integrity.merkle import mth
from ocx_integrity.profile import ASPECTS, PROFILE
from ocx_integrity.records import iter_parts
from ocx_integrity.records.common import Context
from ocx_integrity.salts import derive_salt


def ordered_ids(part_ids: Iterable[str]) -> list[str]:
    """Root leaf order: part IDs sorted by their UTF-8 bytes."""
    return sorted(part_ids, key=lambda s: s.encode("utf-8"))


# --- in-memory result (contains records + salts: never written to a manifest) ---


@dataclass(frozen=True)
class HashedPart:
    kind: str
    id_source: str
    records: dict[str, dict[str, Any]]
    salts: dict[str, bytes]
    aspect_hashes: dict[str, bytes]
    part_hash: bytes


@dataclass(frozen=True)
class HashedModel:
    parts: dict[str, HashedPart]
    warnings: list[str]

    @property
    def root(self) -> bytes:
        return mth([self.parts[p].part_hash for p in ordered_ids(self.parts)])


def hash_vessel(vessel: IrVessel, key: bytes) -> HashedModel:
    ctx = Context(vessel)
    parts: dict[str, HashedPart] = {}
    duplicates: set[str] = set()
    for rec in iter_parts(vessel, ctx):
        if rec.part_id in parts:
            duplicates.add(rec.part_id)
            continue
        salts = {a: derive_salt(key, rec.part_id, a) for a in rec.aspects}
        hashes = {
            a: aspect_hash(salts[a], rec.kind, rec.part_id, a, record)
            for a, record in rec.aspects.items()
        }
        parts[rec.part_id] = HashedPart(
            rec.kind, rec.id_source, rec.aspects, salts, hashes, mth(list(hashes.values()))
        )
    if duplicates:
        raise DuplicatePartIdError(ordered_ids(duplicates))
    return HashedModel(parts, sorted(set(ctx.warnings)))


# --- shareable manifest ---------------------------------------------------------


@dataclass
class PartEntry:
    kind: str
    id_source: str
    part_hash: str
    aspects: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id_source": self.id_source,
            "part_hash": self.part_hash,
            "aspects": dict(self.aspects),
        }


@dataclass
class Manifest:
    root: str
    parts: dict[str, PartEntry]
    warnings: list[str] = field(default_factory=list)
    profile: str = PROFILE
    created: str | None = None
    source: dict[str, Any] | None = None

    @property
    def part_count(self) -> int:
        return len(self.parts)

    def ordered_ids(self) -> list[str]:
        return ordered_ids(self.parts)

    def computed_root(self) -> str:
        return mth([bytes.fromhex(self.parts[p].part_hash) for p in self.ordered_ids()]).hex()

    def check_consistency(self) -> None:
        """Raise IntegrityError unless every part_hash and the root recompute."""
        for pid, entry in self.parts.items():
            unknown = set(entry.aspects) - set(ASPECTS)
            hashes = [bytes.fromhex(entry.aspects[a]) for a in ASPECTS if a in entry.aspects]
            if unknown or mth(hashes).hex() != entry.part_hash:
                raise IntegrityError(f"part {pid!r}: part_hash does not match its aspect hashes")
        if self.computed_root() != self.root:
            raise IntegrityError("manifest root does not match its part hashes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "created": self.created,
            "source": self.source,
            "root": self.root,
            "part_count": self.part_count,
            "warnings": list(self.warnings),
            "parts": {pid: self.parts[pid].to_dict() for pid in self.ordered_ids()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        profile = data.get("profile")
        if profile != PROFILE:
            raise ProfileMismatchError(f"unsupported profile {profile!r} (expected {PROFILE!r})")
        parts = {
            pid: PartEntry(e["kind"], e["id_source"], e["part_hash"], dict(e["aspects"]))
            for pid, e in data["parts"].items()
        }
        manifest = cls(
            root=data["root"],
            parts=parts,
            warnings=list(data.get("warnings", [])),
            profile=profile,
            created=data.get("created"),
            source=data.get("source"),
        )
        manifest.check_consistency()
        return manifest


def manifest_from_hashed(
    hashed: HashedModel, *, created: str | None = None, source: dict[str, Any] | None = None
) -> Manifest:
    parts = {
        pid: PartEntry(
            p.kind, p.id_source, p.part_hash.hex(), {a: h.hex() for a, h in p.aspect_hashes.items()}
        )
        for pid, p in hashed.parts.items()
    }
    return Manifest(
        root=hashed.root.hex(),
        parts=parts,
        warnings=list(hashed.warnings),
        created=created,
        source=source,
    )


def build_manifest(
    vessel: IrVessel,
    key: bytes,
    *,
    source: dict[str, Any] | None = None,
    created: str | None = None,
) -> Manifest:
    if created is None:
        created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return manifest_from_hashed(hash_vessel(vessel, key), created=created, source=source)


def source_info(path: Path, schema_version: str) -> dict[str, Any]:
    with Path(path).open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()
    return {"file": Path(path).name, "sha256": digest, "schema_version": schema_version}


def save_manifest(manifest: Manifest, path: Path) -> None:
    Path(path).write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_manifest(path: Path) -> Manifest:
    return Manifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
