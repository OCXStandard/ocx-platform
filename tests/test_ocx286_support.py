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
    <ocx:Panel id="panel2" ocx:GUIDRef="{00000000-0000-0000-0000-00000000000A}" name="P2">
      <ocx:UnboundedGeometry>
        <ocx:SurfaceRef ocx:GUIDRef="{00000000-0000-0000-0000-00000000000B}" ocx:refType="ocx:Surface"/>
      </ocx:UnboundedGeometry>
    </ocx:Panel>
    <ocx:Plate id="plate1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000004}" name="PL1">
      <ocx:PlateMaterial localRef="mat1">
        <ocx:Thickness numericvalue="10.0" unit="Umm"/>
      </ocx:PlateMaterial>
      <ocx:Offset numericvalue="5.0" unit="Umm"/>
    </ocx:Plate>
    <ocx:Stiffener id="stf1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000005}" name="ST1">
      <ocx:SectionRef localRef="sec1" ocx:GUIDRef="{00000000-0000-0000-0000-000000000006}" ocx:refType="ocx:BarSection"/>
      <ocx:TraceLine>
        <ocx:Line3D id="tl1">
          <ocx:StartPoint>
            <ocx:X numericvalue="1000" unit="Umm"/><ocx:Y numericvalue="200" unit="Umm"/><ocx:Z numericvalue="0" unit="Umm"/>
          </ocx:StartPoint>
          <ocx:EndPoint>
            <ocx:X numericvalue="1000" unit="Umm"/><ocx:Y numericvalue="200" unit="Umm"/><ocx:Z numericvalue="1100" unit="Umm"/>
          </ocx:EndPoint>
        </ocx:Line3D>
      </ocx:TraceLine>
      <ocx:Inclination>
        <ocx:WebDirection x="-1" y="0" z="0"/>
        <ocx:FlangeDirection x="0" y="1" z="0"/>
        <ocx:Position>
          <ocx:X numericvalue="1000" unit="Umm"/><ocx:Y numericvalue="200" unit="Umm"/><ocx:Z numericvalue="200" unit="Umm"/>
        </ocx:Position>
      </ocx:Inclination>
    </ocx:Stiffener>
    <ocx:ReferenceSurfaces>
      <ocx:SurfaceCollection id="hull" name="HULL" ocx:GUIDRef="{00000000-0000-0000-0000-00000000000B}">
        <ocx:Plane3D id="hullplane">
          <ocx:Origin>
            <ocx:X numericvalue="0" unit="Umm"/><ocx:Y numericvalue="0" unit="Umm"/><ocx:Z numericvalue="0" unit="Umm"/>
          </ocx:Origin>
          <ocx:Normal x="0" y="0" z="1"/>
        </ocx:Plane3D>
      </ocx:SurfaceCollection>
    </ocx:ReferenceSurfaces>
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


class TestVersionDetection286:
    def test_get_version_schema_version_as_last_attribute(self, tmp_path: Path):
        """schemaVersion directly before '>' must not pick up the quote/bracket."""
        from ocx_model_core.parsers.parser import OcxVersion

        model = tmp_path / "last_attr.3docx"
        model.write_text(
            '<ocx:ocxXML xmlns:ocx="http://data.dnvgl.com/Schemas/ocxXMLSchema" '
            'schemaVersion="2.8.6"></ocx:ocxXML>',
            encoding="utf-8",
        )
        assert OcxVersion.get_version(model) == "2.8.6"

    def test_detect_schema_version_286_document(self):
        from ocx_model_core.parsers.version import detect_schema_version

        assert detect_schema_version(OCX286_MODEL) == "2.8.6"


@pytest.fixture()
def model_286(tmp_path: Path) -> Path:
    target = tmp_path / "model286.3docx"
    target.write_text(OCX286_MODEL, encoding="utf-8")
    return target


class Test286EndToEnd:
    def test_parse_resolves_286_bindings(self, model_286: Path):
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        assert type(root).__module__ == "ocx.ocx_286.ocx_286"
        assert root.schema_version == "2.8.6"

    def test_build_full_ir(self, model_286: Path):
        from ocx_model_core.builders.factory import get_builder
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        ir = get_builder(root.schema_version).build(root)

        assert ir.schema_version == "2.8.6"
        assert ir.name == "TestVessel"
        # Vessel-level structural parts
        assert set(ir.panels) == {"panel1", "panel2"}
        assert set(ir.plates) == {"plate1"}
        assert set(ir.stiffeners) == {"stf1"}
        # Plate material + thickness resolved through normalised PlateMaterial
        plate = ir.plates["plate1"]
        assert plate.thickness is not None
        assert plate.thickness.value == 10.0
        assert plate.thickness.unit == "Umm"
        assert plate.material_ref is not None
        assert plate.material_ref.local_ref == "mat1"
        assert (plate.offset.value, plate.offset.unit) == (5.0, "Umm")
        # Catalogues (root-level ClassCatalogue list, nested catalogue lists)
        assert "mat1" in ir.materials
        assert ir.materials["mat1"].density is not None
        assert ir.materials["mat1"].density.value == 7850.0
        assert "sec1" in ir.sections
        assert ir.sections["sec1"].section_type == "FlatBar"
        assert ir.sections["sec1"].height.value == 100.0
        # FrameTables flattened onto the coordinate system
        assert "cs1" in ir.coordinate_systems
        assert ir.coordinate_systems["cs1"].x_ref_plane_ids == ["fr0"]
        assert "fr0" in ir.ref_planes
        # Stiffener section ref resolves - no dangling references
        assert ir.stiffeners["stf1"].section_ref.local_ref == "sec1"
        assert ir.dangling_refs == []

    def test_points_and_vectors_carry_286_coordinates(self, model_286: Path):
        """2.8.6 X/Y/Z children and x/y/z attributes are not dropped to (0,0,0)."""
        from ocx_model_core.builders.factory import get_builder
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        stf = get_builder(root.schema_version).build(root).stiffeners["stf1"]

        assert (stf.trace.start.x, stf.trace.start.y, stf.trace.start.z) == (1000.0, 200.0, 0.0)
        assert stf.trace.end.z == 1100.0
        assert stf.trace.start.unit == "Umm"
        inc = stf.inclinations[0]
        assert (inc.web_direction.x, inc.web_direction.y, inc.web_direction.z) == (-1.0, 0.0, 0.0)
        assert inc.flange_direction.y == 1.0
        assert inc.position.z == 200.0

    def test_guid_only_surface_ref_resolves_to_collection_id(self, model_286: Path):
        from ocx_model_core.builders.factory import get_builder
        from ocx_model_core.parsers.parser import OcxParser

        root = OcxParser().parse(str(model_286))
        ir = get_builder(root.schema_version).build(root)

        assert ir.panels["panel2"].unbounded_geometry.surface_ref == "hull"
        assert ir.surface_collections["hull"].surfaces[0].geometry.normal.z == 1.0


class Test286SchemaValidation:
    def test_validate_schema_routes_to_286(self, model_286: Path):
        """The 2.8.6 XSD is selected and produces a structured result.

        The minimal model is intentionally not fully schema-valid (a valid
        2.8.6 Vessel requires ClassificationData, Arrangement, etc.), so this
        asserts the plumbing: version routing, error structure, line numbers.
        """
        from ocx_model_core.validation.schema import validate_schema

        result = validate_schema(model_286)
        assert result.schema_version == "2.8.6"
        assert result.valid is False
        assert result.error_count == len(result.errors) > 0
        assert all(e.line > 0 for e in result.errors)
