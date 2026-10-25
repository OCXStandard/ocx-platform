"""Tests for curve/surface well-formedness checks (OCX-GEO-001..005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    catalogue_holes_planar,
    nurbs_control_points,
    nurbs_knot_multiplicity,
    nurbs_knots_non_decreasing,
    polyline_closed,
)

from tests.rules_xml import context_for


def _nurbs(degree: int, knots: str, points: int) -> str:
    ctrl = "".join(
        f'<ocx:ControlPoint coordinates="{i} 0 0" weight="1.0"/>' for i in range(points))
    return (
        f'<ocx:NURBS3D id="c1">'
        f'<ocx:NURBSproperties degree="{degree}" numCtrlPts="{points}" '
        f'numKnots="{len(knots.split())}" form="Open" isRational="false"/>'
        f'<ocx:KnotVector value="{knots}"/>'
        f"<ocx:ControlPtList>{ctrl}</ocx:ControlPtList>"
        f"</ocx:NURBS3D>")


class TestNurbsControlPoints:
    def test_enough_points_passes(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 1 1 1", 4))
        assert nurbs_control_points(ctx, {}) == []

    def test_too_few_points_fails(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 1 1 1", 3))
        (finding,) = nurbs_control_points(ctx, {})
        assert "degree" in finding.message

    def test_missing_degree_is_finding(self):
        ctx = context_for('<ocx:NURBS3D id="c1"><ocx:NURBSproperties/></ocx:NURBS3D>')
        (finding,) = nurbs_control_points(ctx, {})
        assert "degree" in finding.message


class TestNurbsKnots:
    def test_sorted_knots_pass(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 0.5 1 1 1 1", 5))
        assert nurbs_knots_non_decreasing(ctx, {}) == []
        assert nurbs_knot_multiplicity(ctx, {}) == []

    def test_decreasing_knots_fail(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 0.5 1 1 1", 5))
        (finding,) = nurbs_knots_non_decreasing(ctx, {})
        assert "non-decreasing" in finding.message

    def test_interior_multiplicity_above_degree_fails(self):
        ctx = context_for(_nurbs(2, "0 0 0 0.5 0.5 0.5 1 1 1", 6))
        (finding,) = nurbs_knot_multiplicity(ctx, {})
        assert "multiplicity" in finding.message

    def test_clamped_end_multiplicity_allowed(self):
        ctx = context_for(_nurbs(2, "0 0 0 1 1 1", 3))
        assert nurbs_knot_multiplicity(ctx, {}) == []


def _nurbs_surface(u_knots: str, v_knots: str, u_pts: int = 4, v_pts: int = 4) -> str:
    return (
        '<ocx:NURBSSurface id="s1">'
        f'<ocx:U_NURBSproperties degree="3" numCtrlPts="{u_pts}"/>'
        f'<ocx:UknotVector value="{u_knots}"/>'
        f'<ocx:V_NURBSproperties degree="3" numCtrlPts="{v_pts}"/>'
        f'<ocx:VknotVector value="{v_knots}"/>'
        "</ocx:NURBSSurface>")


class TestNurbsSurface:
    def test_valid_surface_passes(self):
        ctx = context_for(_nurbs_surface("0 0 0 0 1 1 1 1", "0 0 0 0 1 1 1 1"))
        assert nurbs_control_points(ctx, {}) == []
        assert nurbs_knots_non_decreasing(ctx, {}) == []
        assert nurbs_knot_multiplicity(ctx, {}) == []

    def test_decreasing_v_knots_fail(self):
        ctx = context_for(_nurbs_surface("0 0 0 0 1 1 1 1", "0 0 0 0 1 0.5 1 1"))
        (finding,) = nurbs_knots_non_decreasing(ctx, {})
        assert "non-decreasing" in finding.message

    def test_too_few_u_control_points_fail(self):
        ctx = context_for(_nurbs_surface("0 0 0 0 1 1 1 1", "0 0 0 0 1 1 1 1", u_pts=3))
        (finding,) = nurbs_control_points(ctx, {})
        assert "U_NURBSproperties" in finding.message


class TestPolylineClosed:
    def _poly(self, closed: str, coords: list[str]) -> str:
        pts = "".join(f'<ocx:Point3D coordinates="{c}"/>' for c in coords)
        return f'<ocx:PolyLine3D id="p1" isClosed="{closed}">{pts}</ocx:PolyLine3D>'

    def test_closed_loop_passes(self):
        ctx = context_for(self._poly("true", ["0 0 0", "10 0 0", "10 10 0", "0 0 0"]))
        assert polyline_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_open_gap_fails(self):
        ctx = context_for(self._poly("true", ["0 0 0", "10 0 0", "10 10 0"]))
        (finding,) = polyline_closed(ctx, {"tolerance_mm": 0.1})
        assert "mm" in finding.message

    def test_unclosed_polyline_ignored(self):
        ctx = context_for(self._poly("false", ["0 0 0", "10 0 0"]))
        assert polyline_closed(ctx, {"tolerance_mm": 0.1}) == []


class TestCatalogueHolesPlanar:
    def test_planar_contour_passes(self):
        ctx = context_for(
            "<ocx:HoleShapeCatalogue><ocx:Hole2D id=\"h1\">"
            '<ocx:Point3D coordinates="-5 -5 0"/><ocx:Point3D coordinates="5 5 0"/>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        assert catalogue_holes_planar(ctx, {"tolerance_mm": 0.1}) == []

    def test_out_of_plane_point_fails(self):
        ctx = context_for(
            "<ocx:HoleShapeCatalogue><ocx:Hole2D id=\"h1\">"
            '<ocx:Point3D coordinates="0 0 7.5"/>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        (finding,) = catalogue_holes_planar(ctx, {"tolerance_mm": 0.1})
        assert "Z" in finding.message


class TestCatalogueHolesCentered:
    PARAMS = {"tolerance_mm": 0.1, "center_tolerance_mm": 1.0}

    def _catalogue(self, coords: list[str]) -> str:
        pts = "".join(f'<ocx:Point3D coordinates="{c}"/>' for c in coords)
        return (f'<ocx:HoleShapeCatalogue><ocx:Hole2D id="h1">{pts}'
                "</ocx:Hole2D></ocx:HoleShapeCatalogue>")

    def test_centered_contour_passes(self):
        ctx = context_for(self._catalogue(
            ["-50 -50 0", "50 -50 0", "50 50 0", "-50 50 0"]))
        assert catalogue_holes_planar(ctx, self.PARAMS) == []

    def test_off_centre_contour_fails(self):
        # bbox centre = (5, 0) mm -> exceeds 1 mm tolerance
        ctx = context_for(self._catalogue(
            ["-45 -50 0", "55 -50 0", "55 50 0", "-45 50 0"]))
        (finding,) = catalogue_holes_planar(ctx, self.PARAMS)
        assert finding.element_id == "h1"
        assert "center" in finding.message.lower()

    def test_parametric_hole_without_coordinates_passes(self):
        ctx = context_for(
            '<ocx:HoleShapeCatalogue><ocx:Hole2D id="h1">'
            '<ocx:RectangularHole id="h1s"><ocx:Height numericvalue="2.0" unit="Um"/>'
            '<ocx:Width numericvalue="1.8" unit="Um"/></ocx:RectangularHole>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        assert catalogue_holes_planar(ctx, self.PARAMS) == []

    def test_one_finding_per_hole_not_per_point(self):
        two = (self._catalogue(["90 -50 0", "110 -50 0", "110 50 0", "90 50 0"])
               .replace("</ocx:HoleShapeCatalogue>", "")
               + '<ocx:Hole2D id="h2"><ocx:Point3D coordinates="-50 -50 0"/>'
                 '<ocx:Point3D coordinates="50 50 0"/></ocx:Hole2D>'
                 "</ocx:HoleShapeCatalogue>")
        (finding,) = catalogue_holes_planar(context_for(two), self.PARAMS)
        assert finding.element_id == "h1"
