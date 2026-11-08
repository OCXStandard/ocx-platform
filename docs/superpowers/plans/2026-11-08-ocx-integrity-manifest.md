# OCX Integrity Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `ocx-integrity` workspace package. It assigns every OCX part a stable part ID plus canonical, salted per-aspect hashes, and rolls them up in an RFC 9162 Merkle tree to one manifest root. It also provides verify, diff, selective-disclosure proof bundles and a CLI.

**Architecture:** Versioned extractors (`records/*.py`) turn each part of the schema-neutral `IrVessel` into per-aspect canonical records: identity, material, scantlings, geometry, physical. Normalisation converts quantities to SI decimal strings, resolves references to part IDs, sorts unordered collections and canonicalises closed contours. Each record is JCS-serialised (RFC 8785) and hashed with an HMAC-derived salt. Aspect hashes form a per-part Merkle tree, and part hashes form the model tree. The normative spec is `docs/superpowers/specs/2026-11-08-ocx-integrity-manifest-design.md` (profile `ocx-hash/1`).

**Tech Stack:** Python ≥3.12, uv workspace, `rfc8785` (Trail of Bits JCS), stdlib `hashlib`/`hmac`/`decimal`, `typer`, `loguru`, pytest.

---

## Conventions for every task

- Run everything from the repo root `C:\PythonDev\ocx-platform` with `uv` (never bare `pip`/`python`).
- Logging uses `loguru` only. No `print()` outside the CLI's `typer.echo`.
- Ruff line length is 100. Check with `uv run ruff check packages/ocx-integrity tests/test_integrity_*.py tests/integrity_fixtures.py`.
- Every commit message ends with the trailer:
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- Tests live in the shared root `tests/` folder. `tests/` is a package (`tests/__init__.py` exists) and pytest runs with `pythonpath = ["."]`, so tests import shared fixtures with `from tests.integrity_fixtures import ...`.
- Stub `.3docx` files under `tests/data/` are XML fragments and do not build into an `IrVessel`. Use the synthetic vessel in `tests/integrity_fixtures.py` instead.

## File map

```
packages/ocx-integrity/
  pyproject.toml              Task 1  package metadata + deps + script entry point
  README.md, CHANGELOG.md     Task 1 (stub), Task 14 (final)
  src/ocx_integrity/
    __init__.py               Task 1 (docstring only), Task 12 (public API)
    errors.py                 Task 1  exception hierarchy
    profile.py                Task 2  PROFILE, ASPECTS, KINDS, precision table
    quantize.py               Task 2  Quantity/point/vector → SI decimal strings
    jsonutil.py               Task 3  prune(), type_name(), sort_jcs(), dataclass_dict()
    canon_geom.py             Task 3  canonical curve dicts + closed-contour normalisation
    records/
      common.py               Task 4  Context (refs, warnings, canon), part_id(), shared helpers
      __init__.py             Task 5  EXTRACTORS, PartRecords, iter_parts()
      plate.py stiffener.py bracket.py pillar.py edge_reinforcement.py
      panel.py seam.py compartment.py vessel.py      Task 5
    salts.py                  Task 6  derive_salt(), load_key(), generate_key()
    hashing.py                Task 6  payload(), aspect_hash()
    merkle.py                 Task 7  RFC 9162 mth(), inclusion_path(), root_from_path()
    manifest.py               Task 8  hash_vessel(), Manifest, build/save/load
    diff.py                   Task 9  ChangeReport, diff_manifests(), format_report()
    verify.py                 Task 9  verify_model()
    proof.py                  Task 10 DisclosureBundle, prove(), check_bundle()
    cli.py                    Task 11 `ocx-integrity` typer app
tests/
  integrity_fixtures.py       Task 2  synthetic IrVessel + unit registry + KEY
  test_integrity_canon.py     Tasks 2–5, 8  quantize/geometry/record/invariance tests
  test_integrity_hashing.py   Task 6
  test_integrity_merkle.py    Task 7
  test_integrity_manifest.py  Task 8
  test_integrity_diff.py      Task 9
  test_integrity_proof.py     Task 10
  test_integrity_cli.py       Task 11
  test_integrity_golden.py    Task 12 (+ tests/data/integrity/golden_v1.json)
  test_integrity_model.py     Task 13 (models/TR02/TR02_TC01_ai3dx.3docx)
README.md, .github/copilot-instructions.md   Task 14
```

`jsonutil.py` is a small addition to the spec's layout. It holds the JSON helpers that `canon_geom.py` and `records/common.py` both need, which avoids a circular import.

---

### Task 1: Package scaffold and errors

**Files:**
- Create: `packages/ocx-integrity/pyproject.toml`
- Create: `packages/ocx-integrity/README.md`
- Create: `packages/ocx-integrity/CHANGELOG.md`
- Create: `packages/ocx-integrity/src/ocx_integrity/__init__.py`
- Create: `packages/ocx-integrity/src/ocx_integrity/errors.py`

- [ ] **Step 1: Create `packages/ocx-integrity/pyproject.toml`**

```toml
[project]
name = "ocx-integrity"
version = "0.1.0"
description = "Canonical salted per-aspect hashes + Merkle manifest for OCX models (ocx-hash/1)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "ocx-model-core>=0.5,<0.6",
    "rfc8785>=0.1.4",
    "typer>=0.9",
    "loguru>=0.7",
]

[project.scripts]
ocx-integrity = "ocx_integrity.cli:entrypoint"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ocx_integrity"]

[tool.uv.sources]
ocx-model-core = { workspace = true }
```

- [ ] **Step 2: Create `packages/ocx-integrity/README.md`** (a stub for now; Task 14 completes it)

```markdown
# ocx-integrity

Canonical, salted per-aspect hashes and a Merkle manifest root for OCX models
(profile `ocx-hash/1`). See
`docs/superpowers/specs/2026-11-08-ocx-integrity-manifest-design.md`.
```

- [ ] **Step 3: Create `packages/ocx-integrity/CHANGELOG.md`**

```markdown
# Changelog — ocx-integrity

## Unreleased

- Initial package scaffold.
```

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/__init__.py`**

```python
"""ocx-integrity — canonical salted aspect hashes + Merkle manifest (profile ocx-hash/1)."""
```

- [ ] **Step 5: Create `packages/ocx-integrity/src/ocx_integrity/errors.py`**

```python
"""Exception hierarchy for ocx-integrity."""
from __future__ import annotations


class IntegrityError(Exception):
    """Base class for all ocx-integrity errors."""


class InvalidKeyError(IntegrityError):
    """The yard key is missing, not hex, or shorter than 32 bytes."""


class DuplicatePartIdError(IntegrityError):
    """Two parts resolve to the same part ID (e.g. a reused GUID)."""

    def __init__(self, part_ids: list[str]) -> None:
        self.part_ids = part_ids
        super().__init__(f"duplicate part IDs: {', '.join(part_ids)}")


class ProfileMismatchError(IntegrityError):
    """A manifest/bundle uses a profile other than the one expected."""


class UnknownPartError(IntegrityError):
    """A requested part ID or aspect is not present in the manifest."""


class PartDriftError(IntegrityError):
    """The model's rebuilt part hash differs from the manifest entry."""
```

- [ ] **Step 6: Install the new member and confirm it imports**

Run: `uv sync --all-packages; uv run python -c "import ocx_integrity, ocx_integrity.errors, rfc8785; print(rfc8785.dumps({'b': 1, 'a': '2'}))"`
Expected: the last line prints `b'{"a":"2","b":1}'`.

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-integrity uv.lock
git commit -m "feat(integrity): scaffold ocx-integrity package

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Profile constants, quantizer and shared test fixtures

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/profile.py`
- Create: `packages/ocx-integrity/src/ocx_integrity/quantize.py`
- Create: `tests/integrity_fixtures.py`
- Test: `tests/test_integrity_canon.py`

- [ ] **Step 1: Create the shared fixtures `tests/integrity_fixtures.py`**

Later tasks use this synthetic vessel, so it is created in full here. It contains no `ocx_integrity` imports.

```python
"""Synthetic IrVessel + unit registry shared by the ocx-integrity tests."""
from __future__ import annotations

from ocx_model_core.model.ir import (
    IrCog,
    IrCompartment,
    IrFlatBarSection,
    IrHole2D,
    IrHole2DContour,
    IrHoleShapeCatalogue,
    IrLimitedByRef,
    IrLine3D,
    IrMassProperties,
    IrMaterial,
    IrPanel,
    IrParametricHole,
    IrPlane3D,
    IrPlate,
    IrPoint3D,
    IrPolyLine3D,
    IrPrincipalParticulars,
    IrSeam,
    IrShipDesignation,
    IrStiffener,
    IrTransformation,
    IrUnboundedGeometry,
    IrUnit,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)

KEY = bytes(range(32))  # deterministic 32-byte test key
OTHER_KEY = bytes(range(1, 33))


def registry() -> dict[str, IrUnit]:
    return {
        "Um": IrUnit("Um", "meter", "m", "D_L", 1.0, "m"),
        "Umm": IrUnit("Umm", "millimeter", "mm", "D_L", 0.001, "m"),
        "Um3": IrUnit("Um3", "cubic meter", "m3", "D_L3", 1.0, "m³"),
        "Ucm4": IrUnit("Ucm4", "cm4", "cm4", "D_L4", 1e-8, "m⁴"),
        "Ukg": IrUnit("Ukg", "kilogram", "kg", "D_Kg", 1.0, "kg"),
        "Ut": IrUnit("Ut", "tonne", "t", "D_Kg", 1000.0, "kg"),
        "UNOvermm2": IrUnit("UNOvermm2", "N/mm2", "N/mm2", "D_N.MM-2", 1e6, "Pa"),
        "Ukgm3": IrUnit("Ukgm3", "kg/m3", "kg/m3", "D_Kg.M-3", 1.0, "kg/m³"),
        "UDimless": IrUnit("UDimless", "dimensionless", "", None, 1.0, ""),
    }


def square(unit: str = "Umm", size: float = 2000.0, start: int = 0,
           reverse: bool = False, repeat_first: bool = False) -> IrPolyLine3D:
    """Closed square in the z=0 plane, counter-clockwise seen from +z."""
    corners = [(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]
    if reverse:
        corners = corners[::-1]
    corners = corners[start:] + corners[:start]
    verts = [IrPoint3D(x, y, 0.0, unit) for x, y in corners]
    if repeat_first:
        verts.append(verts[0])
    return IrPolyLine3D(curve_length=Quantity(4 * size, unit), vertices=verts, is_closed=True)


def hole(x: float, y: float, hid: str = "HA") -> IrHole2DContour:
    return IrHole2DContour(
        id=hid,
        hole_ref=Ref("H1"),
        transformation=IrTransformation(
            origin=IrPoint3D(x, y, 0.0, "Umm"),
            primary_axis=IrVector3D(1.0, 0.0, 0.0),
            secondary_axis=IrVector3D(0.0, 1.0, 0.0),
        ),
    )


def make_vessel() -> IrVessel:
    """Small vessel: 1 panel, 1 plate, 1 stiffener, 1 seam, 1 compartment."""
    panel_parent = ParentRef(ParentKind.PANEL, "P1")
    material = IrMaterial(
        id="M1", guidref="G-MAT-1", grade="AH36",
        density=Quantity(7850.0, "Ukgm3"),
        yield_stress=Quantity(355.0, "UNOvermm2"),
        youngs_modulus=Quantity(206000.0, "UNOvermm2"),
    )
    section = IrFlatBarSection(
        id="S1", name="FB200x12", section_type="FlatBar",
        height=Quantity(200.0, "Umm"), width=Quantity(12.0, "Umm"),
    )
    holes = IrHoleShapeCatalogue(id="HC", holes={
        "H1": IrHole2D(id="H1", guidref="G-HOLE-1",
                       parametric=IrParametricHole(variant="circle",
                                                   diameter=Quantity(100.0, "Umm"))),
    })
    plate = IrPlate(
        id="PL1", guidref="G-PL-1", parent_ref=panel_parent, name="Deck plate",
        material_ref=Ref("M1", "G-MAT-1"), thickness=Quantity(12.0, "Umm"),
        mass_properties=IrMassProperties(
            moulded_dry_weight=Quantity(1500.0, "Ukg"),
            moulded_cog=IrCog(1000.0, 1000.0, 0.0, "Umm"),
        ),
        outer_contour=square(),
        cut_by_holes=[hole(500.0, 500.0, "HA"), hole(1500.0, 1500.0, "HB")],
    )
    stiffener = IrStiffener(
        id="ST1", parent_ref=panel_parent, name="L1",
        material_ref=Ref("M1"), section_ref=Ref("S1"),
        trace=IrLine3D(curve_length=Quantity(2000.0, "Umm"),
                       start=IrPoint3D(0.0, 1000.0, 0.0, "Umm"),
                       end=IrPoint3D(2000.0, 1000.0, 0.0, "Umm")),
        orientation_rule="ocx:Up",
    )
    seam = IrSeam(
        id="SE1", name="Butt 1",
        trace_line=IrLine3D(curve_length=Quantity(2000.0, "Umm"),
                            start=IrPoint3D(1000.0, 0.0, 0.0, "Umm"),
                            end=IrPoint3D(1000.0, 2000.0, 0.0, "Umm")),
    )
    panel = IrPanel(
        id="P1", guidref="G-PAN-1", name="Deck", tightness="WaterTight",
        plate_ids=["PL1"], stiffener_ids=["ST1"], seam_ids=["SE1"],
        limited_by=[IrLimitedByRef("SeamRef", "SE1"), IrLimitedByRef("StiffenerRef", "ST1")],
        unbounded_geometry=IrUnboundedGeometry(surface=IrPlane3D(
            point_on_surface=IrPoint3D(0.0, 0.0, 0.0, "Umm"),
            normal=IrVector3D(0.0, 0.0, 1.0))),
        mass_properties=IrMassProperties(moulded_dry_weight=Quantity(1.8, "Ut")),
    )
    compartment = IrCompartment(
        id="C1", guidref="G-COMP-1", name="WBT1", compartment_purpose="Ballast",
        volume=Quantity(250.0, "Um3"), face_refs=[Ref("P1", "G-PAN-1")],
    )
    return IrVessel(
        id="V1", name="Test vessel", schema_version="3.1.0", unit_registry=registry(),
        panels={"P1": panel}, plates={"PL1": plate}, stiffeners={"ST1": stiffener},
        seams={"SE1": seam}, materials={"M1": material}, sections={"S1": section},
        hole_shape_catalogue=holes, compartments={"C1": compartment},
        ship_designation=IrShipDesignation(ship_name="TEST", number_imo="1234567"),
        principal_particulars=IrPrincipalParticulars(lpp=Quantity(100.0, "Um")),
    )
```

- [ ] **Step 2: Write the failing quantizer tests in `tests/test_integrity_canon.py`**

```python
"""Canonicalisation tests: quantizer, geometry, records, invariance (ocx-hash/1)."""
from __future__ import annotations

from decimal import Decimal

from ocx_model_core.model.ir import IrPoint3D, IrVector3D, Quantity

from ocx_integrity.quantize import Quantizer, fmt_decimal
from tests.integrity_fixtures import registry


def _quantizer() -> tuple[Quantizer, list[str]]:
    warnings: list[str] = []
    return Quantizer(registry(), warnings.append), warnings


def test_fmt_decimal_rounds_half_even():
    assert fmt_decimal(Decimal("0.0000005"), 6) == "0.000000"
    assert fmt_decimal(Decimal("0.0000015"), 6) == "0.000002"


def test_fmt_decimal_normalises_negative_zero():
    assert fmt_decimal(-0.0000001, 6) == "0.000000"
    assert fmt_decimal(-0.0, 0) == "0"


def test_fmt_decimal_non_finite():
    assert fmt_decimal(float("nan"), 6) == "NaN"
    assert fmt_decimal(float("inf"), 6) == "Infinity"
    assert fmt_decimal(float("-inf"), 6) == "-Infinity"


def test_quantity_mm_and_m_are_identical():
    q, _ = _quantizer()
    assert q.quantity(Quantity(12.5, "Umm")) == q.quantity(Quantity(0.0125, "Um")) == "0.012500"


def test_quantity_precision_per_si_symbol():
    q, _ = _quantizer()
    assert q.quantity(Quantity(355.0, "UNOvermm2")) == "355000000"
    assert q.quantity(Quantity(1.8, "Ut")) == "1800.000"
    assert q.quantity(Quantity(1234.5, "Ucm4")) == "0.000012345"
    assert q.quantity(Quantity(0.3, "UDimless")) == "0.300000"


def test_unknown_unit_kept_raw_with_warning():
    q, warnings = _quantizer()
    assert q.quantity(Quantity(1.5, "Ufoo")) == {"value": "1.500000", "unit": "Ufoo"}
    assert q.point(IrPoint3D(1.0, 2.0, 3.0, "Ufoo")) == [
        "1.000000", "2.000000", "3.000000", "Ufoo"]
    assert warnings == ["unknown unit 'Ufoo'", "unknown unit 'Ufoo'"]


def test_point_and_vector():
    q, _ = _quantizer()
    assert q.point(IrPoint3D(1000.0, 0.0, -0.0000001, "Umm")) == [
        "1.000000", "0.000000", "0.000000"]
    assert q.vector(IrVector3D(0.0, 0.0, 1.0)) == ["0.000000", "0.000000", "1.000000"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.quantize'`.

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/profile.py`**

```python
"""Profile ocx-hash/1 constants: aspect order, part kinds, quantisation precision."""
from __future__ import annotations

