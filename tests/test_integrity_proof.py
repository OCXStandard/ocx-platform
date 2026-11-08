"""Disclosure bundles: prove (yard, with key) and check (class, no key)."""

from __future__ import annotations

import copy
import json

import pytest
from ocx_integrity.errors import PartDriftError, ProfileMismatchError, UnknownPartError
from ocx_integrity.manifest import build_manifest
from ocx_integrity.profile import ASPECTS
from ocx_integrity.proof import BundleCheck, DisclosureBundle, check_bundle, prove
from ocx_model_core.model.ir import Quantity

from tests.integrity_fixtures import KEY, make_vessel


def _setup():
    v = make_vessel()
    return v, build_manifest(v, KEY)


def test_full_bundle_checks_without_key():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1")
    assert list(b.disclosed) == list(ASPECTS)
    assert b.aspect_hashes == m.parts["G-PL-1"].aspects
    assert (b.tree_size, b.leaf_index, b.kind) == (6, 2, "plate")
    assert check_bundle(b) == BundleCheck(True, [])
    assert check_bundle(b, root=m.root.upper()).valid


def test_selective_disclosure_reveals_only_requested_aspects():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1", ["scantlings"])
    assert list(b.disclosed) == ["scantlings"]
    assert set(b.disclosed["scantlings"]) == {"record", "salt"}
    assert b.disclosed["scantlings"]["record"]["kind"] == "plate"
    assert check_bundle(b).valid


def test_bundle_json_roundtrip_never_contains_key():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1")
    text = json.dumps(b.to_dict())
    assert KEY.hex() not in text
    assert DisclosureBundle.from_dict(json.loads(text)) == b


def _set(path, value):
    def tamper(d):
        target = d
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return tamper


@pytest.mark.parametrize(
    "tamper, fragment",
    [
        (_set(["disclosed", "scantlings", "record", "kind"], "stiffener"), "scantlings"),
        (_set(["disclosed", "scantlings", "salt"], "00" * 32), "scantlings"),
        (_set(["aspect_hashes", "scantlings"], "00" * 32), "scantlings"),
        (_set(["aspect_hashes", "identity"], "00" * 32), "root"),
        (_set(["audit_path", 0], "00" * 32), "root"),
        (_set(["root"], "00" * 32), "root"),
        (_set(["leaf_index"], 3), "path"),
        (_set(["aspect_hashes", "bogus"], "00" * 32), "unknown aspect"),
        (_set(["audit_path", 0], "zz"), "hex"),
    ],
)
def test_tampered_bundle_fails(tamper, fragment):
    v, m = _setup()
    d = copy.deepcopy(prove(v, m, KEY, "G-PL-1", ["scantlings"]).to_dict())
    tamper(d)
    result = check_bundle(DisclosureBundle.from_dict(d))
    assert not result.valid
    assert any(fragment in e for e in result.errors), result.errors


@pytest.mark.parametrize(
    "field, value, typ",
    [
        ("disclosed", [], "dict"),
        ("aspect_hashes", None, "dict"),
        ("leaf_index", "2", "int"),
        ("tree_size", None, "int"),
        ("root", 5, "str"),
    ],
)
def test_structurally_malformed_bundle_reported_not_raised(field, value, typ):
    v, m = _setup()
    d = prove(v, m, KEY, "G-PL-1", ["scantlings"]).to_dict()
    d[field] = value
    result = check_bundle(DisclosureBundle.from_dict(d))
    assert result.errors == [f"malformed bundle: {field!r} must be {typ}"]


def test_expected_root_mismatch_fails():
    v, m = _setup()
    result = check_bundle(prove(v, m, KEY, "G-PL-1"), root="00" * 32)
    assert result.errors == ["bundle root does not match the expected root"]


def test_bundle_profile_mismatch_refused():
    v, m = _setup()
    d = prove(v, m, KEY, "G-PL-1").to_dict()
    d["profile"] = "ocx-hash/2"
    with pytest.raises(ProfileMismatchError):
        DisclosureBundle.from_dict(d)


def test_unknown_part_or_aspect_refused():
    v, m = _setup()
    with pytest.raises(UnknownPartError):
        prove(v, m, KEY, "NOPE")
    with pytest.raises(UnknownPartError):
        prove(v, m, KEY, "G-PL-1", ["bogus"])


def test_drifted_part_refused_but_other_parts_still_provable():
    _, m = _setup()
    drifted = make_vessel()
    drifted.plates["PL1"].thickness = Quantity(14.0, "Umm")
    with pytest.raises(PartDriftError):
        prove(drifted, m, KEY, "G-PL-1")
    b = prove(drifted, m, KEY, "ST1")
    assert check_bundle(b, root=m.root).valid
