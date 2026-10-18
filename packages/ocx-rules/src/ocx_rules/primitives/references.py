"""Reference-resolution primitive built on the shared XmlIndex."""
from __future__ import annotations

from ocx_rules.model import Finding


def ref_resolves(context, params: dict) -> list[Finding]:
    """Every indexed ``*Ref`` element resolves to an existing identity.

    Resolution order: normalized GUID against the identity GUID set, then
    ``localRef`` against the id set. References carrying neither attribute
    (pure container elements) are skipped.
    """
    idx = context.xml_index
    findings = []
    for ref in idx.refs:
        if ref.guid is not None:
            if ref.guid in idx.by_guid or (ref.local_ref and ref.local_ref in idx.by_id):
                continue
            findings.append(Finding(
                message=(f"<{ref.tag}> at line {ref.sourceline} does not resolve: "
                         f"no element with GUIDRef '{ref.guid}'"),
                guid=ref.guid, location=ref.sourceline))
        elif ref.local_ref is not None and ref.local_ref not in idx.by_id:
            findings.append(Finding(
                message=(f"<{ref.tag}> at line {ref.sourceline} does not resolve: "
                         f"no element with id '{ref.local_ref}'"),
                element_id=ref.local_ref, location=ref.sourceline))
    return findings
