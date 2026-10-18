"""Property best-practice checks implemented in Phase A (OCX-PROP-004)."""
from __future__ import annotations

from ocx_rules.model import Finding
from ocx_rules.xml_index import localname


def _any_instance_renewal(vessel) -> bool:
    for part in (*vessel.plates.values(), *vessel.brackets.values()):
        if part.renewal_thickness is not None:
            return True
    for part in (*vessel.stiffeners.values(), *vessel.pillars.values(),
                 *vessel.edge_reinforcements.values()):
        if (part.web_renewal_thickness is not None
                or part.flange_renewal_thickness is not None):
            return True
    return False


def renewal_thickness_on_instance(context, params: dict) -> list[Finding]:
    """OCX-PROP-004: renewal thickness must reach the part instance.

    The IR builder only picks up instance-level renewal thickness (part
    attributes or the per-instance SectionRef). If the document declares
    renewal-thickness elements but no instance carries any, the values live
    only on a shared definition — one finding per declaration.
    """
    if _any_instance_renewal(context.vessel):
        return []
    findings = []
    for el in context.xml_index.root.iter():
        tag = localname(el.tag)
        if "RenewalThickness" in tag:
            findings.append(Finding(
                message=(f"<{tag}> at line {el.sourceline} declares renewal thickness "
                         f"on a shared definition only; assign it to the individual "
                         f"part instance"),
                location=el.sourceline))
    return findings
