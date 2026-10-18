"""Curve/surface well-formedness checks — pure XML numerics, no geometry kernel."""
from __future__ import annotations

import math

from ocx_rules.model import Finding
from ocx_rules.xml_index import XML_NS, localname

_XML_ID = f"{{{XML_NS}}}id"

#: metric prefix of an EnumeratedRootUnit 'meter' → scale factor to millimetres.
_PREFIX_TO_MM = {"": 1000.0, "m": 1.0, "c": 10.0, "d": 100.0, "k": 1_000_000.0}


def _int_of(el, attribute: str) -> int | None:
    try:
        return int(el.get(attribute))
    except (TypeError, ValueError):
        return None


def _floats_of(raw: str | None) -> list[float] | None:
    if raw is None:
        return None
    try:
        return [float(token) for token in raw.split()]
    except ValueError:
        return None


def _unit_scales_mm(idx) -> dict[str, float]:
    """Best-effort map of UnitsML unit xml:id → factor to millimetres."""
    scales: dict[str, float] = {}
    for unit in idx.xpath("//unitsml:Unit"):
        uid = unit.get(_XML_ID)
        roots = unit.xpath(".//unitsml:EnumeratedRootUnit", namespaces=idx.nsmap)
        if uid and roots and roots[0].get("unit") == "meter":
            scales[uid] = _PREFIX_TO_MM.get(roots[0].get("prefix") or "", 1.0)
    return scales


def _nurbs_nodes(idx) -> list:
    """NURBSproperties of curves plus the per-direction surface variants."""
    return idx.xpath(
        "//ocx:NURBSproperties | //ocx:U_NURBSproperties | //ocx:V_NURBSproperties")


def nurbs_control_points(context, params: dict) -> list[Finding]:
    """OCX-GEO-001: control-point count >= degree + 1."""
    idx = context.xml_index
    findings = []
    for props in _nurbs_nodes(idx):
        parent = props.getparent()
        props_tag = localname(props.tag)
        where = f"<{localname(parent.tag)}> at line {parent.sourceline}"
        degree = _int_of(props, "degree")
        if degree is None:
            findings.append(Finding(
                message=f"{where} {props_tag} has no integer 'degree'",
                element_id=parent.get("id"), location=props.sourceline))
            continue
        if props_tag == "NURBSproperties":
            points = parent.xpath("./ocx:ControlPtList/ocx:ControlPoint", namespaces=idx.nsmap)
            count = len(points) or _int_of(props, "numCtrlPts") or 0
        else:
            # Surface U/V direction: the control-point grid cannot be counted
            # per direction, so trust the declared numCtrlPts.
            count = _int_of(props, "numCtrlPts") or 0
        if count < degree + 1:
            findings.append(Finding(
                message=(f"{where} has {count} control points ({props_tag}); a "
                         f"degree-{degree} NURBS needs at least {degree + 1}"),
                element_id=parent.get("id"), location=props.sourceline))
    return findings


#: knot-vector element name → matching NURBS-properties element name.
_KNOTS_TO_PROPS = {
    "KnotVector": "NURBSproperties",
    "UknotVector": "U_NURBSproperties",
    "VknotVector": "V_NURBSproperties",
}


def _knot_vectors(idx):
    for kv in idx.xpath("//ocx:KnotVector | //ocx:UknotVector | //ocx:VknotVector"):
        parent = kv.getparent()
        props_name = _KNOTS_TO_PROPS[localname(kv.tag)]
        props = parent.xpath(f"./ocx:{props_name}", namespaces=idx.nsmap)
        degree = _int_of(props[0], "degree") if props else None
        yield kv, parent, degree


def nurbs_knots_non_decreasing(context, params: dict) -> list[Finding]:
    """OCX-GEO-002: knot vectors are non-decreasing."""
    findings = []
    for kv, parent, _degree in _knot_vectors(context.xml_index):
        values = _floats_of(kv.get("value"))
        where = f"<{localname(parent.tag)}> at line {parent.sourceline}"
        if values is None:
            findings.append(Finding(
                message=f"{where} KnotVector is not a numeric list",
                element_id=parent.get("id"), location=kv.sourceline))
        elif any(b < a for a, b in zip(values, values[1:])):
            findings.append(Finding(
                message=f"{where} knot vector is not non-decreasing",
                element_id=parent.get("id"), location=kv.sourceline))
    return findings


def nurbs_knot_multiplicity(context, params: dict) -> list[Finding]:
    """OCX-GEO-003: interior knot multiplicity <= degree (clamped ends may
    reach degree + 1)."""
    findings = []
    for kv, parent, degree in _knot_vectors(context.xml_index):
        values = _floats_of(kv.get("value"))
        if values is None or degree is None or not values:
            continue  # GEO-002 / GEO-001 report the malformed cases
        runs: list[int] = [1]
        for a, b in zip(values, values[1:]):
            if b == a:
                runs[-1] += 1
            else:
                runs.append(1)
        where = f"<{localname(parent.tag)}> at line {parent.sourceline}"
        for i, run in enumerate(runs):
            limit = degree + 1 if i in (0, len(runs) - 1) else degree
            if run > limit:
                findings.append(Finding(
                    message=(f"{where} has knot multiplicity {run} exceeding the "
                             f"allowed {limit} (degree {degree})"),
                    element_id=parent.get("id"), location=kv.sourceline))
    return findings


def polyline_closed(context, params: dict) -> list[Finding]:
    """OCX-GEO-004: a closed PolyLine3D repeats its first point within tolerance."""
    idx = context.xml_index
    tol = float(params.get("tolerance_mm", 0.1))
    scales = _unit_scales_mm(idx)
    findings = []
    for pl in idx.xpath("//ocx:PolyLine3D"):
        if (pl.get("isClosed") or "").lower() != "true":
            continue
        where = f"<PolyLine3D> at line {pl.sourceline}"
        points: list[list[float]] = []
        malformed = False
        for p in pl.xpath("./ocx:Point3D", namespaces=idx.nsmap):
            coords = _floats_of(p.get("coordinates"))
            if coords is None or len(coords) != 3:
                findings.append(Finding(
                    message=f"{where} has a Point3D with malformed coordinates",
                    element_id=pl.get("id"), location=p.sourceline))
                malformed = True
                break
            scale = scales.get(p.get("unit"), 1.0)
            points.append([c * scale for c in coords])
        if malformed or len(points) < 2:
            continue
        gap = math.dist(points[0], points[-1])
        if gap > tol:
            findings.append(Finding(
                message=(f"{where} is marked closed but first and last points are "
                         f"{gap:.3f} mm apart (tolerance {tol} mm)"),
                element_id=pl.get("id"), location=pl.sourceline))
    return findings


def catalogue_holes_planar(context, params: dict) -> list[Finding]:
    """OCX-GEO-005 (warning): catalogue hole contour points lie in Z = 0."""
    idx = context.xml_index
    tol = float(params.get("tolerance_mm", 0.1))
    scales = _unit_scales_mm(idx)
    findings = []
    for point in idx.xpath("//ocx:HoleShapeCatalogue//*[@coordinates]"):
        coords = _floats_of(point.get("coordinates"))
        if coords is None or len(coords) != 3:
            continue
        z_mm = coords[2] * scales.get(point.get("unit"), 1.0)
        if abs(z_mm) > tol:
            findings.append(Finding(
                message=(f"catalogue hole point at line {point.sourceline} has "
                         f"Z = {z_mm:.3f} mm; contours must be planar (Z = 0)"),
                location=point.sourceline))
    return findings