PROFILE = "ocx-hash/1"

ASPECTS: tuple[str, ...] = ("identity", "material", "scantlings", "geometry", "physical")

KINDS: tuple[str, ...] = (
    "vessel", "plate", "stiffener", "bracket", "pillar", "edge_reinforcement",
    "panel", "seam", "compartment",
)

DEFAULT_DECIMALS = 6

# Keyed on IrUnit.si_symbol (see ocx_model_core.model.units._DIM_TO_SI_SYMBOL).
DECIMALS_BY_SI_SYMBOL: dict[str, int] = {
    "m": 6,
    "m²": 6,
    "m³": 6,
    "m⁴": 9,
    "Pa": 0,
    "kg": 3,
    "kg/m³": 3,
    "m/s": 6,
    "N·m": 3,
}


def decimals_for(si_symbol: str) -> int:
    return DECIMALS_BY_SI_SYMBOL.get(si_symbol, DEFAULT_DECIMALS)
```

- [ ] **Step 5: Create `packages/ocx-integrity/src/ocx_integrity/quantize.py`**

```python
"""Quantities, points and vectors → fixed-precision SI decimal strings."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import ROUND_HALF_EVEN, Decimal

from ocx_model_core.model.ir import IrUnit, IrVector3D, Quantity

from ocx_integrity.profile import DEFAULT_DECIMALS, decimals_for


def _dec(value: float | Decimal) -> Decimal:
    # repr() gives the shortest round-tripping string, so 0.001 stays exactly 0.001.
    return value if isinstance(value, Decimal) else Decimal(repr(float(value)))


def fmt_decimal(value: float | Decimal, decimals: int) -> str:
    """Round half-even to ``decimals`` places; ``-0`` becomes ``0``; never a float."""
    d = _dec(value)
    if d.is_nan():
        return "NaN"
    if d.is_infinite():
        return "-Infinity" if d < 0 else "Infinity"
    q = d.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN)
    if q == 0:
        q = q.copy_abs()
    return format(q, "f")


class Quantizer:
    """Convert IR values to SI decimal strings using a vessel's unit registry."""

    def __init__(self, registry: Mapping[str, IrUnit], warn: Callable[[str], None]) -> None:
        self._registry = registry
        self._warn = warn

    def quantity(self, q: Quantity) -> str | dict[str, str]:
        unit = self._registry.get(q.unit)
        if unit is None:
            self._warn(f"unknown unit {q.unit!r}")
            return {"value": fmt_decimal(q.value, DEFAULT_DECIMALS), "unit": q.unit}
        return fmt_decimal(_dec(q.value) * _dec(unit.to_si_factor), decimals_for(unit.si_symbol))

    def point(self, p) -> list[str]:
        """``IrPoint3D`` or ``IrCog`` → ``[x, y, z]`` (``[x, y, z, unit]`` if unit unknown)."""
        coords = (p.x, p.y, p.z)
        unit = self._registry.get(p.unit)
        if unit is None:
            self._warn(f"unknown unit {p.unit!r}")
            return [fmt_decimal(c, DEFAULT_DECIMALS) for c in coords] + [p.unit]
        factor = _dec(unit.to_si_factor)
        decimals = decimals_for(unit.si_symbol)
        return [fmt_decimal(_dec(c) * factor, decimals) for c in coords]

    def scalar(self, value: float) -> str:
        return fmt_decimal(value, DEFAULT_DECIMALS)

    def vector(self, v: IrVector3D) -> list[str]:
        return [self.scalar(c) for c in (v.x, v.y, v.z)]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: `7 passed`.

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/profile.py packages/ocx-integrity/src/ocx_integrity/quantize.py tests/integrity_fixtures.py tests/test_integrity_canon.py
git commit -m "feat(integrity): profile constants and SI quantizer

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: JSON helpers and canonical geometry

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/jsonutil.py`
- Create: `packages/ocx-integrity/src/ocx_integrity/canon_geom.py`
- Test: `tests/test_integrity_canon.py` (append)

Background:
- `canon_geom.curve_record(curve, canon)` receives a `canon` callable that converts any nested IR value (points, quantities, floats, nested curves).
- In production that callable is `Context.canon` (Task 4). These tests use a minimal stand-in.
- Points arrive as lists of decimal strings (`["0.000000", "1.000000", "0.000000"]`), so contour normalisation works on quantised values.

- [ ] **Step 1: Append the failing tests to `tests/test_integrity_canon.py`**

Add these imports to the import block at the top of the file:

```python
from ocx_model_core.model.ir import IrCompositeCurve3D, IrCurve3D, IrLine3D, IrPolyLine3D

from ocx_integrity.canon_geom import _reverse_seg, curve_record
from ocx_integrity.jsonutil import prune, sort_jcs, type_name
from tests.integrity_fixtures import square
```

Append these tests:

```python
def _geom_canon():
    q, _ = _quantizer()

    def canon(v):
        if isinstance(v, IrPoint3D):
            return q.point(v)
        if isinstance(v, IrVector3D):
            return q.vector(v)
        if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
            return v
        if isinstance(v, float):
            return q.scalar(v)
        if isinstance(v, Quantity):
            return q.quantity(v)
        if isinstance(v, IrCurve3D):
            return curve_record(v, canon)
        if isinstance(v, list):
            return [canon(x) for x in v]
        raise TypeError(type(v))

    return canon


def _square_composite(reverse: bool = False, start: int = 0) -> IrCompositeCurve3D:
    c = [(0.0, 0.0), (2000.0, 0.0), (2000.0, 2000.0), (0.0, 2000.0)]
    if reverse:
        c = c[::-1]
    c = c[start:] + c[:start]
    segs = [IrLine3D(curve_length=None,
                     start=IrPoint3D(*c[i], 0.0, "Umm"),
                     end=IrPoint3D(*c[(i + 1) % 4], 0.0, "Umm")) for i in range(4)]
    return IrCompositeCurve3D(curve_length=None, segments=segs)


def test_prune_drops_empty_values_recursively():
    assert prune({"a": None, "b": "", "c": [], "d": {}, "e": False,
                  "f": {"g": None}, "h": 0, "i": True, "j": ["x", None]}) == {
        "h": 0, "i": True, "j": ["x", None]}


def test_type_name_strips_ir_prefix():
    assert type_name(IrPolyLine3D(curve_length=None)) == "polyline3d"


def test_sort_jcs_is_deterministic():
    assert sort_jcs([{"b": "2"}, {"a": "1"}]) == [{"a": "1"}, {"b": "2"}]


def test_closed_polyline_canonical_form():
    canon = _geom_canon()
    rec = curve_record(square(), canon)
    assert rec == {
        "type": "polyline3d",
        "is_closed": True,
        "vertices": [["0.000000", "0.000000", "0.000000"],
                     ["2.000000", "0.000000", "0.000000"],
                     ["2.000000", "2.000000", "0.000000"],
                     ["0.000000", "2.000000", "0.000000"]],
    }


def test_closed_polyline_invariant_to_start_orientation_units_and_closure():
    canon = _geom_canon()
    base = curve_record(square(), canon)
    assert curve_record(square(start=2), canon) == base
    assert curve_record(square(reverse=True, start=1), canon) == base
    assert curve_record(square(repeat_first=True), canon) == base
    assert curve_record(square(unit="Um", size=2.0), canon) == base
    assert curve_record(square(size=2000.0000001), canon) == base  # sub-µm noise


def test_open_polyline_keeps_order():
    canon = _geom_canon()
    pts = [IrPoint3D(0.0, 0.0, 0.0, "Umm"), IrPoint3D(1000.0, 0.0, 0.0, "Umm")]
    fwd = curve_record(IrPolyLine3D(curve_length=None, vertices=pts), canon)
    rev = curve_record(IrPolyLine3D(curve_length=None, vertices=pts[::-1]), canon)
    assert fwd != rev
    assert "is_closed" not in fwd


def test_closed_composite_invariant_to_start_and_orientation():
    canon = _geom_canon()
    base = curve_record(_square_composite(), canon)
    assert base["segments"][0]["start"] == ["0.000000", "0.000000", "0.000000"]
    assert base["segments"][0]["end"] == ["2.000000", "0.000000", "0.000000"]
    assert curve_record(_square_composite(start=3), canon) == base
    assert curve_record(_square_composite(reverse=True, start=2), canon) == base


