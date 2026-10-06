"""Tests for the OCX 3.3.0 bracket schema enhancements (vendored XSD)."""
from __future__ import annotations

import re
from pathlib import Path

from ocx_model_validator.validation.schema import validate_schema

DATA = Path(__file__).parent / "data"
STUB_320 = DATA / "ocx_320_stubs" / "ocxxml.3docx"
NS_320 = "https://3docx.org/fileadmin//ocx_schema//V320//OCX_Schema.xsd"
NS_330 = "https://3docx.org/fileadmin//ocx_schema//V330//OCX_Schema.xsd"
GUID = "12345678-1234-1234-1234-123456789012"


# ---------------------------------------------------------------- fixtures
_GRIDREF_RE = re.compile(r"<ocx:GridRef\b.*?</ocx:GridRef>", re.DOTALL)

_MASS = """
<ocx:MassProperties>
  <ocx:MouldedDryWeight numericvalue="4.0" unit="UKg"/>
  <ocx:MouldedCenterOfGravity coordinates="0.75 4.97 1.61" unit="Um"/>
  <ocx:PhysicalDryWeight numericvalue="4.0" unit="UKg"/>
  <ocx:PhysicalCenterOfGravity coordinates="0.75 4.97 1.61" unit="Um"/>
</ocx:MassProperties>"""

# localRef must resolve: nplcid21 is a Steel material in the 3.2.0 full stub.
_MATERIAL = """
<ocx:PlateMaterial localRef="nplcid21" ocx:GUIDRef="{guid}" ocx:refType="ocx:Material">
  <ocx:Thickness numericvalue="0.01" unit="Um"/>
</ocx:PlateMaterial>""".format(guid=GUID)


def _contour(pid: str) -> str:
    """A closed triangular-ish outer contour (copied from the 3.2.0 bracket stub)."""
    return f"""
<ocx:OuterContour>
  <ocx:CompositeCurve3D id="{pid}_oc" is2D="false">
    <ocx:CurveLength numericvalue="1.0260326" unit="Um"/>
    <ocx:Line3D id="{pid}_l1" is2D="false">
      <ocx:CurveLength numericvalue="0.27" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.053445 1.4999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 4.783445 1.4999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l2" is2D="false">
      <ocx:CurveLength numericvalue="0.025" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 4.783445 1.4999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 4.783445 1.5249375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l3" is2D="false">
      <ocx:CurveLength numericvalue="0.3889087" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 4.783445 1.5249375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.058445 1.7999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l4" is2D="false">
      <ocx:CurveLength numericvalue="0.025" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.058445 1.7999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.083445 1.7999375" unit="Um"/>
    </ocx:Line3D>
    <ocx:Line3D id="{pid}_l5" is2D="false">
      <ocx:CurveLength numericvalue="0.27" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.083445 1.7999375" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.083445 1.5299375" unit="Um"/>
    </ocx:Line3D>
    <ocx:CircumArc3D id="{pid}_a6" is2D="false">
      <ocx:CurveLength numericvalue="0.0471239" unit="Um"/>
      <ocx:StartPoint coordinates="0.750005 5.083445 1.5299375" unit="Um"/>
      <ocx:IntermediatePoint coordinates="0.750005 5.0622318 1.5211507" unit="Um"/>
      <ocx:EndPoint coordinates="0.750005 5.053445 1.4999375" unit="Um"/>
    </ocx:CircumArc3D>
  </ocx:CompositeCurve3D>
</ocx:OuterContour>"""


def _params(extra_elements: str = "", extra_attrs: str = "") -> str:
    return f"""
<ocx:BracketParameters ocx:hasEdgeReinforcement="false" numberOfSupports="2"{extra_attrs}>
  <ocx:ArmLengthU numericvalue="0.3" unit="Um"/>
  <ocx:ArmLengthV numericvalue="0.3" unit="Um"/>
  <ocx:UDirection direction="0.0 -1.0 0.0"/>
  <ocx:VDirection direction="0.0 0.0 1.0"/>
  <ocx:Origin coordinates="0.750005 5.083445 1.499938" unit="Um"/>
  {extra_elements}
</ocx:BracketParameters>"""


