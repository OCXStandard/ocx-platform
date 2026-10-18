# OCX Rule Checks — Phase A (Content Checks) Implementation Plan

> **For agentic workers:** use subagent-driven-development or executing-plans to
> execute this plan task-by-task. Every task is TDD: write the test, watch it
> fail, implement, watch it pass, commit.

Spec: `docs/superpowers/specs/2026-10-18-ocx-rule-checks-phase-a-design.md` (approved).

**Goal:** real check logic for the 24 non-geometry rules (identity 5, document 5,
references 8, curves_surfaces 5, properties PROP-004). The 12 geometry rules
stay `CheckNotImplemented` stubs.

**Conventions (apply to every task):**
- Run tests from the repo root: `uv run pytest tests/<file> -q`.
- loguru only, no prints. Ruff: line length 100, rules E4/E7/E9/F/I.
- Commit after each green task with trailer
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- Check signature everywhere: `(context, params: dict) -> list[Finding]`;
  empty list = pass; zero matched elements = vacuous pass. Checks never raise
  on malformed content — they emit findings instead.

**Verified XML facts the code below relies on (do not re-derive):**
- OCX identity: elements carry un-namespaced `id` plus namespaced `ocx:GUIDRef`
  (values sometimes brace-wrapped `{...}`; compare case-insensitively without braces).
- OCX references are **elements** whose localname ends in `Ref` (`GridRef`,
  `HoleRef`, `PlateRef`, `StiffenerRef`, `LugPlateRef`, …) with attributes
  `localRef` (target id), `ocx:GUIDRef` (target GUID), `ocx:refType`.
  A `GUIDRef` on a `*Ref` element is a pointer, **not** an identity.
- DesignView trees: `OccurrenceGroup` (id, name, type) contains nested
  `OccurrenceGroup`/`Occurrence`; part references (`PlateRef`, `PanelRef`, …)
  are children of `Occurrence`.
- UnitsML: `<unitsml:Unit xml:id="u2" dimensionURL="ID2">` with children
  `UnitName`, `UnitSymbol type="mm"`, `RootUnits/EnumeratedRootUnit
  unit="meter" prefix="m" powerNumerator="1"`. Unit ids use the **xml**
  namespace (`xml:id`). OCX elements reference units via un-namespaced
  `unit="u2"` attributes.
- NURBS: `<ocx:NURBSproperties degree numCtrlPts numKnots .../>`,
  `<ocx:KnotVector value="space separated floats"/>`,
  `<ocx:ControlPtList><ocx:ControlPoint coordinates="x y z" .../>` — all
  siblings under the NURBS3D element. Polyline tag is `ocx:PolyLine3D`
  (capital L) with `isClosed`, child `ocx:Point3D coordinates="x y z" unit="u2"`.
- IR: `vessel.panels: dict[str, IrPanel]`, `IrPanel.limited_by:
  list[IrLimitedByRef]`, `IrPlate.renewal_thickness`,
  `IrBracket.renewal_thickness`, `IrStiffener.web_renewal_thickness` /
  `flange_renewal_thickness`, same pair on `IrPillar` and
  `IrEdgeReinforcement`.
- `ValidationContext.__init__(model_path)`; `xml_tree` / `vessel` are
  `cached_property`, so tests inject via `ctx.__dict__["xml_tree"] = tree`.

**Design deviations from the spec (intentional, keep):**
- `XmlIndex.refs` indexes `*Ref` **elements** (not attributes) — that is how
  OCX actually encodes references (verified against stubs).
- `unique` gains optional params `normalize = "guid"` and
  `exclude_tag_suffix = "Ref"` so OCX-ID-002 skips reference elements and
  brace-format differences; the TOML is updated accordingly.
- OCX-PROP-004 keeps `requires = ["ir"]` and uses IR + XML together:
  if **no** part instance carries renewal thickness in the IR, any
  `*RenewalThickness*` element in the XML must live on a shared definition →
  one finding per such element.

---

## Task 1 — XmlIndex + `context.xml_index` + inline-doc test helper

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/xml_index.py`
- Edit `packages/ocx-rules/src/ocx_rules/context.py`
- Create `tests/rules_xml.py`
- Create `tests/test_rules_xml_index.py`

**Step 1.1 — write `tests/rules_xml.py`** (test helper, not a test module):

```python
"""Inline OCX document builders for rule-check unit tests."""
from __future__ import annotations

from pathlib import Path

import lxml.etree as etree

from ocx_rules.context import ValidationContext

OCX_NS = "https://3docx.org/fileadmin//ocx_schema//V310//OCX_Schema.xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
UNITSML_NS = "urn:oasis:names:tc:unitsml:schema:xsd:UnitsMLSchema_lite-0.9.18"

DEFAULT_ROOT_ATTRS = f'xsi:schemaLocation="{OCX_NS} {OCX_NS}" schemaVersion="3.1.0"'


def ocx_doc(body: str = "", *, root_attrs: str | None = None) -> etree._ElementTree:
    """Wrap *body* fragments in a 3.1.0 ocxXML root with standard namespaces."""
    attrs = DEFAULT_ROOT_ATTRS if root_attrs is None else root_attrs
    xml = (
        f'<ocx:ocxXML xmlns:ocx="{OCX_NS}" xmlns:xsi="{XSI_NS}" '
        f'xmlns:unitsml="{UNITSML_NS}" {attrs}>\n{body}\n</ocx:ocxXML>'
    )
    return etree.ElementTree(etree.fromstring(xml.encode()))


def context_for(body: str = "", *, root_attrs: str | None = None) -> ValidationContext:
    """ValidationContext whose xml_tree is the inline document (no file I/O)."""
    ctx = ValidationContext(Path("inline.3docx"))
    ctx.__dict__["xml_tree"] = ocx_doc(body, root_attrs=root_attrs)
    return ctx


