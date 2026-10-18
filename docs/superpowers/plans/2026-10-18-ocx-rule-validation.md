# OCX Rule-Based Validation (Step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New workspace package `ocx-rules` — a configurable rule engine with a declarative TOML rule catalogue (36 best-practice rules), entry-point plugin discovery, TOML user config, and a `validator validate rules` CLI subcommand. All check logic is stubbed (`NOT_IMPLEMENTED`); implementations come in step 2.

**Architecture:** Rules are `RuleSpec` metadata loaded from TOML files that bind either a named check *primitive* (parameterized, from `PRIMITIVE_REGISTRY`) or a *custom* callable (`module:attr`). `RuleManager` discovers rule packs via the `ocx_rules.packs` entry-point group, applies user config (disable/severity/params), and executes each rule against a `ValidationContext` (lazy lxml tree + lazy IrVessel). Per-rule isolation: exceptions → `CRASHED`, unsatisfied requirements → `SKIPPED`, stubs → `NOT_IMPLEMENTED`.

**Tech Stack:** Python ≥3.12, uv workspace, hatchling, tomllib (stdlib), lxml, loguru, typer/rich (CLI side in ocx-model-validator), pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md`

**Conventions (apply to every task):**
- Run everything from the repo root `C:\PythonDev\ocx-platform`.
- Tests live in the shared `tests/` dir, run with `uv run pytest tests/<file> -v`.
- Logging via `from loguru import logger`; never `print()` or stdlib `logging`.
- Line length 100 (ruff). Run `uv run ruff check .` before each commit.
- Commit after each task with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.

---

### Task 1: Package scaffold

**Files:**
- Create: `packages/ocx-rules/pyproject.toml`
- Create: `packages/ocx-rules/README.md`
- Create: `packages/ocx-rules/src/ocx_rules/__init__.py`
- Modify: `packages/ocx-model-validator/pyproject.toml`

- [ ] **Step 1: Create `packages/ocx-rules/pyproject.toml`**

```toml
[project]
name = "ocx-rules"
version = "0.1.0"
description = "Configurable best-practice rule engine for OCX .3docx models"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "ocx-model-core>=0.5,<0.6",
    "lxml>=6.0",
    "loguru>=0.7",
]

[project.entry-points."ocx_rules.packs"]
best_practice = "ocx_rules.packs.best_practice:load_pack"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ocx_rules"]

[tool.uv.sources]
ocx-model-core = { workspace = true }
```

Note: `ocx-geometry` is deliberately NOT a dependency — geometry rules check for it at
runtime (`importlib.util.find_spec("ocx_geometry")`) and are `SKIPPED` when absent.

- [ ] **Step 2: Create `packages/ocx-rules/README.md`**

```markdown
# ocx-rules

Configurable best-practice rule engine for OCX `.3docx` models.

Rules are defined declaratively in TOML files and bind either a named check
primitive from the built-in library or a custom Python callable. Rule packs are
discovered through the `ocx_rules.packs` entry-point group. See
`docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md` in the repo
root for the full design.
```

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/__init__.py`**

```python
"""ocx-rules — configurable best-practice rule engine for OCX models.

Public API re-exported here; see the design spec in
docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md.
"""
from __future__ import annotations

__version__ = "0.1.0"
```

(The re-exports are added in Task 7 once the symbols exist.)

- [ ] **Step 4: Add the dependency to `packages/ocx-model-validator/pyproject.toml`**

In `dependencies`, after the `"ocx-geometry>=0.1,<0.2",` line add:

```toml
    "ocx-rules>=0.1,<0.2",
```

In `[tool.uv.sources]` add:

```toml
ocx-rules = { workspace = true }
```

- [ ] **Step 5: Sync and verify**

Run: `uv sync --dev`
Expected: resolves cleanly, installs `ocx-rules` as a workspace member.

Run: `uv run python -c "import ocx_rules; print(ocx_rules.__version__)"`
Expected output: `0.1.0`

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-rules packages/ocx-model-validator/pyproject.toml uv.lock
git commit -m "feat(rules): scaffold ocx-rules workspace package"
```

---

### Task 2: Core data model (`model.py`)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/model.py`
- Test: `tests/test_rules_model.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_model.py`**

```python
"""Tests for the ocx_rules core data model."""
from __future__ import annotations

import dataclasses

import pytest

from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    Finding,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
)


def _spec(**overrides) -> RuleSpec:
    base = dict(
        rule_id="OCX-TEST-001",
        title="t",
        description="d",
        category="identity",
        severity=Severity.ERROR,
        source="unittest",
        requires=frozenset({"xml"}),
        check=CheckRef(primitive="unique"),
        params={"xpath": "//*"},
    )
    base.update(overrides)
    return RuleSpec(**base)


class TestModel:
    def test_severity_values(self):
        assert {s.value for s in Severity} == {"error", "warning", "info"}

    def test_rule_status_values(self):
        assert {s.value for s in RuleStatus} == {
            "passed", "failed", "not_implemented", "skipped", "crashed"}

    def test_rule_spec_is_frozen(self):
        spec = _spec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.rule_id = "X"

    def test_check_ref_exactly_one_kind(self):
        with pytest.raises(ValueError):
            CheckRef(primitive="unique", custom="m:f")
        with pytest.raises(ValueError):
            CheckRef()

    def test_finding_defaults(self):
        f = Finding(message="boom")
        assert f.element_id is None and f.guid is None and f.location is None

    def test_rule_result_defaults(self):
        r = RuleResult(spec=_spec(), status=RuleStatus.PASSED)
        assert r.findings == () and r.reason is None and r.duration_ms == 0.0

    def test_rule_pack(self):
        pack = RulePack(name="p", version="1.0", rules=(_spec(),))
        assert pack.rules[0].rule_id == "OCX-TEST-001"

    def test_check_not_implemented_is_exception(self):
        assert issubclass(CheckNotImplemented, Exception)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_model.py -v`
Expected: FAIL / collection error — `ModuleNotFoundError: No module named 'ocx_rules.model'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/model.py`**

```python
"""Core data model for the rule engine.

All dataclasses are frozen. ``RuleSpec.params`` and ``RuleResult.findings``
hold plain data; specs are produced by the catalogue loader and (optionally)
rewritten by the user config before execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Rule severity: wiki shall/must -> error, should -> warning, informative -> info."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleStatus(str, Enum):
    """Outcome of executing one rule."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"
    SKIPPED = "skipped"
    CRASHED = "crashed"


class CheckNotImplemented(Exception):
    """Raised by stub checks; the manager maps it to RuleStatus.NOT_IMPLEMENTED."""


#: Valid entries for RuleSpec.requires.
VALID_REQUIREMENTS = frozenset({"xml", "ir", "geometry"})


@dataclass(frozen=True)
class CheckRef:
    """Reference to the executable check: a registered primitive OR a custom callable.

    Exactly one of ``primitive`` / ``custom`` must be set. ``custom`` uses the
    ``"package.module:callable"`` form.
    """

    primitive: str | None = None
    custom: str | None = None

    def __post_init__(self) -> None:
        if (self.primitive is None) == (self.custom is None):
            raise ValueError(
                "CheckRef requires exactly one of 'primitive' or 'custom'")


@dataclass(frozen=True)
class RuleSpec:
    """One rule's metadata, as loaded from a catalogue TOML file."""

    rule_id: str
    title: str
    description: str
    category: str
    severity: Severity
    source: str
    requires: frozenset[str]
    check: CheckRef
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    """One violation reported by a check."""

    message: str
    element_id: str | None = None
    guid: str | None = None
    location: int | None = None  # XML line number when available


@dataclass(frozen=True)
class RuleResult:
    """Outcome of executing one rule against one model."""

    spec: RuleSpec
    status: RuleStatus
    findings: tuple[Finding, ...] = ()
    reason: str | None = None  # set for SKIPPED / CRASHED
    duration_ms: float = 0.0


@dataclass(frozen=True)
class RulePack:
    """A named, versioned collection of rules provided by a plugin."""

    name: str
    version: str
    rules: tuple[RuleSpec, ...]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_rules_model.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/model.py tests/test_rules_model.py
git commit -m "feat(rules): core data model (RuleSpec, RuleResult, Finding, severities)"
```

---

### Task 3: ValidationContext (`context.py`)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/context.py`
- Test: `tests/test_rules_context.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_context.py`**

