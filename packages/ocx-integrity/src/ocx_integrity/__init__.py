"""ocx-integrity — canonical salted aspect hashes + Merkle manifest (profile ocx-hash/1).

Typical use::

    from ocx_integrity import build_manifest, verify_model, prove, check_bundle

    manifest = build_manifest(vessel, key)             # yard, with the secret key
    report = verify_model(vessel, manifest, key)       # yard: has the model changed?
    bundle = prove(vessel, manifest, key, part_id, ["scantlings"])
    check_bundle(bundle, root=manifest.root).valid     # class: no key needed
"""

from ocx_integrity.diff import ChangeReport, diff_manifests, format_report
from ocx_integrity.errors import (
    DuplicatePartIdError,
    IntegrityError,
    InvalidKeyError,
    PartDriftError,
    ProfileMismatchError,
    UnknownPartError,
)
from ocx_integrity.manifest import (
    Manifest,
    PartEntry,
    build_manifest,
    hash_vessel,
    load_manifest,
    save_manifest,
)
from ocx_integrity.profile import ASPECTS, PROFILE
from ocx_integrity.proof import BundleCheck, DisclosureBundle, check_bundle, prove
from ocx_integrity.salts import generate_key, load_key
from ocx_integrity.verify import verify_model

__all__ = [
    "ASPECTS",
    "PROFILE",
    "BundleCheck",
    "ChangeReport",
    "DisclosureBundle",
    "DuplicatePartIdError",
    "IntegrityError",
    "InvalidKeyError",
    "Manifest",
    "PartDriftError",
    "PartEntry",
    "ProfileMismatchError",
    "UnknownPartError",
    "build_manifest",
    "check_bundle",
    "diff_manifests",
    "format_report",
    "generate_key",
    "hash_vessel",
    "load_key",
    "load_manifest",
    "prove",
    "save_manifest",
    "verify_model",
]
