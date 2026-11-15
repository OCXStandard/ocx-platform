# Unchecked Elements in Rule Results — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every rule result records the elements its check could not evaluate (with a reason), and the JSON sidecar and the HTML/table report show them. Rule status and the CLI exit code stay the same.

**Architecture:** Checks may return a `CheckOutcome(findings, unchecked)` instead of a list of `Finding`. `RuleManager._run_one` normalises both forms and copies `unchecked` onto `RuleResult`. The 15 geometry-dependent checks build their outcome with a small mutable `OutcomeCollector`. The reporting generators in `ocx-model-validator` render the new data.

**Tech Stack:** Python 3.12, dataclasses, loguru, numpy, pytest, ruff, uv workspace.

**Spec:** `docs/superpowers/specs/2026-11-13-unchecked-elements-design.md`

**Conventions (read before starting):**
- Work in `C:\PythonDev\ocx-platform` on branch `feat/unchecked-elements`.
- Run tools only through uv: `uv run pytest ...` and `uv run ruff check packages tests`.
- The baseline is 1148 passed / 42 skipped; `uv run pytest -q` takes about 60 s.
- `git add` explicit paths only. The repo has many unrelated untracked files, so never use `git add -A` or `git add .`.
- Every commit message ends with the trailer
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- Keep lines ≤ 88 chars. Ruff enforces import sorting (isort style).
- PowerShell: `&&` only chains native commands.

**Signature deviation from spec (decided at planning time):** `OutcomeCollector.unchecked` mirrors `Finding`. Its signature is `unchecked(reason, element_id=None, guid=None)`, not `unchecked(element, reason)`. TOP-002 only knows owner id/guid strings, not objects. Task 9 updates the spec.

**Classification reminder (from spec):**
- *Not applicable* elements stay silent and keep their `logger.debug` + `continue`.
- *Unchecked* elements call `out.unchecked(reason, element_id, guid)`, which logs at debug level itself, so remove the old `logger.debug`, then `continue`.
- *Rule-logic* non-cases stay silent.

---

## File map

| File | Change |
|---|---|
| `packages/ocx-rules/src/ocx_rules/model.py` | + `Unchecked`, `CheckOutcome`, `OutcomeCollector`; `RuleResult.unchecked` |
| `packages/ocx-rules/src/ocx_rules/__init__.py` | re-export the three new names |
| `packages/ocx-rules/src/ocx_rules/manager.py` | `_run_one` accepts `CheckOutcome` |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py` | PROP-001/002/003 → `CheckOutcome` |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py` | TOP-001/002/003/004/005/008/009 → `CheckOutcome` |
| `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py` | TOP-010/011/012, PROP-005/006 → `CheckOutcome` |
| `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_json.py` | `unchecked` per result + summary count |
| `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_report.py` | Unchecked column + table |
| `tests/test_rules_model.py`, `tests/test_rules_manager.py`, `tests/test_rules_json_report.py` | new tests |
| `tests/test_rules_report.py` | **new** report tests |
| `tests/test_rules_checks_properties.py`, `tests/test_rules_checks_topology.py`, `tests/test_rules_checks_plausibility.py` | adapt + new tests |
| `packages/ocx-rules/CHANGELOG.md`, `packages/ocx-model-validator/CHANGELOG.md`, `README.md`, spec | docs |

### Mechanical test rewrite (used in Tasks 5–8)

When a check returns `CheckOutcome`, update every **direct call** of that check in its test file:

| Before | After |
|---|---|
| `assert check(ctx, P) == []` | `assert check(ctx, P) == CheckOutcome()` |
| `(finding,) = check(ctx, P)` | `(finding,) = check(ctx, P).findings` |
| `findings = check(ctx, P)` | `findings = check(ctx, P).findings` |
| `len(check(ctx, P))` | `len(check(ctx, P).findings)` |

`== CheckOutcome()` is deliberately strict: a clean element must produce neither findings nor unchecked entries. If a previously-passing test now shows an unexpected `Unchecked`, the classification is wrong. Fix the code; do not loosen the test.

---

### Task 1: Model types and `OutcomeCollector`

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/model.py` (after `Finding`, ~line 82; `RuleResult` ~line 84)
- Modify: `packages/ocx-rules/src/ocx_rules/__init__.py`
- Test: `tests/test_rules_model.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_rules_model.py`, and add `CheckOutcome, OutcomeCollector, Unchecked` to its `from ocx_rules.model import (...)` block (alphabetical order):

```python
class TestOutcomeCollector:
    def test_empty_outcome(self):
        assert OutcomeCollector("R-1").outcome() == CheckOutcome()

    def test_findings_and_unchecked_in_insertion_order(self):
        out = OutcomeCollector("R-1")
        out.add(Finding(message="a", element_id="e1"))
        out.unchecked("no thickness", "e2", "g2")
        out.add(Finding(message="b", element_id="e3"))
        out.unchecked("no surface", "e4")
        outcome = out.outcome()
        assert [f.message for f in outcome.findings] == ["a", "b"]
        assert outcome.unchecked == (Unchecked("no thickness", "e2", "g2"),
                                     Unchecked("no surface", "e4", None))

    def test_reasons_merge_per_element(self):
        out = OutcomeCollector("R-1")
        out.unchecked("first", "e1", "g1")
        out.unchecked("second", "e1", "g1")
        out.unchecked("first", "e1", "g1")  # exact duplicate dropped
        assert out.outcome().unchecked == (Unchecked("first; second", "e1", "g1"),)

    def test_none_element_entries_never_merge(self):
        out = OutcomeCollector("R-1")
        out.unchecked("x")
        out.unchecked("x")
        assert out.outcome().unchecked == (Unchecked("x"), Unchecked("x"))

    def test_outcome_is_a_snapshot(self):
        out = OutcomeCollector("R-1")
        first = out.outcome()
        out.unchecked("later", "e1")
        assert first == CheckOutcome()


def test_rule_result_unchecked_defaults_to_empty():
    result = RuleResult(spec=_spec(), status=RuleStatus.PASSED)
    assert result.unchecked == ()
```

- [ ] **Step 2: Run them and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_model.py -q`
  - Expected: collection error `ImportError: cannot import name 'CheckOutcome'`.

- [ ] **Step 3: Implement.**
  - In `model.py`, add `from loguru import logger` to the imports, after `from enum import Enum` with a blank line between the stdlib and third-party groups.
  - Update the module docstring sentence to: "``RuleSpec.params``, ``RuleResult.findings`` and ``RuleResult.unchecked`` hold plain data; ...". `OutcomeCollector` is the one mutable helper.
  - Insert directly after the `Finding` class:

```python
@dataclass(frozen=True)
class Unchecked:
    """An element a check could not evaluate (informational)."""

    reason: str
    element_id: str | None = None
    guid: str | None = None


@dataclass(frozen=True)
class CheckOutcome:
    """Result of one check: violations plus elements it could not evaluate."""

    findings: tuple[Finding, ...] = ()
    unchecked: tuple[Unchecked, ...] = ()


class OutcomeCollector:
    """Mutable builder for a :class:`CheckOutcome` used inside checks.

    ``unchecked`` keeps one entry per element id: further reasons for the
    same id are appended with ``"; "`` (exact duplicates dropped). Entries
    without an element id are never merged.
    """

    def __init__(self, rule_id: str) -> None:
        self.rule_id = rule_id
        self._findings: list[Finding] = []
        self._unchecked: list[Unchecked] = []
        self._index: dict[str, int] = {}

    def add(self, finding: Finding) -> None:
        self._findings.append(finding)

    def unchecked(self, reason: str, element_id: str | None = None,
                  guid: str | None = None) -> None:
        logger.debug("{}: {} not checked ({})", self.rule_id,
                     element_id or "<unidentified>", reason)
        if element_id is None:
            self._unchecked.append(Unchecked(reason, None, guid))
            return
        idx = self._index.get(element_id)
        if idx is None:
            self._index[element_id] = len(self._unchecked)
            self._unchecked.append(Unchecked(reason, element_id, guid))
            return
        prev = self._unchecked[idx]
        if reason in prev.reason.split("; "):
            return
        self._unchecked[idx] = Unchecked(f"{prev.reason}; {reason}",
                                         element_id, prev.guid or guid)

    def outcome(self) -> CheckOutcome:
        return CheckOutcome(findings=tuple(self._findings),
                            unchecked=tuple(self._unchecked))
```

  - In `RuleResult`, add after `findings`:

