"""Tests for the shared XmlIndex document scan."""
from __future__ import annotations

from ocx_rules.xml_index import XmlIndex, localname, normalize_guid

from tests.rules_xml import OCX_NS, context_for


def _index(body: str) -> XmlIndex:
    return context_for(body).xml_index


class TestHelpers:
    def test_localname_strips_namespace(self):
        assert localname(f"{{{OCX_NS}}}Panel") == "Panel"
        assert localname("Panel") == "Panel"
        assert localname(None) == ""

    def test_normalize_guid(self):
        assert normalize_guid("{ABC-123}") == "abc-123"
        assert normalize_guid(" abc-123 ") == "abc-123"


class TestXmlIndex:
    def test_nsmap_detected_from_root(self):
        idx = _index("")
        assert idx.nsmap["ocx"] == OCX_NS
        assert idx.nsmap["xsi"].endswith("XMLSchema-instance")

    def test_identity_elements_indexed(self):
        idx = _index('<ocx:Panel id="p1" ocx:GUIDRef="{AAA}" name="Deck"/>')
        assert idx.by_id["p1"].tag == "Panel"
        assert idx.by_guid["aaa"].name == "Deck"
        assert idx.by_id["p1"].sourceline is not None

    def test_duplicates_collected(self):
        idx = _index(
            '<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>'
            '<ocx:Plate id="p1" ocx:GUIDRef="{AAA}"/>'
        )
        assert [e.tag for e in idx.duplicate_ids["p1"]] == ["Plate"]
        assert [e.tag for e in idx.duplicate_guids["aaa"]] == ["Plate"]

    def test_ref_elements_are_refs_not_identities(self):
        idx = _index('<ocx:GridRef localRef="BP" ocx:GUIDRef="{BBB}" ocx:refType="ocx:ReferencePlane"/>')
        assert "bbb" not in idx.by_guid
        (ref,) = idx.refs
        assert (ref.tag, ref.local_ref, ref.guid, ref.ref_type) == (
            "GridRef", "BP", "bbb", "ocx:ReferencePlane")

    def test_xpath_uses_nsmap(self):
        idx = _index('<ocx:Panel id="p1"/>')
        assert len(idx.xpath("//ocx:Panel")) == 1

    def test_context_caches_index(self):
        ctx = context_for('<ocx:Panel id="p1"/>')
        assert ctx.xml_index is ctx.xml_index
