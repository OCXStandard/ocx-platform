"""Tests for OCX-TOP-001..005/008/009 topology checks (checks/topology.py)."""
from __future__ import annotations

from types import SimpleNamespace

from ocx_model_core.model.ir import (
    IrCompositeCurve3D,
    IrExtrudedSurface,
    IrHole2D,
    IrHole2DContour,
    IrHoleShapeCatalogue,
    IrInclination,
    IrLimitedByRef,
    IrLine3D,
    IrNurbs3D,
    IrPanel,
    IrParametricHole,
    IrPillar,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrPolyLine3D,
    IrSeam,
    IrStiffener,
    IrSurface,
    IrSurfaceCollection,
    IrTransformation,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)
from ocx_rules.geometry_context import GeometryContext
from ocx_rules.packs.best_practice.checks.topology import (
    composite_curve_continuous,
    hole_contours_closed,
    hole_not_splitting_plate,
    panel_limited_by_closed,
    seam_topology,
    stiffener_inclinations,
    surface_normals_and_boundaries,
)

_UMM = IrUnit(id="Umm", name="millimetre", symbol="mm",
              dimension_url="D_L", to_si_factor=0.001, si_symbol="m")


def _pt(x: float, y: float, z: float = 0.0) -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit="Umm")


def _line(p0: IrPoint3D, p1: IrPoint3D) -> IrLine3D:
    return IrLine3D(curve_length=None, start=p0, end=p1)


def _fec(curve) -> IrLimitedByRef:
    return IrLimitedByRef(ref_type="FreeEdgeCurve3D", local_ref="", curve=curve)


def _square_sides(gap_mm: float = 0.0) -> list[IrLimitedByRef]:
    """Four 1 m square sides in mm; last corner pulled open by gap_mm."""
    a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
    d_open = _pt(0, 1000 + gap_mm)
    return [
        _fec(_line(a, b)),
        _fec(_line(b, c)),
        _fec(_line(c, d_open)),
        _fec(_line(d, a)),
    ]


def _vessel(panels: dict[str, IrPanel] | None = None,
            catalogue: IrHoleShapeCatalogue | None = None) -> IrVessel:
    v = IrVessel(id="v1", unit_registry={"Umm": _UMM})
    if panels:
        v.panels.update(panels)
    if catalogue is not None:
        v.hole_shape_catalogue = catalogue
    return v


def _ctx(vessel: IrVessel) -> SimpleNamespace:
    return SimpleNamespace(vessel=vessel, geometry=GeometryContext(vessel))