def context_for_xml(xml: str) -> ValidationContext:
    """ValidationContext for a complete raw XML document string."""
    ctx = ValidationContext(Path("inline.3docx"))
    ctx.__dict__["xml_tree"] = etree.ElementTree(etree.fromstring(xml.encode()))
    return ctx
```

**Step 1.2 — write `tests/test_rules_xml_index.py`:**

```python
"""Tests for the shared XmlIndex document scan."""
from __future__ import annotations

from ocx_rules.xml_index import XmlIndex, localname, normalize_guid
from tests.rules_xml import OCX_NS, context_for


def _index(body: str) -> XmlIndex:
    return context_for(body).xml_index


class TestHelpers:
    def test_localname_strips_namespace(self):
        assert localname(f"{{{OCX_NS}}}Panel") == "Panel"
        assert localname("Panel") == "Panel"
        assert localname(None) == ""

    def test_normalize_guid(self):
        assert normalize_guid("{ABC-123}") == "abc-123"
        assert normalize_guid(" abc-123 ") == "abc-123"


class TestXmlIndex:
    def test_nsmap_detected_from_root(self):
        idx = _index("")
        assert idx.nsmap["ocx"] == OCX_NS
        assert idx.nsmap["xsi"].endswith("XMLSchema-instance")

    def test_identity_elements_indexed(self):
        idx = _index('<ocx:Panel id="p1" ocx:GUIDRef="{AAA}" name="Deck"/>')
        assert idx.by_id["p1"].tag == "Panel"
        assert idx.by_guid["aaa"].name == "Deck"
        assert idx.by_id["p1"].sourceline is not None

    def test_duplicates_collected(self):
        idx = _index(
            '<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>'
            '<ocx:Plate id="p1" ocx:GUIDRef="{AAA}"/>'
        )
        assert [e.tag for e in idx.duplicate_ids["p1"]] == ["Plate"]
        assert [e.tag for e in idx.duplicate_guids["aaa"]] == ["Plate"]

    def test_ref_elements_are_refs_not_identities(self):
        idx = _index('<ocx:GridRef localRef="BP" ocx:GUIDRef="{BBB}" ocx:refType="ocx:ReferencePlane"/>')
        assert "bbb" not in idx.by_guid
        (ref,) = idx.refs
        assert (ref.tag, ref.local_ref, ref.guid, ref.ref_type) == (
            "GridRef", "BP", "bbb", "ocx:ReferencePlane")

    def test_xpath_uses_nsmap(self):
        idx = _index('<ocx:Panel id="p1"/>')
        assert len(idx.xpath("//ocx:Panel")) == 1

    def test_context_caches_index(self):
        ctx = context_for('<ocx:Panel id="p1"/>')
        assert ctx.xml_index is ctx.xml_index
```

**Step 1.3 — run and watch it fail:**
`uv run pytest tests/test_rules_xml_index.py -q` → `ModuleNotFoundError: ocx_rules.xml_index`.

**Step 1.4 — create `packages/ocx-rules/src/ocx_rules/xml_index.py`:**

```python
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
```

**Step 1.5 — edit `context.py`:** add after the `vessel` property:

```python
    @cached_property
    def xml_index(self) -> "XmlIndex":
        """Shared identity/reference index over the XML tree."""
        from ocx_rules.xml_index import XmlIndex

        return XmlIndex(self.xml_tree)
```

**Step 1.6 — run `uv run pytest tests/test_rules_xml_index.py -q` → all pass.
Also `uv run pytest tests/test_rules_context.py -q` (unchanged behaviour).**

**Step 1.7 — commit:** `feat(ocx-rules): shared XmlIndex document scan`

## Task 2 — content primitives (`has_attribute`, `unique`, `cardinality`, `value_in_set`, `sequence`)

**Files:**
- Rewrite `packages/ocx-rules/src/ocx_rules/primitives/content.py`
- Rewrite `tests/test_rules_primitives.py`

**Step 2.1 — rewrite `tests/test_rules_primitives.py`:**

```python
"""Tests for the check-primitive library (real implementations)."""
from __future__ import annotations

import pytest

from ocx_rules.model import CheckNotImplemented
from ocx_rules.primitives import PRIMITIVE_REGISTRY, content
from tests.rules_xml import context_for

EXPECTED_PRIMITIVES = {
    "has_attribute", "unique", "cardinality", "value_in_set", "sequence",
    "ref_resolves", "closed_contour", "normals_consistent",
}


class TestPrimitiveRegistry:
    def test_all_expected_primitives_registered(self):
        assert set(PRIMITIVE_REGISTRY) == EXPECTED_PRIMITIVES

    @pytest.mark.parametrize("name", ["closed_contour", "normals_consistent"])
    def test_geometry_primitives_still_stubbed(self, name):
        with pytest.raises(CheckNotImplemented):
            PRIMITIVE_REGISTRY[name](context=None, params={})


class TestHasAttribute:
    PARAMS = {"xpath": "//ocx:Panel", "attribute": "ocx:GUIDRef"}

    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>')
        assert content.has_attribute(ctx, self.PARAMS) == []

    def test_missing_and_empty_fail(self):
        ctx = context_for('<ocx:Panel id="p1"/><ocx:Panel id="p2" ocx:GUIDRef=" "/>')
        findings = content.has_attribute(ctx, self.PARAMS)
        assert len(findings) == 2
        assert "ocx:GUIDRef" in findings[0].message
        assert findings[0].location is not None

    def test_no_matches_is_vacuous_pass(self):
        assert content.has_attribute(context_for(""), self.PARAMS) == []


