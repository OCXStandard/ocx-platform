"""Canonicalisation tests: quantizer, geometry, records, invariance (ocx-hash/1)."""

from __future__ import annotations

import decimal
from decimal import Decimal

from ocx_integrity.canon_geom import _reverse_seg, curve_record
from ocx_integrity.jsonutil import prune, sort_jcs, type_name
from ocx_integrity.manifest import hash_vessel
from ocx_integrity.quantize import Quantizer, fmt_decimal
from ocx_integrity.records import iter_parts
from ocx_integrity.records.common import (
    Context,
    hole_placement,
    identity,
    make_record,
    material_aspect,
    part_id,
    section_value,
)
from ocx_model_core.model.ir import (
    IrCog,
    IrCompositeCurve3D,
    IrCurve3D,
    IrLimitedByRef,
    IrLine3D,
    IrMassProperties,
    IrPlane3D,
    IrPoint3D,
    IrPolyLine3D,
    IrSurface,
    IrSurfaceCollection,
    IrUnboundedGeometry,
    IrVector3D,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)

from tests.integrity_fixtures import KEY, hole, make_vessel, registry, square


def _quantizer() -> tuple[Quantizer, list[str]]:
    warnings: list[str] = []
    return Quantizer(registry(), warnings.append), warnings


def test_fmt_decimal_rounds_half_even():
    assert fmt_decimal(Decimal("0.0000005"), 6) == "0.000000"
    assert fmt_decimal(Decimal("0.0000015"), 6) == "0.000002"


def test_fmt_decimal_normalises_negative_zero():
    assert fmt_decimal(-0.0000001, 6) == "0.000000"
    assert fmt_decimal(-0.0, 0) == "0"


def test_fmt_decimal_non_finite():
    assert fmt_decimal(float("nan"), 6) == "NaN"
    assert fmt_decimal(float("inf"), 6) == "Infinity"
    assert fmt_decimal(float("-inf"), 6) == "-Infinity"


def test_fmt_decimal_large_finite_values():
    assert fmt_decimal(1e22, 6) == "10000000000000000000000.000000"
    assert fmt_decimal(1e19, 9) == "10000000000000000000.000000000"
    assert fmt_decimal(1e300, 6) == "1" + "0" * 300 + ".000000"


def test_quantize_independent_of_global_decimal_context():
    q, _ = _quantizer()
    expected = (fmt_decimal(Decimal("123.4567885"), 6), q.quantity(Quantity(1234.5, "Ucm4")))
    with decimal.localcontext() as ctx:
        ctx.prec = 5
        ctx.rounding = decimal.ROUND_DOWN
        actual = (fmt_decimal(Decimal("123.4567885"), 6), q.quantity(Quantity(1234.5, "Ucm4")))
    assert actual == expected == ("123.456788", "0.000012345")


def test_quantity_mm_and_m_are_identical():
    q, _ = _quantizer()
    assert q.quantity(Quantity(12.5, "Umm")) == q.quantity(Quantity(0.0125, "Um")) == "0.012500"


def test_quantity_precision_per_si_symbol():
    q, _ = _quantizer()
    assert q.quantity(Quantity(355.0, "UNOvermm2")) == "355000000"
    assert q.quantity(Quantity(1.8, "Ut")) == "1800.000"
    assert q.quantity(Quantity(1234.5, "Ucm4")) == "0.000012345"
    assert q.quantity(Quantity(0.3, "UDimless")) == "0.300000"


def test_unknown_unit_kept_raw_with_warning():
    q, warnings = _quantizer()
    assert q.quantity(Quantity(1.5, "Ufoo")) == {"value": "1.500000", "unit": "Ufoo"}
    assert q.point(IrPoint3D(1.0, 2.0, 3.0, "Ufoo")) == ["1.000000", "2.000000", "3.000000", "Ufoo"]
    assert warnings == ["unknown unit 'Ufoo'", "unknown unit 'Ufoo'"]


def test_point_and_vector():
    q, _ = _quantizer()
    assert q.point(IrPoint3D(1000.0, 0.0, -0.0000001, "Umm")) == [
        "1.000000",
        "0.000000",
        "0.000000",
    ]
    assert q.vector(IrVector3D(0.0, 0.0, 1.0)) == ["0.000000", "0.000000", "1.000000"]