def test_reverse_nurbs_segment_mirrors_knots():
    seg = {"type": "nurbs3d",
           "control_points": [["0", "0", "0"], ["1", "1", "0"], ["2", "0", "0"]],
           "weights": ["1.000000", "2.000000", "3.000000"],
           "knot_vector": ["0.000000", "0.000000", "0.000000", "0.300000",
                           "1.000000", "1.000000", "1.000000"]}
    rev = _reverse_seg(seg)
    assert rev["control_points"] == [["2", "0", "0"], ["1", "1", "0"], ["0", "0", "0"]]
    assert rev["weights"] == ["3.000000", "2.000000", "1.000000"]
    assert rev["knot_vector"] == ["0.000000", "0.000000", "0.000000", "0.700000",
                                  "1.000000", "1.000000", "1.000000"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.canon_geom'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/jsonutil.py`**

```python
"""JSON-shape helpers shared by geometry and record canonicalisation."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable
from typing import Any

import rfc8785

# Exporter-local ids are never hashed; curve lengths are committed under "physical".
SKIP_FIELDS = frozenset({"id", "guidref", "curve_length"})


def _is_empty(value: Any) -> bool:
    if value is None or value is False:
        return True
    return isinstance(value, (str, list, dict)) and len(value) == 0


def prune(value: Any) -> Any:
    """Recursively drop dict entries that are None, '', False, [] or {}."""
    if isinstance(value, dict):
        out = {k: prune(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if not _is_empty(v)}
    if isinstance(value, list):
        return [prune(v) for v in value]
    return value


def type_name(obj: Any) -> str:
    """``IrPolyLine3D`` → ``"polyline3d"``."""
    name = type(obj).__name__
    return (name[2:] if name.startswith("Ir") else name).lower()


def sort_jcs(items: Iterable[Any]) -> list[Any]:
    """Sort an unordered collection by the JCS bytes of each item."""
    return sorted(items, key=rfc8785.dumps)


def dataclass_dict(obj: Any, canon: Callable[[Any], Any],
                   skip: frozenset[str] = SKIP_FIELDS) -> dict[str, Any]:
    """Generic canonical dict for an IR dataclass: ``{"type": ..., field: canon(value)}``."""
    out: dict[str, Any] = {"type": type_name(obj)}
    for f in dataclasses.fields(obj):
        if f.name not in skip:
            out[f.name] = canon(getattr(obj, f.name))
    return prune(out)
```

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/canon_geom.py`**

```python
"""Canonical curve dicts; closed-contour start-point and orientation normalisation.

Points are lists of quantised decimal strings, as produced by ``Quantizer.point``.
Closed rings start at the lexicographically smallest point. If the dominant
Newell-normal component (ties x > y > z) is negative, the orientation is reversed.
Open curves and NURBS are kept as given.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ocx_model_core.model.ir import IrCompositeCurve3D, IrCurve3D, IrPolyLine3D

from ocx_integrity.jsonutil import dataclass_dict, prune
from ocx_integrity.profile import DEFAULT_DECIMALS
from ocx_integrity.quantize import fmt_decimal

Canon = Callable[[Any], Any]
Point = list[str]

CLOSURE_TOL = Decimal("0.000001")  # 1 µm in SI metres


def curve_record(curve: IrCurve3D, canon: Canon) -> dict[str, Any]:
    if isinstance(curve, IrPolyLine3D):
        return _polyline(curve, canon)
    if isinstance(curve, IrCompositeCurve3D):
        return _composite(curve, canon)
    return dataclass_dict(curve, canon)


# --- point helpers -----------------------------------------------------------

def _key(p: Point) -> tuple[Decimal, ...]:
    return tuple(Decimal(c) for c in p[:3])


def _same(a: Point | None, b: Point | None) -> bool:
    if a is None or b is None or len(a) != len(b):
        return False
    return all(abs(Decimal(x) - Decimal(y)) <= CLOSURE_TOL for x, y in zip(a[:3], b[:3]))


def _rotate_min(pts: list[Point]) -> list[Point]:
    i = min(range(len(pts)), key=lambda k: _key(pts[k]))
    return pts[i:] + pts[:i]


def _newell(pts: list[Point]) -> tuple[float, float, float]:
    nx = ny = nz = 0.0
    for i, cur in enumerate(pts):
        nxt = pts[(i + 1) % len(pts)]
        x1, y1, z1 = (float(c) for c in cur[:3])
        x2, y2, z2 = (float(c) for c in nxt[:3])
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def _dominant_negative(n: tuple[float, float, float]) -> bool:
    i = max(range(3), key=lambda k: (abs(n[k]), -k))  # ties resolved x > y > z
    return n[i] < 0


# --- polylines ---------------------------------------------------------------

def _polyline(curve: IrPolyLine3D, canon: Canon) -> dict[str, Any]:
    pts: list[Point] = [canon(p) for p in curve.vertices]
    repeated = len(pts) > 1 and _same(pts[0], pts[-1])
    closed = bool(curve.is_closed) or (len(pts) > 3 and repeated)
    if closed and repeated:
        pts = pts[:-1]
    if closed and len(pts) >= 3:
        pts = _rotate_min(pts)
        if _dominant_negative(_newell(pts)):
            pts = _rotate_min(pts[::-1])
    return prune({"type": "polyline3d", "vertices": pts, "is_closed": closed})


# --- composite curves --------------------------------------------------------

def _endpoints(seg: dict[str, Any]) -> tuple[Point, Point] | None:
    t = seg.get("type")
    if t in ("line3d", "circumarc3d"):
        start, end = seg.get("start"), seg.get("end")
    elif t == "polyline3d" and not seg.get("is_closed") and seg.get("vertices"):
        start, end = seg["vertices"][0], seg["vertices"][-1]
    elif t == "nurbs3d" and seg.get("control_points"):
        start, end = seg["control_points"][0], seg["control_points"][-1]
    else:
        return None
    if start is None or end is None:
        return None
    return start, end


def _seg_points(seg: dict[str, Any]) -> list[Point]:
    """Ordered points of a segment, excluding its end point (for the Newell normal)."""
    t = seg["type"]
    if t == "line3d":
        return [seg["start"]]
    if t == "circumarc3d":
        return [seg["start"]] + ([seg["intermediate"]] if "intermediate" in seg else [])
    if t == "polyline3d":
        return seg["vertices"][:-1]
    return seg["control_points"][:-1]  # nurbs3d


def _reverse_seg(seg: dict[str, Any]) -> dict[str, Any] | None:
    t = seg.get("type")
    out = dict(seg)
    if t in ("line3d", "circumarc3d"):
        out["start"], out["end"] = seg.get("end"), seg.get("start")
        return prune(out)
    if t == "polyline3d":
        out["vertices"] = seg["vertices"][::-1]
        return out
    if t == "nurbs3d":
        out["control_points"] = seg["control_points"][::-1]
        if "weights" in seg:
            out["weights"] = seg["weights"][::-1]
        if "knot_vector" in seg:
            kv = [Decimal(k) for k in seg["knot_vector"]]
            lo, hi = kv[0], kv[-1]
            out["knot_vector"] = [fmt_decimal(lo + hi - k, DEFAULT_DECIMALS) for k in kv[::-1]]
        return out
    return None


def _rotate_segs(segs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    i = min(range(len(segs)), key=lambda k: _key(_endpoints(segs[k])[0]))
    return segs[i:] + segs[:i]


def _composite(curve: IrCompositeCurve3D, canon: Canon) -> dict[str, Any]:
    segs = [curve_record(s, canon) for s in curve.segments]
    ends = [_endpoints(s) for s in segs]
    closed = bool(segs) and all(e is not None for e in ends) and _same(ends[-1][1], ends[0][0])
    if closed:
        segs = _rotate_segs(segs)
        pts = [p for s in segs for p in _seg_points(s)]
        if len(pts) >= 3 and _dominant_negative(_newell(pts)):
            reversed_segs = [_reverse_seg(s) for s in reversed(segs)]
            if all(r is not None for r in reversed_segs):
                segs = _rotate_segs(reversed_segs)
    return prune({"type": "compositecurve3d", "segments": segs})
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: `15 passed`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/jsonutil.py packages/ocx-integrity/src/ocx_integrity/canon_geom.py tests/test_integrity_canon.py
git commit -m "feat(integrity): canonical curve records with closed-contour normalisation

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Record context — part IDs, reference resolution, catalogue records

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/records/__init__.py` (empty placeholder; Task 5 fills it)
- Create: `packages/ocx-integrity/src/ocx_integrity/records/common.py`
- Test: `tests/test_integrity_canon.py` (append)

Background:
- Part ID policy: use `guidref` if present (`id_source: "guid"`), otherwise the XML `id` (`id_source: "xml_id"`). The vessel part ID is `vessel:<IrVessel.id>`.
- A `Ref` resolves to the **part ID** of its target. The lookup is first by XML id (`local_ref`), then by GUID. If neither resolves, the ref becomes `{"unresolved": raw}` and a warning is recorded.
- `Context.current` names the part being extracted, so warnings say where they came from.

- [ ] **Step 1: Append the failing tests to `tests/test_integrity_canon.py`**

Add to the imports at the top:

```python
from ocx_model_core.model.ir import ParentKind, ParentRef, Ref

from ocx_integrity.records.common import (
    Context,
    hole_placement,
    identity,
    make_record,
    material_aspect,
    part_id,
    section_value,
)
from tests.integrity_fixtures import hole, make_vessel
```

Append:

```python
def test_part_id_prefers_guid():
    v = make_vessel()
    assert part_id(v.plates["PL1"]) == ("G-PL-1", "guid")
    assert part_id(v.stiffeners["ST1"]) == ("ST1", "xml_id")


def test_resolve_by_xml_id_then_guid_then_unresolved():
    ctx = Context(make_vessel())
    ctx.current = "plate G-PL-1"
    assert ctx.resolve(Ref("P1")) == "G-PAN-1"
    assert ctx.resolve(Ref("nope", "G-PAN-1")) == "G-PAN-1"
    assert ctx.resolve(Ref("ST1")) == "ST1"
    assert ctx.resolve(Ref("X9")) == {"unresolved": "X9"}
    assert ctx.warnings == ["unresolved reference 'X9' on plate G-PL-1"]


def test_resolve_keeps_ref_offset():
    ctx = Context(make_vessel())
    ref = Ref("P1", offset=Quantity(10.0, "Umm"), offset_direction=IrVector3D(0.0, 0.0, 1.0))
    assert ctx.resolve(ref) == {"ref": "G-PAN-1", "offset": "0.010000",
                                "offset_direction": ["0.000000", "0.000000", "1.000000"]}


def test_parent_resolves_panel_and_vessel():
    ctx = Context(make_vessel())
    assert ctx.parent(ParentRef(ParentKind.PANEL, "P1")) == "G-PAN-1"
    assert ctx.parent(ParentRef(ParentKind.VESSEL, "V1")) == "vessel:V1"


def test_canon_dataclass_drops_ids_and_adds_type():
    ctx = Context(make_vessel())
    rec = ctx.canon(make_vessel().plates["PL1"].mass_properties)
    assert rec == {"type": "massproperties", "moulded_dry_weight": "1500.000",
                   "moulded_cog": ["1.000000", "1.000000", "0.000000"]}


def test_make_record_returns_none_when_empty():
    assert make_record("plate", thickness=None, name="") is None
    assert make_record("plate", thickness="0.012000") == {"kind": "plate",
                                                          "thickness": "0.012000"}


def test_identity_material_section_and_hole_records():
    v = make_vessel()
    ctx = Context(v)
    plate = v.plates["PL1"]
    assert identity("plate", plate, ctx, function_type=None, parent=ctx.parent(plate.parent_ref)) == {
        "kind": "plate", "id_source": "guid", "name": "Deck plate", "parent": "G-PAN-1"}
    mat = material_aspect("plate", plate.material_ref, ctx)
    assert mat == {"kind": "plate", "material": {
        "part_id": "G-MAT-1", "type": "material", "grade": "AH36", "density": "7850.000",
        "yield_stress": "355000000", "youngs_modulus": "206000000000"}}
    assert material_aspect("plate", None, ctx) is None
    assert section_value(Ref("S1"), ctx) == {
        "part_id": "S1", "type": "flatbarsection", "name": "FB200x12",
        "section_type": "FlatBar", "height": "0.200000", "width": "0.012000"}
    assert hole_placement(hole(500.0, 500.0), ctx) == {
        "hole": {"part_id": "G-HOLE-1", "type": "hole2d",
                 "parametric": {"type": "parametrichole", "variant": "circle",
                                "diameter": "0.100000"}},
        "transformation": {"type": "transformation",
                           "origin": ["0.500000", "0.500000", "0.000000"],
                           "primary_axis": ["1.000000", "0.000000", "0.000000"],
                           "secondary_axis": ["0.000000", "1.000000", "0.000000"]}}


def test_unresolved_material_is_recorded_not_dropped():
    ctx = Context(make_vessel())
    ctx.current = "plate X"
    assert material_aspect("plate", Ref("M404"), ctx) == {
        "kind": "plate", "material": {"unresolved": "M404"}}
    assert ctx.warnings == ["unresolved material reference 'M404' on plate X"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.records'`.

- [ ] **Step 3: Create the empty `packages/ocx-integrity/src/ocx_integrity/records/__init__.py`**

```python
"""Per-kind canonical record extractors (profile ocx-hash/1)."""
```

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/records/common.py`**

```python
"""Shared record machinery: part IDs, reference resolution, canonical values."""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from ocx_model_core.model.ir import (
    IrCog,
    IrCurve3D,
    IrHole2DContour,
    IrPoint3D,
    IrVector3D,
    IrVessel,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)

from ocx_integrity.canon_geom import curve_record
from ocx_integrity.jsonutil import dataclass_dict, prune, sort_jcs
from ocx_integrity.quantize import Quantizer


def part_id(obj: Any) -> tuple[str, str]:
    """``(part_id, id_source)`` — GUID if present, else the XML id."""
    guid = getattr(obj, "guidref", None)
    if guid:
        return guid, "guid"
    return obj.id, "xml_id"


def vessel_part_id(vessel: IrVessel) -> str:
    return f"vessel:{vessel.id}"


def _raw(ref: Ref) -> str:
    return ref.guidref or ref.local_ref


class Context:
    """Per-vessel extraction state: id index, quantizer, warnings, current part."""

    def __init__(self, vessel: IrVessel) -> None:
        self.vessel = vessel
        self.warnings: list[str] = []
        self.current = f"vessel {vessel.id}"
        self.quant = Quantizer(vessel.unit_registry, self.warn)
        self.holes = vessel.hole_shape_catalogue.holes if vessel.hole_shape_catalogue else {}
        self._by_xml_id: dict[str, str] = {}
        self._guids: set[str] = set()
        tables = (
            vessel.plates, vessel.stiffeners, vessel.brackets, vessel.pillars,
            vessel.edge_reinforcements, vessel.panels, vessel.seams, vessel.compartments,
            vessel.materials, vessel.sections, vessel.surfaces, vessel.ref_planes, self.holes,
        )
        for table in tables:
            for obj in table.values():
                pid, _ = part_id(obj)
                self._by_xml_id.setdefault(obj.id, pid)
                if getattr(obj, "guidref", None):
                    self._guids.add(obj.guidref)

    def warn(self, message: str) -> None:
        self.warnings.append(f"{message} on {self.current}")

    def resolve(self, ref: Ref | None) -> Any:
        """Ref → target part ID (or ``{"unresolved": raw}``), keeping any 3.2 offset."""
        if ref is None:
            return None
        if ref.local_ref and ref.local_ref in self._by_xml_id:
            target: Any = self._by_xml_id[ref.local_ref]
        elif ref.guidref and ref.guidref in self._guids:
            target = ref.guidref
        else:
            self.warn(f"unresolved reference {_raw(ref)!r}")
            target = {"unresolved": _raw(ref)}
        if ref.offset is None and ref.offset_direction is None:
            return target
        return prune({"ref": target, "offset": self.canon(ref.offset),
                      "offset_direction": self.canon(ref.offset_direction)})

    def lookup(self, ref: Ref | None, table: dict[str, Any], what: str) -> Any:
        """Return the object a ref points to in ``table`` (by id, then GUID), or None."""
        if ref is None:
            return None
        obj = table.get(ref.local_ref)
        if obj is None and ref.guidref:
            obj = next((o for o in table.values()
                        if getattr(o, "guidref", None) == ref.guidref), None)
        if obj is None:
            self.warn(f"unresolved {what} reference {_raw(ref)!r}")
        return obj

    def parent(self, parent_ref: ParentRef | None) -> Any:
        if parent_ref is None:
            return None
        if parent_ref.kind == ParentKind.VESSEL:
            return vessel_part_id(self.vessel)
        return self.resolve(Ref(parent_ref.id))

    def canon(self, value: Any) -> Any:
        """Any IR value → canonical JSON value (strings for all numbers except ints)."""
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, float):
            return self.quant.scalar(value)
        if isinstance(value, Quantity):
            return self.quant.quantity(value)
        if isinstance(value, (IrPoint3D, IrCog)):
            return self.quant.point(value)
        if isinstance(value, IrVector3D):
            return self.quant.vector(value)
        if isinstance(value, Ref):
            return self.resolve(value)
        if isinstance(value, IrCurve3D):
            return curve_record(value, self.canon)
        if isinstance(value, (list, tuple)):
            return [self.canon(v) for v in value]
        if isinstance(value, dict):
            return {str(k): self.canon(v) for k, v in value.items()}
        if dataclasses.is_dataclass(value):
            return dataclass_dict(value, self.canon)
        raise TypeError(f"cannot canonicalise {type(value).__name__}")

    def canon_set(self, values: list[Any]) -> list[Any]:
        """Canonicalise an unordered collection and sort it by JCS bytes."""
        return sort_jcs(self.canon(v) for v in values)


def make_record(kind: str, **fields: Any) -> dict[str, Any] | None:
    """Pruned record with ``kind``; ``None`` (aspect absent) when no field has content."""
    body = prune(fields)
    return {"kind": kind, **body} if body else None


def identity(kind: str, obj: Any, ctx: Context, **extra: Any) -> dict[str, Any] | None:
    _, source = part_id(obj)
    return make_record(kind, id_source=source, name=obj.name,
                       **{k: ctx.canon(v) for k, v in extra.items()})


def catalogue_record(obj: Any, ctx: Context) -> dict[str, Any]:
    pid, _ = part_id(obj)
    return {"part_id": pid, **ctx.canon(obj)}


def _resolved_catalogue(ref: Ref | None, table: dict[str, Any], what: str,
                        ctx: Context) -> dict[str, Any] | None:
    if ref is None:
        return None
    obj = ctx.lookup(ref, table, what)
    return catalogue_record(obj, ctx) if obj is not None else {"unresolved": _raw(ref)}


def material_aspect(kind: str, ref: Ref | None, ctx: Context) -> dict[str, Any] | None:
    return make_record(kind, material=_resolved_catalogue(ref, ctx.vessel.materials,
                                                          "material", ctx))


def section_value(ref: Ref | None, ctx: Context) -> dict[str, Any] | None:
    return _resolved_catalogue(ref, ctx.vessel.sections, "section", ctx)


def hole_placement(h: IrHole2DContour, ctx: Context) -> dict[str, Any]:
    return prune({
        "name": h.name,
        "hole": _resolved_catalogue(h.hole_ref, ctx.holes, "hole shape", ctx),
        "transformation": ctx.canon(h.transformation),
    })


def curve_lengths(ctx: Context, **curves: Any) -> dict[str, Any]:
    """Committed lengths of the given curves (lists are treated as unordered)."""
    out: dict[str, Any] = {}
    for name, value in curves.items():
        if isinstance(value, list):
            out[name] = sort_jcs(ctx.canon(c.curve_length) for c in value
                                 if c is not None and c.curve_length is not None)
        elif value is not None and value.curve_length is not None:
            out[name] = ctx.canon(value.curve_length)
    return prune(out)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: `23 passed`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/records tests/test_integrity_canon.py
git commit -m "feat(integrity): record context with part IDs and reference resolution

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Per-kind extractors and `iter_parts`

**Files:**
- Modify: `packages/ocx-integrity/src/ocx_integrity/records/common.py` (append `bar_scantlings`)
- Create: `packages/ocx-integrity/src/ocx_integrity/records/{plate,stiffener,bracket,pillar,edge_reinforcement,panel,seam,compartment,vessel}.py`
- Modify: `packages/ocx-integrity/src/ocx_integrity/records/__init__.py`
- Test: `tests/test_integrity_canon.py` (append)

Each extractor returns `{aspect: record | None}`. `iter_parts` drops `None` aspects and orders the rest per `ASPECTS`. Field selection follows the spec's *Canonical records* table exactly. Unordered collections go through `ctx.canon_set` / `sort_jcs`; ordered ones (inclinations, polyline vertices) go through `ctx.canon`.

- [ ] **Step 1: Append the failing tests to `tests/test_integrity_canon.py`**

Add to the imports at the top:

```python
from ocx_integrity.records import iter_parts
```

Append:

```python
def _parts(vessel):
    ctx = Context(vessel)
    return {p.part_id: p for p in iter_parts(vessel, ctx)}, ctx


def test_iter_parts_yields_every_kind_once():
    parts, ctx = _parts(make_vessel())
    assert {pid: p.kind for pid, p in parts.items()} == {
        "vessel:V1": "vessel", "G-PL-1": "plate", "ST1": "stiffener",
        "G-PAN-1": "panel", "SE1": "seam", "G-COMP-1": "compartment"}
    assert ctx.warnings == []


def test_plate_aspects():
    parts, _ = _parts(make_vessel())
    plate = parts["G-PL-1"]
    assert list(plate.aspects) == ["identity", "material", "scantlings", "geometry", "physical"]
    assert plate.aspects["scantlings"] == {"kind": "plate", "thickness": "0.012000"}
    assert plate.aspects["physical"]["curve_lengths"] == {"outer_contour": "8.000000"}
    holes = plate.aspects["geometry"]["cut_by_holes"]
    assert [h["transformation"]["origin"][0] for h in holes] == ["0.500000", "1.500000"]


def test_stiffener_inlines_section_and_material():
    parts, _ = _parts(make_vessel())
    st = parts["ST1"]
    assert st.id_source == "xml_id"
    assert st.aspects["scantlings"]["section"]["part_id"] == "S1"
    assert st.aspects["material"]["material"]["part_id"] == "G-MAT-1"
    assert st.aspects["geometry"]["orientation_rule"] == "ocx:Up"
    assert st.aspects["physical"]["curve_lengths"] == {"trace": "2.000000"}


def test_panel_identity_and_geometry():
    parts, _ = _parts(make_vessel())
    pan = parts["G-PAN-1"]
    assert pan.aspects["identity"]["children"] == {
        "plates": ["G-PL-1"], "stiffeners": ["ST1"], "seams": ["SE1"]}
    assert "material" not in pan.aspects and "scantlings" not in pan.aspects
    assert pan.aspects["geometry"]["limited_by"] == [
        {"ref_type": "SeamRef", "target": "SE1"},
        {"ref_type": "StiffenerRef", "target": "ST1"}]
    assert pan.aspects["geometry"]["unbounded_geometry"]["surface"]["type"] == "plane3d"
    assert pan.aspects["physical"]["mass_properties"]["moulded_dry_weight"] == "1800.000"


def test_seam_compartment_vessel_records():
    parts, _ = _parts(make_vessel())
    assert parts["SE1"].aspects["physical"]["curve_lengths"] == {"trace_line": "2.000000"}
    comp = parts["G-COMP-1"]
    assert comp.aspects["geometry"] == {"kind": "compartment", "face_refs": ["G-PAN-1"]}
    assert comp.aspects["physical"] == {"kind": "compartment", "volume": "250.000000"}
    v = parts["vessel:V1"]
    assert list(v.aspects) == ["identity"]
    assert v.aspects["identity"]["ship_designation"] == {
        "type": "shipdesignation", "ship_name": "TEST", "number_imo": "1234567"}
    assert v.aspects["identity"]["principal_particulars"] == {
        "type": "principalparticulars", "lpp": "100.000000"}


def test_records_invariant_to_collection_order():
    a, b = make_vessel(), make_vessel()
    b.plates["PL1"].cut_by_holes.reverse()
    b.panels["P1"].limited_by.reverse()
    pa, _ = _parts(a)
    pb, _ = _parts(b)
    assert pa["G-PL-1"].aspects == pb["G-PL-1"].aspects
    assert pa["G-PAN-1"].aspects == pb["G-PAN-1"].aspects


def test_unresolved_section_becomes_warning():
    v = make_vessel()
    v.stiffeners["ST1"].section_ref = Ref("S404")
    parts, ctx = _parts(v)
    assert parts["ST1"].aspects["scantlings"]["section"] == {"unresolved": "S404"}
    assert ctx.warnings == ["unresolved section reference 'S404' on stiffener ST1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: collection ERROR `ImportError: cannot import name 'iter_parts' from 'ocx_integrity.records'`.

- [ ] **Step 3: Append `bar_scantlings` to `records/common.py`**

```python
def bar_scantlings(kind: str, part: Any, ctx: Context, **extra: Any) -> dict[str, Any] | None:
    """Scantlings shared by stiffeners, pillars and edge reinforcements."""
    c = ctx.canon
    return make_record(
        kind,
        section=section_value(part.section_ref, ctx),
        web_renewal_thickness=c(part.web_renewal_thickness),
        flange_renewal_thickness=c(part.flange_renewal_thickness),
        voluntary_web_thickness_addition=c(part.voluntary_web_thickness_addition),
        voluntary_flange_thickness_addition=c(part.voluntary_flange_thickness_addition),
        **{k: c(v) for k, v in extra.items()},
    )
```

- [ ] **Step 4: Create `records/plate.py`**

```python
"""Plate → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrPlate

from ocx_integrity.jsonutil import sort_jcs
from ocx_integrity.records.common import (
    Context,
    curve_lengths,
    hole_placement,
    identity,
    make_record,
    material_aspect,
)

KIND = "plate"


def extract(plate: IrPlate, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, plate, ctx, function_type=plate.function_type,
                             parent=ctx.parent(plate.parent_ref)),
        "material": material_aspect(KIND, plate.material_ref, ctx),
        "scantlings": make_record(
            KIND,
            thickness=c(plate.thickness),
            renewal_thickness=c(plate.renewal_thickness),
            voluntary_thickness_addition=c(plate.voluntary_thickness_addition),
        ),
        "geometry": make_record(
            KIND,
            outer_contour=c(plate.outer_contour),
            cut_by_contours=ctx.canon_set(plate.cut_by_contours),
            cut_by_holes=sort_jcs(hole_placement(h, ctx) for h in plate.cut_by_holes),
            point_on_surface=c(plate.point_on_surface),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(plate.mass_properties),
            net_area=c(plate.net_area),
            curve_lengths=curve_lengths(ctx, outer_contour=plate.outer_contour,
                                        cut_by_contours=plate.cut_by_contours),
        ),
    }