The stub fixture dirs (e.g. `tests/data/ocx_310_stubs/`) contain parsable OCX
fragments; `ocxxml.3docx` is a full-document stub (root element + schemaVersion)
that `OcxParser.parse` accepts directly.

```python
"""Tests for ValidationContext laziness and caching."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_rules.context import ValidationContext


@pytest.fixture()
def vessel_stub(stub_dir_310: Path) -> Path:
    return stub_dir_310 / "ocxxml.3docx"


class TestValidationContext:
    def test_xml_tree_parses(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        root = ctx.xml_tree.getroot()
        assert root is not None

    def test_xml_tree_cached(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        assert ctx.xml_tree is ctx.xml_tree

    def test_vessel_not_built_for_xml_access(self, vessel_stub: Path, monkeypatch):
        """Accessing xml_tree must never trigger IR parsing/building."""
        import ocx_rules.context as context_mod

        def boom(*a, **k):  # pragma: no cover - should never run
            raise AssertionError("IR build triggered by xml access")

        monkeypatch.setattr(context_mod, "_build_vessel", boom)
        ctx = ValidationContext(vessel_stub)
        _ = ctx.xml_tree  # must not raise

    def test_vessel_builds_ir(self, vessel_stub: Path):
        ctx = ValidationContext(vessel_stub)
        vessel = ctx.vessel
        assert vessel is ctx.vessel  # cached

    def test_missing_file_raises_on_access_not_init(self, tmp_path: Path):
        ctx = ValidationContext(tmp_path / "nope.3docx")  # no raise here
        with pytest.raises(Exception):
            _ = ctx.xml_tree
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.context'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/context.py`**

```python
"""ValidationContext — lazy access to the raw XML tree and the parsed IR.

Rules declare what they need via ``RuleSpec.requires``; the context only pays
for what is actually accessed. A run containing only XML rules never builds
the IR.
"""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

import lxml.etree as etree
from loguru import logger


def _build_vessel(model_path: Path):
    """Parse *model_path* and build the IR (module-level so tests can patch it)."""
    from ocx_model_core.builders.factory import get_builder
    from ocx_model_core.parsers.parser import OcxParser

    parser = OcxParser()
    root = parser.parse(str(model_path))
    builder = get_builder(root.schema_version)
    return builder.build(root)


class ValidationContext:
    """Shared, lazily-populated inputs for all rule checks on one model."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)

    @cached_property
    def xml_tree(self) -> etree._ElementTree:
        """The raw lxml tree (line numbers preserved for Finding.location)."""
        logger.debug("Parsing XML tree: {}", self.model_path)
        return etree.parse(str(self.model_path))

    @cached_property
    def vessel(self):
        """The schema-neutral IR (IrVessel); built on first access."""
        logger.debug("Building IR: {}", self.model_path)
        return _build_vessel(self.model_path)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_rules_context.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/context.py tests/test_rules_context.py
git commit -m "feat(rules): lazy ValidationContext (xml tree + IR)"
```

---

### Task 4: Check-primitive registry (`primitives/`)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/primitives/__init__.py`
- Create: `packages/ocx-rules/src/ocx_rules/primitives/content.py`
- Create: `packages/ocx-rules/src/ocx_rules/primitives/references.py`
- Create: `packages/ocx-rules/src/ocx_rules/primitives/geometry.py`
- Test: `tests/test_rules_primitives.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_primitives.py`**

```python
"""Tests for the check-primitive registry (step 1: signatures + stubs)."""
from __future__ import annotations

import pytest

from ocx_rules.model import CheckNotImplemented
from ocx_rules.primitives import PRIMITIVE_REGISTRY

EXPECTED_PRIMITIVES = {
    "has_attribute",
    "unique",
    "cardinality",
    "value_in_set",
    "sequence",
    "ref_resolves",
    "closed_contour",
    "normals_consistent",
}


class TestPrimitiveRegistry:
    def test_all_expected_primitives_registered(self):
        assert set(PRIMITIVE_REGISTRY) == EXPECTED_PRIMITIVES

    def test_all_primitives_are_callable(self):
        assert all(callable(fn) for fn in PRIMITIVE_REGISTRY.values())

    @pytest.mark.parametrize("name", sorted(EXPECTED_PRIMITIVES))
    def test_stub_raises_check_not_implemented(self, name):
        with pytest.raises(CheckNotImplemented):
            PRIMITIVE_REGISTRY[name](context=None, params={})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_primitives.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.primitives'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/primitives/content.py`**

Every check — primitive or custom — has the same signature:
`(context: ValidationContext, params: dict) -> list[Finding]` (empty list = passed).

```python
"""Content-inspection primitives (XML/IR attribute, uniqueness, cardinality...).

Step 1 ships signatures only; every body raises CheckNotImplemented.
Implementations land in step 2.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def has_attribute(context, params: dict) -> list[Finding]:
    """Every element matching ``xpath`` carries ``attribute``."""
    raise CheckNotImplemented("has_attribute is not implemented yet")


def unique(context, params: dict) -> list[Finding]:
    """``key`` values over elements matching ``xpath`` are unique."""
    raise CheckNotImplemented("unique is not implemented yet")


def cardinality(context, params: dict) -> list[Finding]:
    """Each element matching ``xpath`` has between ``min`` and ``max`` ``child`` elements."""
    raise CheckNotImplemented("cardinality is not implemented yet")


def value_in_set(context, params: dict) -> list[Finding]:
    """``key`` values over elements matching ``xpath`` are members of ``allowed``."""
    raise CheckNotImplemented("value_in_set is not implemented yet")


def sequence(context, params: dict) -> list[Finding]:
    """Numeric sequences at ``key`` obey ``order`` (e.g. non_decreasing) / ``max_run``."""
    raise CheckNotImplemented("sequence is not implemented yet")
```

- [ ] **Step 4: Create `packages/ocx-rules/src/ocx_rules/primitives/references.py`**

```python
"""Cross-reference primitives. Step 1: stubs only."""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def ref_resolves(context, params: dict) -> list[Finding]:
    """Every ``ref_attribute`` value resolves to an element matching ``target_xpath``."""
    raise CheckNotImplemented("ref_resolves is not implemented yet")
```

- [ ] **Step 5: Create `packages/ocx-rules/src/ocx_rules/primitives/geometry.py`**

```python
"""Geometry primitives. Step 1: stubs only.

Implementations (step 2) must import ocx_geometry INSIDE the function body so
that content-only validation never loads the numpy stack.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented, Finding


def closed_contour(context, params: dict) -> list[Finding]:
    """The contour named by ``target`` is closed within ``tolerance_mm``."""
    raise CheckNotImplemented("closed_contour is not implemented yet")


def normals_consistent(context, params: dict) -> list[Finding]:
    """Normals over ``target`` are consistently oriented within ``angle_tolerance_deg``."""
    raise CheckNotImplemented("normals_consistent is not implemented yet")
```

- [ ] **Step 6: Create `packages/ocx-rules/src/ocx_rules/primitives/__init__.py`**

```python
"""Check-primitive library.

PRIMITIVE_REGISTRY maps the primitive name used in rule TOML files to the
callable implementing it. All checks share the signature
``(context: ValidationContext, params: dict) -> list[Finding]``.
"""
from __future__ import annotations

from collections.abc import Callable

from ocx_rules.primitives import content, geometry, references

PRIMITIVE_REGISTRY: dict[str, Callable] = {
    "has_attribute": content.has_attribute,
    "unique": content.unique,
    "cardinality": content.cardinality,
    "value_in_set": content.value_in_set,
    "sequence": content.sequence,
    "ref_resolves": references.ref_resolves,
    "closed_contour": geometry.closed_contour,
    "normals_consistent": geometry.normals_consistent,
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_rules_primitives.py -v`
Expected: all tests PASS (10 = 2 + 8 parametrized).

- [ ] **Step 8: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/primitives tests/test_rules_primitives.py
git commit -m "feat(rules): check-primitive registry with step-1 stubs"
```

---

### Task 5: Catalogue loader (`catalogue.py`)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/catalogue.py`
- Test: `tests/test_rules_catalogue.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_catalogue.py`**

