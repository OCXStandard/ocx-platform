"""Catalogue-integrity tests for the built-in best_practice rule pack."""
from __future__ import annotations

from ocx_rules.catalogue import resolve_custom
from ocx_rules.model import Severity
from ocx_rules.packs.best_practice import load_pack

EXPECTED_CATEGORIES = {
    "identity": 5,
    "document": 5,
    "references": 8,
    "curves_surfaces": 5,
    "topology": 9,
    "properties": 4,
}


class TestBestPracticePack:
    def test_loads_36_rules(self):
        pack = load_pack()
        assert pack.name == "best_practice"
        assert len(pack.rules) == 36

    def test_category_counts(self):
        pack = load_pack()
        counts: dict[str, int] = {}
        for spec in pack.rules:
            counts[spec.category] = counts.get(spec.category, 0) + 1
        assert counts == EXPECTED_CATEGORIES

    def test_ids_unique_and_well_formed(self):
        pack = load_pack()
        ids = [s.rule_id for s in pack.rules]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("OCX-") for i in ids)

    def test_every_rule_has_source_and_description(self):
        for spec in load_pack().rules:
            assert spec.source, spec.rule_id
            assert spec.description, spec.rule_id

    def test_severities_valid(self):
        for spec in load_pack().rules:
            assert isinstance(spec.severity, Severity)

    def test_custom_checks_importable(self):
        for spec in load_pack().rules:
            if spec.check.custom is not None:
                assert callable(resolve_custom(spec.check.custom)), spec.rule_id

    def test_geometry_rules_declare_geometry_requirement(self):
        for spec in load_pack().rules:
            if spec.category in ("topology", "properties"):
                assert "geometry" in spec.requires or "ir" in spec.requires, spec.rule_id
