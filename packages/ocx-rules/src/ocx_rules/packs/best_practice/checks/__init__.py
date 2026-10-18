"""Custom check callables for the best_practice pack.

Geometry checks live in :mod:`.geometry_stubs` and are re-exported here so
TOML ``custom = "ocx_rules.packs.best_practice.checks:<name>"`` paths keep
working. The remaining checks are stubs raising CheckNotImplemented until
real implementations replace them, keeping name and signature
``(context: ValidationContext, params: dict) -> list[Finding]``.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented

from .geometry_stubs import (
    compartment_closure,
    compartments_disjoint,
    composite_curve_continuous,
    hole_contours_closed,
    hole_not_splitting_plate,
    panel_limited_by_closed,
    panel_weight_cog_consistent,
    plate_weight_consistent,
    profile_closed_section,
    seam_topology,
    stiffener_inclinations,
    surface_normals_and_boundaries,
)
from .identity import (
    entitybase_has_guid_and_id,
    idbase_has_id,
    names_not_identifiers,
)

__all__ = [
    "compartment_closure",
    "compartments_disjoint",
    "composite_curve_continuous",
    "hole_contours_closed",
    "hole_not_splitting_plate",
    "panel_limited_by_closed",
    "panel_weight_cog_consistent",
    "plate_weight_consistent",
    "profile_closed_section",
    "seam_topology",
    "stiffener_inclinations",
    "surface_normals_and_boundaries",
    "entitybase_has_guid_and_id",
    "idbase_has_id",
    "names_not_identifiers",
    "schema_location_tuple",
    "root_declarations",
    "unit_definitions",
    "unit_refs_resolve",
    "enumerated_root_units",
    "stiffener_end_configurations",
    "slot_lug_plate_refs",
    "explicit_connectivity",
    "panel_as_occurrence_group",
    "hole_single_representation",
    "nurbs_control_points",
    "nurbs_knots_non_decreasing",
    "nurbs_knot_multiplicity",
    "polyline_closed",
    "catalogue_holes_planar",
    "renewal_thickness_on_instance",
]


def _stub(summary: str):
    def check(context, params):
        raise CheckNotImplemented(summary)

    check.__doc__ = summary
    return check


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

# properties
renewal_thickness_on_instance = _stub(
    "Renewal thickness assigned to the part instance, not only a shared definition")