class TestUnique:
    PARAMS = {
        "xpath": "//*[@ocx:GUIDRef]", "key": "@ocx:GUIDRef",
        "normalize": "guid", "exclude_tag_suffix": "Ref",
    }

    def test_pass(self):
        ctx = context_for('<ocx:Panel ocx:GUIDRef="aaa"/><ocx:Plate ocx:GUIDRef="bbb"/>')
        assert content.unique(ctx, self.PARAMS) == []

    def test_duplicate_reported_once_with_all_lines(self):
        ctx = context_for(
            '<ocx:Panel ocx:GUIDRef="{AAA}"/>'
            '<ocx:Plate ocx:GUIDRef="aaa"/>'
            '<ocx:Bracket ocx:GUIDRef="AAA"/>'
        )
        (finding,) = content.unique(ctx, self.PARAMS)
        assert "aaa" in finding.message and "3" in finding.message

    def test_ref_elements_excluded(self):
        ctx = context_for(
            '<ocx:Panel ocx:GUIDRef="aaa"/>'
            '<ocx:GridRef ocx:GUIDRef="aaa"/><ocx:GridRef ocx:GUIDRef="aaa"/>'
        )
        assert content.unique(ctx, self.PARAMS) == []

    def test_plain_id_uniqueness(self):
        params = {"xpath": "//*[@id]", "key": "@id"}
        ctx = context_for('<ocx:Panel id="x"/><ocx:Plate id="x"/>')
        assert len(content.unique(ctx, params)) == 1


class TestCardinality:
    PARAMS = {"xpath": "//ocx:Panel", "child": "ocx:ComposedOf", "min": 1}

    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p"><ocx:ComposedOf/></ocx:Panel>')
        assert content.cardinality(ctx, self.PARAMS) == []

    def test_below_min_fails(self):
        ctx = context_for('<ocx:Panel id="p"/>')
        (finding,) = content.cardinality(ctx, self.PARAMS)
        assert "at least 1" in finding.message
        assert finding.element_id == "p"

    def test_above_max_fails(self):
        params = {"xpath": "//ocx:Vessel", "child": "ocx:CoordinateSystem", "min": 1, "max": 1}
        ctx = context_for(
            '<ocx:Vessel id="v"><ocx:CoordinateSystem/><ocx:CoordinateSystem/></ocx:Vessel>')
        (finding,) = content.cardinality(ctx, params)
        assert "at most 1" in finding.message


class TestValueInSet:
    PARAMS = {"xpath": "//ocx:Panel", "key": "@tightness", "allowed": ["WaterTight", "NonTight"]}

    def test_pass_and_missing_key_ignored(self):
        ctx = context_for('<ocx:Panel tightness="WaterTight"/><ocx:Panel id="x"/>')
        assert content.value_in_set(ctx, self.PARAMS) == []

    def test_bad_value_fails(self):
        ctx = context_for('<ocx:Panel tightness="Soggy"/>')
        (finding,) = content.value_in_set(ctx, self.PARAMS)
        assert "Soggy" in finding.message


class TestSequence:
    PARAMS = {"xpath": "//ocx:KnotVector", "key": "@value"}

    def test_non_decreasing_passes(self):
        ctx = context_for('<ocx:KnotVector value="0 0 1 2 2"/>')
        assert content.sequence(ctx, self.PARAMS) == []

    def test_decreasing_fails(self):
        ctx = context_for('<ocx:KnotVector value="0 2 1"/>')
        (finding,) = content.sequence(ctx, self.PARAMS)
        assert "non-decreasing" in finding.message

    def test_max_run_enforced(self):
        params = dict(self.PARAMS, max_run=2)
        ctx = context_for('<ocx:KnotVector value="0 1 1 1 2"/>')
        (finding,) = content.sequence(ctx, params)
        assert "repeated" in finding.message

    def test_non_numeric_is_finding_not_crash(self):
        ctx = context_for('<ocx:KnotVector value="0 x 1"/>')
        (finding,) = content.sequence(ctx, self.PARAMS)
        assert "numeric" in finding.message
```

**Step 2.2 — run, watch fail** (`CheckNotImplemented` raised by current stubs).

**Step 2.3 — rewrite `primitives/content.py`:**

```python
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
```

**Step 2.4 — run `uv run pytest tests/test_rules_primitives.py -q` → pass.**

**Step 2.5 — commit:** `feat(ocx-rules): implement content primitives`

---

## Task 3 — `ref_resolves` primitive + TOML updates

**Files:**
- Rewrite `packages/ocx-rules/src/ocx_rules/primitives/references.py`
- Edit `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/identity.toml`
- Edit `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/references.toml`
- Create `tests/test_rules_primitives_refs.py`

**Step 3.1 — write `tests/test_rules_primitives_refs.py`:**

```python
"""Tests for the ref_resolves primitive."""
from __future__ import annotations

from ocx_rules.primitives.references import ref_resolves
from tests.rules_xml import context_for


class TestRefResolves:
    def test_guid_reference_resolves(self):
        ctx = context_for(
            '<ocx:Plate id="pl1" ocx:GUIDRef="{AAA}"/>'
            '<ocx:PlateRef localRef="pl1" ocx:GUIDRef="aaa" ocx:refType="ocx:Plate"/>'
        )
        assert ref_resolves(ctx, {}) == []

    def test_dangling_guid_falls_back_to_local_ref(self):
        ctx = context_for(
            '<ocx:Plate id="pl1" ocx:GUIDRef="aaa"/>'
            '<ocx:PlateRef localRef="pl1" ocx:GUIDRef="zzz"/>'
        )
        assert ref_resolves(ctx, {}) == []

    def test_dangling_reference_fails(self):
        ctx = context_for('<ocx:GridRef localRef="nope" ocx:GUIDRef="zzz"/>')
        (finding,) = ref_resolves(ctx, {})
        assert "GridRef" in finding.message and "zzz" in finding.message
        assert finding.location is not None

    def test_local_only_reference(self):
        ctx = context_for(
            '<ocx:Section id="s1"/>'
            '<ocx:SectionRef localRef="s1"/><ocx:SectionRef localRef="s2"/>'
        )
        (finding,) = ref_resolves(ctx, {})
        assert "s2" in finding.message

    def test_no_references_is_vacuous_pass(self):
        assert ref_resolves(context_for('<ocx:Panel id="p"/>'), {}) == []
