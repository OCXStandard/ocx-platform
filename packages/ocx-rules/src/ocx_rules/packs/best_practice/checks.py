"""Custom check callables for the best_practice pack.

Step 1: every check is a stub raising CheckNotImplemented. Step 2 replaces
stubs with real implementations keeping name and signature
``(context: ValidationContext, params: dict) -> list[Finding]``.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented


def _stub(summary: str):
    def check(context, params):
        raise CheckNotImplemented(summary)

    check.__doc__ = summary
    return check


# identity
entitybase_has_guid_and_id = _stub(
    "Every EntityBase-derived object carries GUIDRef and id")
idbase_has_id = _stub("IDBase-derived geometry carries a local id")
names_not_identifiers = _stub("Names are not used as identifiers")

# document
schema_location_tuple = _stub(
    "Root xsi:schemaLocation contains the (namespace, XSD location) tuple")
root_declarations = _stub("schemaVersion, xmlns:ocx and xmlns:xsi present on root")
unit_definitions = _stub("Every Unit has a unique id and UnitName")
unit_refs_resolve = _stub("Unit and Dimension references resolve")
enumerated_root_units = _stub("Enumerated UnitsML root units used when available")

# references
stiffener_end_configurations = _stub(
    "A Stiffener has at most two end configurations, one per end")
slot_lug_plate_refs = _stub("A two-lug slot has exactly two LugPlateRef references")
explicit_connectivity = _stub("Structural connectivity encoded explicitly via references")
panel_as_occurrence_group = _stub(
    "A Panel is represented as OccurrenceGroup, never a direct Occurrence")
hole_single_representation = _stub(
    "A hole/slot appears in only one representation (CutBy xor OuterContour)")

# curves_surfaces
nurbs_control_points = _stub("NURBS control-point count >= degree + 1")
nurbs_knots_non_decreasing = _stub("NURBS knot vectors are non-decreasing")
nurbs_knot_multiplicity = _stub("NURBS knot multiplicity <= degree")
polyline_closed = _stub(
    "Closed Polyline3D repeats its first point; adjacent segments coincide")
catalogue_holes_planar = _stub(
    "Catalogue hole contours are 2-D (Z=0) and centered at the origin")

# topology
panel_limited_by_closed = _stub("Panel LimitedBy resolves to one closed contour")
composite_curve_continuous = _stub(
    "CompositeCurve3D segments ordered end-to-end and continuous")
hole_contours_closed = _stub("Hole contours are closed")
hole_not_splitting_plate = _stub("A hole does not split a plate into disjoint regions")
seam_topology = _stub("Seams never connect boundary/seam/hole to a hole; "
                      "seam pattern yields closed plate contours")
compartment_closure = _stub("CompartmentFace/ContourBound curves closed; "
                            "CellBoundary forms a closed volume")
compartments_disjoint = _stub("Compartments do not physically overlap")
surface_normals_and_boundaries = _stub(
    "Surface-collection normals consistent; boundary loops closed, "
    "inner/outer distinguished")
stiffener_inclinations = _stub(
    "Stiffener inclinations: no duplicates, no web/flange vector flips")

# properties
plate_weight_consistent = _stub(
    "Plate weight ~= area x thickness x density within tolerance")
panel_weight_cog_consistent = _stub(
    "Panel weight/CoG consistent with its composed parts")
profile_closed_section = _stub(
    "Profile parameters reproduce a closed section contour")
renewal_thickness_on_instance = _stub(
    "Renewal thickness assigned to the part instance, not only a shared definition")
