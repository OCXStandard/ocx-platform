"""Reference/connectivity best-practice checks."""
from __future__ import annotations

from ocx_rules.model import Finding
from ocx_rules.xml_index import localname, normalize_guid


def stiffener_end_configurations(context, params: dict) -> list[Finding]:
    """OCX-REF-003: at most one end configuration per stiffener end."""
    idx = context.xml_index
    findings = []
    for st in idx.xpath("//ocx:Stiffener"):
        counts: dict[str, int] = {}
        for child in st:
            tag = localname(child.tag)
            if tag.startswith("EndCut"):
                counts[tag] = counts.get(tag, 0) + 1
        for tag, n in counts.items():
            if n > 1:
                findings.append(Finding(
                    message=(f"<Stiffener> at line {st.sourceline} has {n} <{tag}> "
                             f"end configurations; expected at most one per end"),
                    element_id=st.get("id"), location=st.sourceline))
        if sum(counts.values()) > 2:
            findings.append(Finding(
                message=(f"<Stiffener> at line {st.sourceline} has more than two "
                         f"end configurations"),
                element_id=st.get("id"), location=st.sourceline))
    return findings


def slot_lug_plate_refs(context, params: dict) -> list[Finding]:
    """OCX-REF-004: a slot connection carries at most two LugPlateRef."""
    idx = context.xml_index
    by_parent: dict = {}
    for ref in idx.xpath("//ocx:LugPlateRef"):
        parent = ref.getparent()
        if parent is not None:
            by_parent.setdefault(parent, []).append(ref)
    findings = []
    for parent, refs in by_parent.items():
        if len(refs) > 2:
            findings.append(Finding(
                message=(f"<{localname(parent.tag)}> at line {parent.sourceline} carries "
                         f"{len(refs)} <LugPlateRef> references; a slot has at most two "
                         f"lug plates"),
                element_id=parent.get("id"), location=parent.sourceline))
    return findings


def explicit_connectivity(context, params: dict) -> list[Finding]:
    """OCX-REF-005 (ir): panels without LimitedBy boundaries while sibling
    panels declare them (heuristic)."""
    panels = list(context.vessel.panels.values())
    if not any(p.limited_by for p in panels):
        return []
    return [
        Finding(
            message=(f"Panel '{p.name or p.id}' declares no LimitedBy boundary "
                     f"references while other panels do; connectivity must be "
                     f"encoded explicitly"),
            element_id=p.id, guid=p.guidref)
        for p in panels if not p.limited_by
    ]


def panel_as_occurrence_group(context, params: dict) -> list[Finding]:
    """OCX-REF-007: a PanelRef in a DesignView must sit on an OccurrenceGroup,
    never on a direct Occurrence."""
    idx = context.xml_index
    findings = []
    for ref in idx.xpath("//ocx:Occurrence/ocx:PanelRef"):
        raw_guid = ref.get(idx.guid_attr)
        findings.append(Finding(
            message=(f"<PanelRef> at line {ref.sourceline} is attached to a direct "
                     f"<Occurrence>; a Panel must be represented as an OccurrenceGroup"),
            guid=normalize_guid(raw_guid) if raw_guid else None,
            location=ref.sourceline))
    return findings


def hole_single_representation(context, params: dict) -> list[Finding]:
    """OCX-REF-008 (warning): a hole GUID referenced from CutBy must not also
    appear under the plate's OuterContour."""
    idx = context.xml_index
    findings = []
    for plate in idx.xpath("//ocx:Plate"):
        def _guids(expr: str) -> set[str]:
            values = set()
            for el in plate.xpath(expr, namespaces=idx.nsmap):
                raw = el.get(idx.guid_attr)
                if raw:
                    values.add(normalize_guid(raw))
            return values

        cut = _guids(".//ocx:CutBy//ocx:HoleRef")
        outer = _guids(".//ocx:OuterContour//*[@ocx:GUIDRef]")
        for guid in sorted(cut & outer):
            findings.append(Finding(
                message=(f"hole '{guid}' on Plate '{plate.get('id')}' appears both in "
                         f"CutBy and in OuterContour; use a single representation"),
                element_id=plate.get("id"), guid=guid, location=plate.sourceline))
    return findings
