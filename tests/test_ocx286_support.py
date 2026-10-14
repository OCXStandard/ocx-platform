"""Tests for OCX 2.8.6 schema support (validation, parsing, IR building)."""
from __future__ import annotations

from pathlib import Path

import pytest

OCX286_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<ocx:ocxXML xmlns:ocx="http://data.dnvgl.com/Schemas/ocxXMLSchema" ocx:license="x" schemaVersion="2.8.6">
  <ocx:Header time_stamp="2020-01-01T00:00:00" name="test" author="t" organization="t" originating_system="t"/>
  <ocx:Vessel id="vessel1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000001}" name="TestVessel">
    <ocx:CoordinateSystem id="cs1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000009}">
      <ocx:FrameTables>
        <ocx:XRefPlanes>
          <ocx:RefPlane id="fr0" name="FR0">
            <ocx:ReferenceLocation numericvalue="0.0" unit="Um"/>
          </ocx:RefPlane>
        </ocx:XRefPlanes>
      </ocx:FrameTables>
    </ocx:CoordinateSystem>
    <ocx:Panel id="panel1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000002}" name="P1"/>
    <ocx:Plate id="plate1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000004}" name="PL1">
      <ocx:PlateMaterial localRef="mat1">
        <ocx:Thickness numericvalue="10.0" unit="Umm"/>
      </ocx:PlateMaterial>
    </ocx:Plate>
    <ocx:Stiffener id="stf1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000005}" name="ST1">
      <ocx:SectionRef localRef="sec1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000006}" ocx:refType="ocx:BarSection"/>
    </ocx:Stiffener>
  </ocx:Vessel>
  <ocx:ClassCatalogue id="cat1">
    <ocx:MaterialCatalogue id="matcat1">
      <ocx:Material id="mat1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000007}" name="A36">
        <ocx:Density numericvalue="7850" unit="Ukgperm3"/>
        <ocx:YieldStress numericvalue="235" unit="UNpermm2"/>
      </ocx:Material>
    </ocx:MaterialCatalogue>
    <ocx:XSectionCatalogue id="xsec1">
      <ocx:BarSection id="sec1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000008}" name="FB100x10">
        <ocx:FlatBar>
          <ocx:Height numericvalue="100" unit="Umm"/>
          <ocx:Width numericvalue="10" unit="Umm"/>
        </ocx:FlatBar>
      </ocx:BarSection>
    </ocx:XSectionCatalogue>
  </ocx:ClassCatalogue>
</ocx:ocxXML>"""


class Test286SchemaRegistry:
    def test_286_registered_and_compiles(self):
        from ocx_model_core.validation.schema import SUPPORTED_VERSIONS, load_schema

        assert SUPPORTED_VERSIONS["2.8.6"] == "ocx_286"
        assert load_schema("2.8.6") is not None