```python
"""Tests for the TOML rule-catalogue loader."""
from __future__ import annotations

import pytest

from ocx_rules.catalogue import CatalogueError, load_catalogue_dir, parse_rules_toml
from ocx_rules.model import Severity

VALID_RULE = '''
[[rule]]
id          = "OCX-TST-001"
title       = "GUIDs must be unique"
description = "No duplicate GUIDRef values."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]

[rule.check]
primitive = "unique"
xpath     = "//*[@ocx:GUIDRef]"
key       = "@ocx:GUIDRef"
'''

CUSTOM_RULE = '''
[[rule]]
id          = "OCX-TST-002"
title       = "Custom check"
description = "Uses a custom callable."
source      = "unittest"
category    = "topology"
severity    = "warning"
requires    = ["ir", "geometry"]

[rule.check]
custom       = "ocx_rules.primitives.geometry:closed_contour"
tolerance_mm = 1.0
'''


class TestParseRulesToml:
    def test_primitive_rule(self):
        (spec,) = parse_rules_toml(VALID_RULE, source_name="t.toml")
        assert spec.rule_id == "OCX-TST-001"
        assert spec.severity is Severity.ERROR
        assert spec.requires == frozenset({"xml"})
        assert spec.check.primitive == "unique"
        assert spec.params == {"xpath": "//*[@ocx:GUIDRef]", "key": "@ocx:GUIDRef"}

    def test_custom_rule_params_exclude_custom_key(self):
        (spec,) = parse_rules_toml(CUSTOM_RULE, source_name="t.toml")
        assert spec.check.custom == "ocx_rules.primitives.geometry:closed_contour"
        assert spec.params == {"tolerance_mm": 1.0}

    @pytest.mark.parametrize("bad,repl", [
        ('severity    = "error"', 'severity    = "fatal"'),
        ('primitive = "unique"', 'primitive = "no_such_primitive"'),
        ('requires    = ["xml"]', 'requires    = ["xml", "quantum"]'),
        ('category    = "identity"', 'category    = ""'),
        ('id          = "OCX-TST-001"', 'id          = ""'),
    ])
    def test_invalid_rule_rejected(self, bad, repl):
        with pytest.raises(CatalogueError):
            parse_rules_toml(VALID_RULE.replace(bad, repl), source_name="t.toml")

    def test_unimportable_custom_rejected(self):
        text = CUSTOM_RULE.replace(
            "ocx_rules.primitives.geometry:closed_contour", "no.such.module:fn")
        with pytest.raises(CatalogueError):
            parse_rules_toml(text, source_name="t.toml")

    def test_duplicate_ids_rejected(self):
        with pytest.raises(CatalogueError, match="OCX-TST-001"):
            parse_rules_toml(VALID_RULE + VALID_RULE, source_name="t.toml")


class TestLoadCatalogueDir:
    def test_loads_all_toml_files_and_checks_cross_file_duplicates(self, tmp_path):
        (tmp_path / "a.toml").write_text(VALID_RULE, encoding="utf-8")
        (tmp_path / "b.toml").write_text(CUSTOM_RULE, encoding="utf-8")
        specs = load_catalogue_dir(tmp_path)
        assert [s.rule_id for s in specs] == ["OCX-TST-001", "OCX-TST-002"]

        (tmp_path / "c.toml").write_text(VALID_RULE, encoding="utf-8")
        with pytest.raises(CatalogueError, match="OCX-TST-001"):
            load_catalogue_dir(tmp_path)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_catalogue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.catalogue'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/catalogue.py`**

```python
"""Load and validate declarative rule-catalogue TOML files.

All structural problems (unknown primitive, unimportable custom reference,
duplicate ids, invalid severity/category/requires) are hard errors raised at
load time — never at run time.
"""
from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

from loguru import logger

from ocx_rules.model import VALID_REQUIREMENTS, CheckRef, RuleSpec, Severity


class CatalogueError(ValueError):
    """A rule catalogue file is structurally invalid."""


def resolve_custom(ref: str):
    """Import and return the callable behind a ``"module:attr"`` reference."""
    try:
        module_name, _, attr = ref.partition(":")
        if not module_name or not attr:
            raise ImportError(f"malformed custom reference {ref!r}")
        fn = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise CatalogueError(f"cannot import custom check {ref!r}: {exc}") from exc
    if not callable(fn):
        raise CatalogueError(f"custom check {ref!r} is not callable")
    return fn


def _parse_check(raw: dict, rule_id: str, source_name: str) -> tuple[CheckRef, dict]:
    from ocx_rules.primitives import PRIMITIVE_REGISTRY

    primitive = raw.get("primitive")
    custom = raw.get("custom")
    if (primitive is None) == (custom is None):
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} check needs exactly one of "
            f"'primitive' or 'custom'")
    if primitive is not None and primitive not in PRIMITIVE_REGISTRY:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} uses unknown primitive {primitive!r}")
    if custom is not None:
        resolve_custom(custom)  # import check at load time
    params = {k: v for k, v in raw.items() if k not in ("primitive", "custom")}
    return CheckRef(primitive=primitive, custom=custom), params


def _parse_rule(raw: dict, source_name: str) -> RuleSpec:
    for key in ("id", "title", "description", "source", "category",
                "severity", "requires", "check"):
        if key not in raw:
            raise CatalogueError(
                f"{source_name}: rule {raw.get('id', '<missing id>')!r} "
                f"lacks required key {key!r}")
    rule_id = raw["id"]
    if not isinstance(rule_id, str) or not rule_id:
        raise CatalogueError(f"{source_name}: rule id must be a non-empty string")
    if not isinstance(raw["category"], str) or not raw["category"]:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} category must be a non-empty string")
    try:
        severity = Severity(raw["severity"])
    except ValueError as exc:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} has invalid severity "
            f"{raw['severity']!r}") from exc
    requires = frozenset(raw["requires"])
    unknown = requires - VALID_REQUIREMENTS
    if unknown:
        raise CatalogueError(
            f"{source_name}: rule {rule_id!r} has unknown requires {sorted(unknown)}")
    check, params = _parse_check(raw["check"], rule_id, source_name)
    return RuleSpec(
        rule_id=rule_id,
        title=raw["title"],
        description=raw["description"],
        category=raw["category"],
        severity=severity,
        source=raw["source"],
        requires=requires,
        check=check,
        params=params,
    )


def parse_rules_toml(text: str, source_name: str) -> list[RuleSpec]:
    """Parse one TOML document into validated RuleSpecs."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogueError(f"{source_name}: invalid TOML: {exc}") from exc
    specs = [_parse_rule(raw, source_name) for raw in data.get("rule", [])]
    seen: set[str] = set()
    for spec in specs:
        if spec.rule_id in seen:
            raise CatalogueError(
                f"{source_name}: duplicate rule id {spec.rule_id!r}")
        seen.add(spec.rule_id)
    return specs


def load_catalogue_dir(directory) -> tuple[RuleSpec, ...]:
    """Load every ``*.toml`` in *directory* (Path or importlib Traversable)."""
    specs: list[RuleSpec] = []
    seen: set[str] = set()
    entries = sorted(
        (e for e in Path(directory).iterdir() if e.name.endswith(".toml"))
        if isinstance(directory, Path)
        else (e for e in directory.iterdir() if e.name.endswith(".toml")),
        key=lambda e: e.name,
    )
    for entry in entries:
        for spec in parse_rules_toml(entry.read_text(encoding="utf-8"), entry.name):
            if spec.rule_id in seen:
                raise CatalogueError(
                    f"{entry.name}: duplicate rule id {spec.rule_id!r} "
                    f"(already defined in another file)")
            seen.add(spec.rule_id)
            specs.append(spec)
    logger.debug("Loaded {} rules from catalogue {}", len(specs), directory)
    return tuple(specs)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_rules_catalogue.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/catalogue.py tests/test_rules_catalogue.py
git commit -m "feat(rules): TOML catalogue loader with load-time validation"
```

---

### Task 6: User config (`config.py`)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/config.py`
- Test: `tests/test_rules_config.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_config.py`**

