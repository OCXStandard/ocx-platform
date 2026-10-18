"""Identity best-practice checks (wiki page: guidsidsandnames)."""
from __future__ import annotations

from ocx_rules.model import Finding
from ocx_rules.xml_index import localname

#: EntityBase-derived structural objects that must carry GUIDRef + id.
ENTITY_TAGS = frozenset({
    "Vessel", "Panel", "Plate", "Bracket", "Stiffener", "Pillar", "Seam",
    "Member", "EdgeReinforcement", "Compartment", "PhysicalSpace",
    "Material", "Steel", "Aluminium", "Hole2D",
})

#: IDBase-derived geometry objects that must carry a local id.
GEOMETRY_TAGS = frozenset({
    "NURBS3D", "NURBSSurface", "PolyLine3D", "Line3D", "CircumArc3D",
    "Circle3D", "Ellipse3D", "CompositeCurve3D", "Plane3D", "Cylinder3D",
    "Cone3D", "Sphere3D", "ExtrudedSurface", "Surface", "SurfaceCollection",
})


def _tagged_elements(context):
    for el in context.xml_index.root.iter():
        tag = localname(el.tag)
        if tag:
            yield tag, el


def entitybase_has_guid_and_id(context, params: dict) -> list[Finding]:
    """OCX-ID-001: EntityBase objects carry both GUIDRef and id."""
    guid_attr = context.xml_index.guid_attr
    findings = []
    for tag, el in _tagged_elements(context):
        if tag not in ENTITY_TAGS:
            continue
        missing = []
        if not el.get("id"):
            missing.append("id")
        if not el.get(guid_attr):
            missing.append("GUIDRef")
        if missing:
            findings.append(Finding(
                message=f"<{tag}> at line {el.sourceline} is missing {' and '.join(missing)}",
                element_id=el.get("id"), location=el.sourceline))
    return findings


def idbase_has_id(context, params: dict) -> list[Finding]:
    """OCX-ID-004: IDBase geometry objects carry a local id."""
    findings = []
    for tag, el in _tagged_elements(context):
        if tag in GEOMETRY_TAGS and not el.get("id"):
            findings.append(Finding(
                message=f"<{tag}> at line {el.sourceline} is missing a local id",
                location=el.sourceline))
    return findings


def names_not_identifiers(context, params: dict) -> list[Finding]:
    """OCX-ID-005 (info): the same name on elements with different ids."""
    by_name: dict[str, list] = {}
    for _tag, el in _tagged_elements(context):
        name = el.get("name")
        if name:
            by_name.setdefault(name, []).append(el)
    findings = []
    for name, els in by_name.items():
        ids = {el.get("id") for el in els}
        if len(els) > 1 and len(ids) > 1:
            lines = ", ".join(str(e.sourceline) for e in els)
            findings.append(Finding(
                message=(f"name '{name}' is shared by {len(els)} elements with "
                         f"different ids (lines {lines}); names must never be "
                         f"used as identifiers"),
                location=els[0].sourceline))
    return findings