```

- [ ] **Step 5: Create `records/stiffener.py`**

```python
"""Stiffener → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrStiffener

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "stiffener"


def extract(stiffener: IrStiffener, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, stiffener, ctx, function_type=stiffener.function_type,
                             parent=ctx.parent(stiffener.parent_ref)),
        "material": material_aspect(KIND, stiffener.material_ref, ctx),
        "scantlings": bar_scantlings(KIND, stiffener, ctx,
                                     end_cut_end1=stiffener.end_cut_end1,
                                     end_cut_end2=stiffener.end_cut_end2),
        "geometry": make_record(
            KIND,
            trace=c(stiffener.trace),
            trace_refs=ctx.canon_set(stiffener.trace_refs),
            inclinations=c(stiffener.inclinations),
            orientation_rule=stiffener.orientation_rule,
            penetrations=ctx.canon_set(stiffener.penetrations),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(stiffener.mass_properties),
            curve_lengths=curve_lengths(ctx, trace=stiffener.trace),
        ),
    }
```

- [ ] **Step 6: Create `records/bracket.py`**

```python
"""Bracket → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrBracket

from ocx_integrity.records.common import (
    Context,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "bracket"


def extract(bracket: IrBracket, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, bracket, ctx, parent=ctx.parent(bracket.parent_ref)),
        "material": material_aspect(KIND, bracket.material_ref, ctx),
        "scantlings": make_record(
            KIND,
            thickness=c(bracket.thickness),
            renewal_thickness=c(bracket.renewal_thickness),
            voluntary_thickness_addition=c(bracket.voluntary_thickness_addition),
            arm_length_u=c(bracket.arm_length_u),
            arm_length_v=c(bracket.arm_length_v),
            unose=c(bracket.unose),
            vnose=c(bracket.vnose),
            free_edge_radius=c(bracket.free_edge_radius),
            has_edge_reinforcement=bracket.has_edge_reinforcement,
            number_of_supports=bracket.number_of_supports,
            reinforcement_type=bracket.reinforcement_type,
            flange_width=c(bracket.flange_width),
            flange_radius=c(bracket.flange_radius),
            feature_cope=c(bracket.feature_cope),
        ),
        "geometry": make_record(
            KIND,
            origin=c(bracket.origin),
            udirection=c(bracket.udirection),
            vdirection=c(bracket.vdirection),
            outer_contour=c(bracket.outer_contour),
            plane=c(bracket.plane),
            offset=c(bracket.offset),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(bracket.mass_properties),
            curve_lengths=curve_lengths(ctx, outer_contour=bracket.outer_contour),
        ),
    }
```

- [ ] **Step 7: Create `records/pillar.py`**

```python
"""Pillar → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrPillar

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    curve_lengths,
    identity,
    make_record,
    material_aspect,
)

KIND = "pillar"


def extract(pillar: IrPillar, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, pillar, ctx, function_type=pillar.function_type,
                             parent=ctx.parent(pillar.parent_ref)),
        "material": material_aspect(KIND, pillar.material_ref, ctx),
        "scantlings": bar_scantlings(KIND, pillar, ctx),
        "geometry": make_record(
            KIND,
            trace=c(pillar.trace),
            inclinations=c(pillar.inclinations),
            penetrations=ctx.canon_set(pillar.penetrations),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(pillar.mass_properties),
            curve_lengths=curve_lengths(ctx, trace=pillar.trace),
        ),
    }
```

- [ ] **Step 8: Create `records/edge_reinforcement.py`**

```python
"""Edge reinforcement → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrEdgeReinforcement

from ocx_integrity.records.common import (
    Context,
    bar_scantlings,
    identity,
    make_record,
    material_aspect,
)

KIND = "edge_reinforcement"


def extract(er: IrEdgeReinforcement, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, er, ctx, function_type=er.function_type,
                             parent=ctx.parent(er.parent_ref)),
        "material": material_aspect(KIND, er.material_ref, ctx),
        "scantlings": bar_scantlings(KIND, er, ctx),
        "geometry": make_record(
            KIND,
            trace_refs=ctx.canon_set(er.trace_refs),
            orientation_rule=er.orientation_rule,
        ),
        "physical": make_record(KIND, mass_properties=c(er.mass_properties)),
    }
```

- [ ] **Step 9: Create `records/panel.py`**

```python
"""Panel → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrLimitedByRef, IrPanel, IrUnboundedGeometry, Ref

from ocx_integrity.jsonutil import prune, sort_jcs
from ocx_integrity.records.common import (
    Context,
    catalogue_record,
    curve_lengths,
    hole_placement,
    identity,
    make_record,
)

KIND = "panel"


def _children(panel: IrPanel, ctx: Context) -> dict[str, list[Any]]:
    groups = {
        "plates": panel.plate_ids,
        "stiffeners": panel.stiffener_ids,
        "brackets": panel.bracket_ids,
        "pillars": panel.pillar_ids,
        "edge_reinforcements": panel.edge_reinforcement_ids,
        "seams": panel.seam_ids,
    }
    return {name: ctx.canon_set([Ref(i) for i in ids]) for name, ids in groups.items()}


def _limit(lb: IrLimitedByRef, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    if lb.ref_type == "FreeEdgeCurve3D":
        target = c(lb.curve)
    else:
        target = ctx.resolve(Ref(lb.local_ref, lb.guidref))
    return prune({
        "ref_type": lb.ref_type,
        "target": target,
        "offset": c(lb.offset),
        "offset_direction": c(lb.offset_direction),
        "contour_start": c(lb.contour_start),
        "contour_end": c(lb.contour_end),
        "contour_mid_point": c(lb.contour_mid_point),
    })


def _unbounded(ug: IrUnboundedGeometry | None, ctx: Context) -> dict[str, Any] | None:
    """Inline the panel's surface: direct, via SurfaceRef, or via GridRef (ref plane)."""
    if ug is None:
        return None
    if ug.surface is not None:
        return {"surface": ctx.canon(ug.surface)}
    if ug.surface_ref:
        surface = ctx.lookup(Ref(ug.surface_ref), ctx.vessel.surfaces, "surface")
        return {"surface_ref": catalogue_record(surface, ctx) if surface
                else {"unresolved": ug.surface_ref}}
    if ug.grid_ref:
        plane = ctx.lookup(Ref(ug.grid_ref), ctx.vessel.ref_planes, "grid")
        return {"grid_ref": catalogue_record(plane, ctx) if plane
                else {"unresolved": ug.grid_ref}}
    return None


def extract(panel: IrPanel, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(KIND, panel, ctx, function_type=panel.function_type,
                             tightness=panel.tightness, children=_children(panel, ctx)),
        "geometry": make_record(
            KIND,
            unbounded_geometry=_unbounded(panel.unbounded_geometry, ctx),
            limited_by=sort_jcs(_limit(lb, ctx) for lb in panel.limited_by),
            outer_contours=ctx.canon_set(panel.outer_contours),
            cut_by_contours=ctx.canon_set(panel.cut_by_contours),
            cut_by_holes=sort_jcs(hole_placement(h, ctx) for h in panel.cut_by_holes),
            point_on_surface=c(panel.point_on_surface),
        ),
        "physical": make_record(
            KIND,
            mass_properties=c(panel.mass_properties),
            curve_lengths=curve_lengths(ctx, outer_contours=panel.outer_contours,
                                        cut_by_contours=panel.cut_by_contours),
        ),
    }
```

- [ ] **Step 10: Create `records/seam.py`**

```python
"""Seam → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrSeam

from ocx_integrity.records.common import Context, curve_lengths, identity, make_record

KIND = "seam"


def extract(seam: IrSeam, ctx: Context) -> dict[str, Any]:
    return {
        "identity": identity(KIND, seam, ctx),
        "geometry": make_record(
            KIND,
            trace_line=ctx.canon(seam.trace_line),
            trace_refs=ctx.canon_set(seam.trace_refs),
        ),
        "physical": make_record(KIND,
                                curve_lengths=curve_lengths(ctx, trace_line=seam.trace_line)),
    }
```

- [ ] **Step 11: Create `records/compartment.py`**

```python
"""Compartment → canonical aspect records."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrCompartment

from ocx_integrity.records.common import Context, curve_lengths, identity, make_record

KIND = "compartment"


def extract(comp: IrCompartment, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": identity(
            KIND, comp, ctx,
            compartment_purpose=comp.compartment_purpose,
            filling_height=comp.filling_height,
            air_pipe_height=comp.air_pipe_height,
            relief_valve_pressure=comp.relief_valve_pressure,
        ),
        "geometry": make_record(
            KIND,
            face_refs=ctx.canon_set(comp.face_refs),
            face_boundary_curves=ctx.canon_set(comp.face_boundary_curves),
        ),
        "physical": make_record(
            KIND,
            volume=c(comp.volume),
            cog=c(comp.cog),
            curve_lengths=curve_lengths(ctx, face_boundary_curves=comp.face_boundary_curves),
        ),
    }
```

- [ ] **Step 12: Create `records/vessel.py`**

```python
"""Vessel metadata → canonical identity record (IrHeader is deliberately not hashed)."""
from __future__ import annotations

from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.records.common import Context, make_record

KIND = "vessel"


def extract(vessel: IrVessel, ctx: Context) -> dict[str, Any]:
    c = ctx.canon
    return {
        "identity": make_record(
            KIND,
            id_source="vessel",
            name=vessel.name,
            ship_designation=c(vessel.ship_designation),
            principal_particulars=c(vessel.principal_particulars),
            builder_info=c(vessel.builder_info),
            statutory_data=c(vessel.statutory_data),
            tonnage_data=c(vessel.tonnage_data),
        ),
    }
```

- [ ] **Step 13: Replace `records/__init__.py`**

```python
"""Per-kind canonical record extractors (profile ocx-hash/1)."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.profile import ASPECTS
from ocx_integrity.records import (
    bracket,
    compartment,
    edge_reinforcement,
    panel,
    pillar,
    plate,
    seam,
    stiffener,
)
from ocx_integrity.records import vessel as vessel_records
from ocx_integrity.records.common import Context, part_id, vessel_part_id

Extractor = Callable[[Any, Context], dict[str, Any]]

EXTRACTORS: dict[str, Extractor] = {
    "vessel": vessel_records.extract,
    "plate": plate.extract,
    "stiffener": stiffener.extract,
    "bracket": bracket.extract,
    "pillar": pillar.extract,
    "edge_reinforcement": edge_reinforcement.extract,
    "panel": panel.extract,
    "seam": seam.extract,
    "compartment": compartment.extract,
}

# (kind, IrVessel attribute) for every part kind except the vessel itself.
_TABLES: tuple[tuple[str, str], ...] = (
    ("plate", "plates"),
    ("stiffener", "stiffeners"),
    ("bracket", "brackets"),
    ("pillar", "pillars"),
    ("edge_reinforcement", "edge_reinforcements"),
    ("panel", "panels"),
    ("seam", "seams"),
    ("compartment", "compartments"),
)


@dataclass(frozen=True)
class PartRecords:
    kind: str
    part_id: str
    id_source: str
    aspects: dict[str, dict[str, Any]]  # present aspects only, in ASPECTS order


def _present(aspects: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a: aspects[a] for a in ASPECTS if aspects.get(a)}


def iter_parts(vessel: IrVessel, ctx: Context) -> Iterator[PartRecords]:
    """Yield the vessel metadata part, then every structural/arrangement part."""
    vid = vessel_part_id(vessel)
    ctx.current = vid
    yield PartRecords("vessel", vid, "vessel", _present(EXTRACTORS["vessel"](vessel, ctx)))
    for kind, attr in _TABLES:
        for obj in getattr(vessel, attr).values():
            pid, source = part_id(obj)
            ctx.current = f"{kind} {pid}"
            yield PartRecords(kind, pid, source, _present(EXTRACTORS[kind](obj, ctx)))
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_canon.py -q`
Expected: `30 passed`.

- [ ] **Step 15: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/records tests/test_integrity_canon.py
git commit -m "feat(integrity): per-kind canonical record extractors

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Salts, key handling and aspect hashing

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/salts.py`
- Create: `packages/ocx-integrity/src/ocx_integrity/hashing.py`
- Test: `tests/test_integrity_hashing.py`

The rules from the spec:
- `salt = HMAC-SHA256(K, utf8("ocx-hash/1") ‖ 0x00 ‖ utf8(part_id) ‖ 0x00 ‖ utf8(aspect))`
- `payload = JCS({"profile", "kind", "part_id", "aspect", "record"})`
- `aspect_hash = SHA256(salt ‖ payload)`

The key file contains hex text (at least 32 bytes once decoded). `--key FILE` wins over the `OCX_INTEGRITY_KEY` env var.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_hashing.py`**

```python
"""Salt derivation, key loading and aspect hashing (ocx-hash/1)."""
from __future__ import annotations

import hashlib
import hmac

import pytest

from ocx_integrity.errors import InvalidKeyError
from ocx_integrity.hashing import aspect_hash, payload
from ocx_integrity.salts import KEY_ENV, derive_salt, generate_key, load_key, parse_key
from tests.integrity_fixtures import KEY, OTHER_KEY

RECORD = {"kind": "plate", "thickness": "0.012000"}


def test_derive_salt_matches_spec_formula():
    expected = hmac.new(KEY, b"ocx-hash/1\x00G-PL-1\x00scantlings", hashlib.sha256).digest()
    assert derive_salt(KEY, "G-PL-1", "scantlings") == expected
    assert len(expected) == 32


def test_salts_differ_per_part_aspect_and_key():
    base = derive_salt(KEY, "P", "geometry")
    assert derive_salt(KEY, "Q", "geometry") != base
    assert derive_salt(KEY, "P", "physical") != base
    assert derive_salt(OTHER_KEY, "P", "geometry") != base


def test_payload_is_jcs():
    assert payload("plate", "P", "scantlings", RECORD) == (
        b'{"aspect":"scantlings","kind":"plate","part_id":"P","profile":"ocx-hash/1",'
        b'"record":{"kind":"plate","thickness":"0.012000"}}')


def test_aspect_hash_is_sha256_of_salt_and_payload():
    salt = derive_salt(KEY, "P", "scantlings")
    expected = hashlib.sha256(salt + payload("plate", "P", "scantlings", RECORD)).digest()
    assert aspect_hash(salt, "plate", "P", "scantlings", RECORD) == expected


def test_load_key_from_file_and_env(tmp_path):
    key_file = tmp_path / "yard.key"
    key_file.write_text(KEY.hex() + "\n", encoding="utf-8")
    assert load_key(key_file, env={}) == KEY
    assert load_key(None, env={KEY_ENV: OTHER_KEY.hex()}) == OTHER_KEY
    assert load_key(key_file, env={KEY_ENV: OTHER_KEY.hex()}) == KEY  # file wins


@pytest.mark.parametrize("text", ["zz" * 32, "ab" * 31, ""])
def test_parse_key_rejects_bad_keys(text):
    with pytest.raises(InvalidKeyError):
        parse_key(text)


def test_load_key_missing(tmp_path):
    with pytest.raises(InvalidKeyError):
        load_key(None, env={})
    with pytest.raises(InvalidKeyError):
        load_key(tmp_path / "absent.key", env={})


def test_generate_key_roundtrips():
    text = generate_key()
    assert len(text) == 64
    assert len(parse_key(text)) == 32
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_hashing.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.hashing'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/salts.py`**

```python
"""Yard-key handling and HMAC-derived per-(part, aspect) salts.

The key K never leaves this module's callers. Revealing one salt reveals
nothing about K or any other salt.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from collections.abc import Mapping
from pathlib import Path

from ocx_integrity.errors import InvalidKeyError
from ocx_integrity.profile import PROFILE

MIN_KEY_BYTES = 32
KEY_ENV = "OCX_INTEGRITY_KEY"


