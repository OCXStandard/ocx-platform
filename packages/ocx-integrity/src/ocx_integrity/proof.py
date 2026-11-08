"""Selective-disclosure bundles: one part's aspects + a Merkle audit path to the root."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.errors import PartDriftError, ProfileMismatchError, UnknownPartError
from ocx_integrity.hashing import aspect_hash
from ocx_integrity.manifest import Manifest, hash_vessel
from ocx_integrity.merkle import inclusion_path, mth, root_from_path
from ocx_integrity.profile import ASPECTS, PROFILE


@dataclass
class DisclosureBundle:
    root: str
    tree_size: int
    leaf_index: int
    part_id: str
    kind: str
    disclosed: dict[str, dict[str, Any]]  # aspect -> {"record": {...}, "salt": hex}
    aspect_hashes: dict[str, str]
    audit_path: list[str]
    profile: str = PROFILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "root": self.root,
            "tree_size": self.tree_size,
            "leaf_index": self.leaf_index,
            "part_id": self.part_id,
            "kind": self.kind,
            "disclosed": self.disclosed,
            "aspect_hashes": self.aspect_hashes,
            "audit_path": self.audit_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisclosureBundle:
        profile = data.get("profile")
        if profile != PROFILE:
            raise ProfileMismatchError(f"unsupported profile {profile!r} (expected {PROFILE!r})")
        return cls(
            root=data["root"],
            tree_size=data["tree_size"],
            leaf_index=data["leaf_index"],
            part_id=data["part_id"],
            kind=data["kind"],
            disclosed=data["disclosed"],
            aspect_hashes=data["aspect_hashes"],
            audit_path=list(data["audit_path"]),
            profile=profile,
        )


@dataclass(frozen=True)
class BundleCheck:
    valid: bool
    errors: list[str]


def prove(
    vessel: IrVessel,
    manifest: Manifest,
    key: bytes,
    part_id: str,
    aspects: Iterable[str] | None = None,
) -> DisclosureBundle:
    """Build a bundle disclosing ``aspects`` (default: all) of ``part_id``."""
    entry = manifest.parts.get(part_id)
    if entry is None:
        raise UnknownPartError(f"part {part_id!r} is not in the manifest")
    wanted = set(entry.aspects) if aspects is None else set(aspects)
    unknown = sorted(wanted - set(entry.aspects))
    if unknown:
        raise UnknownPartError(f"part {part_id!r} has no aspect(s): {', '.join(unknown)}")
    part = hash_vessel(vessel, key).parts.get(part_id)
    if part is None or part.part_hash.hex() != entry.part_hash:
        raise PartDriftError(f"part {part_id!r} in the model no longer matches the manifest")
    ids = manifest.ordered_ids()
    index = ids.index(part_id)
    leaves = [bytes.fromhex(manifest.parts[p].part_hash) for p in ids]
    return DisclosureBundle(
        root=manifest.root,
        tree_size=len(ids),
        leaf_index=index,
        part_id=part_id,
        kind=entry.kind,
        disclosed={
            a: {"record": part.records[a], "salt": part.salts[a].hex()}
            for a in ASPECTS
            if a in wanted
        },
        aspect_hashes=dict(entry.aspects),
        audit_path=[h.hex() for h in inclusion_path(index, leaves)],
    )


def _check_disclosed(bundle: DisclosureBundle, errors: list[str]) -> None:
    for aspect, item in bundle.disclosed.items():
        try:
            computed = aspect_hash(
                bytes.fromhex(item["salt"]), bundle.kind, bundle.part_id, aspect, item["record"]
            ).hex()
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"aspect {aspect!r}: malformed disclosure ({exc})")
            continue
        if computed != bundle.aspect_hashes.get(aspect):
            errors.append(f"aspect {aspect!r}: disclosed record/salt do not match its hash")


def _check_path(bundle: DisclosureBundle, errors: list[str]) -> None:
    unknown = sorted(set(bundle.aspect_hashes) - set(ASPECTS))
    if unknown:
        errors.append(f"unknown aspect(s) in aspect_hashes: {', '.join(unknown)}")
        return
    try:
        part_hash = mth(
            [bytes.fromhex(bundle.aspect_hashes[a]) for a in ASPECTS if a in bundle.aspect_hashes]
        )
        path = [bytes.fromhex(p) for p in bundle.audit_path]
    except (TypeError, ValueError) as exc:
        errors.append(f"malformed hex in bundle ({exc})")
        return
    try:
        computed = root_from_path(part_hash, bundle.leaf_index, bundle.tree_size, path)
    except ValueError as exc:
        errors.append(f"invalid audit path: {exc}")
        return
    if computed.hex() != bundle.root.lower():
        errors.append("audit path does not lead to the bundle root")


def _check_structure(bundle: DisclosureBundle, errors: list[str]) -> None:
    # Bundles are untrusted input: report wrong field types instead of raising.
    expected = {
        "root": str,
        "tree_size": int,
        "leaf_index": int,
        "part_id": str,
        "kind": str,
        "disclosed": dict,
        "aspect_hashes": dict,
        "audit_path": list,
    }
    for name, typ in expected.items():
        value = getattr(bundle, name)
        if not isinstance(value, typ) or isinstance(value, bool):
            errors.append(f"malformed bundle: {name!r} must be {typ.__name__}")


def check_bundle(bundle: DisclosureBundle, root: str | None = None) -> BundleCheck:
    """Verify a bundle without the key; optionally pin it to an independently known root."""
    errors: list[str] = []
    _check_structure(bundle, errors)
    if errors:
        return BundleCheck(False, errors)
    _check_disclosed(bundle, errors)
    _check_path(bundle, errors)
    if root is not None and root.lower() != bundle.root.lower():
        errors.append("bundle root does not match the expected root")
    return BundleCheck(not errors, errors)