def _geom_canon():
    q, _ = _quantizer()

    def canon(v):
        if isinstance(v, IrPoint3D):
            return q.point(v)
        if isinstance(v, IrVector3D):
            return q.vector(v)
        if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
            return v
        if isinstance(v, float):
            return q.scalar(v)
        if isinstance(v, Quantity):
            return q.quantity(v)
        if isinstance(v, IrCurve3D):
            return curve_record(v, canon)
        if isinstance(v, list):
            return [canon(x) for x in v]
        raise TypeError(type(v))

    return canon


def _square_composite(reverse: bool = False, start: int = 0) -> IrCompositeCurve3D:
    c = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
    if reverse:
        c = c[::-1]
    c = c[start:] + c[:start]
    segs = [
        IrLine3D(
            curve_length=None,
            start=IrPoint3D(*c[i], 0.0, "Umm"),
            end=IrPoint3D(*c[(i + 1) % 4], 0.0, "Umm"),
        )
        for i in range(4)
    ]
    return IrCompositeCurve3D(curve_length=None, segments=segs)


def test_prune_drops_empty_values_recursively():
    assert prune(
        {
            "a": None,
            "b": "",
            "c": [],
            "d": {},
            "e": False,
            "f": {"g": None},
            "h": 0,
            "i": True,
            "j": ["x", None],
        }
    ) == {"h": 0, "i": True, "j": ["x", None]}


def test_type_name_strips_ir_prefix():
    assert type_name(IrPolyLine3D(curve_length=None)) == "polyline3d"


def test_sort_jcs_is_deterministic():
    assert sort_jcs([{"b": "2"}, {"a": "1"}]) == [{"a": "1"}, {"b": "2"}]


def test_closed_polyline_canonical_form():
    canon = _geom_canon()
    rec = curve_record(square(), canon)
    assert rec == {
        "type": "polyline3d",
        "is_closed": True,
        "vertices": [
            ["0.000000", "0.000000", "0.000000"],
            ["2.000000", "0.000000", "0.000000"],
            ["2.000000", "2.000000", "0.000000"],
            ["0.000000", "2.000000", "0.000000"],
        ],
    }


def test_closed_polyline_invariant_to_start_orientation_units_and_closure():
    canon = _geom_canon()
    base = curve_record(square(), canon)
    assert curve_record(square(start=2), canon) == base
    assert curve_record(square(reverse=True, start=1), canon) == base
    assert curve_record(square(repeat_first=True), canon) == base
    assert curve_record(square(unit="Um", size=2.0), canon) == base
    assert curve_record(square(size=2000.0000001), canon) == base  # sub-µm noise


def test_open_polyline_keeps_order():
    canon = _geom_canon()
    pts = [IrPoint3D(0.0, 0.0, 0.0, "Umm"), IrPoint3D(1000.0, 0.0, 0.0, "Umm")]
    fwd = curve_record(IrPolyLine3D(curve_length=None, vertices=pts), canon)
    rev = curve_record(IrPolyLine3D(curve_length=None, vertices=pts[::-1]), canon)
    assert fwd != rev
    assert "is_closed" not in fwd


def test_repeated_endpoint_with_different_unknown_unit_is_kept():
    canon = _geom_canon()
    xy = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]

    def ring(last_unit: str) -> IrPolyLine3D:
        units = ["Ufoo"] * 4 + [last_unit]
        pts = [IrPoint3D(x, y, 0.0, u) for (x, y), u in zip(xy, units)]
        return IrPolyLine3D(curve_length=None, vertices=pts)

    assert curve_record(ring("Ufoo"), canon) != curve_record(ring("Ubar"), canon)
    assert curve_record(ring("Ubar"), canon)["vertices"][-1][3] == "Ubar"


def test_closed_composite_invariant_to_start_and_orientation():
    canon = _geom_canon()
    base = curve_record(_square_composite(), canon)
    assert base["segments"][0]["start"] == ["0.000000", "0.000000", "0.000000"]
    assert base["segments"][0]["end"] == ["2.000000", "0.000000", "0.000000"]
    assert curve_record(_square_composite(start=3), canon) == base
    assert curve_record(_square_composite(reverse=True, start=2), canon) == base