```

**Step 3.2 — run, watch fail. Step 3.3 — rewrite `primitives/references.py`:**

```python
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
```

**Step 3.4 — TOML updates.**
In `identity.toml`, OCX-ID-002 `[rule.check]` becomes:

```toml
[rule.check]
primitive          = "unique"
xpath              = "//*[@ocx:GUIDRef]"
key                = "@ocx:GUIDRef"
normalize          = "guid"
exclude_tag_suffix = "Ref"
```

In `references.toml`, OCX-REF-001 `[rule.check]` becomes (drop the obsolete
`ref_attribute`/`target_xpath` params — resolution is index-driven):

```toml
[rule.check]
primitive = "ref_resolves"
```

**Step 3.5 — run:**
`uv run pytest tests/test_rules_primitives_refs.py tests/test_rules_primitives.py tests/test_rules_best_practice_pack.py tests/test_rules_catalogue.py -q` → pass.

**Step 3.6 — commit:** `feat(ocx-rules): implement ref_resolves and wire identity/reference rules`

## Task 4 — convert `checks.py` into a `checks/` package (facade + geometry stubs)

**Files:**
- Delete `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks.py`
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/__init__.py`
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/geometry_stubs.py`

No new tests — the existing pack test (`test_custom_checks_importable`) is the
gate. TOML `custom = "ocx_rules.packs.best_practice.checks:<name>"` paths are
unchanged because the package `__init__` re-exports every name.

**Step 4.1 — create `checks/geometry_stubs.py`** with the 12 geometry stubs,
moved verbatim from the old `checks.py` (keep `_stub` and the exact summary
strings): `panel_limited_by_closed`, `composite_curve_continuous`,
`hole_contours_closed`, `hole_not_splitting_plate`, `seam_topology`,
`compartment_closure`, `compartments_disjoint`,
`surface_normals_and_boundaries`, `stiffener_inclinations`,
`plate_weight_consistent`, `panel_weight_cog_consistent`,
`profile_closed_section`. Module docstring:
`"""Phase B geometry checks — still stubs raising CheckNotImplemented."""`

**Step 4.2 — temporary facade.** Delete `checks.py`; create
`checks/__init__.py` that, for now, re-exports the geometry stubs AND keeps
the 19 Phase A names as `_stub(...)` definitions (copy them from the old
file). Tasks 5–9 then move each category into its own module and replace the
stub lines in the facade with re-export imports.

**Step 4.3 — run `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_manager.py -q` → pass.**

**Step 4.4 — commit:** `refactor(ocx-rules): split best_practice checks into a package`

---

## Task 5 — identity checks (`entitybase_has_guid_and_id`, `idbase_has_id`, `names_not_identifiers`)

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/identity.py`
- Edit `checks/__init__.py` (replace the three identity stubs with
  `from ocx_rules.packs.best_practice.checks.identity import (...)`)
- Create `tests/test_rules_checks_identity.py`

**Step 5.1 — write `tests/test_rules_checks_identity.py`:**

```python
"""Tests for identity best-practice checks (OCX-ID-001/004/005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    entitybase_has_guid_and_id,
    idbase_has_id,
    names_not_identifiers,
)
from tests.rules_xml import context_for


class TestEntityBaseHasGuidAndId:
    def test_pass(self):
        ctx = context_for('<ocx:Panel id="p1" ocx:GUIDRef="aaa"/>')
        assert entitybase_has_guid_and_id(ctx, {}) == []

    def test_missing_guid_and_missing_id(self):
        ctx = context_for('<ocx:Panel id="p1"/><ocx:Plate ocx:GUIDRef="bbb"/>')
        findings = entitybase_has_guid_and_id(ctx, {})
        assert len(findings) == 2
        assert "GUIDRef" in findings[0].message
        assert "id" in findings[1].message

    def test_non_entity_elements_ignored(self):
        ctx = context_for("<ocx:ComposedOf/><ocx:KnotVector/>")
        assert entitybase_has_guid_and_id(ctx, {}) == []


class TestIdBaseHasId:
    def test_pass_and_fail(self):
        ctx = context_for('<ocx:NURBS3D id="c1"/><ocx:PolyLine3D/>')
        (finding,) = idbase_has_id(ctx, {})
        assert "PolyLine3D" in finding.message


class TestNamesNotIdentifiers:
    def test_distinct_names_pass(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Panel id="b" name="Side"/>')
        assert names_not_identifiers(ctx, {}) == []

    def test_same_name_same_id_not_reported(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Panel id="a" name="Deck"/>')
        assert names_not_identifiers(ctx, {}) == []

    def test_collision_reported(self):
        ctx = context_for('<ocx:Panel id="a" name="Deck"/><ocx:Plate id="b" name="Deck"/>')
        (finding,) = names_not_identifiers(ctx, {})
        assert "Deck" in finding.message
```

**Step 5.2 — run, watch fail. Step 5.3 — create `checks/identity.py`:**

```python
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
```

**Step 5.4 — update facade, run
`uv run pytest tests/test_rules_checks_identity.py tests/test_rules_best_practice_pack.py -q` → pass.**

**Step 5.5 — commit:** `feat(ocx-rules): implement identity checks (ID-001/004/005)`

---

