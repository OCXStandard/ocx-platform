"""End-to-end render_model test on a synthetic IrVessel."""
import numpy as np
from ocx_geometry.backend import TessellationOptions
from ocx_model_core.model.ir.base import IrVector3D, ParentKind, ParentRef, Quantity, Ref
from ocx_model_core.model.ir.geometry import (
    IrLine3D,
    IrNurbs3D,
    IrPlane3D,
    IrPoint3D,
    IrPolyLine3D,
    IrUnboundedGeometry,
)
from ocx_model_core.model.ir.sections import IrFlatBarSection
from ocx_model_core.model.ir.structural import (
    IrPanel,
    IrPillar,
    IrPlate,
    IrStiffener,
    IrVessel,
)
from ocx_render.render import render_model


def pt(x, y, z):
    return IrPoint3D(x, y, z, "Um")


def make_vessel(panel_surface=True):
    panel_geom = (IrUnboundedGeometry(
        surface=IrPlane3D(id="s1", point_on_surface=pt(0, 0, 0),
                          normal=IrVector3D(0, 0, 1)))
                  if panel_surface else None)
    panel = IrPanel(
        id="pan1", name="Deck",
        unbounded_geometry=panel_geom,
        plate_ids=["pl1"], stiffener_ids=["st1"],
    )
    plate = IrPlate(
        id="pl1", parent_ref=ParentRef(ParentKind.PANEL, "pan1"), name="Plate 1",
        outer_contour=IrPolyLine3D(None, vertices=[
            pt(0, 0, 0), pt(4, 0, 0), pt(4, 2, 0), pt(0, 2, 0), pt(0, 0, 0)]),
    )
    stiffener = IrStiffener(
        id="st1", parent_ref=ParentRef(ParentKind.PANEL, "pan1"), name="Stiff 1",
        section_ref=Ref("fb100"),
        trace=IrLine3D(None, start=pt(0, 1, 0), end=pt(4, 1, 0)),
    )
    pillar_no_trace = IrPillar(
        id="pi1", parent_ref=ParentRef(ParentKind.VESSEL, "v"), name="Pillar 1",
    )
    vessel = IrVessel(id="v", name="Test vessel")
    vessel.panels["pan1"] = panel
    vessel.plates["pl1"] = plate
    vessel.stiffeners["st1"] = stiffener
    vessel.pillars["pi1"] = pillar_no_trace
    vessel.sections["fb100"] = IrFlatBarSection(
        id="fb100", height=Quantity(0.1, "Um"), width=Quantity(0.01, "Um"))
    return vessel