def derive_salt(key: bytes, part_id: str, aspect: str) -> bytes:
    message = b"\x00".join(
        (PROFILE.encode("utf-8"), part_id.encode("utf-8"), aspect.encode("utf-8")))
    return hmac.new(key, message, hashlib.sha256).digest()


def parse_key(text: str) -> bytes:
    try:
        key = bytes.fromhex(text.strip())
    except ValueError as exc:
        raise InvalidKeyError("key is not valid hex") from exc
    if len(key) < MIN_KEY_BYTES:
        raise InvalidKeyError(
            f"key must be at least {MIN_KEY_BYTES} bytes (got {len(key)})")
    return key


def load_key(path: Path | None = None, env: Mapping[str, str] | None = None) -> bytes:
    """Read the hex key from ``path``, else from ``$OCX_INTEGRITY_KEY``."""
    if path is not None:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise InvalidKeyError(f"cannot read key file {path}: {exc}") from exc
        return parse_key(text)
    value = (os.environ if env is None else env).get(KEY_ENV)
    if not value:
        raise InvalidKeyError(f"no key given: pass --key FILE or set {KEY_ENV}")
    return parse_key(value)


def generate_key() -> str:
    """A fresh random key as hex text (64 hex chars = 32 bytes)."""
    return secrets.token_hex(MIN_KEY_BYTES)
```

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/hashing.py`**

```python
"""Aspect hashing: SHA-256(salt ‖ JCS(payload))."""
from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

from ocx_integrity.profile import PROFILE


def payload(kind: str, part_id: str, aspect: str, record: dict[str, Any]) -> bytes:
    return rfc8785.dumps({
        "profile": PROFILE,
        "kind": kind,
        "part_id": part_id,
        "aspect": aspect,
        "record": record,
    })


def aspect_hash(salt: bytes, kind: str, part_id: str, aspect: str,
                record: dict[str, Any]) -> bytes:
    return hashlib.sha256(salt + payload(kind, part_id, aspect, record)).digest()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_hashing.py -q`
Expected: `10 passed`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/salts.py packages/ocx-integrity/src/ocx_integrity/hashing.py tests/test_integrity_hashing.py
git commit -m "feat(integrity): HMAC salts, key loading and JCS aspect hashing

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: RFC 9162 Merkle tree

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/merkle.py`
- Test: `tests/test_integrity_merkle.py`

The definitions come from RFC 9162 §2.1:
- `MTH({}) = SHA-256()`
- `MTH({d0}) = SHA-256(0x00 ‖ d0)`
- For n > 1, `MTH(D[n]) = SHA-256(0x01 ‖ MTH(D[0:k]) ‖ MTH(D[k:n]))`, where k is the largest power of two < n.
- The inclusion path is `PATH(m, D[n])` (§2.1.3.1), and verification follows §2.1.3.2.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_merkle.py`**

```python
"""RFC 9162 Merkle Tree Hash, inclusion paths and path verification."""
from __future__ import annotations

import hashlib

import pytest

from ocx_integrity.merkle import inclusion_path, mth, root_from_path


def L(d: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + d).digest()


def N(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _verifies(leaf, index, size, path, root) -> bool:
    try:
        return root_from_path(leaf, index, size, path) == root
    except ValueError:
        return False


def test_mth_empty_is_sha256_of_nothing():
    assert mth([]).hex() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_mth_small_trees_follow_rfc9162_split():
    a, b, c, d, e = b"a", b"b", b"c", b"d", b"e"
    assert mth([a]) == L(a)
    assert mth([a, b]) == N(L(a), L(b))
    assert mth([a, b, c]) == N(N(L(a), L(b)), L(c))
    assert mth([a, b, c, d, e]) == N(N(N(L(a), L(b)), N(L(c), L(d))), L(e))


@pytest.mark.parametrize("n", [1, 2, 3, 7, 8, 1000])
def test_inclusion_paths_verify(n):
    leaves = [f"leaf{i}".encode() for i in range(n)]
    root = mth(leaves)
    indices = range(n) if n <= 8 else (0, 1, 511, 512, 999)
    for m in indices:
        assert root_from_path(leaves[m], m, n, inclusion_path(m, leaves)) == root


def test_path_lengths():
    leaves = [bytes([i]) for i in range(8)]
    assert len(inclusion_path(0, leaves)) == 3
    assert len(inclusion_path(6, leaves[:7])) == 2


def test_tampering_fails_verification():
    leaves = [f"leaf{i}".encode() for i in range(7)]
    root = mth(leaves)
    path = inclusion_path(3, leaves)
    assert _verifies(leaves[3], 3, 7, path, root)
    assert not _verifies(b"forged", 3, 7, path, root)
    assert not _verifies(leaves[3], 4, 7, path, root)
    assert not _verifies(leaves[3], 3, 8, path, root)
    assert not _verifies(leaves[3], 3, 7, [bytes(32)] + path[1:], root)


def test_malformed_inputs_raise():
    with pytest.raises(ValueError):
        root_from_path(b"a", 1, 1, [])  # index out of range
    with pytest.raises(ValueError):
        root_from_path(b"a", 0, 2, [])  # path too short
    with pytest.raises(ValueError):
        root_from_path(b"a", 0, 1, [bytes(32)])  # path too long
    with pytest.raises(ValueError):
        inclusion_path(5, [b"a"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_merkle.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.merkle'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/merkle.py`**

```python
"""RFC 9162 §2.1 Merkle Tree Hash (SHA-256), inclusion paths and verification."""
from __future__ import annotations

import hashlib
from collections.abc import Sequence


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly less than n (n > 1)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(leaves: Sequence[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaf_hash(leaves[0])
    k = _split(n)
    return node_hash(mth(leaves[:k]), mth(leaves[k:]))


def inclusion_path(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    """RFC 9162 PATH(m, D[n]) — sibling hashes from leaf to root."""
    n = len(leaves)
    if not 0 <= index < n:
        raise ValueError(f"leaf index {index} out of range for tree size {n}")
    if n == 1:
        return []
    k = _split(n)
    if index < k:
        return inclusion_path(index, leaves[:k]) + [mth(leaves[k:])]
    return inclusion_path(index - k, leaves[k:]) + [mth(leaves[:k])]


def root_from_path(leaf: bytes, index: int, size: int, path: Sequence[bytes]) -> bytes:
    """RFC 9162 §2.1.3.2: recompute the root from leaf data + audit path.

    Raises ValueError if the index is out of range or the path length is wrong.
    """
    if not 0 <= index < size:
        raise ValueError(f"leaf index {index} out of range for tree size {size}")
    fn, sn = index, size - 1
    r = leaf_hash(leaf)
    for p in path:
        if sn == 0:
            raise ValueError("audit path too long")
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError("audit path too short")
    return r
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_merkle.py -q`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/merkle.py tests/test_integrity_merkle.py
git commit -m "feat(integrity): RFC 9162 Merkle tree hash and inclusion proofs

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Manifest — hash a vessel, build, save, load

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/manifest.py`
- Test: `tests/test_integrity_manifest.py`
- Test: `tests/test_integrity_canon.py` (append hash-level invariance tests)

Background:
- `hash_vessel` returns the full in-memory result (records, salts, hashes). `prove` (Task 10) needs the records and salts.
- `Manifest` is the shareable JSON form: hex hashes only, no records and no salts.
- `created` and `source` are informational and not part of the root.
- `Manifest.from_dict` refuses other profiles, and refuses manifests whose hashes do not recompute.
- Part ordering for the root is by UTF-8 bytes of the part ID.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_manifest.py`**

```python
"""Manifest build / save / load (ocx-hash/1)."""
from __future__ import annotations

import hashlib
import json

import pytest
from ocx_model_core.model.ir import Quantity, Ref

from ocx_integrity.errors import DuplicatePartIdError, IntegrityError, ProfileMismatchError
from ocx_integrity.manifest import (
    build_manifest,
    hash_vessel,
    load_manifest,
    save_manifest,
    source_info,
)
from ocx_integrity.merkle import mth
from ocx_integrity.profile import ASPECTS
from tests.integrity_fixtures import KEY, OTHER_KEY, make_vessel


def test_build_manifest_structure():
    m = build_manifest(make_vessel(), KEY, created="2026-01-01T00:00:00Z")
    assert m.profile == "ocx-hash/1"
    assert m.part_count == 6
    assert m.parts["G-PL-1"].kind == "plate"
    assert m.parts["ST1"].id_source == "xml_id"
    assert m.parts["vessel:V1"].id_source == "vessel"
    assert list(m.parts["G-PL-1"].aspects) == list(ASPECTS)
    assert m.warnings == []
    assert m.computed_root() == m.root


def test_root_is_deterministic_and_key_dependent():
    a = build_manifest(make_vessel(), KEY)
    assert build_manifest(make_vessel(), KEY).root == a.root
    assert build_manifest(make_vessel(), OTHER_KEY).root != a.root


def test_root_ignores_created_and_source():
    a = build_manifest(make_vessel(), KEY, created="2026-01-01T00:00:00Z")
    b = build_manifest(make_vessel(), KEY, created="2027-01-01T00:00:00Z",
                       source={"file": "x.3docx", "sha256": "00", "schema_version": "3.1.0"})
    assert a.root == b.root
    assert a.to_dict() != b.to_dict()


def test_hash_vessel_root_matches_manual_mth():
    hm = hash_vessel(make_vessel(), KEY)
    ids = sorted(hm.parts, key=lambda s: s.encode("utf-8"))
    assert hm.root == mth([hm.parts[p].part_hash for p in ids])
    plate = hm.parts["G-PL-1"]
    assert plate.part_hash == mth([plate.aspect_hashes[a] for a in ASPECTS])


def test_duplicate_part_ids_raise():
    v = make_vessel()
    v.stiffeners["ST1"].guidref = "G-PL-1"
    with pytest.raises(DuplicatePartIdError) as exc:
        hash_vessel(v, KEY)
    assert exc.value.part_ids == ["G-PL-1"]


def test_save_load_roundtrip_never_writes_key(tmp_path):
    m = build_manifest(make_vessel(), KEY,
                       source={"file": "x.3docx", "sha256": "00", "schema_version": "3.1.0"})
    path = tmp_path / "manifest.json"
    save_manifest(m, path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert list(data["parts"]) == sorted(data["parts"], key=lambda s: s.encode("utf-8"))
    assert data["part_count"] == 6
    assert KEY.hex() not in text
    assert load_manifest(path) == m


def test_load_rejects_other_profile(tmp_path):
    data = build_manifest(make_vessel(), KEY).to_dict()
    data["profile"] = "ocx-hash/2"
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProfileMismatchError):
        load_manifest(path)


def test_load_rejects_tampered_hashes(tmp_path):
    good = build_manifest(make_vessel(), KEY).to_dict()
    path = tmp_path / "m.json"
    bad_aspect = json.loads(json.dumps(good))
    bad_aspect["parts"]["G-PL-1"]["aspects"]["scantlings"] = "00" * 32
    path.write_text(json.dumps(bad_aspect), encoding="utf-8")
    with pytest.raises(IntegrityError):
        load_manifest(path)
    bad_root = json.loads(json.dumps(good))
    bad_root["root"] = "00" * 32
    path.write_text(json.dumps(bad_root), encoding="utf-8")
    with pytest.raises(IntegrityError):
        load_manifest(path)


def test_unknown_unit_and_unresolved_refs_become_warnings():
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(12.0, "Ufoo")
    v.plates["PL1"].material_ref = Ref("M404")
    assert build_manifest(v, KEY).warnings == [
        "unknown unit 'Ufoo' on plate G-PL-1",
        "unresolved material reference 'M404' on plate G-PL-1",
    ]


def test_source_info(tmp_path):
    model = tmp_path / "model.3docx"
    model.write_bytes(b"<ocx/>")
    assert source_info(model, "3.1.0") == {
        "file": "model.3docx",
        "sha256": hashlib.sha256(b"<ocx/>").hexdigest(),
        "schema_version": "3.1.0",
    }
```

- [ ] **Step 2: Append the hash-level invariance tests to `tests/test_integrity_canon.py`**

Add to the imports at the top:

```python
from ocx_model_core.model.ir import IrCog, IrMassProperties

from ocx_integrity.manifest import hash_vessel
from tests.integrity_fixtures import KEY
```

Append:

```python
def _aspect_hashes(vessel):
    return {pid: p.aspect_hashes for pid, p in hash_vessel(vessel, KEY).parts.items()}


def _changed(a, b):
    out = {}
    for pid in a:
        diff = sorted(x for x in set(a[pid]) | set(b[pid]) if a[pid].get(x) != b[pid].get(x))
        if diff:
            out[pid] = diff
    return out


def test_thickness_change_only_touches_scantlings():
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    assert _changed(_aspect_hashes(make_vessel()), _aspect_hashes(v)) == {
        "G-PL-1": ["scantlings"]}


def test_weight_change_only_touches_physical():
    v = make_vessel()
    v.plates["PL1"].mass_properties = IrMassProperties(
        moulded_dry_weight=Quantity(1600.0, "Ukg"),
        moulded_cog=IrCog(1000.0, 1000.0, 0.0, "Umm"))
    assert _changed(_aspect_hashes(make_vessel()), _aspect_hashes(v)) == {
        "G-PL-1": ["physical"]}


def test_hashes_invariant_to_units_order_contour_start_and_noise():
    v = make_vessel()
    v.plates["PL1"].outer_contour = square(unit="Um", size=2.0, start=2, reverse=True)
    v.plates["PL1"].thickness = Quantity(0.012, "Um")
    v.plates["PL1"].cut_by_holes.reverse()
    v.panels["P1"].limited_by.reverse()
    v.stiffeners["ST1"].trace = IrLine3D(
        curve_length=Quantity(2.0000000001, "Um"),
        start=IrPoint3D(0.0, 1.0000000001, 0.0, "Um"),
        end=IrPoint3D(2.0, 1.0, 0.0, "Um"))
    assert _aspect_hashes(v) == _aspect_hashes(make_vessel())
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_manifest.py tests/test_integrity_canon.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.manifest'`.

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/manifest.py`**

```python
"""Hash a vessel; build, serialise and load the shareable integrity manifest."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.errors import DuplicatePartIdError, IntegrityError, ProfileMismatchError
from ocx_integrity.hashing import aspect_hash
from ocx_integrity.merkle import mth
from ocx_integrity.profile import ASPECTS, PROFILE
from ocx_integrity.records import iter_parts
from ocx_integrity.records.common import Context
from ocx_integrity.salts import derive_salt


def ordered_ids(part_ids: Iterable[str]) -> list[str]:
    """Root leaf order: part IDs sorted by their UTF-8 bytes."""
    return sorted(part_ids, key=lambda s: s.encode("utf-8"))


# --- in-memory result (contains records + salts: never written to a manifest) ---

@dataclass(frozen=True)
class HashedPart:
    kind: str
    id_source: str
    records: dict[str, dict[str, Any]]
    salts: dict[str, bytes]
    aspect_hashes: dict[str, bytes]
    part_hash: bytes


@dataclass(frozen=True)
class HashedModel:
    parts: dict[str, HashedPart]
    warnings: list[str]

    @property
    def root(self) -> bytes:
        return mth([self.parts[p].part_hash for p in ordered_ids(self.parts)])


def hash_vessel(vessel: IrVessel, key: bytes) -> HashedModel:
    ctx = Context(vessel)
    parts: dict[str, HashedPart] = {}
    duplicates: set[str] = set()
    for rec in iter_parts(vessel, ctx):
        if rec.part_id in parts:
            duplicates.add(rec.part_id)
            continue
        salts = {a: derive_salt(key, rec.part_id, a) for a in rec.aspects}
        hashes = {a: aspect_hash(salts[a], rec.kind, rec.part_id, a, record)
                  for a, record in rec.aspects.items()}
        parts[rec.part_id] = HashedPart(rec.kind, rec.id_source, rec.aspects, salts, hashes,
                                        mth(list(hashes.values())))
    if duplicates:
        raise DuplicatePartIdError(ordered_ids(duplicates))
    return HashedModel(parts, sorted(set(ctx.warnings)))


# --- shareable manifest ---------------------------------------------------------

@dataclass
class PartEntry:
    kind: str
    id_source: str
    part_hash: str
    aspects: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id_source": self.id_source,
                "part_hash": self.part_hash, "aspects": dict(self.aspects)}


@dataclass
class Manifest:
    root: str
    parts: dict[str, PartEntry]
    warnings: list[str] = field(default_factory=list)
    profile: str = PROFILE
    created: str | None = None
    source: dict[str, Any] | None = None

    @property
    def part_count(self) -> int:
        return len(self.parts)

    def ordered_ids(self) -> list[str]:
        return ordered_ids(self.parts)

    def computed_root(self) -> str:
        return mth([bytes.fromhex(self.parts[p].part_hash) for p in self.ordered_ids()]).hex()

    def check_consistency(self) -> None:
        """Raise IntegrityError unless every part_hash and the root recompute."""
        for pid, entry in self.parts.items():
            unknown = set(entry.aspects) - set(ASPECTS)
            hashes = [bytes.fromhex(entry.aspects[a]) for a in ASPECTS if a in entry.aspects]
            if unknown or mth(hashes).hex() != entry.part_hash:
                raise IntegrityError(f"part {pid!r}: part_hash does not match its aspect hashes")
        if self.computed_root() != self.root:
            raise IntegrityError("manifest root does not match its part hashes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "created": self.created,
            "source": self.source,
            "root": self.root,
            "part_count": self.part_count,
            "warnings": list(self.warnings),
            "parts": {pid: self.parts[pid].to_dict() for pid in self.ordered_ids()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        profile = data.get("profile")
        if profile != PROFILE:
            raise ProfileMismatchError(f"unsupported profile {profile!r} (expected {PROFILE!r})")
        parts = {pid: PartEntry(e["kind"], e["id_source"], e["part_hash"], dict(e["aspects"]))
                 for pid, e in data["parts"].items()}
        manifest = cls(root=data["root"], parts=parts, warnings=list(data.get("warnings", [])),
                       profile=profile, created=data.get("created"), source=data.get("source"))
        manifest.check_consistency()
        return manifest


def manifest_from_hashed(hashed: HashedModel, *, created: str | None = None,
                         source: dict[str, Any] | None = None) -> Manifest:
    parts = {
        pid: PartEntry(p.kind, p.id_source, p.part_hash.hex(),
                       {a: h.hex() for a, h in p.aspect_hashes.items()})
        for pid, p in hashed.parts.items()
    }
    return Manifest(root=hashed.root.hex(), parts=parts, warnings=list(hashed.warnings),
                    created=created, source=source)


def build_manifest(vessel: IrVessel, key: bytes, *, source: dict[str, Any] | None = None,
                   created: str | None = None) -> Manifest:
    if created is None:
        created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return manifest_from_hashed(hash_vessel(vessel, key), created=created, source=source)


def source_info(path: Path, schema_version: str) -> dict[str, Any]:
    with Path(path).open("rb") as fh:
        digest = hashlib.file_digest(fh, "sha256").hexdigest()
    return {"file": Path(path).name, "sha256": digest, "schema_version": schema_version}


def save_manifest(manifest: Manifest, path: Path) -> None:
    Path(path).write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def load_manifest(path: Path) -> Manifest:
    return Manifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_manifest.py tests/test_integrity_canon.py -q`
Expected: `43 passed` (10 manifest + 33 canon).

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/manifest.py tests/test_integrity_manifest.py tests/test_integrity_canon.py
git commit -m "feat(integrity): build, save and load the integrity manifest

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Diff and verify

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/diff.py`
- Create: `packages/ocx-integrity/src/ocx_integrity/verify.py`
- Test: `tests/test_integrity_diff.py`

Background:
- A part is "changed" when it exists in both manifests and at least one aspect hash differs, or an aspect was added or removed.
- Changed aspects are listed in `ASPECTS` order.
- Diffing manifests built with different keys reports every part as changed. The spec documents this; the code does not detect it.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_diff.py`**

```python
"""Manifest diff and model verification."""
from __future__ import annotations

import dataclasses

import pytest
from ocx_model_core.model.ir import Quantity

from ocx_integrity.diff import diff_manifests, format_report
from ocx_integrity.errors import ProfileMismatchError
from ocx_integrity.manifest import build_manifest
from ocx_integrity.verify import verify_model
from tests.integrity_fixtures import KEY, OTHER_KEY, make_vessel


def _manifest(vessel=None, key=KEY):
    return build_manifest(vessel or make_vessel(), key, created="2026-01-01T00:00:00Z")


def _edited():
    """+ST2, -compartment C1, thicker plate PL1."""
    v = make_vessel()
    v.stiffeners["ST2"] = dataclasses.replace(v.stiffeners["ST1"], id="ST2", name="L2")
    del v.compartments["C1"]
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    return v


def test_identical_manifests_are_clean():
    a = _manifest()
    report = diff_manifests(a, _manifest())
    assert report.clean
    assert (report.added, report.removed, report.changed) == ([], [], {})
    assert report.unchanged_count == 6
    assert report.root_a == report.root_b == a.root


def test_added_removed_changed_classification():
    a, b = _manifest(), _manifest(_edited())
    report = diff_manifests(a, b)
    assert not report.clean
    assert report.added == ["ST2"]
    assert report.removed == ["G-COMP-1"]
    assert report.changed == {"G-PL-1": ["scantlings"]}
    assert report.unchanged_count == 4
    assert (report.root_a, report.root_b) == (a.root, b.root)


def test_report_to_dict_and_text():
    a, b = _manifest(), _manifest(_edited())
    report = diff_manifests(a, b)
    assert report.to_dict() == {
        "clean": False, "root_a": a.root, "root_b": b.root,
        "added": ["ST2"], "removed": ["G-COMP-1"],
        "changed": {"G-PL-1": ["scantlings"]}, "unchanged_count": 4,
    }
    assert format_report(report) == "\n".join([
        f"root A: {a.root}",
        f"root B: {b.root}",
        "added (1): ST2",
        "removed (1): G-COMP-1",
        "changed (1):",
        "  G-PL-1: scantlings",
        "unchanged: 4",
    ])
    clean = diff_manifests(a, a)
    assert format_report(clean).splitlines()[-1] == "match: 6 parts unchanged"


def test_profile_mismatch_refused():
    a, b = _manifest(), _manifest()
    b.profile = "ocx-hash/2"
    with pytest.raises(ProfileMismatchError):
        diff_manifests(a, b)


def test_different_keys_report_everything_changed():
    report = diff_manifests(_manifest(), _manifest(key=OTHER_KEY))
    assert sorted(report.changed) == sorted(_manifest().parts)
    assert report.unchanged_count == 0


def test_verify_model_clean_and_changed():
    m = _manifest()
    assert verify_model(make_vessel(), m, KEY).clean
    report = verify_model(_edited(), m, KEY)
    assert report.changed == {"G-PL-1": ["scantlings"]}
    assert report.root_a == m.root
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_diff.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.diff'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/diff.py`**

```python
"""Compare two integrity manifests part by part and aspect by aspect."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ocx_integrity.errors import ProfileMismatchError
from ocx_integrity.manifest import Manifest, ordered_ids
from ocx_integrity.profile import ASPECTS


@dataclass
class ChangeReport:
    root_a: str
    root_b: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, list[str]] = field(default_factory=dict)
    unchanged_count: int = 0

    @property
    def clean(self) -> bool:
        return (self.root_a == self.root_b and not self.added and not self.removed
                and not self.changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "root_a": self.root_a,
            "root_b": self.root_b,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": {pid: list(a) for pid, a in self.changed.items()},
            "unchanged_count": self.unchanged_count,
        }


def diff_manifests(a: Manifest, b: Manifest) -> ChangeReport:
    if a.profile != b.profile:
        raise ProfileMismatchError(f"cannot diff profile {a.profile!r} against {b.profile!r}")
    report = ChangeReport(root_a=a.root, root_b=b.root)
    report.added = ordered_ids(set(b.parts) - set(a.parts))
    report.removed = ordered_ids(set(a.parts) - set(b.parts))
    for pid in ordered_ids(set(a.parts) & set(b.parts)):
        ea, eb = a.parts[pid].aspects, b.parts[pid].aspects
        aspects = [x for x in ASPECTS if ea.get(x) != eb.get(x)]
        if aspects or a.parts[pid].part_hash != b.parts[pid].part_hash:
            report.changed[pid] = aspects
        else:
            report.unchanged_count += 1
    return report


def format_report(report: ChangeReport) -> str:
    lines = [f"root A: {report.root_a}", f"root B: {report.root_b}"]
    if report.clean:
        lines.append(f"match: {report.unchanged_count} parts unchanged")
        return "\n".join(lines)
    if report.added:
        lines.append(f"added ({len(report.added)}): {', '.join(report.added)}")
    if report.removed:
        lines.append(f"removed ({len(report.removed)}): {', '.join(report.removed)}")
    if report.changed:
        lines.append(f"changed ({len(report.changed)}):")
        lines += [f"  {pid}: {', '.join(aspects)}" for pid, aspects in report.changed.items()]
    lines.append(f"unchanged: {report.unchanged_count}")
    return "\n".join(lines)
```

- [ ] **Step 4: Create `packages/ocx-integrity/src/ocx_integrity/verify.py`**

```python
"""Verify a model against a stored manifest."""
from __future__ import annotations

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.diff import ChangeReport, diff_manifests
from ocx_integrity.manifest import Manifest, build_manifest


def verify_model(vessel: IrVessel, manifest: Manifest, key: bytes) -> ChangeReport:
    """Rebuild the manifest from ``vessel`` and diff it against ``manifest`` (A = stored)."""
    return diff_manifests(manifest, build_manifest(vessel, key))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_diff.py -q`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/diff.py packages/ocx-integrity/src/ocx_integrity/verify.py tests/test_integrity_diff.py
git commit -m "feat(integrity): manifest diff and model verification

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Selective-disclosure proof bundles

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/proof.py`
- Test: `tests/test_integrity_proof.py`

Background:
- `prove` needs the key: it rebuilds the records and salts, and first refuses if the part has drifted from the manifest.
- `check_bundle` needs only the bundle, and optionally a root obtained independently (e.g. the signed root).
- A bundle always carries all of the part's aspect hashes, so `part_hash` can be recomputed. Only the disclosed aspects carry a record and salt.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_proof.py`**

```python
"""Disclosure bundles: prove (yard, with key) and check (class, no key)."""
from __future__ import annotations

import copy
import json

import pytest
from ocx_model_core.model.ir import Quantity

from ocx_integrity.errors import PartDriftError, ProfileMismatchError, UnknownPartError
from ocx_integrity.manifest import build_manifest
from ocx_integrity.profile import ASPECTS
from ocx_integrity.proof import BundleCheck, DisclosureBundle, check_bundle, prove
from tests.integrity_fixtures import KEY, make_vessel


def _setup():
    v = make_vessel()
    return v, build_manifest(v, KEY)


def test_full_bundle_checks_without_key():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1")
    assert list(b.disclosed) == list(ASPECTS)
    assert b.aspect_hashes == m.parts["G-PL-1"].aspects
    assert (b.tree_size, b.leaf_index, b.kind) == (6, 2, "plate")
    assert check_bundle(b) == BundleCheck(True, [])
    assert check_bundle(b, root=m.root.upper()).valid


def test_selective_disclosure_reveals_only_requested_aspects():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1", ["scantlings"])
    assert list(b.disclosed) == ["scantlings"]
    assert set(b.disclosed["scantlings"]) == {"record", "salt"}
    assert b.disclosed["scantlings"]["record"]["kind"] == "plate"
    assert check_bundle(b).valid


def test_bundle_json_roundtrip_never_contains_key():
    v, m = _setup()
    b = prove(v, m, KEY, "G-PL-1")
    text = json.dumps(b.to_dict())
    assert KEY.hex() not in text
    assert DisclosureBundle.from_dict(json.loads(text)) == b


def _set(path, value):
    def tamper(d):
        target = d
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return tamper


@pytest.mark.parametrize("tamper, fragment", [
    (_set(["disclosed", "scantlings", "record", "kind"], "stiffener"), "scantlings"),
    (_set(["disclosed", "scantlings", "salt"], "00" * 32), "scantlings"),
    (_set(["aspect_hashes", "scantlings"], "00" * 32), "scantlings"),
    (_set(["aspect_hashes", "identity"], "00" * 32), "root"),
    (_set(["audit_path", 0], "00" * 32), "root"),
    (_set(["root"], "00" * 32), "root"),
    (_set(["leaf_index"], 3), "path"),
    (_set(["aspect_hashes", "bogus"], "00" * 32), "unknown aspect"),
    (_set(["audit_path", 0], "zz"), "hex"),
])
def test_tampered_bundle_fails(tamper, fragment):
    v, m = _setup()
    d = copy.deepcopy(prove(v, m, KEY, "G-PL-1", ["scantlings"]).to_dict())
    tamper(d)
    result = check_bundle(DisclosureBundle.from_dict(d))
    assert not result.valid
    assert any(fragment in e for e in result.errors), result.errors


def test_expected_root_mismatch_fails():
    v, m = _setup()
    result = check_bundle(prove(v, m, KEY, "G-PL-1"), root="00" * 32)
    assert result.errors == ["bundle root does not match the expected root"]


def test_bundle_profile_mismatch_refused():
    v, m = _setup()
    d = prove(v, m, KEY, "G-PL-1").to_dict()
    d["profile"] = "ocx-hash/2"
    with pytest.raises(ProfileMismatchError):
        DisclosureBundle.from_dict(d)


def test_unknown_part_or_aspect_refused():
    v, m = _setup()
    with pytest.raises(UnknownPartError):
        prove(v, m, KEY, "NOPE")
    with pytest.raises(UnknownPartError):
        prove(v, m, KEY, "G-PL-1", ["bogus"])


def test_drifted_part_refused_but_other_parts_still_provable():
    _, m = _setup()
    drifted = make_vessel()
    drifted.plates["PL1"].thickness = Quantity(14.0, "Umm")
    with pytest.raises(PartDriftError):
        prove(drifted, m, KEY, "G-PL-1")
    b = prove(drifted, m, KEY, "ST1")
    assert check_bundle(b, root=m.root).valid
```

The fixture's ordered part IDs are `G-COMP-1, G-PAN-1, G-PL-1, SE1, ST1, vessel:V1`, so `G-PL-1` has leaf index 2.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_proof.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.proof'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/proof.py`**

```python
"""Selective-disclosure bundles: one part's aspects + a Merkle audit path to the root."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ocx_model_core.model.ir import IrVessel

from ocx_integrity.errors import PartDriftError, ProfileMismatchError, UnknownPartError
from ocx_integrity.hashing import aspect_hash
from ocx_integrity.manifest import Manifest, hash_vessel
from ocx_integrity.merkle import inclusion_path, mth, root_from_path
from ocx_integrity.profile import ASPECTS, PROFILE


@dataclass
class DisclosureBundle:
    root: str
    tree_size: int
    leaf_index: int
    part_id: str
    kind: str
    disclosed: dict[str, dict[str, Any]]  # aspect -> {"record": {...}, "salt": hex}
    aspect_hashes: dict[str, str]
    audit_path: list[str]
    profile: str = PROFILE

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "root": self.root,
            "tree_size": self.tree_size,
            "leaf_index": self.leaf_index,
            "part_id": self.part_id,
            "kind": self.kind,
            "disclosed": self.disclosed,
            "aspect_hashes": self.aspect_hashes,
            "audit_path": self.audit_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisclosureBundle:
        profile = data.get("profile")
        if profile != PROFILE:
            raise ProfileMismatchError(f"unsupported profile {profile!r} (expected {PROFILE!r})")
        return cls(
            root=data["root"], tree_size=data["tree_size"], leaf_index=data["leaf_index"],
            part_id=data["part_id"], kind=data["kind"], disclosed=data["disclosed"],
            aspect_hashes=data["aspect_hashes"], audit_path=list(data["audit_path"]),
            profile=profile,
        )


@dataclass(frozen=True)
class BundleCheck:
    valid: bool
    errors: list[str]


def prove(vessel: IrVessel, manifest: Manifest, key: bytes, part_id: str,
          aspects: Iterable[str] | None = None) -> DisclosureBundle:
    """Build a bundle disclosing ``aspects`` (default: all) of ``part_id``."""
    entry = manifest.parts.get(part_id)
    if entry is None:
        raise UnknownPartError(f"part {part_id!r} is not in the manifest")
    wanted = set(entry.aspects) if aspects is None else set(aspects)
    unknown = sorted(wanted - set(entry.aspects))
    if unknown:
        raise UnknownPartError(f"part {part_id!r} has no aspect(s): {', '.join(unknown)}")
    part = hash_vessel(vessel, key).parts.get(part_id)
    if part is None or part.part_hash.hex() != entry.part_hash:
        raise PartDriftError(f"part {part_id!r} in the model no longer matches the manifest")
    ids = manifest.ordered_ids()
    index = ids.index(part_id)
    leaves = [bytes.fromhex(manifest.parts[p].part_hash) for p in ids]
    return DisclosureBundle(
        root=manifest.root,
        tree_size=len(ids),
        leaf_index=index,
        part_id=part_id,
        kind=entry.kind,
        disclosed={a: {"record": part.records[a], "salt": part.salts[a].hex()}
                   for a in ASPECTS if a in wanted},
        aspect_hashes=dict(entry.aspects),
        audit_path=[h.hex() for h in inclusion_path(index, leaves)],
    )


def _check_disclosed(bundle: DisclosureBundle, errors: list[str]) -> None:
    for aspect, item in bundle.disclosed.items():
        try:
            computed = aspect_hash(bytes.fromhex(item["salt"]), bundle.kind, bundle.part_id,
                                   aspect, item["record"]).hex()
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"aspect {aspect!r}: malformed disclosure ({exc})")
            continue
        if computed != bundle.aspect_hashes.get(aspect):
            errors.append(f"aspect {aspect!r}: disclosed record/salt do not match its hash")


def _check_path(bundle: DisclosureBundle, errors: list[str]) -> None:
    unknown = sorted(set(bundle.aspect_hashes) - set(ASPECTS))
    if unknown:
        errors.append(f"unknown aspect(s) in aspect_hashes: {', '.join(unknown)}")
        return
    try:
        part_hash = mth([bytes.fromhex(bundle.aspect_hashes[a])
                         for a in ASPECTS if a in bundle.aspect_hashes])
        path = [bytes.fromhex(p) for p in bundle.audit_path]
    except (TypeError, ValueError) as exc:
        errors.append(f"malformed hex in bundle ({exc})")
        return
    try:
        computed = root_from_path(part_hash, bundle.leaf_index, bundle.tree_size, path)
    except ValueError as exc:
        errors.append(f"invalid audit path: {exc}")
        return
    if computed.hex() != bundle.root.lower():
        errors.append("audit path does not lead to the bundle root")


def check_bundle(bundle: DisclosureBundle, root: str | None = None) -> BundleCheck:
    """Verify a bundle without the key; optionally pin it to an independently known root."""
    errors: list[str] = []
    _check_disclosed(bundle, errors)
    _check_path(bundle, errors)
    if root is not None and root.lower() != bundle.root.lower():
        errors.append("bundle root does not match the expected root")
    return BundleCheck(not errors, errors)
```

Why each tampered case fails with its fragment:
- record, salt, or the scantlings hash: `_check_disclosed` reports "aspect 'scantlings' …".
- identity hash, path entry, or root: the recomputed root differs, giving "… bundle root".
- `leaf_index` 3: either the path length check raises ("invalid audit path: …") or the root differs ("audit path does not lead …"). Both contain "path".
- A bogus aspect is caught by the unknown-aspect check.
- `"zz"` is caught as malformed hex.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_proof.py -q`
Expected: `16 passed` (7 single tests + 9 parametrised tamper cases).

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/proof.py tests/test_integrity_proof.py
git commit -m "feat(integrity): selective-disclosure proof bundles

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 11: `ocx-integrity` CLI

**Files:**
- Create: `packages/ocx-integrity/src/ocx_integrity/cli.py`
- Test: `tests/test_integrity_cli.py`

Exit codes from the spec:

| Code | Meaning |
|---|---|
| 0 | ok, match, or bundle valid |
| 1 | mismatch, changes found, bundle invalid, or part drift on `prove` |
| 2 | cannot run: parse/build failure, bad or missing key, unknown profile, tampered or unreadable manifest/bundle, duplicate part IDs, unknown `--part`/`--aspect`, `keygen` target already exists |
| 3 | cannot write output |

`_load_vessel` copies `ocx_render.cli._load_vessel`, so tests can monkeypatch it with the synthetic vessel, as `tests/test_render_cli.py` does. Errors are logged via loguru to stderr. Results go to stdout via `typer.echo`, so JSON output stays parseable.

- [ ] **Step 1: Write the failing tests `tests/test_integrity_cli.py`**

```python
"""CLI tests for `ocx-integrity` (synthetic vessel via a patched _load_vessel)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from ocx_model_core.model.ir import Quantity
from typer.testing import CliRunner