## Task 6 — document checks (DOC-001…005)

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/document.py`
- Edit `checks/__init__.py` (re-export the five names)
- Create `tests/test_rules_checks_document.py`

**Step 6.1 — write `tests/test_rules_checks_document.py`:**

```python
"""Tests for document/root/units best-practice checks (OCX-DOC-001..005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    enumerated_root_units,
    root_declarations,
    schema_location_tuple,
    unit_definitions,
    unit_refs_resolve,
)
from tests.rules_xml import OCX_NS, context_for, context_for_xml

UNITS = """
<unitsml:UnitsML><unitsml:UnitSet>
  <unitsml:Unit xml:id="u2">
    <unitsml:UnitName>millimetre</unitsml:UnitName>
    <unitsml:UnitSymbol type="mm"/>
    <unitsml:RootUnits>
      <unitsml:EnumeratedRootUnit unit="meter" prefix="m" powerNumerator="1"/>
    </unitsml:RootUnits>
  </unitsml:Unit>
</unitsml:UnitSet></unitsml:UnitsML>
"""


class TestSchemaLocationTuple:
    def test_identical_tuple_passes(self):
        assert schema_location_tuple(context_for(""), {}) == []

    def test_missing_attribute_fails(self):
        ctx = context_for("", root_attrs='schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "schemaLocation" in finding.message

    def test_namespace_absent_fails(self):
        ctx = context_for(
            "", root_attrs='xsi:schemaLocation="urn:other loc.xsd" schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "namespace" in finding.message.lower()

    def test_mismatched_pair_fails(self):
        ctx = context_for(
            "", root_attrs=f'xsi:schemaLocation="{OCX_NS} other.xsd" schemaVersion="3.1.0"')
        (finding,) = schema_location_tuple(ctx, {})
        assert "identical" in finding.message


class TestRootDeclarations:
    def test_pass(self):
        assert root_declarations(context_for(""), {}) == []

    def test_missing_schema_version(self):
        ctx = context_for("", root_attrs=f'xsi:schemaLocation="{OCX_NS} {OCX_NS}"')
        (finding,) = root_declarations(ctx, {})
        assert "schemaVersion" in finding.message

    def test_missing_xsi_declaration(self):
        xml = f'<ocx:ocxXML xmlns:ocx="{OCX_NS}" schemaVersion="3.1.0"/>'
        (finding,) = root_declarations(context_for_xml(xml), {})
        assert "xsi" in finding.message


class TestUnitDefinitions:
    def test_complete_unit_passes(self):
        assert unit_definitions(context_for(UNITS), {}) == []

    def test_missing_id_name_and_symbol(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                "<unitsml:Unit/></unitsml:UnitSet></unitsml:UnitsML>")
        messages = [f.message for f in unit_definitions(context_for(body), {})]
        assert any("xml:id" in m for m in messages)
        assert any("UnitName" in m for m in messages)
        assert any("UnitSymbol" in m for m in messages)

    def test_duplicate_unit_id(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>m</unitsml:UnitName>'
                "<unitsml:UnitSymbol/></unitsml:Unit>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>m</unitsml:UnitName>'
                "<unitsml:UnitSymbol/></unitsml:Unit>"
                "</unitsml:UnitSet></unitsml:UnitsML>")
        assert any("duplicate" in f.message for f in unit_definitions(context_for(body), {}))

    def test_no_unitsml_is_vacuous_pass(self):
        assert unit_definitions(context_for(""), {}) == []


class TestUnitRefsResolve:
    def test_resolving_ref_passes(self):
        body = UNITS + '<ocx:Thickness numericvalue="10" unit="u2"/>'
        assert unit_refs_resolve(context_for(body), {}) == []

    def test_dangling_unit_ref_fails(self):
        body = UNITS + '<ocx:Thickness numericvalue="10" unit="u9"/>'
        (finding,) = unit_refs_resolve(context_for(body), {})
        assert "u9" in finding.message


class TestEnumeratedRootUnits:
    def test_enumerated_unit_passes(self):
        assert enumerated_root_units(context_for(UNITS), {}) == []

    def test_common_symbol_without_enumeration_warns(self):
        body = ("<unitsml:UnitsML><unitsml:UnitSet>"
                '<unitsml:Unit xml:id="u1"><unitsml:UnitName>millimetre</unitsml:UnitName>'
                '<unitsml:UnitSymbol type="mm"/></unitsml:Unit>'
                "</unitsml:UnitSet></unitsml:UnitsML>")
        (finding,) = enumerated_root_units(context_for(body), {})
        assert "EnumeratedRootUnit" in finding.message
```

**Step 6.2 — run, watch fail. Step 6.3 — create `checks/document.py`:**

```python
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
```

**Step 6.4 — update facade, run
`uv run pytest tests/test_rules_checks_document.py tests/test_rules_best_practice_pack.py -q` → pass.**

**Step 6.5 — commit:** `feat(ocx-rules): implement document/root/units checks (DOC-001..005)`

## Task 7 — references checks (REF-003/004/005/007/008)

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/references.py`
- Edit `checks/__init__.py` (re-export the five names)
- Create `tests/test_rules_checks_references.py`

**Step 7.1 — write `tests/test_rules_checks_references.py`:**

```python
"""Tests for reference/connectivity best-practice checks."""
from __future__ import annotations

from dataclasses import dataclass, field

from ocx_rules.packs.best_practice.checks import (
    explicit_connectivity,
    hole_single_representation,
    panel_as_occurrence_group,
    slot_lug_plate_refs,
    stiffener_end_configurations,
)
from tests.rules_xml import context_for


class TestStiffenerEndConfigurations:
    def test_one_per_end_passes(self):
        ctx = context_for(
            '<ocx:Stiffener id="s1"><ocx:EndCutEnd1/><ocx:EndCutEnd2/></ocx:Stiffener>')
        assert stiffener_end_configurations(ctx, {}) == []

    def test_duplicate_end_fails(self):
        ctx = context_for(
            '<ocx:Stiffener id="s1"><ocx:EndCutEnd1/><ocx:EndCutEnd1/></ocx:Stiffener>')
        (finding,) = stiffener_end_configurations(ctx, {})
        assert "EndCutEnd1" in finding.message and finding.element_id == "s1"


class TestSlotLugPlateRefs:
    def test_two_lugs_pass(self):
        ctx = context_for(
            '<ocx:Slot><ocx:LugPlateRef localRef="a"/><ocx:LugPlateRef localRef="b"/></ocx:Slot>')
        assert slot_lug_plate_refs(ctx, {}) == []

    def test_three_lugs_fail(self):
        ctx = context_for(
            "<ocx:Slot>"
            '<ocx:LugPlateRef localRef="a"/><ocx:LugPlateRef localRef="b"/>'
            '<ocx:LugPlateRef localRef="c"/>'
            "</ocx:Slot>")
        (finding,) = slot_lug_plate_refs(ctx, {})
        assert "3" in finding.message


@dataclass
class _FakePanel:
    id: str
    name: str | None = None
    guidref: str | None = None
    limited_by: list = field(default_factory=list)


@dataclass
class _FakeVessel:
    panels: dict


class TestExplicitConnectivity:
    def _ctx(self, panels):
        ctx = context_for("")
        ctx.__dict__["vessel"] = _FakeVessel(panels={p.id: p for p in panels})
        return ctx

    def test_all_bounded_passes(self):
        ctx = self._ctx([_FakePanel("p1", limited_by=["x"])])
        assert explicit_connectivity(ctx, {}) == []

    def test_all_empty_passes_heuristic(self):
        ctx = self._ctx([_FakePanel("p1"), _FakePanel("p2")])
        assert explicit_connectivity(ctx, {}) == []

    def test_mixed_flags_unbounded_panel(self):
        ctx = self._ctx([_FakePanel("p1", limited_by=["x"]), _FakePanel("p2", name="Deck")])
        (finding,) = explicit_connectivity(ctx, {})
        assert finding.element_id == "p2" and "Deck" in finding.message


class TestPanelAsOccurrenceGroup:
    def test_panel_ref_on_group_passes(self):
        ctx = context_for(
            '<ocx:DesignView><ocx:OccurrenceGroup id="g1">'
            '<ocx:PanelRef localRef="p1" ocx:refType="ocx:Panel"/>'
            "</ocx:OccurrenceGroup></ocx:DesignView>")
        assert panel_as_occurrence_group(ctx, {}) == []

    def test_panel_ref_on_direct_occurrence_fails(self):
        ctx = context_for(
            '<ocx:DesignView><ocx:Occurrence id="o1">'
            '<ocx:PanelRef localRef="p1" ocx:refType="ocx:Panel"/>'
            "</ocx:Occurrence></ocx:DesignView>")
        (finding,) = panel_as_occurrence_group(ctx, {})
        assert "OccurrenceGroup" in finding.message


class TestHoleSingleRepresentation:
    def test_cutby_only_passes(self):
        ctx = context_for(
            '<ocx:Plate id="pl"><ocx:CutBy><ocx:Hole2DContour id="h">'
            '<ocx:HoleRef localRef="hc" ocx:GUIDRef="aaa"/>'
            "</ocx:Hole2DContour></ocx:CutBy></ocx:Plate>")
        assert hole_single_representation(ctx, {}) == []

    def test_both_representations_fail(self):
        ctx = context_for(
            '<ocx:Plate id="pl">'
            '<ocx:CutBy><ocx:Hole2DContour id="h">'
            '<ocx:HoleRef localRef="hc" ocx:GUIDRef="{AAA}"/>'
            "</ocx:Hole2DContour></ocx:CutBy>"
            '<ocx:OuterContour><ocx:HoleRef localRef="hc" ocx:GUIDRef="aaa"/></ocx:OuterContour>'
            "</ocx:Plate>")
        (finding,) = hole_single_representation(ctx, {})
        assert "aaa" in finding.message
```

**Step 7.2 — run, watch fail. Step 7.3 — create `checks/references.py`:**

```python
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
```

**Step 7.4 — update facade, run
`uv run pytest tests/test_rules_checks_references.py tests/test_rules_best_practice_pack.py -q` → pass.**

**Step 7.5 — commit:** `feat(ocx-rules): implement reference/connectivity checks (REF-003..008)`

---

## Task 8 — curves/surfaces checks (GEO-001…005)

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/curves.py`
- Edit `checks/__init__.py` (re-export the five names)
- Create `tests/test_rules_checks_curves.py`

**Step 8.1 — write `tests/test_rules_checks_curves.py`:**

```python
"""Tests for curve/surface well-formedness checks (OCX-GEO-001..005)."""
from __future__ import annotations

from ocx_rules.packs.best_practice.checks import (
    catalogue_holes_planar,
    nurbs_control_points,
    nurbs_knot_multiplicity,
    nurbs_knots_non_decreasing,
    polyline_closed,
)
from tests.rules_xml import context_for


def _nurbs(degree: int, knots: str, points: int) -> str:
    ctrl = "".join(
        f'<ocx:ControlPoint coordinates="{i} 0 0" weight="1.0"/>' for i in range(points))
    return (
        f'<ocx:NURBS3D id="c1">'
        f'<ocx:NURBSproperties degree="{degree}" numCtrlPts="{points}" '
        f'numKnots="{len(knots.split())}" form="Open" isRational="false"/>'
        f'<ocx:KnotVector value="{knots}"/>'
        f"<ocx:ControlPtList>{ctrl}</ocx:ControlPtList>"
        f"</ocx:NURBS3D>")


class TestNurbsControlPoints:
    def test_enough_points_passes(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 1 1 1", 4))
        assert nurbs_control_points(ctx, {}) == []

    def test_too_few_points_fails(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 1 1 1", 3))
        (finding,) = nurbs_control_points(ctx, {})
        assert "degree" in finding.message

    def test_missing_degree_is_finding(self):
        ctx = context_for('<ocx:NURBS3D id="c1"><ocx:NURBSproperties/></ocx:NURBS3D>')
        (finding,) = nurbs_control_points(ctx, {})
        assert "degree" in finding.message


class TestNurbsKnots:
    def test_sorted_knots_pass(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 0.5 1 1 1 1", 5))
        assert nurbs_knots_non_decreasing(ctx, {}) == []
        assert nurbs_knot_multiplicity(ctx, {}) == []

    def test_decreasing_knots_fail(self):
        ctx = context_for(_nurbs(3, "0 0 0 0 1 0.5 1 1 1", 5))
        (finding,) = nurbs_knots_non_decreasing(ctx, {})
        assert "non-decreasing" in finding.message

    def test_interior_multiplicity_above_degree_fails(self):
        ctx = context_for(_nurbs(2, "0 0 0 0.5 0.5 0.5 1 1 1", 6))
        (finding,) = nurbs_knot_multiplicity(ctx, {})
        assert "multiplicity" in finding.message

    def test_clamped_end_multiplicity_allowed(self):
        ctx = context_for(_nurbs(2, "0 0 0 1 1 1", 3))
        assert nurbs_knot_multiplicity(ctx, {}) == []


class TestPolylineClosed:
    def _poly(self, closed: str, coords: list[str]) -> str:
        pts = "".join(f'<ocx:Point3D coordinates="{c}"/>' for c in coords)
        return f'<ocx:PolyLine3D id="p1" isClosed="{closed}">{pts}</ocx:PolyLine3D>'

    def test_closed_loop_passes(self):
        ctx = context_for(self._poly("true", ["0 0 0", "10 0 0", "10 10 0", "0 0 0"]))
        assert polyline_closed(ctx, {"tolerance_mm": 0.1}) == []

    def test_open_gap_fails(self):
        ctx = context_for(self._poly("true", ["0 0 0", "10 0 0", "10 10 0"]))
        (finding,) = polyline_closed(ctx, {"tolerance_mm": 0.1})
        assert "mm" in finding.message

    def test_unclosed_polyline_ignored(self):
        ctx = context_for(self._poly("false", ["0 0 0", "10 0 0"]))
        assert polyline_closed(ctx, {"tolerance_mm": 0.1}) == []


class TestCatalogueHolesPlanar:
    def test_planar_contour_passes(self):
        ctx = context_for(
            "<ocx:HoleShapeCatalogue><ocx:Hole2D id=\"h1\">"
            '<ocx:Point3D coordinates="0 0 0"/><ocx:Point3D coordinates="5 5 0"/>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        assert catalogue_holes_planar(ctx, {"tolerance_mm": 0.1}) == []

    def test_out_of_plane_point_fails(self):
        ctx = context_for(
            "<ocx:HoleShapeCatalogue><ocx:Hole2D id=\"h1\">"
            '<ocx:Point3D coordinates="0 0 7.5"/>'
            "</ocx:Hole2D></ocx:HoleShapeCatalogue>")
        (finding,) = catalogue_holes_planar(ctx, {"tolerance_mm": 0.1})
        assert "Z" in finding.message
```

**Step 8.2 — run, watch fail. Step 8.3 — create `checks/curves.py`:**

```python
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
    return idx.xpath("//ocx:NURBSproperties")


def nurbs_control_points(context, params: dict) -> list[Finding]:
    """OCX-GEO-001: control-point count >= degree + 1."""
    idx = context.xml_index
    findings = []
    for props in _nurbs_nodes(idx):
        parent = props.getparent()
        where = f"<{localname(parent.tag)}> at line {parent.sourceline}"
        degree = _int_of(props, "degree")
        if degree is None:
            findings.append(Finding(
                message=f"{where} NURBSproperties has no integer 'degree'",
                element_id=parent.get("id"), location=props.sourceline))
            continue
        points = parent.xpath("./ocx:ControlPtList/ocx:ControlPoint", namespaces=idx.nsmap)
        count = len(points) or _int_of(props, "numCtrlPts") or 0
        if count < degree + 1:
            findings.append(Finding(
                message=(f"{where} has {count} control points; a degree-{degree} "
                         f"NURBS needs at least {degree + 1}"),
                element_id=parent.get("id"), location=props.sourceline))
    return findings


def _knot_vectors(idx):
    for kv in idx.xpath("//ocx:KnotVector"):
        parent = kv.getparent()
        props = parent.xpath("./ocx:NURBSproperties", namespaces=idx.nsmap)
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
```

**Step 8.4 — update facade, run
`uv run pytest tests/test_rules_checks_curves.py tests/test_rules_best_practice_pack.py -q` → pass.**

**Step 8.5 — commit:** `feat(ocx-rules): implement curve/surface checks (GEO-001..005)`

## Task 9 — properties check (PROP-004) + final facade

**Files:**
- Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py`
- Finalize `checks/__init__.py`
- Create `tests/test_rules_checks_properties.py`

**Step 9.1 — write `tests/test_rules_checks_properties.py`:**

```python
"""Tests for OCX-PROP-004 renewal_thickness_on_instance."""
from __future__ import annotations

from dataclasses import dataclass, field

from ocx_rules.packs.best_practice.checks import renewal_thickness_on_instance
from tests.rules_xml import context_for


@dataclass
class _Part:
    id: str
    renewal_thickness: object = None
    web_renewal_thickness: object = None
    flange_renewal_thickness: object = None


@dataclass
class _Vessel:
    plates: dict = field(default_factory=dict)
    brackets: dict = field(default_factory=dict)
    stiffeners: dict = field(default_factory=dict)
    pillars: dict = field(default_factory=dict)
    edge_reinforcements: dict = field(default_factory=dict)


def _ctx(body: str, vessel: _Vessel) -> object:
    ctx = context_for(body)
    ctx.__dict__["vessel"] = vessel
    return ctx


class TestRenewalThicknessOnInstance:
    def test_no_renewal_anywhere_passes(self):
        ctx = _ctx('<ocx:Plate id="p"/>', _Vessel(plates={"p": _Part("p")}))
        assert renewal_thickness_on_instance(ctx, {}) == []

    def test_instance_level_renewal_passes(self):
        body = ('<ocx:XSectionCatalogue><ocx:BarSection id="b">'
                '<ocx:WebRenewalThickness numericvalue="2" unit="u1"/>'
                "</ocx:BarSection></ocx:XSectionCatalogue>")
        vessel = _Vessel(stiffeners={"s": _Part("s", web_renewal_thickness=object())})
        assert renewal_thickness_on_instance(_ctx(body, vessel), {}) == []

    def test_shared_definition_only_fails(self):
        body = ('<ocx:XSectionCatalogue><ocx:BarSection id="b">'
                '<ocx:WebRenewalThickness numericvalue="2" unit="u1"/>'
                "</ocx:BarSection></ocx:XSectionCatalogue>")
        vessel = _Vessel(stiffeners={"s": _Part("s")})
        (finding,) = renewal_thickness_on_instance(_ctx(body, vessel), {})
        assert "instance" in finding.message
```

**Step 9.2 — run, watch fail. Step 9.3 — create `checks/properties.py`:**

```python
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
```

**Step 9.4 — finalize `checks/__init__.py`.** All 19 Phase A stubs are now
replaced; the facade is only imports + `__all__`:

```python
"""Custom check callables for the best_practice pack.

