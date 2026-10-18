"""Document/root/units best-practice checks (wiki: schema_root_element, units)."""
from __future__ import annotations

from ocx_rules.model import Finding
from ocx_rules.xml_index import UNITSML_NS, XML_NS, XSI_NS, localname

_XML_ID = f"{{{XML_NS}}}id"
_SCHEMA_LOCATION = f"{{{XSI_NS}}}schemaLocation"

#: UnitsML enumerates root units for these common symbols.
COMMON_ROOT_SYMBOLS = frozenset({
    "m", "mm", "cm", "dm", "km", "g", "kg", "t", "N", "kN", "MN",
    "Pa", "kPa", "MPa", "s", "deg", "rad",
})


def _units(context) -> list:
    return context.xml_index.xpath("//unitsml:Unit")


def schema_location_tuple(context, params: dict) -> list[Finding]:
    """OCX-DOC-001: xsi:schemaLocation holds the (namespace, location) tuple;
    for OCX both entries must be identical."""
    idx = context.xml_index
    root = idx.root
    raw = root.get(_SCHEMA_LOCATION)
    if raw is None:
        return [Finding(message="root element has no xsi:schemaLocation attribute",
                        location=root.sourceline)]
    tokens = raw.split()
    findings = []
    if len(tokens) % 2:
        findings.append(Finding(
            message="xsi:schemaLocation must hold (namespace, location) pairs",
            location=root.sourceline))
    pairs = dict(zip(tokens[0::2], tokens[1::2]))
    ocx_ns = idx.nsmap["ocx"]
    if ocx_ns not in pairs:
        findings.append(Finding(
            message=f"xsi:schemaLocation does not name the OCX namespace '{ocx_ns}'",
            location=root.sourceline))
    elif pairs[ocx_ns] != ocx_ns:
        findings.append(Finding(
            message=(f"OCX schemaLocation tuple entries must be identical, got "
                     f"location '{pairs[ocx_ns]}' for namespace '{ocx_ns}'"),
            location=root.sourceline))
    return findings


def root_declarations(context, params: dict) -> list[Finding]:
    """OCX-DOC-002: schemaVersion, xmlns:ocx and xmlns:xsi present on the root."""
    root = context.xml_index.root
    declared = set(root.nsmap.values())
    findings = []
    if not root.get("schemaVersion"):
        findings.append(Finding(
            message="root element is missing the schemaVersion attribute",
            location=root.sourceline))
    if context.xml_index.nsmap["ocx"] not in declared:
        findings.append(Finding(
            message="root element does not declare the OCX namespace",
            location=root.sourceline))
    if XSI_NS not in declared:
        findings.append(Finding(
            message="root element does not declare the xsi namespace",
            location=root.sourceline))
    return findings


def unit_definitions(context, params: dict) -> list[Finding]:
    """OCX-DOC-003: every Unit has a unique xml:id and a UnitName; a missing
    UnitSymbol is reported as an advisory finding."""
    findings = []
    seen: set[str] = set()
    for unit in _units(context):
        uid = unit.get(_XML_ID)
        where = f"<Unit> at line {unit.sourceline}"
        if not uid:
            findings.append(Finding(message=f"{where} has no xml:id", location=unit.sourceline))
        elif uid in seen:
            findings.append(Finding(
                message=f"{where} has duplicate xml:id '{uid}'", location=unit.sourceline))
        else:
            seen.add(uid)
        children = {localname(c.tag) for c in unit}
        if "UnitName" not in children:
            findings.append(Finding(
                message=f"{where} has no UnitName", location=unit.sourceline))
        if "UnitSymbol" not in children:
            findings.append(Finding(
                message=f"advisory: {where} has no UnitSymbol", location=unit.sourceline))
    return findings


def unit_refs_resolve(context, params: dict) -> list[Finding]:
    """OCX-DOC-004: every unit/dimension reference resolves to a declaration."""
    idx = context.xml_index
    declared = {u.get(_XML_ID) for u in _units(context)} - {None}
    findings = []
    for el in idx.root.iter():
        if not isinstance(el.tag, str) or el.tag.startswith("{" + UNITSML_NS):
            continue  # UnitsML elements use 'unit' as an enumeration name, not a reference
        ref = el.get("unit")
        if ref and ref not in declared:
            findings.append(Finding(
                message=(f"<{localname(el.tag)}> at line {el.sourceline} references "
                         f"undeclared unit '{ref}'"),
                location=el.sourceline))
    dims = {d.get(_XML_ID) for d in idx.xpath("//unitsml:Dimension")} - {None}
    if dims:
        for unit in _units(context):
            durl = unit.get("dimensionURL")
            if durl and durl not in dims:
                findings.append(Finding(
                    message=(f"<Unit> at line {unit.sourceline} references undeclared "
                             f"dimension '{durl}'"),
                    location=unit.sourceline))
    return findings


def enumerated_root_units(context, params: dict) -> list[Finding]:
    """OCX-DOC-005 (warning): units with a common symbol should declare
    UnitsML enumerated root units."""
    idx = context.xml_index
    findings = []
    for unit in _units(context):
        symbol = None
        for child in unit:
            if localname(child.tag) == "UnitSymbol":
                symbol = child.get("type")
        if symbol in COMMON_ROOT_SYMBOLS:
            enumerated = unit.xpath(
                ".//unitsml:EnumeratedRootUnit", namespaces=idx.nsmap)
            if not enumerated:
                findings.append(Finding(
                    message=(f"<Unit> '{unit.get(_XML_ID)}' (symbol '{symbol}') at line "
                             f"{unit.sourceline} should declare an EnumeratedRootUnit"),
                    location=unit.sourceline))
    return findings