```python
    unchecked: tuple[Unchecked, ...] = ()  # PASSED / FAILED only
```

  - In `packages/ocx-rules/src/ocx_rules/__init__.py`, add `CheckOutcome`, `OutcomeCollector` and `Unchecked` to the `from ocx_rules.model import (...)` block and to `__all__`, keeping both alphabetical.

- [ ] **Step 4: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_model.py -q`
  - Expected: all pass.
  - Then run `uv run ruff check packages/ocx-rules tests/test_rules_model.py`. Expected: `All checks passed!`

- [ ] **Step 5: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/model.py packages/ocx-rules/src/ocx_rules/__init__.py tests/test_rules_model.py
git commit -m "feat(rules): add Unchecked, CheckOutcome and OutcomeCollector" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: `RuleManager` accepts `CheckOutcome`

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/manager.py` (`_run_one`, ~lines 88–111)
- Test: `tests/test_rules_manager.py`

- [ ] **Step 1: Write the failing tests.**
  - Add `CheckOutcome` and `Unchecked` to the `from ocx_rules.model import (...)` block.
  - Add these helper checks after `check_stub`:

```python
def check_outcome_pass_with_unchecked(context, params):
    return CheckOutcome(unchecked=(Unchecked("no surface", "e9", "g9"),))


def check_outcome_fail_with_unchecked(context, params):
    return CheckOutcome(findings=(Finding(message="violation", element_id="e1"),),
                        unchecked=(Unchecked("no surface", "e9"),))


def check_generator(context, params):
    yield Finding(message="from generator")
```

  - Append to `class TestExecution`:

```python
    def test_check_outcome_unchecked_does_not_change_status(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-OK", "check_outcome_pass_with_unchecked"),
            _spec("R-BAD", "check_outcome_fail_with_unchecked"),
        )])
        by_id = {r.spec.rule_id: r for r in manager.run(context)}
        ok, bad = by_id["R-OK"], by_id["R-BAD"]
        assert ok.status is RuleStatus.PASSED
        assert ok.findings == ()
        assert ok.unchecked == (Unchecked("no surface", "e9", "g9"),)
        assert bad.status is RuleStatus.FAILED
        assert bad.findings[0].message == "violation"
        assert bad.unchecked == (Unchecked("no surface", "e9"),)

    def test_plain_iterable_wrapped(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-GEN", "check_generator"), _spec("R-PASS", "check_passes"))])
        by_id = {r.spec.rule_id: r for r in manager.run(context)}
        assert by_id["R-GEN"].status is RuleStatus.FAILED
        assert by_id["R-GEN"].findings[0].message == "from generator"
        assert by_id["R-GEN"].unchecked == ()
        assert by_id["R-PASS"].status is RuleStatus.PASSED

    def test_non_run_statuses_carry_no_unchecked(self, context):
        manager = RuleManager(packs=[_pack(
            _spec("R-CRASH", "check_crashes"), _spec("R-STUB", "check_stub"))])
        assert all(r.unchecked == () for r in manager.run(context))
```