```python
"""Tests for the user rule-configuration (TOML) layer."""
from __future__ import annotations

import pytest

from ocx_rules.config import ConfigError, RuleConfig, apply_config, load_config
from ocx_rules.model import CheckRef, RuleSpec, Severity

CONFIG_TOML = '''
[rules]
disable = ["OCX-TST-002"]

[rules.overrides.OCX-TST-001]
severity     = "warning"
tolerance_mm = 0.5
'''


def _spec(rule_id: str) -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id, title="t", description="d", category="identity",
        severity=Severity.ERROR, source="unittest", requires=frozenset({"xml"}),
        check=CheckRef(primitive="unique"), params={"xpath": "//*", "tolerance_mm": 1.0})


class TestLoadConfig:
    def test_none_path_gives_empty_config(self):
        cfg = load_config(None)
        assert cfg.disabled == frozenset() and cfg.overrides == {}

    def test_load_from_file(self, tmp_path):
        path = tmp_path / "ocx-rules.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        assert cfg.disabled == frozenset({"OCX-TST-002"})
        assert cfg.overrides["OCX-TST-001"]["severity"] == "warning"

    def test_invalid_severity_override_rejected(self, tmp_path):
        path = tmp_path / "ocx-rules.toml"
        path.write_text(CONFIG_TOML.replace('"warning"', '"fatal"'), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError):
            load_config(tmp_path / "nope.toml")


class TestApplyConfig:
    def test_disable_removes_rule(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        out = apply_config([_spec("OCX-TST-001"), _spec("OCX-TST-002")], cfg)
        assert [s.rule_id for s in out] == ["OCX-TST-001"]

    def test_override_changes_severity_and_params(self, tmp_path):
        path = tmp_path / "c.toml"
        path.write_text(CONFIG_TOML, encoding="utf-8")
        cfg = load_config(path)
        (out,) = apply_config([_spec("OCX-TST-001")], cfg)
        assert out.severity is Severity.WARNING
        assert out.params["tolerance_mm"] == 0.5
        assert out.params["xpath"] == "//*"  # untouched params survive

    def test_empty_config_is_identity(self):
        specs = [_spec("OCX-TST-001")]
        assert apply_config(specs, RuleConfig()) == specs
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.config'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/config.py`**

```python
"""User configuration: enable/disable rules, override severity and parameters.

Format (``ocx-rules.toml``)::

    [rules]
    disable = ["OCX-PROP-001"]

    [rules.overrides.OCX-TOP-001]
    severity     = "warning"
    tolerance_mm = 0.5

Overrides may change severity and any check parameter; never the check itself.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from loguru import logger

from ocx_rules.model import RuleSpec, Severity


class ConfigError(ValueError):
    """The user configuration file is invalid or unreadable."""


@dataclass(frozen=True)
class RuleConfig:
    """Parsed user configuration; the default is a no-op."""

    disabled: frozenset[str] = frozenset()
    overrides: dict[str, dict] = field(default_factory=dict)


def load_config(path: Path | None) -> RuleConfig:
    """Load *path*; ``None`` returns the empty (no-op) config."""
    if path is None:
        return RuleConfig()
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    rules = data.get("rules", {})
    overrides = rules.get("overrides", {})
    for rule_id, override in overrides.items():
        if "severity" in override:
            try:
                Severity(override["severity"])
            except ValueError as exc:
                raise ConfigError(
                    f"{path}: override for {rule_id!r} has invalid severity "
                    f"{override['severity']!r}") from exc
    cfg = RuleConfig(
        disabled=frozenset(rules.get("disable", [])),
        overrides=dict(overrides),
    )
    logger.debug("Loaded rule config from {}: {} disabled, {} overridden",
                 path, len(cfg.disabled), len(cfg.overrides))
    return cfg


def apply_config(specs: list[RuleSpec], config: RuleConfig) -> list[RuleSpec]:
    """Drop disabled rules and apply severity/param overrides."""
    out: list[RuleSpec] = []
    for spec in specs:
        if spec.rule_id in config.disabled:
            continue
        override = config.overrides.get(spec.rule_id)
        if override:
            severity = (Severity(override["severity"])
                        if "severity" in override else spec.severity)
            params = {**spec.params,
                      **{k: v for k, v in override.items() if k != "severity"}}
            spec = replace(spec, severity=severity, params=params)
        out.append(spec)
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_rules_config.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/config.py tests/test_rules_config.py
git commit -m "feat(rules): user config (disable, severity/param overrides)"
```

---

### Task 7: RuleManager (`manager.py`) + public API

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/manager.py`
- Modify: `packages/ocx-rules/src/ocx_rules/__init__.py`
- Test: `tests/test_rules_manager.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_manager.py`**

The execution-semantics tests bypass entry points by injecting packs directly
(`RuleManager(packs=[...])`). The discovery test uses the real entry point
(registered when Task 8 lands — see note in Step 4).

```python
"""Tests for RuleManager: discovery, filtering, execution semantics."""
from __future__ import annotations

from pathlib import Path

import pytest

from ocx_rules.config import RuleConfig
from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    Finding,
    RulePack,
    RuleSpec,
    RuleStatus,
    Severity,
)

# --- helper checks used via CheckRef(custom=...) -----------------------------

def check_passes(context, params):
    return []


def check_fails(context, params):
    return [Finding(message="violation", element_id="e1")]


def check_crashes(context, params):
    raise RuntimeError("kaboom")


def check_stub(context, params):
    raise CheckNotImplemented("later")


_HERE = "tests.test_rules_manager"


def _spec(rule_id, custom, requires=frozenset({"xml"}), category="identity",
          severity=Severity.ERROR):
    return RuleSpec(
        rule_id=rule_id, title=rule_id, description="d", category=category,
        severity=severity, source="unittest", requires=requires,
        check=CheckRef(custom=f"{_HERE}:{custom}"), params={})


def _pack(*specs):
    return RulePack(name="test", version="0", rules=tuple(specs))


@pytest.fixture()
def context(stub_dir_310: Path) -> ValidationContext:
    return ValidationContext(stub_dir_310 / "ocxxml.3docx")


class TestExecution:
    def test_statuses(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-PASS", "check_passes"),
            _spec("R-FAIL", "check_fails"),
            _spec("R-CRASH", "check_crashes"),
            _spec("R-STUB", "check_stub"),
        )])
        by_id = {r.spec.rule_id: r for r in manager.run(context)}
        assert by_id["R-PASS"].status is RuleStatus.PASSED
        assert by_id["R-FAIL"].status is RuleStatus.FAILED
        assert by_id["R-FAIL"].findings[0].message == "violation"
        assert by_id["R-CRASH"].status is RuleStatus.CRASHED
        assert "kaboom" in by_id["R-CRASH"].reason
        assert by_id["R-STUB"].status is RuleStatus.NOT_IMPLEMENTED

    def test_crash_does_not_abort_run(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-CRASH", "check_crashes"), _spec("R-PASS", "check_passes"))])
        results = manager.run(context)
        assert [r.status for r in results] == [RuleStatus.CRASHED, RuleStatus.PASSED]

    def test_unsatisfied_xml_requirement_skips(self, tmp_path):
        manager = RuleManager(packs=[_pack(_spec("R-PASS", "check_passes"))])
        results = manager.run(ValidationContext(tmp_path / "nope.3docx"))
        assert results[0].status is RuleStatus.SKIPPED
        assert results[0].reason

    def test_unsatisfied_ir_requirement_skips(self, context, monkeypatch):
        import ocx_rules.context as context_mod
        monkeypatch.setattr(
            context_mod, "_build_vessel",
            lambda p: (_ for _ in ()).throw(ValueError("no IR")))
        manager = RuleManager(packs=[_pack(
            _spec("R-IR", "check_passes", requires=frozenset({"ir"})))])
        results = manager.run(context)
        assert results[0].status is RuleStatus.SKIPPED

    def test_filter_by_category_and_rule_id(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-A", "check_passes", category="identity"),
            _spec("R-B", "check_passes", category="topology"),
        )])
        assert [r.spec.rule_id for r in manager.run(context, category="topology")] == ["R-B"]
        assert [r.spec.rule_id for r in manager.run(context, rule_id="R-A")] == ["R-A"]

    def test_config_disable_and_override(self, context):
        cfg = RuleConfig(disabled=frozenset({"R-B"}),
                         overrides={"R-A": {"severity": "info"}})
        manager = RuleManager(config=cfg, packs=[_pack(
            _spec("R-A", "check_passes"), _spec("R-B", "check_passes"))])
        results = manager.run(context)
        assert [r.spec.rule_id for r in results] == ["R-A"]
        assert results[0].spec.severity is Severity.INFO


class TestDiscovery:
    def test_entry_point_discovery_finds_best_practice_pack(self):
        packs = RuleManager().discover()
        assert "best_practice" in [p.name for p in packs]

    def test_duplicate_rule_ids_across_packs_rejected(self):
        from ocx_rules.catalogue import CatalogueError
        manager = RuleManager(packs=[
            _pack(_spec("R-DUP", "check_passes")),
            _pack(_spec("R-DUP", "check_passes")),
        ])
        with pytest.raises(CatalogueError, match="R-DUP"):
            manager.rules()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.manager'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/manager.py`**

