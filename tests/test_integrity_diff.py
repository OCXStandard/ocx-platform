"""Manifest diff and model verification."""

from __future__ import annotations

import dataclasses

import pytest
from ocx_integrity.diff import diff_manifests, format_report
from ocx_integrity.errors import ProfileMismatchError
from ocx_integrity.manifest import build_manifest
from ocx_integrity.verify import verify_model
from ocx_model_core.model.ir import Quantity

from tests.integrity_fixtures import KEY, OTHER_KEY, make_vessel


def _manifest(vessel=None, key=KEY):
    return build_manifest(vessel or make_vessel(), key, created="2026-01-01T00:00:00Z")


def _edited():
    """+ST2, -compartment C1, thicker plate PL1."""
    v = make_vessel()
    v.stiffeners["ST2"] = dataclasses.replace(v.stiffeners["ST1"], id="ST2", name="L2")
    del v.compartments["C1"]
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    return v


def test_identical_manifests_are_clean():
    a = _manifest()
    report = diff_manifests(a, _manifest())
    assert report.clean
    assert (report.added, report.removed, report.changed) == ([], [], {})
    assert report.unchanged_count == 6
    assert report.root_a == report.root_b == a.root


def test_added_removed_changed_classification():
    a, b = _manifest(), _manifest(_edited())
    report = diff_manifests(a, b)
    assert not report.clean
    assert report.added == ["ST2"]
    assert report.removed == ["G-COMP-1"]
    assert report.changed == {"G-PL-1": ["scantlings"]}
    assert report.unchanged_count == 4
    assert (report.root_a, report.root_b) == (a.root, b.root)


def test_report_to_dict_and_text():
    a, b = _manifest(), _manifest(_edited())
    report = diff_manifests(a, b)
    assert report.to_dict() == {
        "clean": False,
        "root_a": a.root,
        "root_b": b.root,
        "added": ["ST2"],
        "removed": ["G-COMP-1"],
        "changed": {"G-PL-1": ["scantlings"]},
        "unchanged_count": 4,
    }
    assert format_report(report) == "\n".join(
        [
            f"root A: {a.root}",
            f"root B: {b.root}",
            "added (1): ST2",
            "removed (1): G-COMP-1",
            "changed (1):",
            "  G-PL-1: scantlings",
            "unchanged: 4",
        ]
    )
    clean = diff_manifests(a, a)
    assert format_report(clean).splitlines()[-1] == "match: 6 parts unchanged"


def test_profile_mismatch_refused():
    a, b = _manifest(), _manifest()
    b.profile = "ocx-hash/2"
    with pytest.raises(ProfileMismatchError):
        diff_manifests(a, b)


def test_different_keys_report_everything_changed():
    report = diff_manifests(_manifest(), _manifest(key=OTHER_KEY))
    assert sorted(report.changed) == sorted(_manifest().parts)
    assert report.unchanged_count == 0


def test_verify_model_clean_and_changed():
    m = _manifest()
    assert verify_model(make_vessel(), m, KEY).clean
    report = verify_model(_edited(), m, KEY)
    assert report.changed == {"G-PL-1": ["scantlings"]}
    assert report.root_a == m.root