- [ ] **Step 2: Run them and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_manager.py -q`
  - Expected: `test_check_outcome_unchecked_does_not_change_status` FAILS, because a `CheckOutcome` is truthy and becomes `findings=tuple(outcome)`, so a TypeError is raised inside `done`.
  - `test_plain_iterable_wrapped` already passes thanks to `tuple(findings)`; keep it as a regression guard.

- [ ] **Step 3: Implement.** Add `CheckOutcome` to manager.py's `from ocx_rules.model import (...)` block. Replace the body of `_run_one` from `def done(` to the end of the method with:

```python
        def done(status: RuleStatus, findings=(), reason=None,
                 unchecked=()) -> RuleResult:
            return RuleResult(
                spec=spec, status=status, findings=tuple(findings), reason=reason,
                unchecked=tuple(unchecked),
                duration_ms=(time.perf_counter() - start) * 1000.0)

        reason = self._unsatisfied(spec, context)
        if reason is not None:
            logger.debug("Rule {} skipped: {}", spec.rule_id, reason)
            return done(RuleStatus.SKIPPED, reason=reason)
        try:
            check = _resolve_check(spec.check)
            result = check(context, dict(spec.params))
            outcome = (result if isinstance(result, CheckOutcome)
                       else CheckOutcome(findings=tuple(result)))
        except CheckNotImplemented as exc:
            return done(RuleStatus.NOT_IMPLEMENTED, reason=str(exc))
        except Exception as exc:
            logger.warning("Rule {} crashed: {}", spec.rule_id, exc)
            return done(RuleStatus.CRASHED, reason=f"{type(exc).__name__}: {exc}")
        return done(RuleStatus.FAILED if outcome.findings else RuleStatus.PASSED,
                    findings=outcome.findings, unchecked=outcome.unchecked)
```

  Keep `tuple(result)` inside the `try`: generator checks that raise while iterating must still become CRASHED.

- [ ] **Step 4: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_manager.py tests/test_rules_best_practice_pack.py -q`
  - Expected: all pass.

- [ ] **Step 5: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/manager.py tests/test_rules_manager.py
git commit -m "feat(rules): RuleManager records unchecked elements from CheckOutcome" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: JSON sidecar

**Files:**
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_json.py`
- Test: `tests/test_rules_json_report.py`

- [ ] **Step 1: Write the failing tests.** Add `Unchecked` to the model imports, then append to `class TestRulesJsonBuild`:

```python
    def test_result_carries_unchecked_elements(self):
        result = RuleResult(spec=_spec(), status=RuleStatus.PASSED,
                            unchecked=(Unchecked("no surface", "PL1", "g1"),))
        (entry,) = rules_json.build([result], model="m.3docx")["results"]
        assert entry["unchecked"] == [
            {"element_id": "PL1", "guid": "g1", "reason": "no surface"}]

    def test_summary_counts_unchecked_elements(self):
        a = RuleResult(spec=_spec("R-1"), status=RuleStatus.PASSED,
                       unchecked=(Unchecked("x", "e1"), Unchecked("y", "e2")))
        b = RuleResult(spec=_spec("R-2"), status=RuleStatus.FAILED,
                       findings=(Finding(message="m"),),
                       unchecked=(Unchecked("z", "e3"),))
        c = RuleResult(spec=_spec("R-3"), status=RuleStatus.PASSED)
        doc = rules_json.build([a, b, c], model="m.3docx")
        assert doc["summary"]["unchecked_elements"] == 3
        assert doc["results"][2]["unchecked"] == []
```

- [ ] **Step 2: Run them and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_json_report.py -q`
  - Expected: FAIL with `KeyError: 'unchecked'` / `'unchecked_elements'`.

- [ ] **Step 3: Implement.** In `rules_json.py`:
  - Add `"unchecked_elements": sum(len(r.unchecked) for r in results),` to the `"summary"` dict after `"warning_findings"`.
  - Add to `_result_entry` after `"findings"`:

```python
        "unchecked": [
            {"element_id": u.element_id, "guid": u.guid, "reason": u.reason}
            for u in result.unchecked
        ],
```

  - Extend the module docstring's last sentence with: "..., plus the elements each check could not evaluate (``unchecked``)."

- [ ] **Step 4: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_json_report.py -q`
  - Expected: all pass.

- [ ] **Step 5: Commit.**

```powershell
git add packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_json.py tests/test_rules_json_report.py
git commit -m "feat(validator): unchecked elements in the rules JSON sidecar" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: HTML/table report

**Files:**
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_report.py`
- Create: `tests/test_rules_report.py`

- [ ] **Step 1: Write the failing tests.** Create `tests/test_rules_report.py`:

```python
"""Tests for the rule-validation Report (tables rendered to rich/md/HTML)."""
from __future__ import annotations

from ocx_model_validator.reporting.generators import rules_report
from ocx_rules.model import (
    CheckRef,
    RuleResult,
    RuleSpec,
    RuleStatus,
    Severity,
    Unchecked,
)


def _spec(rule_id: str = "R-1") -> RuleSpec:
    return RuleSpec(rule_id=rule_id, title="t", description="d",
                    category="topology", severity=Severity.ERROR,
                    source="s", requires=frozenset({"xml"}),
                    check=CheckRef(primitive="noop"))


def _tables(report):
    (section,) = report.sections
    return {t.title: t for t in section.tables}, section.notes


def test_rules_table_has_unchecked_count_column():
    results = [
        RuleResult(spec=_spec("R-1"), status=RuleStatus.PASSED,
                   unchecked=(Unchecked("x", "e1"), Unchecked("y", "e2"))),
        RuleResult(spec=_spec("R-2"), status=RuleStatus.PASSED),
    ]
    tables, _ = _tables(rules_report.build(results, source_file="m"))
    rules = tables["Rules"]
    col = rules.columns.index("Unchecked")
    assert rules.columns[col - 1] == "Findings"
    assert [row[col] for row in rules.rows] == [2, None]


def test_unchecked_elements_table_lists_entries():
    results = [RuleResult(spec=_spec("R-1"), status=RuleStatus.PASSED,
                          unchecked=(Unchecked("no surface", "e1", "g1"),))]
    tables, notes = _tables(rules_report.build(results, source_file="m"))
    table = tables["Unchecked elements"]
    assert table.columns == ["Rule", "Element", "GUID", "Reason"]
    assert table.rows == [["R-1", "e1", "g1", "no surface"]]
    assert notes == []


def test_unchecked_table_absent_when_empty():
    results = [RuleResult(spec=_spec(), status=RuleStatus.PASSED)]
    tables, _ = _tables(rules_report.build(results, source_file="m"))
    assert "Unchecked elements" not in tables


def test_unchecked_table_truncated_with_note():
    many = tuple(Unchecked("r", f"e{i}") for i in range(5))
    results = [RuleResult(spec=_spec(), status=RuleStatus.PASSED,
                          unchecked=many)]
    tables, notes = _tables(rules_report.build(results, source_file="m",
                                               max_findings=2))
    assert len(tables["Unchecked elements"].rows) == 2
    assert "Unchecked elements truncated to the first 2 of 5." in notes
```

- [ ] **Step 2: Run them and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_report.py -q`
  - Expected: FAIL (`ValueError: 'Unchecked' is not in list`, `KeyError: 'Unchecked elements'`).

- [ ] **Step 3: Implement.** In `rules_report.py`:
  - Change the Rules table columns to `["Rule", "Title", "Category", "Severity", "Status", "Findings", "Unchecked", "Note"]`.
  - Change the row to `..., len(r.findings) or None, len(r.unchecked) or None, r.reason]`.
  - After the findings truncation note block (`if truncated: ...`), add:

```python
    unchecked_rows = [[result.spec.rule_id, u.element_id, u.guid, u.reason]
                      for result in results for u in result.unchecked]
    if len(unchecked_rows) > max_findings:
        notes.append(f"Unchecked elements truncated to the first "
                     f"{max_findings} of {len(unchecked_rows)}.")
```

  - After `if finding_rows: tables.append(findings_table)`, add:

```python
    if unchecked_rows:
        tables.append(ReportTable(
            title="Unchecked elements",
            columns=["Rule", "Element", "GUID", "Reason"],
            rows=unchecked_rows[:max_findings]))
```

  - Update the `build` docstring to: "Build a Report: status summary, per-rule table, findings and unchecked elements."

- [ ] **Step 4: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_report.py tests/test_rules_cli.py -q`
  - Expected: all pass. `test_rules_cli.py` exercises report rendering end-to-end.

- [ ] **Step 5: Commit.**

```powershell
git add packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/rules_report.py tests/test_rules_report.py
git commit -m "feat(validator): Unchecked column and table in the rules report" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Retrofit `properties.py` (PROP-001/002/003)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py:46-199`
- Test: `tests/test_rules_checks_properties.py`

- [ ] **Step 1: Adapt the existing tests.**
  - Add `from unittest.mock import patch` to the stdlib imports.
  - Add `from ocx_rules.model import CheckOutcome, Unchecked`, keeping isort order (before `ocx_rules.packs...`).
  - Apply the **Mechanical test rewrite** to every direct call of `plate_weight_consistent`, `panel_weight_cog_consistent` and `profile_closed_section`. Leave `renewal_thickness_on_instance` alone; it stays a list-returning content check.
  - Then change these existing tests as shown (renamed tests replace the old ones):

```python
    def test_missing_declared_weight_skipped(self):  # not applicable: silent
        ctx = self._ctx_with_plate(declared_kg=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == CheckOutcome()

    def test_missing_thickness_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=90.0, thickness_mm=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == CheckOutcome(
            unchecked=(Unchecked("no thickness", "pl1", "gpl1"),))

    def test_missing_density_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=90.0, density=None)
        assert plate_weight_consistent(ctx, self.PARAMS) == CheckOutcome(
            unchecked=(Unchecked("no material density", "pl1", "gpl1"),))

    def test_degenerate_outline_unchecked(self):
        # A collapsed (linear) outline yields surface_area 0.0, which must
        # be treated as unevaluable, not as a weight deviation.
        ctx = self._ctx_with_plate(declared_kg=78.5)
        ctx.vessel.plates["pl1"] = replace(
            ctx.vessel.plates["pl1"],
            outer_contour=_line(_pt(0, 0), _pt(1000, 0)))
        outcome = plate_weight_consistent(ctx, self.PARAMS)
        assert outcome.findings == ()
        (u,) = outcome.unchecked
        assert (u.element_id, u.guid) == ("pl1", "gpl1")
        assert u.reason.startswith("degenerate computed area")
```

- [ ] **Step 2: Add the new tests.**
  - Append to `TestPlateWeightConsistent`:

```python
    def test_no_owning_panel_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=78.5)
        ctx.vessel.plates["pl1"] = replace(
            ctx.vessel.plates["pl1"],
            parent_ref=ParentRef(kind=ParentKind.VESSEL, id="v1"))
        assert plate_weight_consistent(ctx, self.PARAMS).unchecked == (
            Unchecked("no owning panel", "pl1", "gpl1"),)

    def test_no_buildable_surface_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=78.5)
        ctx.vessel.panels["pan1"] = replace(ctx.vessel.panels["pan1"],
                                            unbounded_geometry=None)
        assert plate_weight_consistent(ctx, self.PARAMS).unchecked == (
            Unchecked("no buildable panel surface", "pl1", "gpl1"),)

    def test_unsampleable_outline_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=78.5)
        ctx.vessel.plates["pl1"] = replace(ctx.vessel.plates["pl1"],
                                           outer_contour=None)
        assert plate_weight_consistent(ctx, self.PARAMS).unchecked == (
            Unchecked("unsampleable outer contour", "pl1", "gpl1"),)

    def test_area_exception_unchecked(self):
        ctx = self._ctx_with_plate(declared_kg=78.5)
        with patch("ocx_rules.packs.best_practice.checks.properties."
                   "surface_area", side_effect=RuntimeError("boom")):
            outcome = plate_weight_consistent(ctx, self.PARAMS)
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("area evaluation failed: boom", "pl1", "gpl1"),))
```

  - In `TestPanelWeightCogConsistent`, change the two skip tests to:

```python
    def test_panel_without_declared_mass_props_skipped(self):  # silent
        ctx = self._ctx_with_panel(None, [_mass_props(weight_kg=78.5)])
        assert panel_weight_cog_consistent(ctx, self.PARAMS) == CheckOutcome()

    def test_panel_without_weighed_children_unchecked(self):
        ctx = self._ctx_with_panel(_mass_props(weight_kg=157.0),
                                   [IrMassProperties()])
        outcome = panel_weight_cog_consistent(ctx, self.PARAMS)
        assert outcome.findings == ()
        (u,) = outcome.unchecked
        assert u.reason == "no children with declared mass"