```python
"""RuleManager — plugin discovery, configuration, filtering and execution.

Each rule executes in isolation: an exception becomes a CRASHED result,
CheckNotImplemented becomes NOT_IMPLEMENTED, unsatisfied requirements become
SKIPPED. The run never aborts because of one rule.
"""
from __future__ import annotations

import importlib.util
import time
from importlib.metadata import entry_points

from loguru import logger

from ocx_rules.catalogue import CatalogueError, resolve_custom
from ocx_rules.config import RuleConfig, apply_config
from ocx_rules.context import ValidationContext
from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
)

ENTRY_POINT_GROUP = "ocx_rules.packs"


def _resolve_check(check: CheckRef):
    if check.primitive is not None:
        from ocx_rules.primitives import PRIMITIVE_REGISTRY

        return PRIMITIVE_REGISTRY[check.primitive]
    return resolve_custom(check.custom)


class RuleManager:
    """Discover rule packs, apply configuration and execute rules."""

    def __init__(self, config: RuleConfig | None = None,
                 packs: list[RulePack] | None = None) -> None:
        self._config = config or RuleConfig()
        self._packs = packs  # None -> discover() on first use

    def discover(self) -> list[RulePack]:
        """Load every pack registered under the ``ocx_rules.packs`` entry-point group."""
        packs: list[RulePack] = []
        for ep in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
            pack = ep.load()()
            logger.debug("Discovered rule pack {!r} v{} ({} rules)",
                         pack.name, pack.version, len(pack.rules))
            packs.append(pack)
        self._packs = packs
        return packs

    def rules(self, *, category: str | None = None,
              rule_id: str | None = None) -> list[RuleSpec]:
        """All enabled rules after config, optionally filtered."""
        if self._packs is None:
            self.discover()
        specs: list[RuleSpec] = []
        seen: set[str] = set()
        for pack in self._packs:
            for spec in pack.rules:
                if spec.rule_id in seen:
                    raise CatalogueError(
                        f"duplicate rule id {spec.rule_id!r} across packs")
                seen.add(spec.rule_id)
                specs.append(spec)
        specs = apply_config(specs, self._config)
        if category is not None:
            specs = [s for s in specs if s.category == category]
        if rule_id is not None:
            specs = [s for s in specs if s.rule_id == rule_id]
        return specs

    def run(self, context: ValidationContext, *, category: str | None = None,
            rule_id: str | None = None) -> list[RuleResult]:
        """Execute every enabled (filtered) rule against *context*."""
        return [self._run_one(spec, context)
                for spec in self.rules(category=category, rule_id=rule_id)]

    def _run_one(self, spec: RuleSpec, context: ValidationContext) -> RuleResult:
        start = time.perf_counter()

        def done(status: RuleStatus, findings=(), reason=None) -> RuleResult:
            return RuleResult(
                spec=spec, status=status, findings=tuple(findings), reason=reason,
                duration_ms=(time.perf_counter() - start) * 1000.0)

        reason = self._unsatisfied(spec, context)
        if reason is not None:
            logger.debug("Rule {} skipped: {}", spec.rule_id, reason)
            return done(RuleStatus.SKIPPED, reason=reason)
        try:
            check = _resolve_check(spec.check)
            findings = check(context, dict(spec.params))
        except CheckNotImplemented as exc:
            return done(RuleStatus.NOT_IMPLEMENTED, reason=str(exc))
        except Exception as exc:
            logger.warning("Rule {} crashed: {}", spec.rule_id, exc)
            return done(RuleStatus.CRASHED, reason=f"{type(exc).__name__}: {exc}")
        return done(RuleStatus.FAILED if findings else RuleStatus.PASSED,
                    findings=findings)

    @staticmethod
    def _unsatisfied(spec: RuleSpec, context: ValidationContext) -> str | None:
        if "xml" in spec.requires:
            try:
                context.xml_tree  # noqa: B018 — triggers lazy parse
            except Exception as exc:
                return f"cannot parse XML: {exc}"
        if "ir" in spec.requires:
            try:
                context.vessel  # noqa: B018 — triggers lazy build
            except Exception as exc:
                return f"cannot build IR: {exc}"
        if "geometry" in spec.requires and importlib.util.find_spec("ocx_geometry") is None:
            return "ocx-geometry is not installed"
        return None
```

- [ ] **Step 4: Update `packages/ocx-rules/src/ocx_rules/__init__.py` with the public API**

Replace the file content with:

```python
"""ocx-rules — configurable best-practice rule engine for OCX models.

See docs/superpowers/specs/2026-10-18-ocx-rule-validation-design.md.
"""
from __future__ import annotations

from ocx_rules.catalogue import CatalogueError, load_catalogue_dir, parse_rules_toml
from ocx_rules.config import ConfigError, RuleConfig, apply_config, load_config
from ocx_rules.context import ValidationContext
from ocx_rules.manager import RuleManager
from ocx_rules.model import (
    CheckNotImplemented,
    CheckRef,
    Finding,
    RulePack,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
)

__version__ = "0.1.0"

__all__ = [
    "CatalogueError",
    "CheckNotImplemented",
    "CheckRef",
    "ConfigError",
    "Finding",
    "RuleConfig",
    "RuleManager",
    "RulePack",
    "RuleResult",
    "RuleSpec",
    "RuleStatus",
    "Severity",
    "ValidationContext",
    "apply_config",
    "load_catalogue_dir",
    "load_config",
    "parse_rules_toml",
]
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_rules_manager.py -v`
Expected: `TestExecution` and `test_duplicate_rule_ids_across_packs_rejected` PASS.
`test_entry_point_discovery_finds_best_practice_pack` FAILS (the entry point
target `ocx_rules.packs.best_practice:load_pack` does not exist until Task 8).
Mark it as expected for now — do NOT skip it; Task 8 turns it green. If running
tasks strictly in order, temporarily verify with:
`uv run pytest tests/test_rules_manager.py -v --deselect tests/test_rules_manager.py::TestDiscovery::test_entry_point_discovery_finds_best_practice_pack`
Expected: all selected tests PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/manager.py packages/ocx-rules/src/ocx_rules/__init__.py tests/test_rules_manager.py
git commit -m "feat(rules): RuleManager with entry-point discovery and isolated execution"
```

---

### Task 8: Built-in `best_practice` rule pack (36 rules)

**Files:**
- Create: `packages/ocx-rules/src/ocx_rules/packs/__init__.py`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/__init__.py`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks.py`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/identity.toml`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/document.toml`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/references.toml`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/curves_surfaces.toml`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/topology.toml`
- Create: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/properties.toml`
- Test: `tests/test_rules_best_practice_pack.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_best_practice_pack.py`**

```python
"""Catalogue-integrity tests for the built-in best_practice rule pack."""
from __future__ import annotations

from ocx_rules.catalogue import resolve_custom
from ocx_rules.model import Severity
from ocx_rules.packs.best_practice import load_pack

EXPECTED_CATEGORIES = {
    "identity": 5,
    "document": 5,
    "references": 8,
    "curves_surfaces": 5,
    "topology": 9,
    "properties": 4,
}


class TestBestPracticePack:
    def test_loads_36_rules(self):
        pack = load_pack()
        assert pack.name == "best_practice"
        assert len(pack.rules) == 36

    def test_category_counts(self):
        pack = load_pack()
        counts: dict[str, int] = {}
        for spec in pack.rules:
            counts[spec.category] = counts.get(spec.category, 0) + 1
        assert counts == EXPECTED_CATEGORIES

    def test_ids_unique_and_well_formed(self):
        pack = load_pack()
        ids = [s.rule_id for s in pack.rules]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("OCX-") for i in ids)

    def test_every_rule_has_source_and_description(self):
        for spec in load_pack().rules:
            assert spec.source, spec.rule_id
            assert spec.description, spec.rule_id

    def test_severities_valid(self):
        for spec in load_pack().rules:
            assert isinstance(spec.severity, Severity)

    def test_custom_checks_importable(self):
        for spec in load_pack().rules:
            if spec.check.custom is not None:
                assert callable(resolve_custom(spec.check.custom)), spec.rule_id

    def test_geometry_rules_declare_geometry_requirement(self):
        for spec in load_pack().rules:
            if spec.category in ("topology", "properties"):
                assert "geometry" in spec.requires or "ir" in spec.requires, spec.rule_id
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_best_practice_pack.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ocx_rules.packs'`.

