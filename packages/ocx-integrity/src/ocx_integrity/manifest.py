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
    def from_dict(cls, data: Any) -> Manifest:
        """Build from untrusted JSON data; raise IntegrityError unless fully consistent."""
        if not isinstance(data, dict):
            raise IntegrityError("manifest must be a JSON object")
        profile = data.get("profile")
        if profile != PROFILE:
            raise ProfileMismatchError(f"unsupported profile {profile!r} (expected {PROFILE!r})")
        raw_parts = _field(data, "parts", dict, "manifest")
        parts: dict[str, PartEntry] = {}
        for pid, e in raw_parts.items():
            where = f"part {pid!r}"
            if not isinstance(e, dict):
                raise IntegrityError(f"{where}: entry must be an object")
            aspects = _field(e, "aspects", dict, where)
            for aspect, digest in aspects.items():
                _check_digest(digest, f"{where} aspect {aspect!r}")
            parts[pid] = PartEntry(
                _field(e, "kind", str, where),
                _field(e, "id_source", str, where),
                _check_digest(e.get("part_hash"), f"{where} part_hash"),
                dict(aspects),
            )
        part_count = data.get("part_count")
        if type(part_count) is not int or part_count != len(parts):
            raise IntegrityError(f"part_count {part_count!r} does not match {len(parts)} parts")
        warnings = data.get("warnings", [])
        if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
            raise IntegrityError("manifest 'warnings' must be a list of strings")
        created = data.get("created")
        if created is not None and not isinstance(created, str):
            raise IntegrityError("manifest 'created' must be a string or null")
        source = data.get("source")
        if source is not None and not isinstance(source, dict):
            raise IntegrityError("manifest 'source' must be an object or null")
        manifest = cls(
            root=_check_digest(data.get("root"), "manifest root"),
            parts=parts,
            warnings=list(warnings),
            profile=profile,
            created=created,
            source=source,
        )
        manifest.check_consistency()
        return manifest


_HEX = frozenset("0123456789abcdef")


def _field(obj: dict[str, Any], name: str, typ: type, where: str) -> Any:
    value = obj.get(name)
    if not isinstance(value, typ):
        raise IntegrityError(f"{where}: {name!r} must be a {typ.__name__}, got {value!r}")
    return value


def _check_digest(value: Any, where: str) -> str:
    """A digest is exactly what to_dict emits: 64 lowercase hex characters."""
    if not isinstance(value, str) or len(value) != 64 or not set(value) <= _HEX:
        raise IntegrityError(f"{where}: expected 64 lowercase hex characters, got {value!r}")
    return value


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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise IntegrityError(f"duplicate JSON key {key!r} in manifest")
        obj[key] = value
    return obj


def load_manifest(path: Path) -> Manifest:
    """Load and validate a manifest file. OSError propagates; bad content -> IntegrityError."""
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"manifest is not valid UTF-8 JSON: {exc}") from exc
    return Manifest.from_dict(data)