def _bracket(pid: str, params: str, topology: str = "") -> str:
    """An inline (mode 1) Bracket; topology goes after OuterContour."""
    return (
        f'<ocx:Bracket id="{pid}" name="Bkt {pid}" ocx:GUIDRef="{GUID}">'
        f"{_MASS}{params}{_MATERIAL}{_contour(pid)}{topology}</ocx:Bracket>"
    )


def _as_330(text: str) -> str:
    return text.replace(NS_320, NS_330).replace(
        'schemaVersion="3.2.0"', 'schemaVersion="3.3.0"'
    )


def _stub_330() -> str:
    return _as_330(STUB_320.read_text(encoding="utf-8"))


def _first_gridref(text: str) -> str:
    """A complete, valid GridRef block (BoundedRef needs ContourBounds etc.)."""
    match = _GRIDREF_RE.search(text)
    assert match, "no GridRef in stub model"
    return match.group(0)


def _write_model(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "model.3docx"
    target.write_text(text, encoding="utf-8")
    return target


def _inject_bracket(text: str, bracket_xml: str) -> str:
    assert "</ocx:Vessel>" in text
    return text.replace("</ocx:Vessel>", bracket_xml + "</ocx:Vessel>", 1)


def _assert_valid(result) -> None:
    messages = "; ".join(e.message for e in result.errors[:5])
    assert result.valid, f"expected valid, got {result.error_count} error(s): {messages}"


class TestRegistry:
    def test_330_schema_compiles(self):
        from ocx_model_validator.validation.schema import SUPPORTED_VERSIONS, load_schema

        assert SUPPORTED_VERSIONS["3.3.0"] == "ocx_330"
        assert load_schema("3.3.0") is not None


class TestBackwardCompatibility:
    def test_relabelled_320_model_is_valid_330(self, tmp_path):
        """Spec criterion 4: a valid 3.2.0 document relabelled 3.3.0 still validates."""
        model = _write_model(tmp_path, _stub_330())
        result = validate_schema(model)
        assert result.schema_version == "3.3.0"
        _assert_valid(result)

    def test_legacy_bracket_with_limitedby_is_valid(self, tmp_path):
        """Deprecated LimitedBy topology remains schema-valid in 3.3.0."""
        text = _stub_330()
        topology = f"<ocx:LimitedBy>{_first_gridref(text)}</ocx:LimitedBy>"
        bracket = _bracket("bkt330leg", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        _assert_valid(validate_schema(model))


class TestOrderedSupports:
    def test_ordered_supports_with_lap_are_valid(self, tmp_path):
        text = _stub_330()
        grid = _first_gridref(text)
        topology = (
            f'<ocx:Support1Limit lapped="true">{grid}'
            f'<ocx:Lap numericvalue="0.05" unit="Um"/></ocx:Support1Limit>'
            f"<ocx:Support2Limit>{grid}</ocx:Support2Limit>"
            f"<ocx:Support3Limit>{grid}</ocx:Support3Limit>"
        )
        bracket = _bracket("bkt330sup", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        _assert_valid(validate_schema(model))

    def test_support2_without_support1_is_invalid(self, tmp_path):
        text = _stub_330()
        topology = f"<ocx:Support2Limit>{_first_gridref(text)}</ocx:Support2Limit>"
        bracket = _bracket("bkt330bad", _params(), topology)
        model = _write_model(tmp_path, _inject_bracket(text, bracket))
        result = validate_schema(model)
        assert result.valid is False


class TestBracketParameters330:
    def test_shape_and_multiple_copes_are_valid(self, tmp_path):
        copes = (
            '<ocx:FeatureCope><ocx:CopeRadius numericvalue="0.03" unit="Um"/></ocx:FeatureCope>'
            '<ocx:FeatureCope><ocx:CopeRadius numericvalue="0.05" unit="Um"/></ocx:FeatureCope>'
        )
        params = _params(extra_elements=copes, extra_attrs=' bracketShape="Triangular"')
        bracket = _bracket("bkt330shape", params)
        model = _write_model(tmp_path, _inject_bracket(_stub_330(), bracket))
        _assert_valid(validate_schema(model))

    def test_non_enum_bracket_shape_is_invalid(self, tmp_path):
        params = _params(extra_attrs=' bracketShape="Circular"')
        bracket = _bracket("bkt330badshape", params)
        model = _write_model(tmp_path, _inject_bracket(_stub_330(), bracket))
        result = validate_schema(model)
        assert result.valid is False


class TestFlangeEdgeReinforcement330:
    def test_snipe_angle_and_direction_are_valid(self, tmp_path):
        flange = (
            '<ocx:FlangeEdgeReinforcement flangeDirection="AgainstNormal">'
            '<ocx:FlangeWidth numericvalue="0.075" unit="Um"/>'
            '<ocx:Radius numericvalue="0.025" unit="Um"/>'
            '<ocx:FlangeSnipeAngle numericvalue="0.5236" unit="URad"/>'
            "</ocx:FlangeEdgeReinforcement>"
        )
        params = _params(extra_elements=flange).replace(
            'ocx:hasEdgeReinforcement="false"', 'ocx:hasEdgeReinforcement="true"'
        )
        bracket = _bracket("bkt330flg", params)
        model = _write_model(tmp_path, _inject_bracket(_stub_330(), bracket))
        _assert_valid(validate_schema(model))


def _catalogue_xml() -> str:
    return (
        '<ocx:BracketCatalogue id="bktcat330" name="Bracket catalogue">'
        '<ocx:CatalogueBracket id="cbkt1" name="Plate-Plate 300"'
        ' connectionKind="PlatePlate" customerCatalogRefName="VENDOR-BKT-42">'
        + _params()
        + _contour("cbkt1g")
        + "</ocx:CatalogueBracket></ocx:BracketCatalogue>"
    )


def _occurrence_bracket(pid: str) -> str:
    transformation = (
        "<ocx:Transformation>"
        '<ocx:Origin coordinates="0.75 5.08 1.5" unit="Um"/>'
        '<ocx:PrimaryAxis direction="0.0 -1.0 0.0"/>'
        '<ocx:SecondaryAxis direction="0.0 0.0 1.0"/>'
        "</ocx:Transformation>"
    )
    ref = (
        f'<ocx:CatalogueBracketRef localRef="cbkt1" ocx:GUIDRef="{GUID}"'
        ' ocx:refType="ocx:CatalogueBracket"/>'
    )
    return (
        f'<ocx:Bracket id="{pid}" name="BktOcc" ocx:GUIDRef="{GUID}">'
        f"{_MASS}{ref}{transformation}{_MATERIAL}</ocx:Bracket>"
    )


class TestBracketCatalogue:
    def test_catalogue_and_occurrence_are_valid(self, tmp_path):
        text = _stub_330()
        assert "</ocx:ClassCatalogue>" in text
        text = text.replace(
            "</ocx:ClassCatalogue>", _catalogue_xml() + "</ocx:ClassCatalogue>", 1
        )
        text = _inject_bracket(text, _occurrence_bracket("bkt330occ"))
        model = _write_model(tmp_path, text)
        _assert_valid(validate_schema(model))

    def test_occurrence_without_transformation_is_invalid(self, tmp_path):
        """Deviation from plan: lxml/libxml2 does not enforce xs:IDREF
        resolution during XSD validation, so an orphan localRef cannot be
        detected by schema validation. Instead verify the occurrence content
        model: Transformation is mandatory in catalogue-occurrence mode."""
        bracket = re.sub(
            r"<ocx:Transformation>.*?</ocx:Transformation>",
            "",
            _occurrence_bracket("bkt330bad2"),
            flags=re.DOTALL,
        )
        text = _inject_bracket(_stub_330(), bracket)
        model = _write_model(tmp_path, text)
        result = validate_schema(model)
        assert result.valid is False