import ocx_integrity.cli as cli_mod
from ocx_integrity.cli import app
from ocx_integrity.salts import KEY_ENV, parse_key
from tests.integrity_fixtures import KEY, make_vessel

runner = CliRunner()


def _invoke(*args):
    return runner.invoke(app, [str(a) for a in args])


def _edited_vessel(model):
    v = make_vessel()
    v.plates["PL1"].thickness = Quantity(14.0, "Umm")
    return v


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.setattr(cli_mod, "_load_vessel", lambda model: make_vessel())
    model = tmp_path / "m.3docx"
    model.write_text("<x/>", encoding="utf-8")
    key = tmp_path / "yard.key"
    key.write_text(KEY.hex() + "\n", encoding="utf-8")
    return SimpleNamespace(tmp=tmp_path, model=model, key=key,
                           manifest=tmp_path / "manifest.json")


def _make_manifest(env, output=None):
    output = output or env.manifest
    result = _invoke("manifest", env.model, "--key", env.key, "-o", output)
    assert result.exit_code == 0, result.output
    return output


def test_keygen_writes_key_and_refuses_overwrite(tmp_path):
    out = tmp_path / "yard.key"
    result = _invoke("keygen", "-o", out)
    assert result.exit_code == 0, result.output
    assert len(parse_key(out.read_text(encoding="utf-8"))) == 32
    assert out.read_text(encoding="utf-8").strip() not in result.stdout
    assert _invoke("keygen", "-o", out).exit_code == 2


def test_manifest_then_verify_clean(env):
    _make_manifest(env)
    text = env.manifest.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["part_count"] == 6
    assert data["source"]["file"] == "m.3docx"
    assert data["created"].endswith("Z")
    assert KEY.hex() not in text
    result = _invoke("verify", env.model, env.manifest, "--key", env.key)
    assert result.exit_code == 0, result.output
    assert "match: 6 parts unchanged" in result.stdout


def test_manifest_default_output_and_env_key(env, monkeypatch):
    monkeypatch.setenv(KEY_ENV, KEY.hex())
    result = _invoke("manifest", env.model)
    assert result.exit_code == 0, result.output
    assert (env.tmp / "m.manifest.json").exists()


def test_verify_edited_model_exits_1(env, monkeypatch):
    _make_manifest(env)
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    result = _invoke("verify", env.model, env.manifest, "--key", env.key)
    assert result.exit_code == 1
    assert "  G-PL-1: scantlings" in result.stdout


def test_prove_then_check(env):
    _make_manifest(env)
    root = json.loads(env.manifest.read_text(encoding="utf-8"))["root"]
    bundle = env.tmp / "bundle.json"
    result = _invoke("prove", env.model, env.manifest, "--key", env.key,
                     "--part", "G-PL-1", "--aspect", "scantlings", "-o", bundle)
    assert result.exit_code == 0, result.output
    assert list(json.loads(bundle.read_text(encoding="utf-8"))["disclosed"]) == ["scantlings"]

    result = _invoke("check", bundle, "--root", root)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("VALID")
    assert _invoke("check", bundle, "--root", "00" * 32).exit_code == 1

    data = json.loads(bundle.read_text(encoding="utf-8"))
    data["disclosed"]["scantlings"]["salt"] = "00" * 32
    bundle.write_text(json.dumps(data), encoding="utf-8")
    result = _invoke("check", bundle)
    assert result.exit_code == 1
    assert result.stdout.startswith("INVALID")


def test_prove_unknown_part_exits_2_and_drift_exits_1(env, monkeypatch):
    _make_manifest(env)
    out = env.tmp / "b.json"
    args = ("prove", env.model, env.manifest, "--key", env.key, "-o", out)
    assert _invoke(*args, "--part", "NOPE").exit_code == 2
    assert _invoke(*args, "--part", "G-PL-1", "--aspect", "bogus").exit_code == 2
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    assert _invoke(*args, "--part", "G-PL-1").exit_code == 1
    assert not out.exists()


def test_diff_text_and_json(env, monkeypatch):
    old = _make_manifest(env)
    monkeypatch.setattr(cli_mod, "_load_vessel", _edited_vessel)
    new = _make_manifest(env, env.tmp / "new.json")
    result = _invoke("diff", old, new)
    assert result.exit_code == 1
    assert "  G-PL-1: scantlings" in result.stdout
    result = _invoke("diff", old, new, "--format", "json")
    assert result.exit_code == 1
    assert json.loads(result.stdout)["changed"] == {"G-PL-1": ["scantlings"]}
    assert _invoke("diff", old, old).exit_code == 0
    assert _invoke("diff", old, new, "--format", "xml").exit_code == 2


@pytest.mark.parametrize("key_text", ["abcd", "not hex at all"])
def test_bad_key_exits_2(env, key_text):
    env.key.write_text(key_text, encoding="utf-8")
    assert _invoke("manifest", env.model, "--key", env.key, "-o", env.manifest).exit_code == 2
    assert not env.manifest.exists()


def test_missing_key_exits_2(env):
    assert _invoke("manifest", env.model, "-o", env.manifest).exit_code == 2


def test_duplicate_part_ids_exit_2(env, monkeypatch):
    def duplicated(model):
        v = make_vessel()
        v.stiffeners["ST1"].guidref = "G-PL-1"
        return v

    monkeypatch.setattr(cli_mod, "_load_vessel", duplicated)
    assert _invoke("manifest", env.model, "--key", env.key, "-o", env.manifest).exit_code == 2


def test_tampered_or_foreign_manifest_exits_2(env):
    _make_manifest(env)
    data = json.loads(env.manifest.read_text(encoding="utf-8"))
    data["root"] = "00" * 32
    env.manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _invoke("verify", env.model, env.manifest, "--key", env.key).exit_code == 2
    data["profile"] = "ocx-hash/2"
    env.manifest.write_text(json.dumps(data), encoding="utf-8")
    assert _invoke("diff", env.manifest, env.manifest).exit_code == 2
    env.manifest.write_text("not json", encoding="utf-8")
    assert _invoke("verify", env.model, env.manifest, "--key", env.key).exit_code == 2


def test_unparseable_model_exits_2(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    bad = tmp_path / "bad.3docx"
    bad.write_text("this is not xml", encoding="utf-8")
    key = tmp_path / "yard.key"
    key.write_text(KEY.hex(), encoding="utf-8")
    assert _invoke("manifest", bad, "--key", key, "-o", tmp_path / "m.json").exit_code == 2


def test_write_failure_exits_3(env):
    out = env.tmp / "missing-dir" / "manifest.json"
    assert _invoke("manifest", env.model, "--key", env.key, "-o", out).exit_code == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_integrity_cli.py -q`
Expected: collection ERROR `ModuleNotFoundError: No module named 'ocx_integrity.cli'`.

- [ ] **Step 3: Create `packages/ocx-integrity/src/ocx_integrity/cli.py`**

```python
"""ocx-integrity — salted aspect-hash manifests, verification, diffs and disclosure bundles."""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import typer
from loguru import logger

from ocx_integrity.diff import diff_manifests, format_report
from ocx_integrity.errors import IntegrityError, PartDriftError
from ocx_integrity.manifest import Manifest, build_manifest, save_manifest, source_info
from ocx_integrity.proof import DisclosureBundle, check_bundle
from ocx_integrity.proof import prove as prove_bundle
from ocx_integrity.salts import KEY_ENV, generate_key, load_key
from ocx_integrity.verify import verify_model

T = TypeVar("T")

app = typer.Typer(add_completion=False, help=__doc__)

KEY_HELP = f"Hex key file (default: ${KEY_ENV}). The key is never written to any output."


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(sys.stderr, level=level)


def _load_vessel(model: Path):
    """Parse the model and build the IR (raises on failure)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser

    root = OcxParser().parse(str(model))
    return get_builder(root.schema_version).build(root)


def _fail(code: int, message: str, *args: Any) -> typer.Exit:
    logger.error(message, *args)
    return typer.Exit(code=code)


def _key(path: Path | None) -> bytes:
    try:
        return load_key(path)
    except IntegrityError as exc:
        raise _fail(2, "Bad key: {}", exc) from exc


def _vessel(model: Path):
    try:
        return _load_vessel(model)
    except Exception as exc:  # noqa: BLE001 — any parse/build failure is exit 2
        raise _fail(2, "Cannot parse/build {}: {}", model, exc) from exc


def _read_json(path: Path, loader: Callable[[dict[str, Any]], T]) -> T:
    try:
        return loader(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IntegrityError) as exc:
        raise _fail(2, "Cannot load {}: {}", path, exc) from exc


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise _fail(3, "Cannot write {}: {}", path, exc) from exc


@app.command()
def keygen(
    output: Path = typer.Option(..., "--output", "-o", dir_okay=False,
                                help="Key file to create (refuses to overwrite)."),
) -> None:
    """Create a new random 32-byte key (hex). Keep it secret; never share it."""
    if output.exists():
        raise _fail(2, "Refusing to overwrite existing key file {}", output)
    _write_text(output, generate_key() + "\n")
    typer.echo(f"Key written to {output} (keep it secret)")


@app.command()
def manifest(
    model: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                 help="Path to the .3docx model."),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
    output: Path | None = typer.Option(None, "--output", "-o", dir_okay=False,
                                       help="Manifest path (default: <model>.manifest.json)."),
) -> None:
    """Hash every part of MODEL and write the shareable integrity manifest."""
    k = _key(key)
    vessel = _vessel(model)
    try:
        result = build_manifest(vessel, k, source=source_info(model, vessel.schema_version))
    except IntegrityError as exc:
        raise _fail(2, "Cannot build manifest for {}: {}", model, exc) from exc
    for warning in result.warnings:
        logger.warning(warning)
    out = output if output is not None else model.with_suffix(".manifest.json")
    try:
        save_manifest(result, out)
    except OSError as exc:
        raise _fail(3, "Cannot write {}: {}", out, exc) from exc
    typer.echo(f"Manifest written to {out}: root {result.root}, "
               f"{result.part_count} parts, {len(result.warnings)} warnings")


@app.command()
def verify(
    model: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                 help="Path to the .3docx model."),
    manifest_file: Path = typer.Argument(..., exists=True, dir_okay=False,
                                         help="Stored manifest.json."),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
) -> None:
    """Rebuild MODEL's hashes and compare them with MANIFEST_FILE (exit 1 on any change)."""
    stored = _read_json(manifest_file, Manifest.from_dict)
    k = _key(key)
    vessel = _vessel(model)
    try:
        report = verify_model(vessel, stored, k)
    except IntegrityError as exc:
        raise _fail(2, "Cannot verify {}: {}", model, exc) from exc
    typer.echo(format_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


@app.command()
def prove(
    model: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                 help="Path to the .3docx model."),
    manifest_file: Path = typer.Argument(..., exists=True, dir_okay=False,
                                         help="Stored manifest.json."),
    part: str = typer.Option(..., "--part", "-p", help="Part ID to disclose."),
    aspect: list[str] | None = typer.Option(
        None, "--aspect", "-a", help="Aspect to disclose (repeatable; default: all)."),
    output: Path = typer.Option(..., "--output", "-o", dir_okay=False,
                                help="Bundle path to write."),
    key: Path | None = typer.Option(None, "--key", "-k", dir_okay=False, help=KEY_HELP),
) -> None:
    """Write a disclosure bundle for one part (refused if the part has drifted)."""
    stored = _read_json(manifest_file, Manifest.from_dict)
    k = _key(key)
    vessel = _vessel(model)
    try:
        bundle = prove_bundle(vessel, stored, k, part, aspect or None)
    except PartDriftError as exc:
        raise _fail(1, "{}", exc) from exc
    except IntegrityError as exc:
        raise _fail(2, "{}", exc) from exc
    _write_text(output, json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False) + "\n")
    typer.echo(f"Bundle written to {output}: part {part}, "
               f"disclosed {', '.join(bundle.disclosed)}")


@app.command()
def check(
    bundle_file: Path = typer.Argument(..., exists=True, dir_okay=False,
                                       help="Disclosure bundle.json."),
    root: str | None = typer.Option(
        None, "--root", help="Expected root (hex), e.g. taken from the signed manifest."),
) -> None:
    """Verify a disclosure bundle without the key (exit 1 if invalid)."""
    bundle = _read_json(bundle_file, DisclosureBundle.from_dict)
    result = check_bundle(bundle, root=root)
    if result.valid:
        disclosed = ", ".join(bundle.disclosed) or "no aspects"
        typer.echo(f"VALID: part {bundle.part_id} ({disclosed}) is included "
                   f"under root {bundle.root}")
        return
    typer.echo("INVALID:")
    for error in result.errors:
        typer.echo(f"  {error}")
    raise typer.Exit(code=1)


@app.command()
def diff(
    old: Path = typer.Argument(..., exists=True, dir_okay=False, help="Older manifest.json."),
    new: Path = typer.Argument(..., exists=True, dir_okay=False, help="Newer manifest.json."),
    fmt: str = typer.Option("text", "--format", "-f", help="Output format: text or json."),
) -> None:
    """Compare two manifests part by part and aspect by aspect (exit 1 on any change)."""
    if fmt not in ("text", "json"):
        raise typer.BadParameter("expected 'text' or 'json'", param_hint="--format")
    a = _read_json(old, Manifest.from_dict)
    b = _read_json(new, Manifest.from_dict)
    try:
        report = diff_manifests(a, b)
    except IntegrityError as exc:
        raise _fail(2, "Cannot diff: {}", exc) from exc
    typer.echo(json.dumps(report.to_dict(), indent=2) if fmt == "json"
               else format_report(report))
    if not report.clean:
        raise typer.Exit(code=1)


def entrypoint() -> None:
    configure_logging()
    app()
```

Notes:
- `typer.BadParameter`, a missing file on an `exists=True` argument, and a missing required option are all Click usage errors, which exit 2. That matches "cannot run".
- In `verify`/`prove`, the manifest is read before the key and model, so a tampered manifest fails fast.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_integrity_cli.py -q`
Expected: `14 passed`.

- [ ] **Step 5: Smoke-test the installed entry point**

Run: `uv run ocx-integrity --help`
Expected: usage text listing the commands `keygen`, `manifest`, `verify`, `prove`, `check`, `diff`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/cli.py tests/test_integrity_cli.py
git commit -m "feat(integrity): ocx-integrity CLI (keygen/manifest/verify/prove/check/diff)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 12: Public API and golden vectors

