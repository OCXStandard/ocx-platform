"""Manifest build / save / load (ocx-hash/1)."""

from __future__ import annotations

import hashlib
import json

import pytest
from ocx_integrity.errors import DuplicatePartIdError, IntegrityError, ProfileMismatchError
from ocx_integrity.manifest import (
    Manifest,
    build_manifest,
    hash_vessel,
    load_manifest,
    save_manifest,
    source_info,
)
from ocx_integrity.merkle import mth
from ocx_integrity.profile import ASPECTS
from ocx_model_core.model.ir import Quantity, Ref

from tests.integrity_fixtures import KEY, OTHER_KEY, make_vessel


def test_build_manifest_structure():
    m = build_manifest(make_vessel(), KEY, created="2026-01-01T00:00:00Z")
    assert m.profile == "ocx-hash/1"
    assert m.part_count == 6
    assert m.parts["G-PL-1"].kind == "plate"
    assert m.parts["ST1"].id_source == "xml_id"
    assert m.parts["vessel:V1"].id_source == "vessel"
    assert list(m.parts["G-PL-1"].aspects) == list(ASPECTS)
    assert m.warnings == []
    assert m.computed_root() == m.root


def test_root_is_deterministic_and_key_dependent():
    a = build_manifest(make_vessel(), KEY)
    assert build_manifest(make_vessel(), KEY).root == a.root
    assert build_manifest(make_vessel(), OTHER_KEY).root != a.root


def test_root_ignores_created_and_source():
    a = build_manifest(make_vessel(), KEY, created="2026-01-01T00:00:00Z")
    b = build_manifest(
        make_vessel(),
        KEY,
        created="2027-01-01T00:00:00Z",
        source={"file": "x.3docx", "sha256": "00", "schema_version": "3.1.0"},
    )
    assert a.root == b.root
    assert a.to_dict() != b.to_dict()


def test_hash_vessel_root_matches_manual_mth():
    hm = hash_vessel(make_vessel(), KEY)
    ids = sorted(hm.parts, key=lambda s: s.encode("utf-8"))
    assert hm.root == mth([hm.parts[p].part_hash for p in ids])
    plate = hm.parts["G-PL-1"]
    assert plate.part_hash == mth([plate.aspect_hashes[a] for a in ASPECTS])


def test_duplicate_part_ids_raise():
    v = make_vessel()
    v.stiffeners["ST1"].guidref = "G-PL-1"
    with pytest.raises(DuplicatePartIdError) as exc:
        hash_vessel(v, KEY)
    assert exc.value.part_ids == ["G-PL-1"]


def test_save_load_roundtrip_never_writes_key(tmp_path):
    m = build_manifest(
        make_vessel(), KEY, source={"file": "x.3docx", "sha256": "00", "schema_version": "3.1.0"}
    )
    path = tmp_path / "manifest.json"
    save_manifest(m, path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert list(data["parts"]) == sorted(data["parts"], key=lambda s: s.encode("utf-8"))
    assert data["part_count"] == 6
    assert KEY.hex() not in text
    assert load_manifest(path) == m


def test_load_rejects_other_profile(tmp_path):
    data = build_manifest(make_vessel(), KEY).to_dict()
    data["profile"] = "ocx-hash/2"
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProfileMismatchError):
        load_manifest(path)


def test_load_rejects_tampered_hashes(tmp_path):
    good = build_manifest(make_vessel(), KEY).to_dict()
    path = tmp_path / "m.json"
    bad_aspect = json.loads(json.dumps(good))
    bad_aspect["parts"]["G-PL-1"]["aspects"]["scantlings"] = "00" * 32
    path.write_text(json.dumps(bad_aspect), encoding="utf-8")
    with pytest.raises(IntegrityError):
        load_manifest(path)
    bad_root = json.loads(json.dumps(good))
    bad_root["root"] = "00" * 32
    path.write_text(json.dumps(bad_root), encoding="utf-8")
    with pytest.raises(IntegrityError):
        load_manifest(path)


def test_unknown_unit_and_unresolved_refs_become_warnings():
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(12.0, "Ufoo")
    v.plates["PL1"].material_ref = Ref("M404")
    assert build_manifest(v, KEY).warnings == [
        "unknown unit 'Ufoo' on plate G-PL-1",
        "unresolved material reference 'M404' on plate G-PL-1",
    ]


def test_source_info(tmp_path):
    model = tmp_path / "model.3docx"
    model.write_bytes(b"<ocx/>")
    assert source_info(model, "3.1.0") == {
        "file": "model.3docx",
        "sha256": hashlib.sha256(b"<ocx/>").hexdigest(),
        "schema_version": "3.1.0",
    }


def _good():
    return build_manifest(make_vessel(), KEY).to_dict()


def _mutate(fn):
    data = json.loads(json.dumps(_good()))
    fn(data)
    return data


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("root"),
        lambda d: d.update(root=None),
        lambda d: d.update(root="00"),
        lambda d: d.update(parts=[]),
        lambda d: d["parts"].update({"X": "nope"}),
        lambda d: d["parts"]["G-PL-1"].pop("kind"),
        lambda d: d["parts"]["G-PL-1"].update(kind=[]),
        lambda d: d["parts"]["G-PL-1"].update(id_source=1),
        lambda d: d["parts"]["G-PL-1"].update(aspects=[]),
        lambda d: d["parts"]["G-PL-1"].update(part_hash="00"),
        lambda d: d["parts"]["G-PL-1"]["aspects"].update(scantlings="zz"),
        lambda d: d["parts"]["G-PL-1"]["aspects"].update(scantlings=None),
        lambda d: d["parts"]["G-PL-1"]["aspects"].update(scantlings="AB" * 32),
        lambda d: d.update(warnings="w"),
        lambda d: d.update(warnings=[1]),
        lambda d: d.update(created=5),
        lambda d: d.update(source=[]),
    ],
)
def test_from_dict_rejects_malformed(mutate):
    with pytest.raises(IntegrityError):
        Manifest.from_dict(_mutate(mutate))


@pytest.mark.parametrize("data", [[], "x", None])
def test_from_dict_rejects_non_object(data):
    with pytest.raises(IntegrityError):
        Manifest.from_dict(data)


def test_from_dict_wrong_profile_still_profile_mismatch():
    with pytest.raises(ProfileMismatchError):
        Manifest.from_dict(_mutate(lambda d: (d.update(profile="x"), d.pop("root"))))


@pytest.mark.parametrize("count", [None, "6", 6.0, True, 5, 7])
def test_from_dict_checks_part_count(count):
    def set_count(d):
        if count is None:
            d.pop("part_count")
        else:
            d["part_count"] = count

    with pytest.raises(IntegrityError, match="part_count"):
        Manifest.from_dict(_mutate(set_count))


@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe\x00garbage"])
def test_load_rejects_invalid_json_or_encoding(tmp_path, raw):
    path = tmp_path / "m.json"
    path.write_bytes(raw)
    with pytest.raises(IntegrityError):
        load_manifest(path)


def test_load_rejects_duplicate_part_ids(tmp_path):
    text = json.dumps(_good(), indent=2)
    entry = json.dumps(_good()["parts"]["G-PL-1"])
    text = text.replace('"parts": {', '"parts": {\n    "G-PL-1": ' + entry + ",", 1)
    path = tmp_path / "m.json"
    path.write_text(text, encoding="utf-8")
    assert text.count('"G-PL-1"') == 2
    with pytest.raises(IntegrityError, match="duplicate"):
        load_manifest(path)