def test_reverse_nurbs_segment_mirrors_knots():
    seg = {
        "type": "nurbs3d",
        "control_points": [["0", "0", "0"], ["1", "1", "0"], ["2", "0", "0"]],
        "weights": ["1.000000", "2.000000", "3.000000"],
        "knot_vector": [
            "0.000000",
            "0.000000",
            "0.000000",
            "0.300000",
            "1.000000",
            "1.000000",
            "1.000000",
        ],
    }
    rev = _reverse_seg(seg)
    assert rev["control_points"] == [["2", "0", "0"], ["1", "1", "0"], ["0", "0", "0"]]
    assert rev["weights"] == ["3.000000", "2.000000", "1.000000"]
    assert rev["knot_vector"] == [
        "0.000000",
        "0.000000",
        "0.000000",
        "0.700000",
        "1.000000",
        "1.000000",
        "1.000000",
    ]


def _p(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def _ring_composite(pts: list[IrPoint3D]) -> IrCompositeCurve3D:
    n = len(pts)
    segs = [IrLine3D(curve_length=None, start=pts[i], end=pts[(i + 1) % n]) for i in range(n)]
    return IrCompositeCurve3D(curve_length=None, segments=segs)


_TIED_NORMAL = [
    _p(39.302, 39.302, 10.062),
    _p(19.234, 19.234, 27.478),
    _p(-6.785, -6.785, -10.417),
    _p(19.59, 19.59, -28.297),
]


def test_closed_polyline_with_tied_normal_components_is_orientation_invariant():
    canon = _geom_canon()
    fwd = IrPolyLine3D(curve_length=None, vertices=_TIED_NORMAL, is_closed=True)
    rev = IrPolyLine3D(curve_length=None, vertices=_TIED_NORMAL[::-1], is_closed=True)
    assert curve_record(fwd, canon) == curve_record(rev, canon)


def test_closed_composite_with_tied_normal_components_is_orientation_invariant():
    canon = _geom_canon()
    fwd = curve_record(_ring_composite(_TIED_NORMAL), canon)
    assert curve_record(_ring_composite(_TIED_NORMAL[::-1]), canon) == fwd


def test_closed_polyline_with_repeated_min_vertex_is_rotation_invariant():
    canon = _geom_canon()
    a, b, c, d, e = _p(0, 0, 0), _p(1, 0, 0), _p(1, 1, 0), _p(0, 1, 0), _p(0.5, 0.5, 0)
    ring = [a, b, c, a, e, d]
    records = set()
    for r_ring in (ring, ring[::-1]):
        for r in range(len(r_ring)):
            verts = r_ring[r:] + r_ring[:r]
            pl = IrPolyLine3D(curve_length=None, vertices=verts, is_closed=True)
            records.add(repr(curve_record(pl, canon)))
    assert len(records) == 1


def test_closed_composite_with_repeated_min_start_is_rotation_invariant():
    canon = _geom_canon()
    a, b, c, d, e = _p(0, 0, 0), _p(1, 0, 0), _p(1, 1, 0), _p(0, 1, 0), _p(0.5, 0.5, 0)
    ring = [a, b, c, a, e, d]
    records = set()
    for r_ring in (ring, ring[::-1]):
        for r in range(len(r_ring)):
            records.add(repr(curve_record(_ring_composite(r_ring[r:] + r_ring[:r]), canon)))
    assert len(records) == 1


def test_part_id_prefers_guid():
    v = make_vessel()
    assert part_id(v.plates["PL1"]) == ("G-PL-1", "guid")
    assert part_id(v.stiffeners["ST1"]) == ("ST1", "xml_id")


def test_resolve_by_xml_id_then_guid_then_unresolved():
    ctx = Context(make_vessel())
    ctx.current = "plate G-PL-1"
    assert ctx.resolve(Ref("P1")) == "G-PAN-1"
    assert ctx.resolve(Ref("nope", "G-PAN-1")) == "G-PAN-1"
    assert ctx.resolve(Ref("ST1")) == "ST1"
    assert ctx.resolve(Ref("X9")) == {"unresolved": "X9"}
    assert ctx.warnings == ["unresolved reference 'X9' on plate G-PL-1"]


def test_resolve_keeps_ref_offset():
    ctx = Context(make_vessel())
    ref = Ref("P1", offset=Quantity(10.0, "Umm"), offset_direction=IrVector3D(0.0, 0.0, 1.0))
    assert ctx.resolve(ref) == {
        "ref": "G-PAN-1",
        "offset": "0.010000",
        "offset_direction": ["0.000000", "0.000000", "1.000000"],
    }


def test_parent_resolves_panel_and_vessel():
    ctx = Context(make_vessel())
    assert ctx.parent(ParentRef(ParentKind.PANEL, "P1")) == "G-PAN-1"
    assert ctx.parent(ParentRef(ParentKind.VESSEL, "V1")) == "vessel:V1"


def test_canon_dataclass_drops_ids_and_adds_type():
    ctx = Context(make_vessel())
    rec = ctx.canon(make_vessel().plates["PL1"].mass_properties)
    assert rec == {
        "type": "massproperties",
        "moulded_dry_weight": "1500.000",
        "moulded_cog": ["1.000000", "1.000000", "0.000000"],
    }


def test_make_record_returns_none_when_empty():
    assert make_record("plate", thickness=None, name="") is None
    assert make_record("plate", thickness="0.012000") == {"kind": "plate", "thickness": "0.012000"}


def test_identity_material_section_and_hole_records():
    v = make_vessel()
    ctx = Context(v)
    plate = v.plates["PL1"]
    assert identity(
        "plate", plate, ctx, function_type=None, parent=ctx.parent(plate.parent_ref)
    ) == {"kind": "plate", "id_source": "guid", "name": "Deck plate", "parent": "G-PAN-1"}
    mat = material_aspect("plate", plate.material_ref, ctx)
    assert mat == {
        "kind": "plate",
        "material": {
            "part_id": "G-MAT-1",
            "type": "material",
            "grade": "AH36",
            "density": "7850.000",
            "yield_stress": "355000000",
            "youngs_modulus": "206000000000",
        },
    }
    assert material_aspect("plate", None, ctx) is None
    assert section_value(Ref("S1"), ctx) == {
        "part_id": "S1",
        "type": "flatbarsection",
        "name": "FB200x12",
        "section_type": "FlatBar",
        "height": "0.200000",
        "width": "0.012000",
    }
    assert hole_placement(hole(500.0, 500.0), ctx) == {
        "type": "hole2dcontour",
        "hole": {
            "part_id": "G-HOLE-1",
            "type": "hole2d",
            "parametric": {"type": "parametrichole", "variant": "circle", "diameter": "0.100000"},
        },
        "transformation": {
            "type": "transformation",
            "origin": ["0.500000", "0.500000", "0.000000"],
            "primary_axis": ["1.000000", "0.000000", "0.000000"],
            "secondary_axis": ["0.000000", "1.000000", "0.000000"],
        },
    }


def test_unresolved_material_is_recorded_not_dropped():
    ctx = Context(make_vessel())
    ctx.current = "plate X"
    assert material_aspect("plate", Ref("M404"), ctx) == {
        "kind": "plate",
        "material": {"unresolved": "M404"},
    }
    assert ctx.warnings == ["unresolved material reference 'M404' on plate X"]


def test_generic_section_extra_drops_nested_xml_ids():
    from ocx_model_core.model.ir import IrGenericSection

    from tests.integrity_fixtures import make_vessel

    v = make_vessel()
    v.sections["S9"] = IrGenericSection(
        id="S9",
        guidref="G-S9",
        section_type="Generic",
        extra={"id": "S9", "guidref": "G-S9", "catalogue_reference": "c"},
    )
    rec = section_value(Ref("S9"), Context(v))
    assert rec["part_id"] == "G-S9"
    assert rec["extra"] == {"catalogue_reference": "c"}


def _parts(vessel):
    ctx = Context(vessel)
    return {p.part_id: p for p in iter_parts(vessel, ctx)}, ctx


def test_iter_parts_yields_every_kind_once():
    parts, ctx = _parts(make_vessel())
    assert {pid: p.kind for pid, p in parts.items()} == {
        "vessel:V1": "vessel",
        "G-PL-1": "plate",
        "ST1": "stiffener",
        "G-PAN-1": "panel",
        "SE1": "seam",
        "G-COMP-1": "compartment",
    }
    assert ctx.warnings == []


def test_plate_aspects():
    parts, _ = _parts(make_vessel())
    plate = parts["G-PL-1"]
    assert list(plate.aspects) == ["identity", "material", "scantlings", "geometry", "physical"]
    assert plate.aspects["scantlings"] == {"kind": "plate", "thickness": "0.012000"}
    assert plate.aspects["physical"]["curve_lengths"] == {"outer_contour": "8.000000"}
    holes = plate.aspects["geometry"]["cut_by_holes"]
    assert [h["transformation"]["origin"][0] for h in holes] == ["0.500000", "1.500000"]


def test_stiffener_inlines_section_and_material():
    parts, _ = _parts(make_vessel())
    st = parts["ST1"]
    assert st.id_source == "xml_id"
    assert st.aspects["scantlings"]["section"]["part_id"] == "S1"
    assert st.aspects["material"]["material"]["part_id"] == "G-MAT-1"
    assert st.aspects["geometry"]["orientation_rule"] == "ocx:Up"
    assert st.aspects["physical"]["curve_lengths"] == {"trace": "2.000000"}


def test_panel_identity_and_geometry():
    parts, _ = _parts(make_vessel())
    pan = parts["G-PAN-1"]
    assert pan.aspects["identity"]["children"] == {
        "plates": ["G-PL-1"],
        "stiffeners": ["ST1"],
        "seams": ["SE1"],
    }
    assert "material" not in pan.aspects and "scantlings" not in pan.aspects
    assert pan.aspects["geometry"]["limited_by"] == [
        {"ref_type": "SeamRef", "target": "SE1"},
        {"ref_type": "StiffenerRef", "target": "ST1"},
    ]
    assert pan.aspects["geometry"]["unbounded_geometry"]["surface"]["type"] == "plane3d"
    assert pan.aspects["physical"]["mass_properties"]["moulded_dry_weight"] == "1800.000"


def test_seam_compartment_vessel_records():
    parts, _ = _parts(make_vessel())
    assert parts["SE1"].aspects["physical"]["curve_lengths"] == {"trace_line": "2.000000"}
    comp = parts["G-COMP-1"]
    assert comp.aspects["geometry"] == {"kind": "compartment", "face_refs": ["G-PAN-1"]}
    assert comp.aspects["physical"] == {"kind": "compartment", "volume": "250.000000"}
    v = parts["vessel:V1"]
    assert list(v.aspects) == ["identity"]
    assert v.aspects["identity"]["ship_designation"] == {
        "type": "shipdesignation",
        "ship_name": "TEST",
        "number_imo": "1234567",
    }
    assert v.aspects["identity"]["principal_particulars"] == {
        "type": "principalparticulars",
        "lpp": "100.000000",
    }


def test_records_invariant_to_collection_order():
    a, b = make_vessel(), make_vessel()
    b.plates["PL1"].cut_by_holes.reverse()
    b.panels["P1"].limited_by.reverse()
    pa, _ = _parts(a)
    pb, _ = _parts(b)
    assert pa["G-PL-1"].aspects == pb["G-PL-1"].aspects
    assert pa["G-PAN-1"].aspects == pb["G-PAN-1"].aspects


def test_unresolved_section_becomes_warning():
    v = make_vessel()
    v.stiffeners["ST1"].section_ref = Ref("S404")
    parts, ctx = _parts(v)
    assert parts["ST1"].aspects["scantlings"]["section"] == {"unresolved": "S404"}
    assert ctx.warnings == ["unresolved section reference 'S404' on stiffener ST1"]


def _collection_vessel():
    v = make_vessel()
    plane = v.panels["P1"].unbounded_geometry.surface
    other = IrPlane3D(
        point_on_surface=IrPoint3D(0.0, 0.0, 5.0, "Umm"), normal=IrVector3D(0.0, 0.0, 1.0)
    )
    v.surface_collections["COL1"] = IrSurfaceCollection(
        id="COL1",
        name="hull",
        surfaces=[IrSurface(id="NS1", geometry=plane), IrSurface(id="NS2", geometry=other)],
    )
    return v


def test_panel_surface_ref_to_collection_inlines_collection():
    v, w = _collection_vessel(), _collection_vessel()
    w.surface_collections["COL1"].surfaces.reverse()
    for vessel in (v, w):
        vessel.panels["P1"].unbounded_geometry = IrUnboundedGeometry(surface_ref="COL1")
    (pa, ctx), (pb, _) = _parts(v), _parts(w)
    ug = pa["G-PAN-1"].aspects["geometry"]["unbounded_geometry"]
    coll = ug["surface_ref"]
    assert coll["type"] == "surfacecollection" and coll["part_id"] == "COL1"
    assert [s["part_id"] for s in coll["surfaces"]] == ["NS1", "NS2"]
    assert all(s["geometry"]["type"] == "plane3d" for s in coll["surfaces"])
    assert ug == pb["G-PAN-1"].aspects["geometry"]["unbounded_geometry"]
    assert ctx.warnings == []


def test_panel_surface_ref_to_nested_surface_resolves():
    v = _collection_vessel()
    v.panels["P1"].unbounded_geometry = IrUnboundedGeometry(surface_ref="NS2")
    parts, ctx = _parts(v)
    rec = parts["G-PAN-1"].aspects["geometry"]["unbounded_geometry"]["surface_ref"]
    assert rec["part_id"] == "NS2"
    assert rec["geometry"]["point_on_surface"] == ["0.000000", "0.000000", "0.005000"]
    assert ctx.warnings == []


def test_limited_by_surface_ref_to_collection_resolves():
    v = _collection_vessel()
    v.panels["P1"].limited_by = [
        IrLimitedByRef("SurfaceRef", "COL1"),
        IrLimitedByRef("SurfaceRef", "NS1"),
    ]
    parts, ctx = _parts(v)
    assert parts["G-PAN-1"].aspects["geometry"]["limited_by"] == [
        {"ref_type": "SurfaceRef", "target": "COL1"},
        {"ref_type": "SurfaceRef", "target": "NS1"},
    ]
    assert ctx.warnings == []


def test_edge_curve_ref_limits_commit_guid_never_xml_id():
    v = make_vessel()
    v.panels["P1"].limited_by = [
        IrLimitedByRef("EdgeCurveRef", "EC1", guidref="G-EC-1"),
        IrLimitedByRef("EdgeCurveRef", "EC2", contour_start=IrPoint3D(0.0, 0.0, 0.0, "Umm")),
    ]
    parts, ctx = _parts(v)
    assert parts["G-PAN-1"].aspects["geometry"]["limited_by"] == [
        {"ref_type": "EdgeCurveRef", "contour_start": ["0.000000", "0.000000", "0.000000"]},
        {"ref_type": "EdgeCurveRef", "target": "G-EC-1"},
    ]
    assert ctx.warnings == []


def _aspect_hashes(vessel):
    return {pid: p.aspect_hashes for pid, p in hash_vessel(vessel, KEY).parts.items()}


def _changed(a, b):
    out = {}
    for pid in a:
        diff = sorted(x for x in set(a[pid]) | set(b[pid]) if a[pid].get(x) != b[pid].get(x))
        if diff:
            out[pid] = diff
    return out


def test_thickness_change_only_touches_scantlings():
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    assert _changed(_aspect_hashes(make_vessel()), _aspect_hashes(v)) == {"G-PL-1": ["scantlings"]}


def test_weight_change_only_touches_physical():
    v = make_vessel()
    v.plates["PL1"].mass_properties = IrMassProperties(
        moulded_dry_weight=Quantity(1600.0, "Ukg"), moulded_cog=IrCog(1000.0, 1000.0, 0.0, "Umm")
    )
    assert _changed(_aspect_hashes(make_vessel()), _aspect_hashes(v)) == {"G-PL-1": ["physical"]}


def test_hashes_invariant_to_units_order_contour_start_and_noise():
    v = make_vessel()
    v.plates["PL1"].outer_contour = square(unit="Um", size=2.0, start=2, reverse=True)
    v.plates["PL1"].thickness = Quantity(0.012, "Um")
    v.plates["PL1"].cut_by_holes.reverse()
    v.panels["P1"].limited_by.reverse()
    v.stiffeners["ST1"].trace = IrLine3D(
        curve_length=Quantity(2.0000000001, "Um"),
        start=IrPoint3D(0.0, 1.0000000001, 0.0, "Um"),
        end=IrPoint3D(2.0, 1.0, 0.0, "Um"),
    )
    assert _aspect_hashes(v) == _aspect_hashes(make_vessel())