```

  - `_ctx_with_panel` creates panel `pan1` with guid `gpan1`. Also assert `(u.element_id, u.guid) == ("pan1", "gpan1")`.
  - In `TestProfileClosedSection`, replace `test_unbuildable_section_skipped` with the two tests below:

```python
    def test_unbuildable_section_unchecked(self):
        ctx = self._ctx_with_section(IrGenericSection(id="s1", guidref="gs1"))
        # IrGenericSection inherits ``guidref`` from IrSection
        assert profile_closed_section(ctx, {}) == CheckOutcome(unchecked=(
            Unchecked("profile could not be built", "s1", "gs1"),))

    def test_profile_exception_unchecked(self):
        ctx = self._ctx_with_section(IrGenericSection(id="s1"))
        with patch("ocx_rules.packs.best_practice.checks.properties."
                   "section_polygon", side_effect=RuntimeError("boom")):
            outcome = profile_closed_section(ctx, {})
        assert outcome.unchecked == (
            Unchecked("profile build failed: boom", "s1", None),)
```


- [ ] **Step 3: Run the tests and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_checks_properties.py -q`
  - Expected: many FAILs (`AttributeError: 'list' object has no attribute 'findings'`, and `[] == CheckOutcome()` is False).

- [ ] **Step 4: Implement.** In `properties.py`, change `from ocx_rules.model import Finding` to `from ocx_rules.model import CheckOutcome, Finding, OutcomeCollector`. Replace the three functions as follows.

  *PROP-001:* replace `plate_weight_consistent` entirely:

```python
def plate_weight_consistent(context, params: dict[str, Any]) -> CheckOutcome:
    """OCX-PROP-001: plate weight ~= area x thickness x density."""
    tol = float(params.get("relative_tolerance", 0.02))
    out = OutcomeCollector("OCX-PROP-001")
    geo = context.geometry
    vessel = context.vessel
    for pid, plate in vessel.plates.items():
        declared = _declared_weight_kg(geo, plate.mass_properties)
        if declared is None or declared <= 0.0:
            logger.debug("PROP-001: plate {} skipped (no declared dry "
                         "weight)", pid)
            continue
        thickness = geo.length.qty(plate.thickness)
        if thickness is None:
            out.unchecked("no thickness", pid, plate.guidref)
            continue
        material = (vessel.materials.get(plate.material_ref.local_ref)
                    if plate.material_ref is not None else None)
        density = geo.to_si(material.density) if material is not None else None
        if density is None:
            out.unchecked("no material density", pid, plate.guidref)
            continue
        panel = None
        pr = plate.parent_ref
        if pr is not None and pr.kind == ParentKind.PANEL:
            panel = vessel.panels.get(pr.id)
        if panel is None:
            out.unchecked("no owning panel", pid, plate.guidref)
            continue
        param = geo.surface_param(geo.panel_surface(panel))
        if param is None:
            out.unchecked("no buildable panel surface", pid, plate.guidref)
            continue
        if param.periodic_u:
            out.unchecked("periodic surface, ambiguous UV mapping", pid,
                          plate.guidref)
            continue
        outline = geo.sample(plate.outer_contour)
        if outline is None or len(outline) < 3:
            out.unchecked("unsampleable outer contour", pid, plate.guidref)
            continue
        holes_3d, skipped = _placed_hole_outlines(
            context, plate.cut_by_holes, plate.cut_by_contours)
        if skipped:
            logger.debug("PROP-001: plate {}: {} hole(s) could not be "
                         "placed; ignored in the area", pid, skipped)
        try:
            outline_uv = _open_uv(np.asarray(param.inverse(outline),
                                             dtype=float))
            holes_uv = [_open_uv(np.asarray(param.inverse(h), dtype=float))
                        for h in holes_3d]
            area = surface_area(param, outline_uv, holes_uv)
        except Exception as exc:  # noqa: BLE001 — lean-pass on UV failure
            out.unchecked(f"area evaluation failed: {exc}", pid, plate.guidref)
            continue
        if not np.isfinite(area) or area <= 0.0:
            out.unchecked(f"degenerate computed area {area}", pid,
                          plate.guidref)
            continue
        computed = area * thickness * density
        if abs(computed - declared) / declared > tol:
            out.add(Finding(
                message=(f"Plate declared dry weight {declared:.2f} kg "
                         f"deviates from computed area x thickness x density "
                         f"= {computed:.2f} kg by more than {tol * 100:.0f}%"),
                element_id=pid, guid=plate.guidref))
    return out.outcome()
```

  *PROP-002:* in `panel_weight_cog_consistent`, make these edits; everything else stays as is.
  - Return annotation becomes `-> CheckOutcome`.
  - Replace `findings: list[Finding] = []` with `out = OutcomeCollector("OCX-PROP-002")`.
  - Replace the `if not children:` block with:

```python
        if not children:
            out.unchecked("no children with declared mass", pid, panel.guidref)
            continue
```

  - Replace both `findings.append(Finding(` with `out.add(Finding(`.
  - Replace the final `return findings` with `return out.outcome()`.

  *PROP-003:* replace `profile_closed_section` entirely:

```python
def profile_closed_section(context, params: dict[str, Any]) -> CheckOutcome:
    """OCX-PROP-003: section parameters must yield a closed valid profile."""
    out = OutcomeCollector("OCX-PROP-003")
    geo = context.geometry
    for sid, section in context.vessel.sections.items():
        try:
            poly = section_polygon(section, geo.length)
        except Exception as exc:  # noqa: BLE001 — lean-pass per section
            out.unchecked(f"profile build failed: {exc}", sid, section.guidref)
            continue
        if poly is None:
            out.unchecked("profile could not be built", sid, section.guidref)
            continue
        reason = polygon_ok(poly)
        if reason is not None:
            out.add(Finding(
                message=(f"Section profile is not a closed valid polygon: "
                         f"{reason}"),
                element_id=sid, guid=section.guidref))
    return out.outcome()
```

  - Update the module docstring to: `"""Property consistency checks (OCX-PROP-001 through 004).` Then add the line: `Geometry-dependent checks return CheckOutcome (findings + unchecked)."""`

- [ ] **Step 5: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_checks_properties.py tests/test_rules_best_practice_pack.py -q`
  - Expected: all pass.
  - Then run `uv run ruff check packages/ocx-rules tests/test_rules_checks_properties.py`. Expected: clean.

- [ ] **Step 6: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/properties.py tests/test_rules_checks_properties.py
git commit -m "feat(rules): PROP-001/002/003 report unchecked elements" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Retrofit `topology.py` part 1 (TOP-001…005)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py:38-356`
- Test: `tests/test_rules_checks_topology.py`

- [ ] **Step 1: Adapt the existing tests.**
  - Add `from unittest.mock import patch` to the stdlib imports.
  - Add `from ocx_rules.model import CheckOutcome, Unchecked`, keeping isort order.
  - Apply the **Mechanical test rewrite** to every direct call of `panel_limited_by_closed`, `composite_curve_continuous`, `hole_contours_closed`, `hole_not_splitting_plate` and `seam_topology`.
  - Then replace these tests:

```python
    # TestPanelLimitedByClosed
    def test_unresolvable_ref_unchecked(self):
        sides = _square_sides(gap_mm=5.0)[:3]
        sides.append(IrLimitedByRef(ref_type="PanelRef", local_ref="nowhere"))
        panel = IrPanel(id="p1", guidref="g1", limited_by=sides)
        ctx = _ctx(_vessel({"p1": panel}))
        assert panel_limited_by_closed(ctx, {"tolerance_mm": 1.0}) == CheckOutcome(
            unchecked=(Unchecked("1 unresolved boundary ref(s)", "p1", "g1"),))

    # TestCompositeCurveContinuous
    def test_unsampleable_segment_unchecked(self):
        segs = [_line(_pt(0, 0), _pt(1000, 0)),
                IrNurbs3D(curve_length=None)]  # no data -> cannot sample
        ctx = _ctx(_vessel({"p1": self._panel_with_composite(segs)}))
        assert composite_curve_continuous(ctx, {"tolerance_mm": 0.1}) == CheckOutcome(
            unchecked=(Unchecked("composite curve has an unsampleable segment",
                                 "p1", "g1"),))

    # TestHoleContoursClosed
    def test_hole_without_representation_skipped(self):  # silent
        hole = IrHole2D(id="h1")
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == CheckOutcome()

    # TestHoleNotSplittingPlate
    def test_plate_without_buildable_surface_unchecked(self):
        ctx = self._ctx_with_plate(_rect_hole(2000.0, 100.0), 500.0, 500.0,
                                   surface=None)
        assert hole_not_splitting_plate(ctx, {}) == CheckOutcome(unchecked=(
            Unchecked("no buildable panel surface", "pl1", "gpl1"),))

    # TestSeamTopology
    def test_unsampleable_seam_trace_unchecked(self):
        seam = IrSeam(id="s1", guidref="gs1",
                      trace_line=IrNurbs3D(curve_length=None))
        ctx = self._ctx_with_seam(seam, hole_at=(500.0, 500.0))
        assert seam_topology(ctx, {"tolerance_mm": 5.0}) == CheckOutcome(
            unchecked=(Unchecked("unsampleable trace", "s1", "gs1"),))
```

  - Composite-curve note: `_panel_with_composite` places the curve in `limited_by`. TOP-002 collects it from both `boundary_curves` and `limited_by`, and dedupes by identity, so only one entry is expected. If two arrive, they merge into one per element id anyway, because the reasons are identical.

- [ ] **Step 2: Add the new tests.**

```python
    # TestHoleContoursClosed
    def test_unsampleable_contour_unchecked(self):
        hole = IrHole2D(id="h1", guidref="gh1",
                        contour=IrNurbs3D(curve_length=None))
        cat = IrHoleShapeCatalogue(id="cat", holes={"h1": hole})
        ctx = _ctx(_vessel(catalogue=cat))
        assert hole_contours_closed(ctx, {"tolerance_mm": 0.1}) == CheckOutcome(
            unchecked=(Unchecked("unsampleable contour", "h1", "gh1"),))

    def test_unbuildable_parametric_profile_unchecked(self):
        hole = _circle_hole(100.0)
        cat = IrHoleShapeCatalogue(id="cat", holes={hole.id: hole})
        ctx = _ctx(_vessel(catalogue=cat))
        with patch("ocx_rules.packs.best_practice.checks.topology."
                   "parametric_profile", return_value=None):
            outcome = hole_contours_closed(ctx, {"tolerance_mm": 0.1})
        (u,) = outcome.unchecked
        assert u.reason == "parametric profile could not be built"

    # TestHoleNotSplittingPlate
    def test_no_owning_panel_unchecked(self):
        ctx = self._ctx_with_plate(_circle_hole(100.0), 500.0, 500.0)
        plate = ctx.vessel.plates["pl1"]
        ctx.vessel.plates["pl1"] = dataclasses.replace(
            plate, parent_ref=ParentRef(kind=ParentKind.VESSEL, id="v1"))
        assert hole_not_splitting_plate(ctx, {}).unchecked == (
            Unchecked("no owning panel", "pl1", "gpl1"),)

    def test_no_hole_placeable_unchecked(self):
        ctx = self._ctx_with_plate(IrHole2D(id="h1"), 500.0, 500.0)
        assert hole_not_splitting_plate(ctx, {}).unchecked == (
            Unchecked("1 hole(s) could not be placed", "pl1", "gpl1"),)

    def test_uv_mapping_exception_unchecked(self):
        ctx = self._ctx_with_plate(_circle_hole(100.0), 500.0, 500.0)
        param = ctx.geometry.surface_param(
            ctx.geometry.panel_surface(ctx.vessel.panels["pan1"]))
        with patch.object(type(param), "inverse",
                          side_effect=RuntimeError("boom")):
            outcome = hole_not_splitting_plate(ctx, {})
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("UV mapping failed: boom", "pl1", "gpl1"),))

    # TestSeamTopology
    def test_seamed_panel_unsampleable_plate_contour_unchecked(self):
        ctx = self._ctx_with_seam_and_plate(closed_plate=True)
        ctx.vessel.plates["pl1"] = dataclasses.replace(
            ctx.vessel.plates["pl1"], outer_contour=IrNurbs3D(curve_length=None))
        outcome = seam_topology(ctx, {"tolerance_mm": 5.0})
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("unsampleable outer contour", "pl1", "gpl1"),))
```

  - Add `import dataclasses` to the stdlib imports of the topology test file. It is used by `test_no_owning_panel_unchecked` and the seam test.
  - `GeometryContext.surface_param` is **not** memoized (each call builds a new param), so patch `inverse` on the param *class*, as shown, not on an instance.

- [ ] **Step 3: Run the tests and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_checks_topology.py -q`
  - Expected: FAILs for every adapted test of TOP-001…005; the TOP-008/009 tests are untouched and still pass.

- [ ] **Step 4: Implement.** In `topology.py`, change the import to `from ocx_rules.model import CheckOutcome, Finding, OutcomeCollector`.

  *TOP-001* `panel_limited_by_closed`:
  - Return annotation `-> CheckOutcome`.
  - `findings: list[Finding] = []` → `out = OutcomeCollector("OCX-TOP-001")`.
  - Replace the two skip blocks with:

```python
        if skipped:
            out.unchecked(f"{skipped} unresolved boundary ref(s)", pid,
                          panel.guidref)
            continue
        if not samples:
            out.unchecked("no sampleable boundary", pid, panel.guidref)
            continue