- [ ] **Step 3: Create `packages/ocx-rules/src/ocx_rules/packs/__init__.py`**

```python
"""Rule packs shipped with ocx-rules."""
```

- [ ] **Step 4: Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks.py`**

All custom checks are step-1 stubs built by one factory; step 2 replaces them
one by one with real implementations (same names, same signature).

```python
"""Custom check callables for the best_practice pack.

Step 1: every check is a stub raising CheckNotImplemented. Step 2 replaces
stubs with real implementations keeping name and signature
``(context: ValidationContext, params: dict) -> list[Finding]``.
"""
from __future__ import annotations

from ocx_rules.model import CheckNotImplemented


def _stub(summary: str):
    def check(context, params):
        raise CheckNotImplemented(summary)

    check.__doc__ = summary
    return check


# identity
entitybase_has_guid_and_id = _stub(
    "Every EntityBase-derived object carries GUIDRef and id")
idbase_has_id = _stub("IDBase-derived geometry carries a local id")
names_not_identifiers = _stub("Names are not used as identifiers")

# document
schema_location_tuple = _stub(
    "Root xsi:schemaLocation contains the (namespace, XSD location) tuple")
root_declarations = _stub("schemaVersion, xmlns:ocx and xmlns:xsi present on root")
unit_definitions = _stub("Every Unit has a unique id and UnitName")
unit_refs_resolve = _stub("Unit and Dimension references resolve")
enumerated_root_units = _stub("Enumerated UnitsML root units used when available")

# references
stiffener_end_configurations = _stub(
    "A Stiffener has at most two end configurations, one per end")
slot_lug_plate_refs = _stub("A two-lug slot has exactly two LugPlateRef references")
explicit_connectivity = _stub("Structural connectivity encoded explicitly via references")
panel_as_occurrence_group = _stub(
    "A Panel is represented as OccurrenceGroup, never a direct Occurrence")
hole_single_representation = _stub(
    "A hole/slot appears in only one representation (CutBy xor OuterContour)")

# curves_surfaces
nurbs_control_points = _stub("NURBS control-point count >= degree + 1")
nurbs_knots_non_decreasing = _stub("NURBS knot vectors are non-decreasing")
nurbs_knot_multiplicity = _stub("NURBS knot multiplicity <= degree")
polyline_closed = _stub(
    "Closed Polyline3D repeats its first point; adjacent segments coincide")
catalogue_holes_planar = _stub(
    "Catalogue hole contours are 2-D (Z=0) and centered at the origin")

# topology
panel_limited_by_closed = _stub("Panel LimitedBy resolves to one closed contour")
composite_curve_continuous = _stub(
    "CompositeCurve3D segments ordered end-to-end and continuous")
hole_contours_closed = _stub("Hole contours are closed")
hole_not_splitting_plate = _stub("A hole does not split a plate into disjoint regions")
seam_topology = _stub("Seams never connect boundary/seam/hole to a hole; "
                      "seam pattern yields closed plate contours")
compartment_closure = _stub("CompartmentFace/ContourBound curves closed; "
                            "CellBoundary forms a closed volume")
compartments_disjoint = _stub("Compartments do not physically overlap")
surface_normals_and_boundaries = _stub(
    "Surface-collection normals consistent; boundary loops closed, "
    "inner/outer distinguished")
stiffener_inclinations = _stub(
    "Stiffener inclinations: no duplicates, no web/flange vector flips")

# properties
plate_weight_consistent = _stub(
    "Plate weight ~= area x thickness x density within tolerance")
panel_weight_cog_consistent = _stub(
    "Panel weight/CoG consistent with its composed parts")
profile_closed_section = _stub(
    "Profile parameters reproduce a closed section contour")
renewal_thickness_on_instance = _stub(
    "Renewal thickness assigned to the part instance, not only a shared definition")
```

- [ ] **Step 5: Create `.../rules/identity.toml`**

The engine resolves the `ocx:` prefix in xpath params to the document's OCX
namespace at execution time (step 2); step 1 only stores the strings.

```toml
# GUID / local-id rules — source wiki page: guidsidsandnames

[[rule]]
id          = "OCX-ID-001"
title       = "Structural objects carry GUIDRef and id"
description = "Every EntityBase-derived object (Vessel, Panel, Plate, Stiffener, Bracket, ...) must carry both a GUIDRef and a local id."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:entitybase_has_guid_and_id"

[[rule]]
id          = "OCX-ID-002"
title       = "GUIDs are unique"
description = "Duplicate GUIDRef values must not identify different objects within the document."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]
[rule.check]
primitive = "unique"
xpath     = "//*[@ocx:GUIDRef]"
key       = "@ocx:GUIDRef"

[[rule]]
id          = "OCX-ID-003"
title       = "Local ids are unique"
description = "Local id attribute values must be unique within the exchange document."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]
[rule.check]
primitive = "unique"
xpath     = "//*[@id]"
key       = "@id"

[[rule]]
id          = "OCX-ID-004"
title       = "Geometry objects carry a local id"
description = "Geometry objects derived from IDBase (curves, surfaces) must carry a local id."
source      = "guidsidsandnames"
category    = "identity"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:idbase_has_id"

[[rule]]
id          = "OCX-ID-005"
title       = "Names are not identifiers"
description = "Names are optional, need not be unique and must never be used as identifiers."
source      = "guidsidsandnames"
category    = "identity"
severity    = "info"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:names_not_identifiers"
```

- [ ] **Step 6: Create `.../rules/document.toml`**

```toml
# Root-element and units rules — source wiki pages: schema_root_element, units

[[rule]]
id          = "OCX-DOC-001"
title       = "schemaLocation names the namespace/XSD tuple"
description = "The root xsi:schemaLocation must contain the (NAMESPACE, XSD_LOCATION) tuple; for OCX export both entries must be identical."
source      = "schema_root_element"
category    = "document"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:schema_location_tuple"

[[rule]]
id          = "OCX-DOC-002"
title       = "Root declarations present"
description = "schemaVersion, xmlns:ocx and xmlns:xsi must be present on the OCX root element."
source      = "schema_root_element"
category    = "document"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:root_declarations"

[[rule]]
id          = "OCX-DOC-003"
title       = "Units fully declared"
description = "Every Unit must have a unique mandatory id and a UnitName; a missing UnitSymbol is reported as a warning-level finding."
source      = "units"
category    = "document"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:unit_definitions"

[[rule]]
id          = "OCX-DOC-004"
title       = "Unit and dimension references resolve"
description = "All unit and dimension references must resolve to declared UnitsML definitions."
source      = "units"
category    = "document"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:unit_refs_resolve"

[[rule]]
id          = "OCX-DOC-005"
title       = "Enumerated root units preferred"
description = "Enumerated UnitsML root units should be used whenever the unit exists in the UnitsML enumeration."
source      = "units"
category    = "document"
severity    = "warning"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:enumerated_root_units"
```

- [ ] **Step 7: Create `.../rules/references.toml`**

```toml
# Cross-reference and connectivity rules

[[rule]]
id          = "OCX-REF-001"
title       = "All references resolve"
description = "Every *Ref attribute must resolve to an existing object in the document."
source      = "topology"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
primitive     = "ref_resolves"
ref_attribute = "*Ref"
target_xpath  = "//*[@id or @ocx:GUIDRef]"

[[rule]]
id          = "OCX-REF-002"
title       = "Panel contains at least one plate"
description = "Every valid Panel must contain at least one Plate through ComposedOf."
source      = "panel"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
primitive = "cardinality"
xpath     = "//ocx:Panel"
child     = "ocx:ComposedOf"
min       = 1

[[rule]]
id          = "OCX-REF-003"
title       = "Stiffener has one end configuration per end"
description = "Each Stiffener may have at most two end configurations, one at each end."
source      = "endconfiguration"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:stiffener_end_configurations"

[[rule]]
id          = "OCX-REF-004"
title       = "Two-lug slot has two LugPlateRef"
description = "A slot with two attached lug plates must contain exactly two LugPlateRef references, one per lug plate."
source      = "slots"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:slot_lug_plate_refs"