class TestRenderModel:
    def test_renders_plate_and_stiffener_skips_bad_pillar(self):
        result = render_model(make_vessel(), TessellationOptions())
        kinds = {m.kind for m in result.meshes}
        assert kinds == {"plate", "stiffener"}
        assert result.rendered_count == 2
        assert result.skipped == {"pi1": "no trace"}

    def test_extras_carry_identity_and_grouping(self):
        result = render_model(make_vessel())
        plate = next(m for m in result.meshes if m.kind == "plate")
        assert plate.extras["id"] == "pl1"
        assert plate.extras["panel_id"] == "pan1"
        stiff = next(m for m in result.meshes if m.kind == "stiffener")
        assert stiff.extras["panel_id"] == "pan1"

    def test_all_vertices_finite_and_in_metres(self):
        result = render_model(make_vessel())
        for m in result.meshes:
            assert np.all(np.isfinite(m.vertices))
        plate = next(m for m in result.meshes if m.kind == "plate")
        assert plate.vertices[:, 0].max() <= 4.0 + 1e-9    # metres, not mm

    def test_plate_without_panel_surface_is_skipped(self):
        result = render_model(make_vessel(panel_surface=False))
        assert result.skipped["pl1"] == "no resolvable panel surface"

    def test_unknown_section_falls_back_to_proxy(self):
        vessel = make_vessel()
        del vessel.sections["fb100"]          # dangling section ref
        result = render_model(vessel)
        assert any(m.kind == "stiffener" for m in result.meshes)

    def test_bad_nurbs_stiffener_trace_doesnt_raise(self):
        """ISSUE 1: GeomdlException from bad NURBS setup should not escape."""
        vessel = make_vessel()
        # Bad NURBS: degree=3 but only 2 control points (requires degree+1)
        bad_nurbs = IrNurbs3D(
            None, degree=3, control_points=[pt(0, 0, 0), pt(1, 0, 0)],
            knot_vector=[0, 0, 0, 0, 1, 1, 1, 1]
        )
        vessel.stiffeners["st1"].trace = bad_nurbs
        # Should not raise; stiffener should be in skipped
        result = render_model(vessel)
        assert "st1" in result.skipped
        assert "error" in result.skipped["st1"].lower()
        # Plate should still render
        assert any(m.kind == "plate" for m in result.meshes)

    def test_vessel_parented_plate_not_parented_to_panel(self):
        """ISSUE 2: plate parented to VESSEL (not PANEL) → skip reason."""
        vessel = make_vessel()
        # Create a plate parented to VESSEL instead of PANEL
        plate = IrPlate(
            id="pl2", parent_ref=ParentRef(ParentKind.VESSEL, "v"), name="Plate 2",
            outer_contour=IrPolyLine3D(None, vertices=[
                pt(0, 0, 0), pt(1, 0, 0), pt(1, 1, 0), pt(0, 1, 0), pt(0, 0, 0)]),
        )
        vessel.plates["pl2"] = plate
        result = render_model(vessel)
        assert result.skipped["pl2"] == "not parented to a panel"

    def test_grid_ref_plane_synthesized_from_location(self):
        """Grid ref planes carry only an axis location; a plane must be
        synthesized from the owning coordinate-system axis."""
        from ocx_model_core.model.ir.geometry import (
            IrCoordinateSystem,
            IrRefPlane,
        )

        vessel = make_vessel(panel_surface=False)
        vessel.panels["pan1"] = IrPanel(
            id="pan1", name="Deck",
            unbounded_geometry=IrUnboundedGeometry(grid_ref="BP"),
            plate_ids=["pl1"], stiffener_ids=["st1"],
        )
        vessel.ref_planes["BP"] = IrRefPlane(
            id="BP", name="BasePlane", location=Quantity(0.0, "Um"))
        vessel.coordinate_systems["cs"] = IrCoordinateSystem(
            id="cs", is_global=True, z_ref_plane_ids=["BP"])
        result = render_model(vessel)
        assert any(m.kind == "plate" for m in result.meshes), result.skipped

    def test_surface_ref_to_collection_id_uses_member_geometry(self):
        """A panel SurfaceRef may point at a SurfaceCollection id."""
        from ocx_model_core.model.ir.geometry import (
            IrSurface,
            IrSurfaceCollection,
        )

        vessel = make_vessel(panel_surface=False)
        vessel.panels["pan1"] = IrPanel(
            id="pan1", name="Deck",
            unbounded_geometry=IrUnboundedGeometry(surface_ref="coll1"),
            plate_ids=["pl1"], stiffener_ids=["st1"],
        )
        vessel.surface_collections["coll1"] = IrSurfaceCollection(
            id="coll1", surfaces=[IrSurface(
                id="m1", geometry=IrPlane3D(
                    id="m1", point_on_surface=pt(0, 0, 0),
                    normal=IrVector3D(0, 0, 1)))])
        result = render_model(vessel)
        assert any(m.kind == "plate" for m in result.meshes), result.skipped

    def test_collection_picks_member_matching_plate_contour(self):
        """With a multi-member collection, the member nearest the plate
        contour must be chosen — not simply the first member."""
        from ocx_model_core.model.ir.geometry import (
            IrSurface,
            IrSurfaceCollection,
        )

        vessel = make_vessel(panel_surface=False)
        vessel.panels["pan1"] = IrPanel(
            id="pan1", name="Deck",
            unbounded_geometry=IrUnboundedGeometry(surface_ref="coll1"),
            plate_ids=["pl1"], stiffener_ids=["st1"],
        )
        # First member is a plane far from the contour (z=10); the plate
        # contour in make_vessel lies at z=0 on the second member.
        vessel.surface_collections["coll1"] = IrSurfaceCollection(
            id="coll1", surfaces=[
                IrSurface(id="m0", geometry=IrPlane3D(
                    id="m0", point_on_surface=pt(0, 0, 10),
                    normal=IrVector3D(0, 0, 1))),
                IrSurface(id="m1", geometry=IrPlane3D(
                    id="m1", point_on_surface=pt(0, 0, 0),
                    normal=IrVector3D(0, 0, 1))),
            ])
        result = render_model(vessel)
        plate = next(m for m in result.meshes if m.kind == "plate")
        assert abs(plate.vertices[:, 2]).max() < 1e-6

    def test_plate_spanning_collection_members_projects_onto_each(self):
        """A plate spanning several collection members (flat bottom + bilge
        cylinder + side) must lie on the composite surface — not entirely on
        the single best-fitting member."""
        from ocx_model_core.model.ir.geometry import (
            IrCylinder3D,
            IrSurface,
            IrSurfaceCollection,
        )

        # bottom plane z=0 (y<=1), bilge cylinder c=(y1,z1) R=1, side y=2 (z>=1)
        def girth(x):
            out = [pt(x, 0.0, 0.0)]
            for th in np.linspace(0.0, np.pi / 2, 9):
                out.append(pt(x, 1.0 + np.sin(th), 1.0 - np.cos(th)))
            out.append(pt(x, 2.0, 2.0))
            return out

        ring = girth(0.0) + girth(4.0)[::-1] + [pt(0.0, 0.0, 0.0)]
        vessel = make_vessel(panel_surface=False)
        vessel.panels["pan1"] = IrPanel(
            id="pan1", name="Shell",
            unbounded_geometry=IrUnboundedGeometry(surface_ref="coll1"),
            plate_ids=["pl1"], stiffener_ids=[],
        )
        vessel.plates["pl1"] = IrPlate(
            id="pl1", parent_ref=ParentRef(ParentKind.PANEL, "pan1"),
            outer_contour=IrPolyLine3D(None, vertices=ring),
        )
        del vessel.stiffeners["st1"]
        vessel.surface_collections["coll1"] = IrSurfaceCollection(
            id="coll1", surfaces=[
                IrSurface(id="bot", geometry=IrPlane3D(
                    id="bot", point_on_surface=pt(0, 0, 0),
                    normal=IrVector3D(0, 0, 1))),
                IrSurface(id="bilge", geometry=IrCylinder3D(
                    id="bilge", origin=pt(0, 1, 1),
                    axis=IrVector3D(1, 0, 0), radius=Quantity(1.0, "Um"))),
                IrSurface(id="side", geometry=IrPlane3D(
                    id="side", point_on_surface=pt(0, 2, 0),
                    normal=IrVector3D(0, 1, 0))),
            ])
        result = render_model(vessel)
        plate = next(m for m in result.meshes if m.kind == "plate")
        v3 = plate.vertices
        # every vertex on the composite: bottom plane, cylinder, or side plane
        d_bot = np.where(v3[:, 1] <= 1.0 + 1e-6, np.abs(v3[:, 2]), np.inf)
        d_side = np.where(v3[:, 2] >= 1.0 - 1e-6, np.abs(v3[:, 1] - 2.0), np.inf)
        rad = np.linalg.norm(v3[:, 1:] - [1.0, 1.0], axis=1)
        d_cyl = np.abs(rad - 1.0)
        d = np.minimum(np.minimum(d_bot, d_side), d_cyl)
        assert d.max() < 1e-6, f"max off-surface distance {d.max()}"
        # coverage: mesh must reach the flat bottom AND the flat side
        on_bottom = (np.abs(v3[:, 2]) < 1e-6) & (v3[:, 1] < 0.9)
        on_side = (np.abs(v3[:, 1] - 2.0) < 1e-6) & (v3[:, 2] > 1.1)
        assert on_bottom.any(), "no vertices on the flat bottom"
        assert on_side.any(), "no vertices on the flat side"

