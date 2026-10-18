"""Content primitives — namespace-aware XML checks shared by many rules."""
from __future__ import annotations

from ocx_rules.model import Finding
from ocx_rules.xml_index import localname, normalize_guid


def _elements(context, xpath: str) -> list:
    return [el for el in context.xml_index.xpath(xpath) if isinstance(el.tag, str)]


def _attr(el, key: str, nsmap: dict[str, str]) -> str | None:
    """Resolve an '@id' / '@ocx:GUIDRef' style key against an element."""
    name = key.lstrip("@")
    if ":" in name:
        prefix, local = name.split(":", 1)
        return el.get(f"{{{nsmap[prefix]}}}{local}")
    return el.get(name)


def _where(el) -> str:
    return f"<{localname(el.tag)}> at line {el.sourceline}"


def has_attribute(context, params: dict) -> list[Finding]:
    """Every element matched by ``xpath`` carries a non-empty ``attribute``."""
    nsmap = context.xml_index.nsmap
    findings = []
    for el in _elements(context, params["xpath"]):
        value = _attr(el, params["attribute"], nsmap)
        if value is None or not value.strip():
            findings.append(Finding(
                message=f"{_where(el)} is missing attribute '{params['attribute']}'",
                element_id=el.get("id"), location=el.sourceline))
    return findings


def unique(context, params: dict) -> list[Finding]:
    """``key`` values are unique across elements matched by ``xpath``.

    Optional params: ``normalize = "guid"`` (brace/case-insensitive compare),
    ``exclude_tag_suffix`` (skip e.g. ``*Ref`` reference elements).
    """
    nsmap = context.xml_index.nsmap
    suffix = params.get("exclude_tag_suffix")
    seen: dict[str, list] = {}
    for el in _elements(context, params["xpath"]):
        if suffix and localname(el.tag).endswith(suffix):
            continue
        value = _attr(el, params["key"], nsmap)
        if value is None:
            continue
        if params.get("normalize") == "guid":
            value = normalize_guid(value)
        seen.setdefault(value, []).append(el)
    findings = []
    for value, els in seen.items():
        if len(els) > 1:
            lines = ", ".join(str(e.sourceline) for e in els)
            findings.append(Finding(
                message=(f"{params['key']} value '{value}' is used by {len(els)} "
                         f"elements (lines {lines}); values must be unique"),
                location=els[0].sourceline))
    return findings


def cardinality(context, params: dict) -> list[Finding]:
    """Per element matched by ``xpath``, count of direct ``child`` children
    lies within ``min``/``max`` bounds."""
    nsmap = context.xml_index.nsmap
    lo, hi = params.get("min"), params.get("max")
    findings = []
    for el in _elements(context, params["xpath"]):
        count = len(el.xpath(f"./{params['child']}", namespaces=nsmap))
        if lo is not None and count < lo:
            findings.append(Finding(
                message=(f"{_where(el)} has {count} <{params['child']}> children, "
                         f"expected at least {lo}"),
                element_id=el.get("id"), location=el.sourceline))
        elif hi is not None and count > hi:
            findings.append(Finding(
                message=(f"{_where(el)} has {count} <{params['child']}> children, "
                         f"expected at most {hi}"),
                element_id=el.get("id"), location=el.sourceline))
    return findings


def value_in_set(context, params: dict) -> list[Finding]:
    """``key`` value, when present, is a member of ``allowed``."""
    nsmap = context.xml_index.nsmap
    allowed = set(params["allowed"])
    findings = []
    for el in _elements(context, params["xpath"]):
        value = _attr(el, params["key"], nsmap)
        if value is not None and value not in allowed:
            findings.append(Finding(
                message=(f"{_where(el)} has {params['key']} value '{value}', "
                         f"expected one of {sorted(allowed)}"),
                element_id=el.get("id"), location=el.sourceline))
    return findings


def sequence(context, params: dict) -> list[Finding]:
    """Space-separated numeric ``key`` obeys ordering and ``max_run`` limits."""
    nsmap = context.xml_index.nsmap
    order = params.get("order", "non_decreasing")
    max_run = params.get("max_run")
    findings = []
    for el in _elements(context, params["xpath"]):
        raw = _attr(el, params["key"], nsmap)
        if raw is None:
            continue
        try:
            values = [float(token) for token in raw.split()]
        except ValueError:
            findings.append(Finding(
                message=f"{_where(el)} {params['key']} is not a numeric list",
                element_id=el.get("id"), location=el.sourceline))
            continue
        if order == "non_decreasing" and any(b < a for a, b in zip(values, values[1:])):
            findings.append(Finding(
                message=f"{_where(el)} {params['key']} values are not non-decreasing",
                element_id=el.get("id"), location=el.sourceline))
        if max_run is not None and values:
            run = longest = 1
            for a, b in zip(values, values[1:]):
                run = run + 1 if b == a else 1
                longest = max(longest, run)
            if longest > max_run:
                findings.append(Finding(
                    message=(f"{_where(el)} {params['key']} has a value repeated "
                             f"{longest} times (max {max_run})"),
                    element_id=el.get("id"), location=el.sourceline))
    return findings
