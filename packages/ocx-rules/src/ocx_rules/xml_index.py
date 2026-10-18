"""XmlIndex — one shared scan of the lxml document for all content checks.

OCX identity: elements (Panel, Plate, ...) carry an un-namespaced ``id`` and
a namespaced ``ocx:GUIDRef``. OCX references are *elements* whose localname
ends in ``Ref`` (GridRef, HoleRef, PlateRef, ...) carrying ``localRef``
(target id), ``ocx:GUIDRef`` (target GUID) and ``ocx:refType``. A GUIDRef on
a ``*Ref`` element is therefore a pointer, not an identity.

The namespace map is detected from the document root, so rules written with
the ``ocx:`` prefix work for OCX 3.x and legacy 2.8.6 documents alike.
"""
from __future__ import annotations

from dataclasses import dataclass

import lxml.etree as etree

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"
UNITSML_NS = "urn:oasis:names:tc:unitsml:schema:xsd:UnitsMLSchema_lite-0.9.18"


def localname(tag: object) -> str:
    """Local name of an lxml tag; comments/PIs (non-str tags) give ''."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def normalize_guid(value: str) -> str:
    """Strip optional braces and whitespace, lowercase a GUID string."""
    return value.strip().lstrip("{").rstrip("}").lower()


@dataclass(frozen=True)
class ElementInfo:
    """Identity facts about one non-reference element."""

    tag: str
    id: str | None
    guid: str | None  # normalized
    name: str | None
    sourceline: int | None


@dataclass(frozen=True)
class RefInfo:
    """One reference occurrence (an element whose localname ends in 'Ref')."""

    tag: str
    local_ref: str | None
    guid: str | None  # normalized
    ref_type: str | None
    sourceline: int | None


class XmlIndex:
    """Identity/reference index built in a single document scan."""

    def __init__(self, tree: etree._ElementTree) -> None:
        self.tree = tree
        self.root = tree.getroot()
        ocx_ns = etree.QName(self.root).namespace or ""
        self.nsmap: dict[str, str] = {
            "ocx": ocx_ns,
            "xsi": XSI_NS,
            "xml": XML_NS,
            "unitsml": UNITSML_NS,
        }
        self.guid_attr = f"{{{ocx_ns}}}GUIDRef"
        self.reftype_attr = f"{{{ocx_ns}}}refType"
        self.by_id: dict[str, ElementInfo] = {}
        self.duplicate_ids: dict[str, list[ElementInfo]] = {}
        self.by_guid: dict[str, ElementInfo] = {}
        self.duplicate_guids: dict[str, list[ElementInfo]] = {}
        self.refs: list[RefInfo] = []
        self._scan()

    def _scan(self) -> None:
        for el in self.root.iter():
            tag = localname(el.tag)
            if not tag:
                continue
            raw_guid = el.get(self.guid_attr)
            guid = normalize_guid(raw_guid) if raw_guid else None
            if tag.endswith("Ref"):
                self.refs.append(RefInfo(
                    tag=tag,
                    local_ref=el.get("localRef"),
                    guid=guid,
                    ref_type=el.get(self.reftype_attr),
                    sourceline=el.sourceline,
                ))
                continue
            info = ElementInfo(
                tag=tag, id=el.get("id"), guid=guid,
                name=el.get("name"), sourceline=el.sourceline,
            )
            if info.id is not None:
                if info.id in self.by_id:
                    self.duplicate_ids.setdefault(info.id, []).append(info)
                else:
                    self.by_id[info.id] = info
            if info.guid is not None:
                if info.guid in self.by_guid:
                    self.duplicate_guids.setdefault(info.guid, []).append(info)
                else:
                    self.by_guid[info.guid] = info

    def xpath(self, expr: str) -> list:
        """Evaluate *expr* with the detected namespace map."""
        return self.tree.xpath(expr, namespaces=self.nsmap)