[[rule]]
id          = "OCX-REF-005"
title       = "Connectivity is explicit"
description = "Structural connectivity must be encoded explicitly via references, never left to proximity inference."
source      = "structural_connectivity"
category    = "references"
severity    = "error"
requires    = ["xml", "ir"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:explicit_connectivity"

[[rule]]
id          = "OCX-REF-006"
title       = "Exactly one root coordinate system"
description = "The model must contain exactly one global/root CoordinateSystem; local systems may be nested beneath it."
source      = "coordinatesystem"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
primitive = "cardinality"
xpath     = "//ocx:Vessel"
child     = "ocx:CoordinateSystem"
min       = 1
max       = 1

[[rule]]
id          = "OCX-REF-007"
title       = "Panel represented as OccurrenceGroup"
description = "A Panel must be represented as an OccurrenceGroup in a DesignView, never referenced directly as an Occurrence."
source      = "designview"
category    = "references"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:panel_as_occurrence_group"

[[rule]]
id          = "OCX-REF-008"
title       = "Single hole representation"
description = "A plate hole or slot should appear in only one representation: either CutBy or embedded in OuterContour, not both."
source      = "holeshapecatalogue"
category    = "references"
severity    = "warning"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:hole_single_representation"
```

- [ ] **Step 8: Create `.../rules/curves_surfaces.toml`**

```toml
# Curve/surface well-formedness rules

[[rule]]
id          = "OCX-GEO-001"
title       = "NURBS control-point count"
description = "The number of NURBS control points must be at least degree + 1."
source      = "nurbs"
category    = "curves_surfaces"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:nurbs_control_points"

[[rule]]
id          = "OCX-GEO-002"
title       = "NURBS knots non-decreasing"
description = "NURBS knot vector values must be non-decreasing."
source      = "nurbs"
category    = "curves_surfaces"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:nurbs_knots_non_decreasing"

[[rule]]
id          = "OCX-GEO-003"
title       = "NURBS knot multiplicity"
description = "NURBS knot multiplicity must not exceed the degree."
source      = "nurbs"
category    = "curves_surfaces"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:nurbs_knot_multiplicity"

[[rule]]
id          = "OCX-GEO-004"
title       = "Closed polylines well-formed"
description = "A closed Polyline3D must repeat its first position at the end and adjacent segment endpoints must coincide."
source      = "polyline3d"
category    = "curves_surfaces"
severity    = "error"
requires    = ["xml"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:polyline_closed"
tolerance_mm = 0.1

[[rule]]
id          = "OCX-GEO-005"
title       = "Catalogue hole contours planar and centered"
description = "Parametric catalogue hole contours should be two-dimensional (Z = 0) and centered at the catalogue origin."
source      = "pararmetricholesandholeshapecatalogue"
category    = "curves_surfaces"
severity    = "warning"
requires    = ["xml"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:catalogue_holes_planar"
tolerance_mm = 0.1
```

- [ ] **Step 9: Create `.../rules/topology.toml`**

```toml
# Geometry/topology closure and orientation rules

[[rule]]
id          = "OCX-TOP-001"
title       = "Panel LimitedBy closes"
description = "A panel's LimitedBy objects must resolve to one closed geometric contour bounding a trimmed surface."
source      = "panel"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:panel_limited_by_closed"
tolerance_mm = 1.0

[[rule]]
id          = "OCX-TOP-002"
title       = "Composite curves continuous"
description = "CompositeCurve3D segments must be ordered end-to-end and continuous at every junction."
source      = "compositecurve3d"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:composite_curve_continuous"
tolerance_mm = 0.1

[[rule]]
id          = "OCX-TOP-003"
title       = "Hole contours closed"
description = "Hole and opening contours must be closed."
source      = "holeshapecatalogue"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:hole_contours_closed"
tolerance_mm = 0.1

[[rule]]
id          = "OCX-TOP-004"
title       = "Holes do not split plates"
description = "A panel hole must not cut completely across a plate so as to create two disjoint plate regions."
source      = "holeshapecatalogue"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:hole_not_splitting_plate"

[[rule]]
id          = "OCX-TOP-005"
title       = "Seam topology valid"
description = "Seams must never connect boundary-hole, seam-hole or hole-hole; the seam pattern must subdivide the panel into closed plate contours."
source      = "seamsandopenings"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:seam_topology"

[[rule]]
id          = "OCX-TOP-006"
title       = "Compartment boundaries closed"
description = "CompartmentFace and ContourBound curves must be closed; every CellBoundary must form a closed volume."
source      = "compartment"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom       = "ocx_rules.packs.best_practice.checks:compartment_closure"
tolerance_mm = 1.0

[[rule]]
id          = "OCX-TOP-007"
title       = "Compartments disjoint"
description = "Compartments should not physically overlap; each represents a distinct subregion of the vessel volume."
source      = "compartment"
category    = "topology"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:compartments_disjoint"

[[rule]]
id          = "OCX-TOP-008"
title       = "Surface normals and boundaries consistent"
description = "Normals across a connected surface collection must be consistently oriented; boundary loops must be closed with inner and outer boundaries distinguished."
source      = "surfacecollectionnormals"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom              = "ocx_rules.packs.best_practice.checks:surface_normals_and_boundaries"
angle_tolerance_deg = 90.0

[[rule]]
id          = "OCX-TOP-009"
title       = "Stiffener inclinations consistent"
description = "Stiffener inclinations must not duplicate positions and web/flange direction vectors must not flip between samples."
source      = "inclination"
category    = "topology"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:stiffener_inclinations"
```

- [ ] **Step 10: Create `.../rules/properties.toml`**

```toml
# Mass/property consistency rules

[[rule]]
id          = "OCX-PROP-001"
title       = "Plate weight consistent"
description = "Plate weight must equal surface area x thickness x material density within tolerance, after all cuts and splits."
source      = "property_validation"
category    = "properties"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom                = "ocx_rules.packs.best_practice.checks:plate_weight_consistent"
relative_tolerance    = 0.02

[[rule]]
id          = "OCX-PROP-002"
title       = "Panel weight/CoG consistent"
description = "Panel weight and centre of gravity must be consistent with all composed plates, stiffeners, pillars and brackets."
source      = "property_validation"
category    = "properties"
severity    = "warning"
requires    = ["ir", "geometry"]
[rule.check]
custom             = "ocx_rules.packs.best_practice.checks:panel_weight_cog_consistent"
relative_tolerance = 0.02

[[rule]]
id          = "OCX-PROP-003"
title       = "Profile parameters close"
description = "Profile parameters (e.g. bulb flat) must reproduce a closed cross-section contour."
source      = "bulbflatparameters"
category    = "properties"
severity    = "error"
requires    = ["ir", "geometry"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:profile_closed_section"

[[rule]]
id          = "OCX-PROP-004"
title       = "Renewal thickness on instance"
description = "Renewal thickness must be assigned to the individual part instance, not only to a shared definition."
source      = "renewal_thickness"
category    = "properties"
severity    = "error"
requires    = ["ir"]
[rule.check]
custom = "ocx_rules.packs.best_practice.checks:renewal_thickness_on_instance"
```

- [ ] **Step 11: Create `packages/ocx-rules/src/ocx_rules/packs/best_practice/__init__.py`**

```python
"""Built-in best-practice rule pack, sourced from the OCX wiki."""
from __future__ import annotations

from importlib import resources

from ocx_rules.catalogue import load_catalogue_dir
from ocx_rules.model import RulePack

_PACK_VERSION = "0.1.0"


def load_pack() -> RulePack:
    """Entry-point target for the ``ocx_rules.packs`` group."""
    rules_dir = resources.files("ocx_rules.packs.best_practice") / "rules"
    return RulePack(
        name="best_practice",
        version=_PACK_VERSION,
        rules=load_catalogue_dir(rules_dir),
    )
```

Note: `load_catalogue_dir` receives an `importlib.resources` Traversable here —
the loader's non-`Path` branch handles it.

- [ ] **Step 12: Reinstall so the entry point registers, then run the tests**

Run: `uv sync --dev`
Run: `uv run pytest tests/test_rules_best_practice_pack.py tests/test_rules_manager.py -v`
Expected: ALL tests pass, including
`test_entry_point_discovery_finds_best_practice_pack` from Task 7.

- [ ] **Step 13: Commit**

```bash
git add packages/ocx-rules/src/ocx_rules/packs tests/test_rules_best_practice_pack.py uv.lock
git commit -m "feat(rules): built-in best_practice pack with 36 wiki-sourced rules"
```

---

### Task 9: CLI subcommand + reporting generator

**Files:**
- Create: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_report.py`
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/cli.py` (add command to `validate_app`, extend module docstring usage block)
- Test: `tests/test_rules_cli.py`

- [ ] **Step 1: Write the failing test `tests/test_rules_cli.py`**

```python
"""Smoke tests for `validator validate rules`."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ocx_model_validator.cli import app

runner = CliRunner()


class TestValidateRulesCli:
    def test_runs_clean_on_stub_model(self, stub_dir_310: Path):
        # Step 1 ships stubs only -> every rule is NOT_IMPLEMENTED/SKIPPED -> exit 0.
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx")])
        assert result.exit_code == 0, result.output
        assert "OCX-ID-002" in result.output

    def test_missing_model_exits_2(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(tmp_path / "nope.3docx")])
        assert result.exit_code == 2

    def test_rule_filter(self, stub_dir_310: Path):
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--rule", "OCX-ID-002"])
        assert result.exit_code == 0
        assert "OCX-ID-002" in result.output
        assert "OCX-TOP-001" not in result.output

    def test_markdown_destination(self, stub_dir_310: Path, tmp_path: Path):
        dest = tmp_path / "rules.md"
        result = runner.invoke(app, ["validate", "rules",
                                     str(stub_dir_310 / "ocxxml.3docx"),
                                     "--destination", str(dest)])
        assert result.exit_code == 0
        assert dest.exists()
        assert "OCX-ID-002" in dest.read_text(encoding="utf-8")
```

Note: typer validates `exists=True` on the model argument with exit code 2
(usage error), which matches the "cannot run" contract.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rules_cli.py -v`
Expected: FAIL — `No such command 'rules'`.

- [ ] **Step 3: Create `reporting/generators/rules_report.py`**

```python
"""Report generator for rule-based validation results."""
from __future__ import annotations

from ocx_rules.model import RuleResult, RuleStatus

from ocx_model_validator.reporting.model import Report, ReportSection, ReportTable

_STATUS_LABEL = {
    RuleStatus.PASSED: "passed",
    RuleStatus.FAILED: "FAILED",
    RuleStatus.NOT_IMPLEMENTED: "not implemented",
    RuleStatus.SKIPPED: "skipped",
    RuleStatus.CRASHED: "CRASHED",
}


def build(results: list[RuleResult], *, source_file: str,
          max_findings: int = 50) -> Report:
    """Build a Report: status summary, per-rule table and a findings table."""
    counts: dict[RuleStatus, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    summary = ReportTable(
        title="Summary",
        columns=["Status", "Rules"],
        rows=[[_STATUS_LABEL[s], n] for s, n in sorted(
            counts.items(), key=lambda kv: kv[0].value)],
        footer_rows=[["total", len(results)]],
    )

    rules_table = ReportTable(
        title="Rules",
        columns=["Rule", "Title", "Category", "Severity", "Status",
                 "Findings", "Note"],
        rows=[[r.spec.rule_id, r.spec.title, r.spec.category,
               r.spec.severity.value, _STATUS_LABEL[r.status],
               len(r.findings) or None, r.reason]
              for r in results],
    )

    finding_rows = []
    for result in results:
        for finding in result.findings:
            finding_rows.append([result.spec.rule_id,
                                 result.spec.severity.value,
                                 finding.message, finding.element_id,
                                 finding.guid, finding.location])
    truncated = len(finding_rows) > max_findings
    findings_table = ReportTable(
        title="Findings",
        columns=["Rule", "Severity", "Message", "Element", "GUID", "Line"],
        rows=finding_rows[:max_findings],
    )

    notes = []
    if truncated:
        notes.append(f"Findings truncated to the first {max_findings} of "
                     f"{len(finding_rows)}.")
    tables = [summary, rules_table]
    if finding_rows:
        tables.append(findings_table)
    return Report(
        title="Rule validation",
        metadata={"model": source_file, "rules run": str(len(results))},
        sections=[ReportSection(title="Rule-based validation",
                                tables=tables, notes=notes)],
    )
```

- [ ] **Step 4: Add the CLI command to `cli.py`**

Insert after the `validate_schema_cmd` function (before `def entrypoint`), and
add `validator validate rules MODEL.3docx [--config FILE] ...` to the usage
block in the module docstring:

```python
@validate_app.command("rules")
def validate_rules_cmd(
    model: Path = _MODEL_ARG,
    config: Path | None = typer.Option(
        None, "--config", exists=True, readable=True,
        help="Rule configuration TOML (disable rules, override severity/params)."),
    category: str | None = typer.Option(
        None, "--category", help="Run only rules in this category."),
    rule: str | None = typer.Option(
        None, "--rule", help="Run only the rule with this id."),
    max_findings: int = typer.Option(
        50, "--max-findings", min=1,
        help="Maximum number of findings listed in the report."),
    fmt: ReportFormat | None = _FORMAT_OPT,
    destination: Path | None = _DEST_OPT,
) -> None:
    """Run the configurable best-practice rules against the model.

    Exit codes: 0 = no error-level findings, 1 = error-level findings or
    crashed rules, 2 = cannot run (bad model path, config or catalogue).
    """
    from ocx_rules import (
        CatalogueError,
        ConfigError,
        RuleManager,
        RuleStatus,
        Severity,
        ValidationContext,
        load_config,
    )

    from ocx_model_validator.reporting.generators import rules_report

    try:
        manager = RuleManager(config=load_config(config))
        results = manager.run(ValidationContext(model),
                              category=category, rule_id=rule)
    except (CatalogueError, ConfigError) as exc:
        logger.error("{}", exc)
        raise typer.Exit(code=2) from exc

    _emit(rules_report.build(results, source_file=str(model),
                             max_findings=max_findings), fmt, destination)

    failed = any(
        (r.status is RuleStatus.FAILED and r.spec.severity is Severity.ERROR)
        or r.status is RuleStatus.CRASHED
        for r in results)
    raise typer.Exit(code=1 if failed else 0)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_rules_cli.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Manual smoke check (markdown render)**

Run: `uv run validator validate rules tests/data/ocx_310_stubs/ocxxml.3docx`
Expected: rich tables (Summary / Rules) on stdout, exit code 0, 36 rules listed
as not implemented or skipped.

- [ ] **Step 7: Commit**

```bash
git add packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_report.py packages/ocx-model-validator/src/ocx_model_validator/cli.py tests/test_rules_cli.py
git commit -m "feat(validator): 'validate rules' CLI subcommand with rule report"
```

---

### Task 10: Full-suite verification and docs

**Files:**
- Modify: `.github/copilot-instructions.md` — add `ocx-rules` to the project layout, dependency direction and CLI sections (follow the existing style; brief).

- [ ] **Step 1: Run the whole test suite**

Run: `uv run pytest`
Expected: all tests pass, no regressions.

- [ ] **Step 2: Lint**

Run: `uv run ruff check .`
Expected: no findings. Fix anything reported, re-run.

- [ ] **Step 3: Update `.github/copilot-instructions.md`**

Add to the layout tree (after ocx-render):

```
│   └── ocx-rules/              ← configurable best-practice rule engine
│       └── src/ocx_rules/
│           ├── model.py         ← RuleSpec/RuleResult/Finding/Severity/RuleStatus
│           ├── context.py       ← ValidationContext (lazy lxml tree + lazy IrVessel)
│           ├── catalogue.py     ← TOML rule-catalogue loader (load-time validation)
│           ├── primitives/      ← parameterized check primitives (PRIMITIVE_REGISTRY)
│           ├── manager.py       ← RuleManager: entry-point discovery + execution
│           ├── config.py        ← user TOML config (disable/severity/params)
│           └── packs/best_practice/ ← built-in pack: rules/*.toml + checks.py
```

Add to dependency direction: `ocx-model-validator → ocx-rules → ocx-model-core`
(geometry used lazily by rule checks when installed).

Add to the CLI section:

```bash
# Run configurable best-practice rules (exit 0 clean / 1 error findings / 2 cannot run)
validator validate rules model.3docx [--config FILE] [--category CAT] [--rule ID]
```

- [ ] **Step 4: Final commit**

```bash
git add .github/copilot-instructions.md
git commit -m "docs: document ocx-rules package and validate-rules CLI"
```




