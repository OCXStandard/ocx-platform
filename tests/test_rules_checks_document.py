"""Tests for document/root/units best-practice checks (OCX-DOC-001..005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    enumerated_root_units,
    root_declarations,
    schema_location_tuple,
    unit_definitions,
    unit_refs_resolve,
)

from tests.rules_xml import OCX_NS, context_for, context_for_xml

UNITS = """
<unitsml:UnitsML><unitsml:UnitSet>
  <unitsml:Unit xml:id="u2">
    <unitsml:UnitName>millimetre</unitsml:UnitName>
    <unitsml:UnitSymbol type="mm"/>
    <unitsml:RootUnits>
      <unitsml:EnumeratedRootUnit unit="meter" prefix="m" powerNumerator="1"/>
    </unitsml:RootUnits>
  </unitsml:Unit>
</unitsml:UnitSet></unitsml:UnitsML>
"""


class TestSchemaLocationTuple:
    def test_identical_tuple_passes(self):
        assert schema_location_tuple(context_for(""), {}) == []

    def test_missing_attribute_fails(self):
        ctx = context_for("", root_attrs='schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "schemaLocation" in finding.message

    def test_namespace_absent_fails(self):
        ctx = context_for(
            "", root_attrs='xsi:schemaLocation="urn:other loc.xsd" schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "namespace" in finding.message.lower()

    def test_mismatched_pair_fails(self):
        ctx = context_for(
            "", root_attrs=f'xsi:schemaLocation="{OCX_NS} other.xsd" schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "identical" in finding.message


class TestRootDeclarations:
    def test_pass(self):
        assert root_declarations(context_for(""), {}) == []

    def test_missing_schema_version(self):
        ctx = context_for("", root_attrs=f'xsi:schemaLocation="{OCX_NS} {OCX_NS}"')
        (finding,) = root_declarations(ctx, {})
        assert "schemaVersion" in finding.message

    def test_missing_xsi_declaration(self):
        xml = f'<ocx:ocxXML xmlns:ocx="{OCX_NS}" schemaVersion="3.1.0"/>'
        (finding,) = root_declarations(context_for_xml(xml), {})
        assert "xsi" in finding.message


class TestUnitDefinitions:
    def test_complete_unit_passes(self):
        assert unit_definitions(context_for(UNITS), {}) == []

    def test_missing_id_name_and_symbol(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                "<unitsml:Unit/></unitsml:UnitSet></unitsml:UnitsML>")
        messages = [f.message for f in unit_definitions(context_for(body), {})]
        assert any("xml:id" in m for m in messages)
        assert any("UnitName" in m for m in messages)
        assert any("UnitSymbol" in m for m in messages)

    def test_duplicate_unit_id(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>m</unitsml:UnitName>'
                "<unitsml:UnitSymbol/></unitsml:Unit>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>m</unitsml:UnitName>'
                "<unitsml:UnitSymbol/></unitsml:Unit>"
                "</unitsml:UnitSet></unitsml:UnitsML>")
        assert any("duplicate" in f.message for f in unit_definitions(context_for(body), {}))

    def test_no_unitsml_is_vacuous_pass(self):
        assert unit_definitions(context_for(""), {}) == []


class TestUnitRefsResolve:
    def test_resolving_ref_passes(self):
        body = UNITS + '<ocx:Thickness numericvalue="10" unit="u2"/>'
        assert unit_refs_resolve(context_for(body), {}) == []

    def test_dangling_unit_ref_fails(self):
        body = UNITS + '<ocx:Thickness numericvalue="10" unit="u9"/>'
        (finding,) = unit_refs_resolve(context_for(body), {})
        assert "u9" in finding.message


class TestEnumeratedRootUnits:
    def test_enumerated_unit_passes(self):
        assert enumerated_root_units(context_for(UNITS), {}) == []

    def test_common_symbol_without_enumeration_warns(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>millimetre</unitsml:UnitName>'
                '<unitsml:UnitSymbol type="mm"/></unitsml:Unit>'
                "</unitsml:UnitSet></unitsml:UnitsML>")
        (finding,) = enumerated_root_units(context_for(body), {})
        assert "EnumeratedRootUnit" in finding.message
