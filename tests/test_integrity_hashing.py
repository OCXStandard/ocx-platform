"""Salt derivation, key loading and aspect hashing (ocx-hash/1)."""

from __future__ import annotations

import hashlib
import hmac

import pytest
from ocx_integrity.errors import InvalidKeyError
from ocx_integrity.hashing import aspect_hash, payload
from ocx_integrity.salts import KEY_ENV, derive_salt, generate_key, load_key, parse_key

from tests.integrity_fixtures import KEY, OTHER_KEY

RECORD = {"kind": "plate", "thickness": "0.012000"}


def test_derive_salt_matches_spec_formula():
    expected = hmac.new(KEY, b"ocx-hash/1\x00G-PL-1\x00scantlings", hashlib.sha256).digest()
    assert derive_salt(KEY, "G-PL-1", "scantlings") == expected
    assert len(expected) == 32


def test_salts_differ_per_part_aspect_and_key():
    base = derive_salt(KEY, "P", "geometry")
    assert derive_salt(KEY, "Q", "geometry") != base
    assert derive_salt(KEY, "P", "physical") != base
    assert derive_salt(OTHER_KEY, "P", "geometry") != base


def test_payload_is_jcs():
    assert payload("plate", "P", "scantlings", RECORD) == (
        b'{"aspect":"scantlings","kind":"plate","part_id":"P","profile":"ocx-hash/1",'
        b'"record":{"kind":"plate","thickness":"0.012000"}}'
    )


def test_aspect_hash_is_sha256_of_salt_and_payload():
    salt = derive_salt(KEY, "P", "scantlings")
    expected = hashlib.sha256(salt + payload("plate", "P", "scantlings", RECORD)).digest()
    assert aspect_hash(salt, "plate", "P", "scantlings", RECORD) == expected


def test_load_key_from_file_and_env(tmp_path):
    key_file = tmp_path / "yard.key"
    key_file.write_text(KEY.hex() + "\n", encoding="utf-8")
    assert load_key(key_file, env={}) == KEY
    assert load_key(None, env={KEY_ENV: OTHER_KEY.hex()}) == OTHER_KEY
    assert load_key(key_file, env={KEY_ENV: OTHER_KEY.hex()}) == KEY  # file wins


@pytest.mark.parametrize("text", ["zz" * 32, "ab" * 31, ""])
def test_parse_key_rejects_bad_keys(text):
    with pytest.raises(InvalidKeyError):
        parse_key(text)


def test_load_key_missing(tmp_path):
    with pytest.raises(InvalidKeyError):
        load_key(None, env={})
    with pytest.raises(InvalidKeyError):
        load_key(tmp_path / "absent.key", env={})


def test_generate_key_roundtrips():
    text = generate_key()
    assert len(text) == 64
    assert len(parse_key(text)) == 32
