"""Custom check callables for the best_practice pack.

Phase A: identity, document, references and curves_surfaces checks plus
OCX-PROP-004 are real implementations. Phase B implemented the geometry
checks in topology and properties; only the two compartment checks remain
stubs (see geometry_stubs). TOML rules address every name as
``ocx_rules.packs.best_practice.checks:<name>``.
"""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks.curves import (
    catalogue_holes_planar,
    nurbs_control_points,
    nurbs_knot_multiplicity,
    nurbs_knots_non_decreasing,
    polyline_closed,
)
from ocx_rules.packs.best_practice.checks.document import (
    enumerated_root_units,
    root_declarations,
    schema_location_tuple,
    unit_definitions,
    unit_refs_resolve,
)
from ocx_rules.packs.best_practice.checks.geometry_stubs import (
    compartment_closure,
    compartments_disjoint,
)
from ocx_rules.packs.best_practice.checks.identity import (
    entitybase_has_guid_and_id,
    idbase_has_id,
    names_not_identifiers,
)
from ocx_rules.packs.best_practice.checks.properties import (
    panel_weight_cog_consistent,
    plate_weight_consistent,
    profile_closed_section,
    renewal_thickness_on_instance,
)
from ocx_rules.packs.best_practice.checks.references import (
    explicit_connectivity,
    hole_single_representation,
    panel_as_occurrence_group,
    slot_lug_plate_refs,
    stiffener_end_configurations,
)
from ocx_rules.packs.best_practice.checks.topology import (
    composite_curve_continuous,
    hole_contours_closed,
    hole_not_splitting_plate,
    panel_limited_by_closed,
    seam_topology,
    stiffener_inclinations,
    surface_normals_and_boundaries,
)

__all__ = [
    "catalogue_holes_planar", "compartment_closure", "compartments_disjoint",
    "composite_curve_continuous", "entitybase_has_guid_and_id",
    "enumerated_root_units", "explicit_connectivity", "hole_contours_closed",
    "hole_not_splitting_plate", "hole_single_representation", "idbase_has_id",
    "names_not_identifiers", "nurbs_control_points", "nurbs_knot_multiplicity",
    "nurbs_knots_non_decreasing", "panel_as_occurrence_group",
    "panel_limited_by_closed", "panel_weight_cog_consistent",
    "plate_weight_consistent", "polyline_closed", "profile_closed_section",
    "renewal_thickness_on_instance", "root_declarations",
    "schema_location_tuple", "seam_topology", "slot_lug_plate_refs",
    "stiffener_end_configurations", "stiffener_inclinations",
    "surface_normals_and_boundaries", "unit_definitions", "unit_refs_resolve",
]