class TestPanelLimitedByClosed:
    def test_closed_square_panel_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_open_contour_fails_with_gap_in_message(self):
        panel = IrPanel(id="p1", guidref="g1", limited_by=_square_sides(gap_mm=5.0))
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})
        assert finding.element_id == "p1"
        assert finding.guid == "g1"
        assert "gap" in finding.message
        assert "mm" in finding.message

    def test_unresolvable_ref_skips_panel(self):
        sides = _square_sides(gap_mm=5.0)[:3]
        sides.append(IrLimitedByRef(ref_type="PanelRef", local_ref="nowhere"))
        panel = IrPanel(id="p1", limited_by=sides)
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_no_panels_passes(self):
        ctx = _ctx(_vessel({}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_single_closed_boundary_curve_passes(self):
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        ring = IrCompositeCurve3D(curve_length=None, segments=[
            _line(a, b), _line(b, c), _line(c, d), _line(d, a)])
        panel = IrPanel(id="p1", limited_by=[_fec(ring)])
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == []

    def test_single_open_boundary_curve_fails(self):
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        open_curve = IrCompositeCurve3D(curve_length=None, segments=[
            _line(a, b), _line(b, c), _line(c, d)])
        panel = IrPanel(id="p1", guidref="g1", limited_by=[_fec(open_curve)])
        ctx = _ctx(_vessel({"p1": panel}))
        (finding,) = panel_limited_by_closed(ctx, {"tolerance_mm": 1.0})
        assert finding.element_id == "p1"
        assert "gap" in finding.message


class TestCompositeCurveContinuous:
    def _panel_with_composite(self, segments) -> IrPanel:
        comp = IrCompositeCurve3D(curve_length=None, segments=segments)
        return IrPanel(id="p1", guidref="g1", limited_by=[_fec(comp)])

    def test_continuous_composite_passes(self):
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(1000, 0), _pt(1000, 1000))]
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []

    def test_junction_gap_fails(self):
        # 2 mm gap between the end of segment 1 and the start of segment 2
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(1002, 0), _pt(1002, 1000))]
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        (finding,) = composite_curve_continuous(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "p1"
        assert finding.guid == "g1"
        assert "gap" in finding.message
        assert "mm" in finding.message

    def test_out_of_order_but_chainable_passes(self):
        # Three sides of a square declared out of order and one reversed:
        # continuous geometrically, discontinuous in declared order.
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                _line(_pt(0, 1000), _pt(1000, 1000)),     # out of order
                _line(_pt(1000, 1000), _pt(1000, 0))]     # reversed
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []

    def test_unsampleable_segment_skips_curve(self):
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                IrNurbs3D(curve_length=None)]  # no data -> cannot sample
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []

    def test_no_composite_curves_passes(self):
        panel = IrPanel(id="p1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"p1": panel}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == []


class TestHoleContoursClosed:
    def test_parametric_circular_hole_passes(self):
        hole = IrHole2D(id="h1", parametric=IrParametricHole(
            variant="parametric_circle",
            diameter=Quantity(value=100.0, unit="Umm")))
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_open_curve_contour_fails(self):
        hole = IrHole2D(id="h1", guidref="gh1",
                        contour=_line(_pt(0, 0), _pt(100, 0)))
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        (finding,) = hole_contours_closed(ctx, {"tolerance_mm": 0.1})
        assert finding.element_id == "h1"
        assert finding.guid == "gh1"
        assert "closed" in finding.message

    def test_empty_catalogue_passes(self):
        cat = IrHoleShapeCatalogue(id="cat")
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_missing_catalogue_passes(self):
        ctx = _ctx(_vessel())
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_hole_without_representation_skipped(self):
        hole = IrHole2D(id="h1")
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == []


# ---------------------------------------------------------------------------
# TOP-004 / TOP-005 shared helpers
# ---------------------------------------------------------------------------

_Z_PLANE = IrPlane3D(
    id="surf1",
    point_on_surface=_pt(0, 0, 0),
    normal=IrVector3D(x=0.0, y=0.0, z=1.0),
    udirection=IrVector3D(x=1.0, y=0.0, z=0.0),
)


def _square_outline() -> IrCompositeCurve3D:
    """Closed 1 m square contour in the z=0 plane (mm units)."""
    a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
    return IrCompositeCurve3D(curve_length=None, segments=[
        _line(a, b), _line(b, c), _line(c, d), _line(d, a)])


def _placement(x_mm: float, y_mm: float) -> IrTransformation:
    return IrTransformation(
        origin=_pt(x_mm, y_mm),
        primary_axis=IrVector3D(x=1.0, y=0.0, z=0.0),
        secondary_axis=IrVector3D(x=0.0, y=1.0, z=0.0))


def _circle_hole(diameter_mm: float) -> IrHole2D:
    return IrHole2D(id="h1", parametric=IrParametricHole(
        variant="parametric_circle",
        diameter=Quantity(value=diameter_mm, unit="Umm")))


def _rect_hole(width_mm: float, height_mm: float) -> IrHole2D:
    return IrHole2D(id="h1", parametric=IrParametricHole(
        variant="rectangular_hole",
        width=Quantity(value=width_mm, unit="Umm"),
        height=Quantity(value=height_mm, unit="Umm")))


class TestHoleNotSplittingPlate:
    def _ctx_with_plate(self, hole: IrHole2D, x_mm: float, y_mm: float,
                        surface=_Z_PLANE) -> SimpleNamespace:
        panel = IrPanel(
            id="pan1", plate_ids=["pl1"],
            unbounded_geometry=(IrUnboundedGeometry(surface=surface)
                                if surface is not None else None))
        plate = IrPlate(
            id="pl1", guidref="gpl1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            outer_contour=_square_outline(),
            cut_by_holes=[IrHole2DContour(
                id="hc1", hole_ref=Ref(local_ref="h1"),
                transformation=_placement(x_mm, y_mm))])
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        vessel = _vessel({"pan1": panel}, catalogue=cat)
        vessel.plates["pl1"] = plate
        return _ctx(vessel)

    def test_hole_inside_outline_passes(self):
        ctx = self._ctx_with_plate(_circle_hole(100.0), 500.0, 500.0)
        assert hole_not_splitting_plate(ctx, {}) == []

    def test_hole_cutting_across_plate_fails(self):
        # 2 m wide slot across a 1 m plate -> splits it into two regions
        ctx = self._ctx_with_plate(_rect_hole(2000.0, 100.0), 500.0, 500.0)
        (finding,) = hole_not_splitting_plate(ctx, {})
        assert finding.element_id == "pl1"
        assert finding.guid == "gpl1"
        assert "split" in finding.message

    def test_plate_without_buildable_surface_skipped(self):
        ctx = self._ctx_with_plate(_rect_hole(2000.0, 100.0), 500.0, 500.0,
                                   surface=None)
        assert hole_not_splitting_plate(ctx, {}) == []

    def test_no_plates_passes(self):
        ctx = _ctx(_vessel({}))
        assert hole_not_splitting_plate(ctx, {}) == []


class TestSeamTopology:
    def _ctx_with_seam(self, seam: IrSeam,
                       hole_at: tuple[float, float] | None = None
                       ) -> SimpleNamespace:
        cut_by = []
        cat = None
        if hole_at is not None:
            cat = IrHoleShapeCatalogue(id="cat",
                                       holes={"h1": _circle_hole(100.0)})
            cut_by = [IrHole2DContour(
                id="hc1", hole_ref=Ref(local_ref="h1"),
                transformation=_placement(*hole_at))]
        panel = IrPanel(
            id="pan1", seam_ids=[seam.id], limited_by=_square_sides(),
            unbounded_geometry=IrUnboundedGeometry(surface=_Z_PLANE),
            cut_by_holes=cut_by)
        vessel = _vessel({"pan1": panel}, catalogue=cat)
        vessel.seams[seam.id] = seam
        return _ctx(vessel)

    def test_seam_endpoints_on_boundary_pass(self):
        seam = IrSeam(id="s1",
                      trace_line=_line(_pt(0, 500), _pt(1000, 500)))
        ctx = self._ctx_with_seam(seam, hole_at=(500.0, 100.0))
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_seam_endpoint_on_hole_contour_fails(self):
        # hole: r=50 mm circle at (500, 500); seam ends at (450, 500)
        seam = IrSeam(id="s1", guidref="gs1",
                      trace_line=_line(_pt(0, 500), _pt(450, 500)))
        ctx = self._ctx_with_seam(seam, hole_at=(500.0, 500.0))
        (finding,) = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert finding.element_id == "s1"
        assert finding.guid == "gs1"
        assert "hole" in finding.message

    def test_unsampleable_seam_trace_skipped(self):
        seam = IrSeam(id="s1", trace_line=IrNurbs3D(curve_length=None))
        ctx = self._ctx_with_seam(seam, hole_at=(500.0, 500.0))
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_panel_without_seams_passes(self):
        panel = IrPanel(id="pan1", limited_by=_square_sides())
        ctx = _ctx(_vessel({"pan1": panel}))
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def _ctx_with_seam_and_plate(self, closed_plate: bool,
                                 with_seam: bool = True,
                                 hole_at: tuple[float, float] | None = None
                                 ) -> SimpleNamespace:
        a, b, c, d = _pt(0, 0), _pt(1000, 0), _pt(1000, 1000), _pt(0, 1000)
        segs = [_line(a, b), _line(b, c), _line(c, d)]
        if closed_plate:
            segs.append(_line(d, a))
        outline = IrCompositeCurve3D(curve_length=None, segments=segs)
        cut_by = []
        cat = None
        if hole_at is not None:
            cat = IrHoleShapeCatalogue(id="cat",
                                       holes={"h1": _circle_hole(100.0)})
            cut_by = [IrHole2DContour(
                id="hc1", hole_ref=Ref(local_ref="h1"),
                transformation=_placement(*hole_at))]
        panel = IrPanel(
            id="pan1", plate_ids=["pl1"],
            seam_ids=(["s1"] if with_seam else []),
            limited_by=_square_sides(),
            unbounded_geometry=IrUnboundedGeometry(surface=_Z_PLANE),
            cut_by_holes=cut_by)
        plate = IrPlate(
            id="pl1", guidref="gpl1",
            parent_ref=ParentRef(kind=ParentKind.PANEL, id="pan1"),
            outer_contour=outline)
        vessel = _vessel({"pan1": panel}, catalogue=cat)
        vessel.plates["pl1"] = plate
        if with_seam:
            vessel.seams["s1"] = IrSeam(
                id="s1", trace_line=_line(_pt(0, 500), _pt(1000, 500)))
        return _ctx(vessel)

    def test_seamed_panel_closed_plate_contour_passes(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=True)
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_seamed_panel_open_plate_contour_fails(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False)
        (finding,) = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert finding.element_id == "pl1"
        assert finding.guid == "gpl1"
        assert "closed" in finding.message

    def test_unseamed_panel_open_plate_contour_ignored(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False, with_seam=False)
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == []

    def test_open_plate_contour_reported_even_with_holes_present(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=False,
                                            hole_at=(500.0, 100.0))
        (finding,) = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert finding.element_id == "pl1"


def _coll_member(sid: str, x0_mm: float, x1_mm: float, sweep_y: float = 1.0,
                 guid: str | None = None, buildable: bool = True) -> IrSurface:
    """1 m deep extruded strip spanning [x0, x1] mm with a rectangular
    face boundary; ``sweep_y`` flips the analytic normal (+z vs -z)."""
    boundary = IrPolyLine3D(curve_length=None, vertices=[
        _pt(x0_mm, 0), _pt(x1_mm, 0), _pt(x1_mm, 1000),
        _pt(x0_mm, 1000), _pt(x0_mm, 0)], is_closed=True)
    geom = IrExtrudedSurface(
        base_curve=_line(_pt(x0_mm, 0), _pt(x1_mm, 0)) if buildable else None,
        sweep=IrVector3D(0.0, sweep_y, 0.0) if buildable else None,
        face_boundary_curve=boundary)
    return IrSurface(id=sid, guidref=guid, geometry=geom)


def _coll_ctx(*members: IrSurface) -> SimpleNamespace:
    vessel = _vessel({})
    vessel.surface_collections["sc1"] = IrSurfaceCollection(
        id="sc1", surfaces=list(members))
    return _ctx(vessel)


class TestSurfaceNormalsAndBoundaries:
    PARAMS: dict = {}

    def test_coplanar_adjacent_members_pass(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        _coll_member("sb", 1000, 2000))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []

    def test_opposed_normals_fail(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000, guid="ga"),
                        _coll_member("sb", 1000, 2000, sweep_y=-1.0))
        (finding,) = surface_normals_and_boundaries(ctx, self.PARAMS)
        assert finding.element_id == "sa"
        assert finding.guid == "ga"
        assert "orientation reverses" in finding.message
        assert "sb" in finding.message

    def test_unbuildable_member_skipped(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        _coll_member("sb", 1000, 2000, sweep_y=-1.0,
                                     buildable=False))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []

    def test_distant_members_not_adjacent(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        _coll_member("sb", 3000, 4000, sweep_y=-1.0))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []

    def test_t_configuration_without_shared_corners_fails(self):
        # Member B abuts the interior of A's x=1000 edge (no coincident
        # boundary vertices) — adjacency must still be detected.
        boundary_b = IrPolyLine3D(curve_length=None, vertices=[
            _pt(1000, 250), _pt(2000, 250), _pt(2000, 750),
            _pt(1000, 750), _pt(1000, 250)], is_closed=True)
        geom_b = IrExtrudedSurface(
            base_curve=_line(_pt(1000, 250), _pt(2000, 250)),
            sweep=IrVector3D(0.0, -1.0, 0.0),
            face_boundary_curve=boundary_b)
        ctx = _coll_ctx(_coll_member("sa", 0, 1000, guid="ga"),
                        IrSurface(id="sb", geometry=geom_b))
        (finding,) = surface_normals_and_boundaries(ctx, self.PARAMS)
        assert finding.element_id == "sa"
        assert "sb" in finding.message

    def test_sharp_knuckle_consistently_oriented_passes(self):
        # Face A in z=0; face B folds up steeply from the shared edge
        # x=1000: normals ~143 deg apart, but orientation is consistent
        # (both probes obey the opposite-handedness relation).
        boundary_b = IrPolyLine3D(curve_length=None, vertices=[
            _pt(1000, 0, 0), _pt(200, 0, 600), _pt(200, 1000, 600),
            _pt(1000, 1000, 0), _pt(1000, 0, 0)], is_closed=True)
        geom_b = IrExtrudedSurface(
            base_curve=_line(_pt(1000, 0, 0), _pt(200, 0, 600)),
            sweep=IrVector3D(0.0, 1.0, 0.0),
            face_boundary_curve=boundary_b)
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        IrSurface(id="sb", geometry=geom_b))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []

    def test_curved_shared_edge_consistently_oriented_passes(self):
        # Quarter-arc shared edge (r = 1000 mm) between an inner pie
        # sector and an outer quarter annulus, both coplanar in z=0
        # with the same +z normal — consistently oriented, must pass.
        # Projection onto the bounding-box diagonal (cos t + sin t) is
        # non-monotonic along the arc, so a diagonal sort interleaves
        # the two arc halves and produces cross-chords whose midpoints
        # lie deep inside the sector; ordering must follow the curve.
        import math
        n = 17
        thetas = [math.pi / 2 * i / (n - 1) for i in range(n)]
        arc = [(1000 * math.cos(t), 1000 * math.sin(t)) for t in thetas]
        outer = [(3000 * math.cos(t), 3000 * math.sin(t)) for t in thetas]
        # Inner pie sector: origin -> arc (ccw) -> back to origin.
        boundary_b = IrPolyLine3D(curve_length=None, vertices=(
            [_pt(0, 0)] + [_pt(x, y) for x, y in arc] + [_pt(0, 0)]),
            is_closed=True)
        geom_b = IrExtrudedSurface(
            base_curve=_line(_pt(0, 0), _pt(1000, 0)),
            sweep=IrVector3D(0.0, 1.0, 0.0),
            face_boundary_curve=boundary_b)
        # Outer quarter annulus: inner arc (ccw) -> outer arc (cw) -> close.
        boundary_a = IrPolyLine3D(curve_length=None, vertices=(
            [_pt(x, y) for x, y in arc]
            + [_pt(x, y) for x, y in reversed(outer)]
            + [_pt(*arc[0])]), is_closed=True)
        geom_a = IrExtrudedSurface(
            base_curve=_line(_pt(1000, 0), _pt(3000, 0)),
            sweep=IrVector3D(0.0, 1.0, 0.0),
            face_boundary_curve=boundary_a)
        ctx = _coll_ctx(IrSurface(id="sa", geometry=geom_a),
                        IrSurface(id="sb", geometry=geom_b))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []

    def test_no_collections_passes(self):
        ctx = _ctx(_vessel({}))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == []


