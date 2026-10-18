"""Phase B geometry checks — still stubs raising CheckNotImplemented."""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented


def _stub(summary: str):
    def check(context, params):
        raise CheckNotImplemented(summary)

    check.__doc__ = summary
    return check


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
