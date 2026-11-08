"""ocx-integrity on real tracked models: parse → build → manifest → verify / prove / check."""

from __future__ import annotations

from pathlib import Path

import pytest
from ocx_integrity import (
    build_manifest,
    check_bundle,
    load_manifest,
    prove,
    save_manifest,
    verify_model,
)

from tests.conftest import _build_session
from tests.integrity_fixtures import KEY

MODELS = Path(__file__).resolve().parents[1] / "models" / "TR02"
CASES = [("TR02_TC01_ai3dx.3docx", 3), ("TR02_TC04_ai3dx.3docx", 9)]


def _vessel(name: str):
    _, vessel = _build_session(str(MODELS / name))
    return vessel


@pytest.mark.parametrize("name, part_count", CASES)
def test_manifest_roundtrip_and_fresh_parse_verifies_clean(tmp_path, name, part_count):
    manifest = build_manifest(_vessel(name), KEY)
    assert manifest.part_count == part_count
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)
    report = verify_model(_vessel(name), load_manifest(path), KEY)
    assert report.clean, report.to_dict()


@pytest.mark.parametrize("name", [name for name, _ in CASES])
def test_every_part_proves_and_checks(name):
    vessel = _vessel(name)
    manifest = build_manifest(vessel, KEY)
    for pid in manifest.ordered_ids():
        result = check_bundle(prove(vessel, manifest, KEY, pid), root=manifest.root)
        assert result.valid, (pid, result.errors)