def _incl(x_mm: float, web: tuple = (0, 0, 1),
          flange: tuple | None = None) -> IrInclination:
    return IrInclination(
        position=_pt(x_mm, 0),
        web_direction=IrVector3D(*web),
        flange_direction=IrVector3D(*flange) if flange is not None else None)


def _vessel_parent() -> ParentRef:
    return ParentRef(kind=ParentKind.VESSEL, id="v1")


def _stiffener_ctx(inclinations: list[IrInclination]) -> SimpleNamespace:
    vessel = _vessel({})
    vessel.stiffeners["st1"] = IrStiffener(
        id="st1", parent_ref=_vessel_parent(), guidref="gst",
        inclinations=inclinations)
    return _ctx(vessel)


class TestStiffenerInclinations:
    def test_monotone_consistent_inclinations_pass(self):
        ctx = _stiffener_ctx([_incl(0, flange=(0, 1, 0)),
                              _incl(500, flange=(0, 1, 0)),
                              _incl(1000, flange=(0, 1, 0))])
        assert stiffener_inclinations(ctx, {}) == []

    def test_duplicate_position_fails(self):
        ctx = _stiffener_ctx([_incl(0), _incl(500), _incl(500)])
        (finding,) = stiffener_inclinations(ctx, {})
        assert finding.element_id == "st1"
        assert finding.guid == "gst"
        assert "duplicate inclination position" in finding.message.lower()

    def test_web_direction_flip_fails(self):
        ctx = _stiffener_ctx([_incl(0, web=(0, 0, 1)),
                              _incl(500, web=(0, 0, -1))])
        (finding,) = stiffener_inclinations(ctx, {})
        assert finding.element_id == "st1"
        assert finding.guid == "gst"
        assert "web direction flips" in finding.message.lower()

    def test_flange_direction_flip_fails(self):
        ctx = _stiffener_ctx([_incl(0, flange=(0, 1, 0)),
                              _incl(500, flange=(0, -1, 0))])
        (finding,) = stiffener_inclinations(ctx, {})
        assert "flange direction flips" in finding.message.lower()

    def test_missing_vectors_skipped(self):
        ctx = _stiffener_ctx([
            _incl(0, web=(0, 0, 1)),
            IrInclination(position=_pt(500, 0)),   # no vectors
            _incl(1000, web=(0, 0, 1))])
        assert stiffener_inclinations(ctx, {}) == []

    def test_stiffener_without_inclinations_passes(self):
        ctx = _stiffener_ctx([])
        assert stiffener_inclinations(ctx, {}) == []

    def test_pillar_web_flip_fails(self):
        vessel = _vessel({})
        vessel.pillars["pil1"] = IrPillar(
            id="pil1", parent_ref=_vessel_parent(), guidref="gpil",
            inclinations=[_incl(0, web=(1, 0, 0)), _incl(500, web=(-1, 0, 0))])
        (finding,) = stiffener_inclinations(_ctx(vessel), {})
        assert finding.element_id == "pil1"
        assert finding.guid == "gpil"
        assert "web direction flips" in finding.message.lower()