**Files:**
- Modify: `packages/ocx-integrity/src/ocx_integrity/__init__.py`
- Create: `tests/test_integrity_golden.py`
- Create: `tests/data/integrity/golden_v1.json` (generated once, then pinned)

Background:
- The golden file pins profile `ocx-hash/1`.
- If any canonicalisation, serialisation or hashing detail changes, a golden test fails. **Never regenerate the golden file to make a test pass.** A real profile change needs a new profile id (`ocx-hash/2`) and a new golden file.
- The canonical records are pinned next to the hashes, so a failure shows *what* changed in readable form.

- [ ] **Step 1: Replace `packages/ocx-integrity/src/ocx_integrity/__init__.py`**

```python
"""ocx-integrity — canonical salted aspect hashes + Merkle manifest (profile ocx-hash/1).

Typical use::

    from ocx_integrity import build_manifest, verify_model, prove, check_bundle

    manifest = build_manifest(vessel, key)             # yard, with the secret key
    report = verify_model(vessel, manifest, key)       # yard: has the model changed?
    bundle = prove(vessel, manifest, key, part_id, ["scantlings"])
    check_bundle(bundle, root=manifest.root).valid     # class: no key needed
"""
from ocx_integrity.diff import ChangeReport, diff_manifests, format_report
from ocx_integrity.errors import (
    DuplicatePartIdError,
    IntegrityError,
    InvalidKeyError,
    PartDriftError,
    ProfileMismatchError,
    UnknownPartError,
)
from ocx_integrity.manifest import (
    Manifest,
    PartEntry,
    build_manifest,
    hash_vessel,
    load_manifest,
    save_manifest,
)
from ocx_integrity.profile import ASPECTS, PROFILE
from ocx_integrity.proof import BundleCheck, DisclosureBundle, check_bundle, prove
from ocx_integrity.salts import generate_key, load_key
from ocx_integrity.verify import verify_model

__all__ = [
    "ASPECTS",
    "PROFILE",
    "BundleCheck",
    "ChangeReport",
    "DisclosureBundle",
    "DuplicatePartIdError",
    "IntegrityError",
    "InvalidKeyError",
    "Manifest",
    "PartDriftError",
    "PartEntry",
    "ProfileMismatchError",
    "UnknownPartError",
    "build_manifest",
    "check_bundle",
    "diff_manifests",
    "format_report",
    "generate_key",
    "hash_vessel",
    "load_key",
    "load_manifest",
    "prove",
    "save_manifest",
    "verify_model",
]
```

- [ ] **Step 2: Write `tests/test_integrity_golden.py`**

```python
"""Golden vectors for profile ocx-hash/1 — a failure here means the profile changed.

Generate the pinned file ONCE (and only when introducing a new profile):
    uv run python -m tests.test_integrity_golden
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ocx_integrity import PROFILE, build_manifest, hash_vessel
from ocx_integrity.manifest import ordered_ids
from tests.integrity_fixtures import KEY, make_vessel

GOLDEN = Path(__file__).parent / "data" / "integrity" / "golden_v1.json"


def current_vectors() -> dict[str, Any]:
    hashed = hash_vessel(make_vessel(), KEY)
    parts = {}
    for pid in ordered_ids(hashed.parts):
        p = hashed.parts[pid]
        parts[pid] = {
            "kind": p.kind,
            "records": p.records,
            "aspects": {a: h.hex() for a, h in p.aspect_hashes.items()},
            "part_hash": p.part_hash.hex(),
        }
    return {"profile": PROFILE, "key": KEY.hex(), "root": hashed.root.hex(), "parts": parts}


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_canonical_records_match_golden(golden):
    current = current_vectors()
    assert list(current["parts"]) == list(golden["parts"])
    for pid, expected in golden["parts"].items():
        assert current["parts"][pid]["records"] == expected["records"], pid


def test_hashes_match_golden(golden):
    current = current_vectors()
    assert current["profile"] == golden["profile"] == "ocx-hash/1"
    for pid, expected in golden["parts"].items():
        assert current["parts"][pid]["aspects"] == expected["aspects"], pid
        assert current["parts"][pid]["part_hash"] == expected["part_hash"], pid
    assert current["root"] == golden["root"]


def test_public_api_reproduces_golden_root(golden):
    assert build_manifest(make_vessel(), KEY).root == golden["root"]


if __name__ == "__main__":
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(current_vectors(), indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"wrote {GOLDEN}")
```

(`print` is allowed here: it runs only in the one-off generator `__main__` block, never in library code.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_integrity_golden.py -q`
Expected: 3 errors, `FileNotFoundError` for `golden_v1.json`.

- [ ] **Step 4: Generate the golden file and review it by eye**

Run: `uv run python -m tests.test_integrity_golden`
Expected: `wrote ...\tests\data\integrity\golden_v1.json`

Open the file and check:
- `profile` is `ocx-hash/1` and there are 6 parts, in the order `G-COMP-1, G-PAN-1, G-PL-1, SE1, ST1, vessel:V1`.
- The `G-PL-1` scantlings record has `"thickness": "0.012000"`.
- The material record is inlined with `"part_id": "G-MAT-1"`.
- The outer contour starts at the minimum point, and `is_closed` is `true`.
- No record contains a float, and no `id`/`guidref` keys appear inside nested objects.

If anything looks wrong, fix the code (not the file), delete the file and regenerate.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_integrity_golden.py -q`
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-integrity/src/ocx_integrity/__init__.py tests/test_integrity_golden.py tests/data/integrity/golden_v1.json
git commit -m "feat(integrity): public API and pinned ocx-hash/1 golden vectors

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 13: Real-model end-to-end test

**Files:**
- Test: `tests/test_integrity_model.py`

The models are tracked in git. Their part counts were checked when this plan was written:
- `TR02_TC01_ai3dx.3docx` (the spec's model): 1 panel and 1 plate, giving 3 parts with the vessel.
- `TR02_TC04_ai3dx.3docx`: 1 panel, 1 plate and 6 stiffeners, giving 9 parts.

Neither model has duplicate part IDs. If this test fails inside an extractor (e.g. a `TypeError: cannot canonicalise …`), the real model is exercising an IR shape the synthetic vessel does not cover. In that case, fix the extractor and add a focused case to `tests/test_integrity_canon.py`. Do not weaken this test.

- [ ] **Step 1: Write the test `tests/test_integrity_model.py`**

```python
"""ocx-integrity on real tracked models: parse → build → manifest → verify / prove / check."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_integrity import (
    build_manifest,
    check_bundle,
    load_manifest,
    prove,
    save_manifest,
    verify_model,
)
from tests.conftest import _build_session
from tests.integrity_fixtures import KEY

MODELS = Path(__file__).resolve().parents[1] / "models" / "TR02"
CASES = [("TR02_TC01_ai3dx.3docx", 3), ("TR02_TC04_ai3dx.3docx", 9)]


def _vessel(name: str):
    _, vessel = _build_session(str(MODELS / name))
    return vessel


@pytest.mark.parametrize("name, part_count", CASES)
def test_manifest_roundtrip_and_fresh_parse_verifies_clean(tmp_path, name, part_count):
    manifest = build_manifest(_vessel(name), KEY)
    assert manifest.part_count == part_count
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)
    report = verify_model(_vessel(name), load_manifest(path), KEY)
    assert report.clean, report.to_dict()


@pytest.mark.parametrize("name", [name for name, _ in CASES])
def test_every_part_proves_and_checks(name):
    vessel = _vessel(name)
    manifest = build_manifest(vessel, KEY)
    for pid in manifest.ordered_ids():
        result = check_bundle(prove(vessel, manifest, KEY, pid), root=manifest.root)
        assert result.valid, (pid, result.errors)
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_integrity_model.py -q`
Expected: `4 passed`. If it fails, follow the instructions above, then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integrity_model.py
git commit -m "test(integrity): end-to-end manifest/verify/prove on TR02 models

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 14: Documentation and final verification

**Files:**
- Modify: `packages/ocx-integrity/README.md`
- Modify: `packages/ocx-integrity/CHANGELOG.md`
- Modify: `README.md` (Features, Project structure, dependency direction, CLI)
- Modify: `.github/copilot-instructions.md` (layout paragraph, tree, import rule, CLI)

- [ ] **Step 1: Replace `packages/ocx-integrity/README.md`**

````markdown
# ocx-integrity

Canonical, salted per-aspect hashes and a Merkle manifest root for OCX models
(profile `ocx-hash/1`). The full specification is
`docs/superpowers/specs/2026-11-08-ocx-integrity-manifest-design.md`.

- Every part (plate, stiffener, bracket, pillar, edge reinforcement, panel,
  seam, compartment, plus one vessel-metadata part) gets a stable **part ID**:
  its GUID, or its XML id if it has no GUID.
- Each part is split into up to five **aspects**: `identity`, `material`,
  `scantlings`, `geometry`, `physical`. Each aspect is a canonical JSON record:
  SI decimal strings, resolved references, sorted sets, normalised closed
  contours, serialised with RFC 8785 (JCS).
- `aspect_hash = SHA-256(salt ‖ JCS(payload))`, where
  `salt = HMAC-SHA256(K, "ocx-hash/1" ‖ 0 ‖ part_id ‖ 0 ‖ aspect)`. Without the
  key, hashes cannot be brute-forced against guessed scantlings.
- Part hashes are RFC 9162 Merkle roots of their aspect hashes. The manifest
  root is the Merkle root of all part hashes in UTF-8 byte order of the part IDs.
- The manifest contains only part IDs and salted hashes, so it is safe to share.
  The key `K` (≥ 32 bytes, hex) never leaves the yard.

## CLI

```bash
ocx-integrity keygen   -o yard.key                               # once; keep it secret
ocx-integrity manifest model.3docx --key yard.key -o manifest.json
ocx-integrity verify   model.3docx manifest.json --key yard.key  # exit 1 if anything changed
ocx-integrity prove    model.3docx manifest.json --key yard.key --part ID [--aspect A]... -o bundle.json
ocx-integrity check    bundle.json [--root HEX]                  # no key needed
ocx-integrity diff     old.json new.json [--format text|json]
```

The key can also be given via `OCX_INTEGRITY_KEY` (hex); `--key FILE` wins.
Exit codes:
- `0`: ok, match, or bundle valid.
- `1`: changes found, bundle invalid, or part drift on `prove`.
- `2`: cannot run (parse/build failure, bad key, unknown profile, tampered manifest, duplicate part IDs, unknown part/aspect).
- `3`: cannot write output.

Diffing manifests built with different keys reports every part as changed.

## Python API

```python
from ocx_integrity import build_manifest, verify_model, prove, check_bundle, diff_manifests
```
````

- [ ] **Step 2: Replace `packages/ocx-integrity/CHANGELOG.md`**

```markdown
# Changelog — ocx-integrity

## Unreleased

- Profile `ocx-hash/1`: canonical per-aspect records for 9 part kinds, JCS
  serialisation, HMAC-derived salts, RFC 9162 Merkle part/model roots.
- Manifest build/save/load with consistency checks; verify and diff.
- Selective-disclosure proof bundles (`prove` / `check_bundle`).
- `ocx-integrity` CLI: `keygen`, `manifest`, `verify`, `prove`, `check`, `diff`.
```

- [ ] **Step 3: Update `README.md`**

(a) In **Features**, insert this bullet directly after the "Render diagnostics" bullet, which ends with `failing rule OCX-TOP-001 (panel boundary must close).`:

```markdown
- **Integrity manifest - EXPERIMENTAL** (`ocx-integrity`): stable part IDs and
  canonical, salted per-aspect hashes (identity, material, scantlings,
  geometry, physical) rolled up in an RFC 9162 Merkle tree to one manifest
  root. `verify` and `diff` report exactly which parts and aspects changed.
  `prove` writes a selective-disclosure bundle that class can `check` without
  the yard key (profile `ocx-hash/1`).
```

(b) In **Project structure**, insert directly above the line
`│   └── ocx-model-validator/       ← validation, reports, CLI, MCP server`:

```text
│   ├── ocx-integrity/             ← salted aspect hashes + Merkle manifest (core only)
│   │   └── src/ocx_integrity/
│   │       ├── profile.py / quantize.py / canon_geom.py ← ocx-hash/1 canonicalisation
│   │       ├── records/           ← per-kind canonical aspect records
│   │       ├── salts.py / hashing.py / merkle.py ← HMAC salts, JCS hashing, RFC 9162
│   │       ├── manifest.py / diff.py / verify.py / proof.py
│   │       └── cli.py             ← ocx-integrity entrypoint
```

(c) Replace the dependency-direction sentence's line
`` `ocx-diagnose` → `ocx-render` + `ocx-rules`, and `` with:

```markdown
`ocx-diagnose` → `ocx-render` + `ocx-rules`, `ocx-integrity` → `ocx-model-core`, and
```

(d) In the **CLI** code block, insert after the
`ocx-diagnose top-001 model.3docx [--panel ID]... [--tolerance MM] [--report out.html]` line:

```bash

# integrity manifest: salted aspect hashes + Merkle root (exit 0 ok / 1 changed or invalid / 2 cannot run / 3 cannot write)
ocx-integrity keygen -o yard.key
ocx-integrity manifest model.3docx --key yard.key -o manifest.json
ocx-integrity verify model.3docx manifest.json --key yard.key
ocx-integrity prove model.3docx manifest.json --key yard.key --part ID [--aspect A]... -o bundle.json
ocx-integrity check bundle.json [--root HEX]
ocx-integrity diff old.json new.json [--format text|json]
```

- [ ] **Step 4: Update `.github/copilot-instructions.md`**

(a) Layout paragraph: replace
`` `ocx-model-validator` → `ocx-rules` → `ocx-model-core` (rule checks use ``
`geometry lazily when installed).`
with:

```markdown
`ocx-model-validator` → `ocx-rules` → `ocx-model-core` (rule checks use
geometry lazily when installed), and `ocx-integrity` → `ocx-model-core`.
```

(b) Tree: insert directly above `│   └── ocx-model-validator/    ← reports, CLI, MCP server`:

```text
│   ├── ocx-integrity/          ← salted aspect hashes + Merkle manifest (core only)
│   │   └── src/ocx_integrity/
│   │       ├── profile.py       ← PROFILE "ocx-hash/1", ASPECTS, precision table
│   │       ├── quantize.py / canon_geom.py / jsonutil.py ← canonical values + contours
│   │       ├── records/         ← per-kind extractors → per-aspect canonical records
│   │       ├── salts.py / hashing.py ← HMAC salts, SHA-256(salt ‖ JCS payload)
│   │       ├── merkle.py        ← RFC 9162 MTH + inclusion proofs
│   │       ├── manifest.py      ← hash_vessel, Manifest build/save/load
│   │       ├── diff.py / verify.py / proof.py ← ChangeReport, disclosure bundles
│   │       └── cli.py           ← ocx-integrity entrypoint
```

(c) Import rule: replace
`tessellation/rendering code under `ocx_render.*`. The validator never reaches`
with:

```markdown
tessellation/rendering code under `ocx_render.*`; integrity hashing/manifest/proof
code under `ocx_integrity.*` (core only — never imports geometry/render). The validator never reaches
```

(d) CLI block: insert after the `ocx-diagnose top-001 model.3docx …` line:

```bash

# Integrity manifest (profile ocx-hash/1; exit 0 ok / 1 changed or invalid / 2 cannot run / 3 cannot write)
ocx-integrity keygen -o yard.key
ocx-integrity manifest model.3docx --key yard.key -o manifest.json
ocx-integrity verify model.3docx manifest.json --key yard.key
ocx-integrity prove model.3docx manifest.json --key yard.key --part ID [--aspect A]... -o bundle.json
ocx-integrity check bundle.json [--root HEX]
ocx-integrity diff old.json new.json [--format text|json]
```

- [ ] **Step 5: Lint**

Run: `uv run ruff check packages/ocx-integrity tests/test_integrity_canon.py tests/test_integrity_hashing.py tests/test_integrity_merkle.py tests/test_integrity_manifest.py tests/test_integrity_diff.py tests/test_integrity_proof.py tests/test_integrity_cli.py tests/test_integrity_golden.py tests/test_integrity_model.py tests/integrity_fixtures.py`
Expected: `All checks passed!` Fix any finding, e.g. import order after the "add to the imports" steps, with `uv run ruff check --fix` on the same paths.

- [ ] **Step 6: Run the whole integrity suite, then the full suite**

Run: `uv run pytest tests/test_integrity_canon.py tests/test_integrity_hashing.py tests/test_integrity_merkle.py tests/test_integrity_manifest.py tests/test_integrity_diff.py tests/test_integrity_proof.py tests/test_integrity_cli.py tests/test_integrity_golden.py tests/test_integrity_model.py -q`
Expected: `107 passed` (33 + 10 + 11 + 10 + 6 + 16 + 14 + 3 + 4).

Run: `uv run pytest -q`
Expected: the same pass/skip counts as before this plan plus the 107 new tests. Nothing previously passing fails.

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-integrity/README.md packages/ocx-integrity/CHANGELOG.md README.md .github/copilot-instructions.md
git commit -m "docs(integrity): document ocx-integrity package, CLI and layout

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