Phase A: identity, document, references and curves_surfaces checks plus
OCX-PROP-004 are real implementations; the 12 geometry checks remain stubs
(see geometry_stubs, Phase B). TOML rules address every name as
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
    composite_curve_continuous,
    hole_contours_closed,
    hole_not_splitting_plate,
    panel_limited_by_closed,
    panel_weight_cog_consistent,
    plate_weight_consistent,
    profile_closed_section,
    seam_topology,
    stiffener_inclinations,
    surface_normals_and_boundaries,
)
from ocx_rules.packs.best_practice.checks.identity import (
    entitybase_has_guid_and_id,
    idbase_has_id,
    names_not_identifiers,
)
from ocx_rules.packs.best_practice.checks.properties import (
    renewal_thickness_on_instance,
)
from ocx_rules.packs.best_practice.checks.references import (
    explicit_connectivity,
    hole_single_representation,
    panel_as_occurrence_group,
    slot_lug_plate_refs,
    stiffener_end_configurations,
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
```

**Step 9.5 — run `uv run pytest tests/test_rules_checks_properties.py tests/test_rules_best_practice_pack.py -q` → pass.**

**Step 9.6 — commit:** `feat(ocx-rules): implement PROP-004 and finalize checks facade`

---

## Task 10 — corpus integration test

**Files:**
- Create `tests/test_rules_corpus.py`

**Step 10.1 — create the test** (marked `integration`, deselected by default):

```python
"""Integration: the full best_practice pack never crashes on real models.

Reference models are expected to FAIL rules — failures are fine; CRASHED is
not. Run explicitly with:  uv run pytest tests/test_rules_corpus.py -m integration -q
"""
from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger

from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import RuleStatus

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MODELS = sorted(MODELS_DIR.rglob("*.3docx")) if MODELS_DIR.is_dir() else []

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("model", MODELS, ids=lambda p: p.name)
def test_no_rule_crashes(model: Path):
    results = RuleManager().run(ValidationContext(model))
    summary: dict[str, int] = {}
    for r in results:
        summary[r.status.value] = summary.get(r.status.value, 0) + 1
    logger.info("{}: {}", model.name, summary)
    crashed = [r for r in results if r.status is RuleStatus.CRASHED]
    details = "; ".join(f"{r.spec.rule_id}: {r.reason}" for r in crashed)
    assert not crashed, f"{model.name} crashed rules — {details}"
```

**Step 10.2 — verify it is deselected by default** (`uv run pytest tests/test_rules_corpus.py -q`
reports all deselected), then run it for real:
`uv run pytest tests/test_rules_corpus.py -m integration -q` (expect several
minutes; ~90 models). Fix any CRASHED rule by hardening the offending check
(findings, never exceptions) until the run is green.

**Step 10.3 — commit:** `test(ocx-rules): corpus integration run over models/`

---

## Task 11 — full verification + smoke run

1. `uv run pytest -q` — full suite green (previously 838 passed / 41 skipped;
   expect a higher pass count now).
2. `uv run ruff check .` — clean (the 2 pre-existing E402s in
   `tests/test_diag_hooks.py` stay).
3. Smoke run:
   `uv run validator validate rules models/D-VLCC_1-HOLD-OCX-simple_v3.3docx`
   — expect 24 rules PASSED/FAILED with meaningful findings, 12
   NOT_IMPLEMENTED, exit code reflecting failures.
4. Docs touch-up: in `README.md` and `.github/copilot-instructions.md`, note
   that the 24 content rules are implemented and the 12 geometry rules await
   Phase B; mention `ocx_rules/xml_index.py` and the `checks/` package in the
   layout tree.
5. Commit: `docs: Phase A rule checks implemented` and report back for the
   finishing-a-development-branch decision.

---

## Definition of done (from the spec)

- 24 Phase A rules report real PASSED/FAILED on stub and corpus models; 12
  geometry rules remain NOT_IMPLEMENTED.
- `validator validate rules models/D-VLCC_1-HOLD-OCX-simple_v3.3docx` gives a
  meaningful report.
- Full test suite and `ruff check .` green.
- Integration corpus run: zero CRASHED rules across all models.




