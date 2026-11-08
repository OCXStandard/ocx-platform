"""Golden vectors for profile ocx-hash/1 — a failure here means the profile changed.

Generate the pinned file ONCE (and only when introducing a new profile):
    uv run python -m tests.test_integrity_golden
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ocx_integrity import PROFILE, build_manifest, hash_vessel
from ocx_integrity.manifest import ordered_ids

from tests.integrity_fixtures import KEY, make_vessel

GOLDEN = Path(__file__).parent / "data" / "integrity" / "golden_v1.json"


def current_vectors() -> dict[str, Any]:
    hashed = hash_vessel(make_vessel(), KEY)
    parts = {}
    for pid in ordered_ids(hashed.parts):
        p = hashed.parts[pid]
        parts[pid] = {
            "kind": p.kind,
            "records": p.records,
            "aspects": {a: h.hex() for a, h in p.aspect_hashes.items()},
            "part_hash": p.part_hash.hex(),
        }
    return {"profile": PROFILE, "key": KEY.hex(), "root": hashed.root.hex(), "parts": parts}


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_canonical_records_match_golden(golden):
    current = current_vectors()
    assert list(current["parts"]) == list(golden["parts"])
    for pid, expected in golden["parts"].items():
        assert current["parts"][pid]["records"] == expected["records"], pid


def test_hashes_match_golden(golden):
    current = current_vectors()
    assert current["profile"] == golden["profile"] == "ocx-hash/1"
    for pid, expected in golden["parts"].items():
        assert current["parts"][pid]["aspects"] == expected["aspects"], pid
        assert current["parts"][pid]["part_hash"] == expected["part_hash"], pid
    assert current["root"] == golden["root"]


def test_public_api_reproduces_golden_root(golden):
    assert build_manifest(make_vessel(), KEY).root == golden["root"]


if __name__ == "__main__":
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(
        json.dumps(current_vectors(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {GOLDEN}")
