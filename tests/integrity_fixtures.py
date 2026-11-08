"""Synthetic IrVessel + unit registry shared by the ocx-integrity tests."""

from __future__ import annotations

from ocx_model_core.model.ir import (
    IrCog,
    IrCompartment,
    IrFlatBarSection,
    IrHole2D,
    IrHole2DContour,
    IrHoleShapeCatalogue,
    IrLimitedByRef,
    IrLine3D,
    IrMassProperties,
    IrMaterial,
    IrPanel,
    IrParametricHole,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrPolyLine3D,
    IrPrincipalParticulars,
    IrSeam,
    IrShipDesignation,
    IrStiffener,
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

KEY = bytes(range(32))  # deterministic 32-byte test key
OTHER_KEY = bytes(range(1, 33))


def registry() -> dict[str, IrUnit]:
    return {
        "Um": IrUnit("Um", "meter", "m", "D_L", 1.0, "m"),
        "Umm": IrUnit("Umm", "millimeter", "mm", "D_L", 0.001, "m"),
        "Um3": IrUnit("Um3", "cubic meter", "m3", "D_L3", 1.0, "m³"),
        "Ucm4": IrUnit("Ucm4", "cm4", "cm4", "D_L4", 1e-8, "m⁴"),
        "Ukg": IrUnit("Ukg", "kilogram", "kg", "D_Kg", 1.0, "kg"),
        "Ut": IrUnit("Ut", "tonne", "t", "D_Kg", 1000.0, "kg"),
        "UNOvermm2": IrUnit("UNOvermm2", "N/mm2", "N/mm2", "D_N.MM-2", 1e6, "Pa"),
        "Ukgm3": IrUnit("Ukgm3", "kg/m3", "kg/m3", "D_Kg.M-3", 1.0, "kg/m³"),
        "UDimless": IrUnit("UDimless", "dimensionless", "", None, 1.0, ""),
    }


def square(
    unit: str = "Umm",
    size: float = 2000.0,
    start: int = 0,
    reverse: bool = False,
    repeat_first: bool = False,
) -> IrPolyLine3D:
    """Closed square in the z=0 plane, counter-clockwise seen from +z."""
    corners = [(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]
    if reverse:
        corners = corners[::-1]
    corners = corners[start:] + corners[:start]
    verts = [IrPoint3D(x, y, 0.0, unit) for x, y in corners]
    if repeat_first:
        verts.append(verts[0])
    return IrPolyLine3D(curve_length=Quantity(4 * size, unit), vertices=verts, is_closed=True)


def hole(x: float, y: float, hid: str = "HA") -> IrHole2DContour:
    return IrHole2DContour(
        id=hid,
        hole_ref=Ref("H1"),
        transformation=IrTransformation(
            origin=IrPoint3D(x, y, 0.0, "Umm"),
            primary_axis=IrVector3D(1.0, 0.0, 0.0),
            secondary_axis=IrVector3D(0.0, 1.0, 0.0),
        ),
    )


def make_vessel() -> IrVessel:
    """Small vessel: 1 panel, 1 plate, 1 stiffener, 1 seam, 1 compartment."""
    panel_parent = ParentRef(ParentKind.PANEL, "P1")
    material = IrMaterial(
        id="M1",
        guidref="G-MAT-1",
        grade="AH36",
        density=Quantity(7850.0, "Ukgm3"),
        yield_stress=Quantity(355.0, "UNOvermm2"),
        youngs_modulus=Quantity(206000.0, "UNOvermm2"),
    )
    section = IrFlatBarSection(
        id="S1",
        name="FB200x12",
        section_type="FlatBar",
        height=Quantity(200.0, "Umm"),
        width=Quantity(12.0, "Umm"),
    )
    holes = IrHoleShapeCatalogue(
        id="HC",
        holes={
            "H1": IrHole2D(
                id="H1",
                guidref="G-HOLE-1",
                parametric=IrParametricHole(variant="circle", diameter=Quantity(100.0, "Umm")),
            ),
        },
    )
    plate = IrPlate(
        id="PL1",
        guidref="G-PL-1",
        parent_ref=panel_parent,
        name="Deck plate",
        material_ref=Ref("M1", "G-MAT-1"),
        thickness=Quantity(12.0, "Umm"),
        mass_properties=IrMassProperties(
            moulded_dry_weight=Quantity(1500.0, "Ukg"),
            moulded_cog=IrCog(1000.0, 1000.0, 0.0, "Umm"),
        ),
        outer_contour=square(),
        cut_by_holes=[hole(500.0, 500.0, "HA"), hole(1500.0, 1500.0, "HB")],
    )
    stiffener = IrStiffener(
        id="ST1",
        parent_ref=panel_parent,
        name="L1",
        material_ref=Ref("M1"),
        section_ref=Ref("S1"),
        trace=IrLine3D(
            curve_length=Quantity(2000.0, "Umm"),
            start=IrPoint3D(0.0, 1000.0, 0.0, "Umm"),
            end=IrPoint3D(2000.0, 1000.0, 0.0, "Umm"),
        ),
        orientation_rule="ocx:Up",
    )
    seam = IrSeam(
        id="SE1",
        name="Butt 1",
        trace_line=IrLine3D(
            curve_length=Quantity(2000.0, "Umm"),
            start=IrPoint3D(1000.0, 0.0, 0.0, "Umm"),
            end=IrPoint3D(1000.0, 2000.0, 0.0, "Umm"),
        ),
    )
    panel = IrPanel(
        id="P1",
        guidref="G-PAN-1",
        name="Deck",
        tightness="WaterTight",
        plate_ids=["PL1"],
        stiffener_ids=["ST1"],
        seam_ids=["SE1"],
        limited_by=[IrLimitedByRef("SeamRef", "SE1"), IrLimitedByRef("StiffenerRef", "ST1")],
        unbounded_geometry=IrUnboundedGeometry(
            surface=IrPlane3D(
                point_on_surface=IrPoint3D(0.0, 0.0, 0.0, "Umm"), normal=IrVector3D(0.0, 0.0, 1.0)
            )
        ),
        mass_properties=IrMassProperties(moulded_dry_weight=Quantity(1.8, "Ut")),
    )
    compartment = IrCompartment(
        id="C1",
        guidref="G-COMP-1",
        name="WBT1",
        compartment_purpose="Ballast",
        volume=Quantity(250.0, "Um3"),
        face_refs=[Ref("P1", "G-PAN-1")],
    )
    return IrVessel(
        id="V1",
        name="Test vessel",
        schema_version="3.1.0",
        unit_registry=registry(),
        panels={"P1": panel},
        plates={"PL1": plate},
        stiffeners={"ST1": stiffener},
        seams={"SE1": seam},
        materials={"M1": material},
        sections={"S1": section},
        hole_shape_catalogue=holes,
        compartments={"C1": compartment},
        ship_designation=IrShipDesignation(ship_name="TEST", number_imo="1234567"),
        principal_particulars=IrPrincipalParticulars(lpp=Quantity(100.0, "Um")),
    )