```

  - Leave `if ring is None: continue` as is. It is unreachable once `samples` is non-empty, because `chain_polylines` returns `None` only for empty input.
  - `findings.append(Finding(` → `out.add(Finding(`; `return findings` → `return out.outcome()`.

  *TOP-002* `composite_curve_continuous`:
  - Return annotation `-> CheckOutcome`; `out = OutcomeCollector("OCX-TOP-002")`.
  - Replace the `logger.debug(...)` in the segment loop with
    `out.unchecked("composite curve has an unsampleable segment", owner_id, guid)`.
    Keep `samples = None` and `break`.
  - `findings.append` → `out.add`; `return out.outcome()`.

  *TOP-003* `hole_contours_closed`:
  - Return annotation `-> CheckOutcome`.
  - `return []` (no catalogue) → `return CheckOutcome()`.
  - `findings: list[Finding] = []` → `out = OutcomeCollector("OCX-TOP-003")`.
  - Parametric skip:
    `out.unchecked("parametric profile could not be built", hid, hole.guidref)`, then `continue`.
  - Contour skip: `out.unchecked("unsampleable contour", hid, hole.guidref)`, then `continue`.
  - Keep `if hole.contour is None: continue` silent (no representation means not applicable).
  - Both `findings.append` → `out.add`; `return out.outcome()`.

  *TOP-004* `hole_not_splitting_plate`:
  - Return annotation `-> CheckOutcome`; `out = OutcomeCollector("OCX-TOP-004")`.
  - Replace the skip logs with `out.unchecked(<reason>, pid, plate.guidref)` + `continue`. The reasons are, in order:
    - `"no owning panel"`
    - `"no buildable panel surface"`
    - `"periodic surface, ambiguous UV mapping"`
    - `"unsampleable outer contour"`
    - `f"UV mapping failed: {exc}"`
  - Replace the `if skipped: logger.debug(...)` / `if not holes_3d: continue` pair with:

```python
        if not holes_3d:
            out.unchecked(f"{skipped} hole(s) could not be placed", pid,
                          plate.guidref)
            continue
        if skipped:
            logger.debug("TOP-004: plate {}: {} hole(s) could not be "
                         "placed; skipped", pid, skipped)
```

  - `findings.append` → `out.add`; `return out.outcome()`.

  *TOP-005* helper `_plate_contours_closed`: replace with the version below.

```python
def _plate_contours_closed(context, panel, tol_m: float,
                           out: OutcomeCollector) -> None:
    """OCX-TOP-005 aspect: plates of a seamed panel have closed outer contours."""
    geo = context.geometry
    vessel = context.vessel
    for plate_id in panel.plate_ids:
        plate = vessel.plates.get(plate_id)
        if plate is None or plate.outer_contour is None:
            continue
        pts = geo.sample(plate.outer_contour)
        if pts is None or len(pts) < 3:
            out.unchecked("unsampleable outer contour", plate_id,
                          plate.guidref)
            continue
        gap = float(np.linalg.norm(pts[0] - pts[-1]))
        if gap > tol_m:
            out.add(Finding(
                message=(f"Plate outer contour is not closed: gap "
                         f"{gap * 1000:.2f} mm exceeds "
                         f"{tol_m * 1000:.2f} mm"),
                element_id=plate_id, guid=plate.guidref))
```

  *TOP-005* `seam_topology`:
  - Return annotation `-> CheckOutcome`; `out = OutcomeCollector("OCX-TOP-005")`.
  - `findings += _plate_contours_closed(context, panel, tol_m)` → `_plate_contours_closed(context, panel, tol_m, out)`.
  - **Move** `if not hole_outlines: continue` to just *before* the `seam_samples` loop. This preserves behaviour (seam samples are only used afterwards) and makes an unsampleable seam unchecked only when there are holes to test against.
  - In the seam loop, replace the `logger.debug(...)` with `out.unchecked("unsampleable trace", sid, seam.guidref)`.
  - `findings.append` → `out.add`; `return out.outcome()`.

- [ ] **Step 5: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_checks_topology.py tests/test_rules_checks_properties.py tests/test_rules_best_practice_pack.py -q`
  - Expected: all pass.
  - Then run `uv run ruff check packages/ocx-rules tests/test_rules_checks_topology.py`. Expected: clean.

- [ ] **Step 6: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py tests/test_rules_checks_topology.py
git commit -m "feat(rules): TOP-001..005 report unchecked elements" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Retrofit `topology.py` part 2 (TOP-008, TOP-009)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py` (`surface_normals_and_boundaries` ~386–510, `stiffener_inclinations` ~556–588)
- Test: `tests/test_rules_checks_topology.py`

- [ ] **Step 1: Adapt the existing tests.**
  - Apply the **Mechanical test rewrite** to every direct call of `surface_normals_and_boundaries` and `stiffener_inclinations`.
  - Replace `test_unbuildable_member_skipped` with:

```python
    def test_unbuildable_member_unchecked(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        _coll_member("sb", 1000, 2000, sweep_y=-1.0,
                                     guid="gb", buildable=False))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == CheckOutcome(
            unchecked=(Unchecked("no buildable surface or boundary", "sb", "gb"),))
```

- [ ] **Step 2: Add the new tests.** Append to `TestSurfaceNormalsAndBoundaries`:

```python
    def test_pair_exception_unchecked_on_first_surface(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000, guid="ga"),
                        _coll_member("sb", 1000, 2000))
        with patch("ocx_rules.packs.best_practice.checks.topology."
                   "points_polyline_distances",
                   side_effect=RuntimeError("boom")):
            outcome = surface_normals_and_boundaries(ctx, self.PARAMS)
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("evaluation against sb failed: boom", "sa", "ga"),))

    def test_distant_members_silent(self):
        ctx = _coll_ctx(_coll_member("sa", 0, 1000),
                        _coll_member("sb", 5000, 6000))
        assert surface_normals_and_boundaries(ctx, self.PARAMS) == CheckOutcome()
```

  - If `test_distant_members_not_adjacent` already asserts exactly this after the mechanical rewrite, skip adding `test_distant_members_silent`.

- [ ] **Step 3: Run the tests and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_checks_topology.py -q`
  - Expected: FAILs for the TOP-008/009 tests.

- [ ] **Step 4: Implement.**

  *TOP-008* `surface_normals_and_boundaries`:
  - Return annotation `-> CheckOutcome`; `findings: list[Finding] = []` → `out = OutcomeCollector("OCX-TOP-008")`.
  - Member skip: replace the `logger.debug("TOP-008: member ...")` with
    `out.unchecked("no buildable surface or boundary", surf.id, surf.guidref)`. Keep `continue`.
  - Pair `except` block: replace its `logger.debug(...)` with
    `out.unchecked(f"evaluation against {surf_b.id} failed: {exc}", surf_a.id, surf_a.guidref)`. Keep `continue`.
  - No evaluable samples for a confirmed-adjacent pair (`if not votes:`): replace its `logger.debug(...)` with
    `out.unchecked(f"no evaluable shared boundary samples with {surf_b.id}", surf_a.id, surf_a.guidref)`. Keep `continue`.
  - Leave every other `logger.debug` in this function unchanged: collection < 2 members, point contact and individual per-sample failures (when other samples of the pair succeed) are rule logic per the spec.
  - `findings.append(Finding(` → `out.add(Finding(`; `return findings` → `return out.outcome()`.

  *TOP-009* `stiffener_inclinations`:
  - Return annotation `-> CheckOutcome`; `out = OutcomeCollector("OCX-TOP-009")`.
  - Both `findings.append` → `out.add`; `return out.outcome()`.
  - There are no unchecked sites: `_inclination_positions` already maps unparseable positions to `None`, which is "missing position", not applicable.

  Update the module docstring to: `"""Geometry topology checks (OCX-TOP-001 through 005, 008 and 009).` Then add the line: `Every check returns CheckOutcome (findings + unchecked elements)."""`

- [ ] **Step 5: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_checks_topology.py tests/test_rules_best_practice_pack.py -q`
  - Expected: all pass. Ruff is clean.
  - Also confirm `Finding` is still used in topology.py; it is, via `out.add(Finding(...))`.

- [ ] **Step 6: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/topology.py tests/test_rules_checks_topology.py
git commit -m "feat(rules): TOP-008/009 report unchecked elements" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 8: Retrofit `plausibility.py` (TOP-010/011/012, PROP-005/006)

**Files:**
- Modify: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py`
- Test: `tests/test_rules_checks_plausibility.py`

- [ ] **Step 1: Adapt the existing tests.**
  - Add `import dataclasses` to the stdlib imports.
  - Add `Ref` to the `ocx_model_core.model.ir` import block.
  - Add `from ocx_rules.model import CheckOutcome, Unchecked`, keeping isort order.
  - Apply the **Mechanical test rewrite** to every direct call of `inclination_position_on_trace`, `web_not_in_plate`, `web_near_normal`, `part_cog_within_geometry` and `shared_positions_and_cogs`. That includes the helper returning `(web_not_in_plate(...), web_near_normal(...))`: change it to return `.findings` of each.
  - Existing "skipped" tests (missing position, no inclinations, no panel parent, no COG, far surface) must keep asserting **silent** results with `== CheckOutcome()`.

- [ ] **Step 2: Add the new tests.**

```python
def _ref_only(part):
    """Copy of *part* whose trace is given only by reference."""
    return dataclasses.replace(part, trace=None,
                               trace_refs=[Ref(local_ref="c9")])


class TestUncheckedPlausibility:
    REF_ONLY = Unchecked("trace given only by reference (trace_refs)",
                         "s1", "g-s1")

    def test_top010_ref_only_trace_unchecked(self):
        ctx = _ctx(stiffeners=[_ref_only(_stiffener("s1"))])
        assert inclination_position_on_trace(
            ctx, {"position_tolerance_mm": 50.0}) == CheckOutcome(
                unchecked=(self.REF_ONLY,))

    def test_top010_exception_unchecked(self):
        ctx = _ctx(stiffeners=[_stiffener("s1")])
        with patch("ocx_rules.packs.best_practice.checks.plausibility."
                   "_nearest_on_polyline", side_effect=RuntimeError("boom")):
            outcome = inclination_position_on_trace(
                ctx, {"position_tolerance_mm": 50.0})
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("evaluation failed: boom", "s1", "g-s1"),))

    def test_top011_012_ref_only_trace_unchecked(self):
        ctx = _ctx(panels=[_panel()],
                   stiffeners=[_ref_only(_stiffener("s1"))])
        for check in (web_not_in_plate, web_near_normal):
            assert check(ctx, {}) == CheckOutcome(unchecked=(self.REF_ONLY,))

    def test_top011_missing_panel_unchecked(self):
        ctx = _ctx(stiffeners=[_stiffener("s1", panel="p9")])
        assert web_not_in_plate(ctx, {}).unchecked == (
            Unchecked("owning panel p9 not found", "s1", "g-s1"),)

    def test_top011_no_buildable_surface_unchecked(self):
        ctx = _ctx(panels=[_panel(surfaces=())], stiffeners=[_stiffener("s1")])
        assert web_not_in_plate(ctx, {}).unchecked == (
            Unchecked("no buildable panel surface", "s1", "g-s1"),)

    def test_top011_free_standing_stiffener_silent(self):
        ctx = _ctx(panels=[_panel(surfaces=(_FAR_PLANE,))],
                   stiffeners=[_stiffener("s1")])
        assert web_not_in_plate(ctx, {}) == CheckOutcome()

    def test_prop005_plate_without_outline_unchecked(self):
        plate = dataclasses.replace(_plate("pl1", cog=(500, 500, 0)),
                                    outer_contour=None)
        ctx = _ctx(plates=[plate])
        assert part_cog_within_geometry(ctx, {"margin_mm": 500.0}) == CheckOutcome(
            unchecked=(Unchecked("no outline or trace", "pl1", "g-pl1"),))

    def test_prop005_ref_only_trace_unchecked(self):
        ctx = _ctx(stiffeners=[_ref_only(_stiffener("s1", cog=(500, 0, 0)))])
        assert part_cog_within_geometry(ctx, {"margin_mm": 500.0}).unchecked == (
            self.REF_ONLY,)

    def test_prop005_part_without_cog_silent(self):
        ctx = _ctx(stiffeners=[_ref_only(_stiffener("s1"))])
        assert part_cog_within_geometry(ctx, {"margin_mm": 500.0}) == CheckOutcome()

    def test_prop006_cog_exception_unchecked(self):
        ctx = _ctx(plates=[_plate("pl1", cog=(0, 0, 0))])
        with patch("ocx_rules.packs.best_practice.checks.plausibility._cog_m",
                   side_effect=RuntimeError("boom")):
            outcome = shared_positions_and_cogs(
                ctx, {"tolerance_mm": 1.0, "min_parts": 3})
        assert outcome == CheckOutcome(unchecked=(
            Unchecked("COG evaluation failed: boom", "pl1", "g-pl1"),))
```

  - Check the existing parameter dicts used by the TOP-011/012 tests (`NOT_IN_PLATE`, `NEAR_NORMAL`). If `{}` behaves differently from them, use them instead; the defaults are 80°/30°.
  - `_panel(surfaces=())` builds a panel with `unbounded_geometry=None`, so `_panel_surface_params` returns `[]`.

- [ ] **Step 3: Run the tests and confirm they fail.**
  - Run: `uv run pytest tests/test_rules_checks_plausibility.py -q`
  - Expected: many FAILs.

- [ ] **Step 4: Implement.** In `plausibility.py`:
  - Imports: `from ocx_rules.model import CheckOutcome, Finding, OutcomeCollector, Unchecked`.
  - Add after `_unit_vector`:

```python
def _curve_unusable(part, curve) -> str:
    """Why a part's outline/trace cannot be sampled (unchecked reason)."""
    if curve is None:
        if getattr(part, "trace_refs", None):
            return "trace given only by reference (trace_refs)"
        return "no outline or trace"
    return "unsampleable outline or trace"
```

  - Replace the cache, `_web_angles` and `_compute_web_angles` with:

```python
_WebAngles = tuple[list[tuple[Any, int, float]], tuple[Unchecked, ...]]

_WEB_ANGLES_CACHE: "weakref.WeakKeyDictionary[Any, _WebAngles]" = (
    weakref.WeakKeyDictionary())


def _web_angles(context) -> _WebAngles:
    """Memoized ``_compute_web_angles`` per GeometryContext (TOP-011/012)."""
    geo = context.geometry
    cached = _WEB_ANGLES_CACHE.get(geo)
    if cached is None:
        cached = _compute_web_angles(context)
        _WEB_ANGLES_CACHE[geo] = cached
    return cached


def _compute_web_angles(context) -> _WebAngles:
    """((stiffener, inclination index, web-to-normal angle deg), unchecked).

    Shared by OCX-TOP-011/012. Evaluated at the trace point nearest the
    inclination position (trace start when it has none). Stiffeners without
    inclinations or a panel parent are not applicable; stiffeners farther
    than 50 mm from every panel surface are free-standing (rule logic).
    Missing panels/surfaces, unusable traces and exceptions are unchecked.
    """
    geo = context.geometry
    vessel = context.vessel
    out = OutcomeCollector("OCX-TOP-011/012")
    surface_cache: dict[str, list] = {}
    angles_out: list[tuple[Any, int, float]] = []
    for stiffener in vessel.stiffeners.values():
        parent = stiffener.parent_ref
        if (not stiffener.inclinations or parent is None
                or parent.kind is not ParentKind.PANEL):
            continue
        panel = vessel.panels.get(parent.id)
        if panel is None:
            out.unchecked(f"owning panel {parent.id} not found",
                          stiffener.id, stiffener.guidref)
            continue
        try:
            if panel.id not in surface_cache:
                surface_cache[panel.id] = _panel_surface_params(geo, panel)
            params = surface_cache[panel.id]
            if not params:
                out.unchecked("no buildable panel surface", stiffener.id,
                              stiffener.guidref)
                continue
            poly = geo.sample(stiffener.trace)
            if poly is None or len(poly) == 0:
                out.unchecked(_curve_unusable(stiffener, stiffener.trace),
                              stiffener.id, stiffener.guidref)
                continue
            positions = _inclination_positions(geo, stiffener.inclinations)
            angles: list[tuple[Any, int, float]] = []
            for i, (entry, pos) in enumerate(zip(stiffener.inclinations,
                                                 positions, strict=True)):
                web = _unit_vector(entry.web_direction)
                if web is None:
                    continue
                point = poly[0] if pos is None else _nearest_on_polyline(poly, pos)[0]
                normal = _surface_normal_at(params, point)
                if normal is None:
                    continue
                cos = min(abs(float(web @ normal)), 1.0)
                angles.append((stiffener, i, math.degrees(math.acos(cos))))
            angles_out.extend(angles)
        except Exception as exc:  # noqa: BLE001 — skip stiffener
            out.unchecked(f"evaluation failed: {exc}", stiffener.id,
                          stiffener.guidref)
    return angles_out, out.outcome().unchecked
```

  - Replace `web_not_in_plate` and `web_near_normal` with:

```python
def web_not_in_plate(context, params: dict[str, Any]) -> CheckOutcome:
    """OCX-TOP-011: the web must not lie in the plate plane."""
    max_deg = float(params.get("max_angle_deg", 80.0))
    angles, unchecked = _web_angles(context)
    return CheckOutcome(findings=tuple(
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (lies in the plate plane; limit "
                f"{max_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in angles if angle >= max_deg), unchecked=unchecked)


def web_near_normal(context, params: dict[str, Any]) -> CheckOutcome:
    """OCX-TOP-012: the web should be close to the panel surface normal."""
    warn_deg = float(params.get("warn_angle_deg", 30.0))
    max_deg = float(params.get("max_angle_deg", 80.0))
    angles, unchecked = _web_angles(context)
    return CheckOutcome(findings=tuple(
        Finding(f"Inclination {i}: web direction is {angle:.1f}° from the "
                f"panel surface normal (warning above {warn_deg:.0f}°)",
                element_id=s.id, guid=s.guidref)
        for s, i, angle in angles if warn_deg < angle < max_deg),
        unchecked=unchecked)
```

  - *TOP-010* `inclination_position_on_trace`:
    - Return annotation `-> CheckOutcome`; `findings: list[Finding] = []` → `out = OutcomeCollector("OCX-TOP-010")`.
    - Replace `if poly is None or len(poly) == 0: continue` with:

```python
            if poly is None or len(poly) == 0:
                out.unchecked(_curve_unusable(part, part.trace), part.id,
                              part.guidref)
                continue
```

    - Replace the `except` body's `logger.debug(...)` with `out.unchecked(f"evaluation failed: {exc}", part.id, part.guidref)`.
    - `findings.append` → `out.add` (twice); `return out.outcome()`.

  - *PROP-005* `part_cog_within_geometry`:
    - Return annotation `-> CheckOutcome`; `out = OutcomeCollector("OCX-PROP-005")`.
    - Change the first guard to `if cog is None: continue`. A missing COG is not applicable; a `None` curve is now handled below.
    - Replace `if pts is None or len(pts) == 0: continue` with:

```python
            if pts is None or len(pts) == 0:
                out.unchecked(_curve_unusable(part, curve), part.id,
                              part.guidref)
                continue
```

    - Replace the `except` body's `logger.debug(...)` with `out.unchecked(f"evaluation failed: {exc}", part.id, part.guidref)`.
    - `findings.append` → `out.add` (twice); `return out.outcome()`.

  - *PROP-006* `shared_positions_and_cogs`:
    - Return annotation `-> CheckOutcome`. After the `ValueError` guard add `out = OutcomeCollector("OCX-PROP-006")`.
    - Replace the positions `except` body with `out.unchecked(f"inclination positions failed: {exc}", part.id, part.guidref)`.
    - Replace the COG `except` body with `out.unchecked(f"COG evaluation failed: {exc}", part.id, part.guidref)`.
    - Replace the final `return` with:

```python
    for finding in positions.findings(min_parts) + cogs.findings(min_parts):
        out.add(finding)
    return out.outcome()
```

  - If `logger` is no longer used anywhere in plausibility.py, remove `from loguru import logger`. Ruff F401 will tell you.
  - Update the module docstring with one line at the end: "Checks return CheckOutcome; parts they cannot evaluate (unusable trace, reference-only trace, exceptions) are reported as unchecked."

- [ ] **Step 5: Run the tests and confirm they pass.**
  - Run: `uv run pytest tests/test_rules_checks_plausibility.py tests/test_rules_best_practice_pack.py -q`
  - Expected: all pass.
  - Then run `uv run ruff check packages tests`. Expected: clean.

- [ ] **Step 6: Commit.**

```powershell
git add packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/plausibility.py tests/test_rules_checks_plausibility.py
git commit -m "feat(rules): plausibility checks report unchecked elements" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 9: Documentation

**Files:**
- Modify: `packages/ocx-rules/CHANGELOG.md`, `packages/ocx-model-validator/CHANGELOG.md`, `README.md` (~lines 28–37 and ~158), `docs/superpowers/specs/2026-11-13-unchecked-elements-design.md`

- [ ] **Step 1:** `packages/ocx-rules/CHANGELOG.md`, under `## Unreleased` → `### Added`, add at the top of the list:

```markdown
- Unchecked elements: checks may return `CheckOutcome(findings, unchecked)`;
  `RuleResult.unchecked` lists elements a check could not evaluate (with a
  reason) without changing PASSED/FAILED. `OutcomeCollector` builds outcomes
  inside checks. All 15 geometry-dependent best-practice checks report
  unchecked elements (unsampleable/reference-only traces, missing surfaces,
  thickness or density, caught exceptions, …).
```

- [ ] **Step 2:** `packages/ocx-model-validator/CHANGELOG.md`: insert directly after the `# Changelog — ocx-model-validator` heading:

```markdown
## Unreleased

### Added

- Rule reports show unchecked elements: the JSON sidecar gains a per-result
  `unchecked` list and `summary.unchecked_elements`; the rules report gains
  an `Unchecked` column and an "Unchecked elements" table (capped by
  `--max-findings`). The exit code is unchanged.
```

- [ ] **Step 3:** `README.md`:
  - In the rule-validation bullet (~line 35–37), after the sentence ending in "deferred …", add: "Elements a check cannot evaluate (e.g. reference-only traces, unbuildable surfaces) are listed as *unchecked* in the reports; they never change a rule's status or the exit code."
  - In the tree at ~line 158, change the `model.py` comment to `← RuleSpec, RuleResult, Finding, CheckOutcome, Unchecked, Severity, RuleStatus`.
  - Re-wrap the paragraph to the surrounding width.

- [ ] **Step 4:** Spec: in the `OutcomeCollector` section, replace the `unchecked(element, reason: str)` bullet with:

```markdown
- `unchecked(reason: str, element_id: str | None = None, guid: str | None = None) -> None`
  — mirrors `Finding` (some owners, e.g. TOP-002 composite-curve owners, are
  only known by id/GUID). Logs the reason at debug level, prefixed with the
  collector's `rule_id`. One entry per element id: a repeated call for the
  same id appends the new reason to the existing one, separated by `"; "`,
  unless that exact reason is already present. Entries with
  `element_id=None` are never merged.
```

- [ ] **Step 5: Commit.**

```powershell
git add packages/ocx-rules/CHANGELOG.md packages/ocx-model-validator/CHANGELOG.md README.md docs/superpowers/specs/2026-11-13-unchecked-elements-design.md
git commit -m "docs: unchecked elements in rule results" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 10: Full verification and manual iter0 run

- [ ] **Step 1: Full suite.**
  - Run: `uv run pytest -q`
  - Expected: ≥ 1148 + new tests passed, 42 skipped, 0 failed.
  - Then run `uv run ruff check packages tests`. Expected: `All checks passed!`

- [ ] **Step 2: Manual run on iter0.**

```powershell
$tmp = Join-Path $env:TEMP "uc-iter0"; New-Item -ItemType Directory -Force $tmp | Out-Null
Copy-Item C:\PythonDev\ocx-render\example-models\iter0.3docx $tmp -Force
uv run ocx-validate validate rules (Join-Path $tmp iter0.3docx) --rule OCX-TOP-010 --rule OCX-TOP-011 --rule OCX-TOP-012 --rule OCX-PROP-005 --rule OCX-PROP-006 --max-findings 5
```

  Then summarise the sidecar:

```powershell
@'
import json, os, collections
doc = json.load(open(os.path.join(os.environ["TEMP"], "uc-iter0", "iter0.rules.json")))
print("unchecked_elements:", doc["summary"]["unchecked_elements"])
for r in doc["results"]:
    reasons = collections.Counter(u["reason"] for u in r["unchecked"])
    print(r["rule_id"], r["status"], len(r["findings"]), len(r["unchecked"]),
          dict(reasons.most_common(3)))
'@ | uv run python -
```

  - Expected finding counts, unchanged from master: TOP-010 156, TOP-011 6, TOP-012 6, PROP-005 160, PROP-006 312.
  - Record the unchecked totals and top reasons in the PR description.
  - If the sidecar file name differs, list `$tmp` to find it.
  - Afterwards remove `$tmp`.

- [ ] **Step 3:** If anything differs, debug with superpowers:systematic-debugging before continuing. Otherwise hand off to superpowers:finishing-a-development-branch.
