# Unchecked elements in rule results — design

**Status:** approved 2026-11-13
**Packages:** `ocx-rules`, `ocx-model-validator`
**Origin:** Sourcery review of PR #15 ("Skipped parts appear clean",
"Referenced traces are skipped").

## Problem

Geometry-dependent checks in the `best_practice` pack silently drop elements
they cannot evaluate: per-element exceptions are caught and logged at debug
level, and unusable geometry (unsampleable contour, unbuildable surface,
reference-only trace, …) is skipped with `continue`. When no violations remain
the rule reports PASSED, so a user cannot tell that part of the model was never
examined.

## Goals

- Every rule result carries the elements its check could not evaluate, with a
  reason.
- Reports (JSON sidecar, HTML/table) show them.
- No change to rule status semantics or the CLI exit code.

## Non-goals

- Resolving `trace_refs` or otherwise making more elements checkable.
- Retrofitting content (non-geometry) checks and primitives; they keep
  returning plain lists and report no unchecked elements.
- A new `RuleStatus`.

## Decisions

| Question | Decision |
|---|---|
| Outcome when elements are unchecked | Status stays PASSED/FAILED (from findings only); unchecked elements are recorded on the result. |
| Exit-code impact | None. Unchecked elements are informational. |
| What counts as unchecked | Caught exceptions **and** unusable/missing evaluation input (see Classification). |
| Rollout | Mechanism + all 15 implemented geometry-dependent checks. |
| Mechanism | Structured return value `CheckOutcome` (approach A). |

## Data model (`ocx_rules.model`)

```python
@dataclass(frozen=True)
class Unchecked:
    """An element a check could not evaluate."""
    reason: str
    element_id: str | None = None
    guid: str | None = None


@dataclass(frozen=True)
class CheckOutcome:
    """Result of one check: violations plus elements it could not evaluate."""
    findings: tuple[Finding, ...] = ()
    unchecked: tuple[Unchecked, ...] = ()
```

`RuleResult` gains `unchecked: tuple[Unchecked, ...] = ()`.

### `OutcomeCollector` (`ocx_rules.model`)

Mutable helper used inside checks:

- `add(finding: Finding) -> None` — append a finding.
- `unchecked(reason: str, element_id: str | None = None, guid: str | None = None) -> None`
  — mirrors `Finding` (some owners, e.g. TOP-002 composite-curve owners, are
  only known by id/GUID). Logs the reason at debug level, prefixed with the
  collector's `rule_id`. One entry per element id: a repeated call for the
  same id appends the new reason to the existing one, separated by `"; "`,
  unless that exact reason is already present. Entries with
  `element_id=None` are never merged.
- `outcome() -> CheckOutcome` — findings and unchecked in insertion order.

Constructed as `OutcomeCollector("OCX-TOP-010")`.

## Runner (`RuleManager._run_one`)

- A check may return `CheckOutcome` or any iterable of `Finding`; an iterable
  is wrapped as `CheckOutcome(findings=tuple(it))`.
- Status: FAILED if `findings` is non-empty, else PASSED — unchanged.
- `RuleResult.unchecked` is copied from the outcome for PASSED/FAILED.
  SKIPPED, CRASHED and NOT_IMPLEMENTED results have `unchecked == ()`.

## Classification

- **Not applicable (silent):** the element has nothing the rule verifies.
  Examples: plate without declared dry weight (PROP-001), panel without
  declared mass properties (PROP-002), panel without `limited_by` (TOP-001),
  plate without holes (TOP-004), member with fewer than two inclinations
  (TOP-009), part without inclinations (TOP-010…012), stiffener without a
  panel parent (TOP-011/012), part without moulded COG (PROP-005/006),
  missing inclination position (TOP-010).
- **Unchecked:** the element has something the rule verifies, but the check
  could not evaluate it. Examples: caught exception; no thickness or material
  density; no owning panel; no buildable panel surface; periodic surface
  (ambiguous UV); unsampleable contour/trace; UV mapping or area evaluation
  failed; degenerate computed area; profile build failed; unresolved
  `limited_by` refs; trace given only by reference (`trace is None` with
  non-empty `trace_refs`); TOP-008 member without buildable surface/boundary,
  and a surface pair whose evaluation raised (reported on the first surface,
  reason names the second).
- **Rule logic (silent):** geometric non-cases that are part of the rule's
  definition, e.g. TOP-008 pairs whose boxes do not overlap or that touch only
  at a point; TOP-011/012 stiffeners farther than 50 mm from every panel
  surface; per-sample normal/probe failures inside TOP-008 when other samples
  for the pair succeed.

Reason text reuses the wording of today's `logger.debug` messages.

## Check retrofit

Checks returning `CheckOutcome` (15): TOP-001, 002, 003, 004, 005, 008, 009,
010, 011, 012; PROP-001, 002, 003, 005, 006 — in `checks/topology.py`,
`checks/properties.py`, `checks/plausibility.py`.

- Each builds one `OutcomeCollector`, replaces skip-with-debug-log sites
  classified as unchecked by `collector.unchecked(...)`, and returns
  `collector.outcome()`.
- `_web_angles` returns `(angles, unchecked)` and remains memoized per
  `GeometryContext`; TOP-011 and TOP-012 both report the same unchecked list.
- `GeometryContext` is unchanged (still returns `None` on failure).

## Reporting (`ocx-model-validator`)

- **JSON sidecar** (`rules_json.py`): each result entry gains
  `"unchecked": [{"element_id", "guid", "reason"}]` (uncapped);
  `summary` gains `"unchecked_elements": <int>` (sum over results).
  Existing keys unchanged.
- **Report** (`rules_report.py`): Rules table gains an `Unchecked` column
  (count, empty when 0). New table **Unchecked elements** with columns
  Rule, Element, GUID, Reason — present only when non-empty, capped by
  `max_findings`, with its own truncation note.
- CLI exit code (`cli.py`) unchanged.

## Testing

- `ocx_rules`: runner accepts list and `CheckOutcome`; unchecked entries do not
  change PASSED/FAILED; CRASHED/SKIPPED carry none. `OutcomeCollector` merges
  reasons per element and keeps `None`-element entries separate.
- Each retrofitted check: at least one test per unchecked category it
  produces; one test that a not-applicable element stays silent.
- Existing check tests that compare the return value to `[]` switch to
  `.findings == ()` via a small test helper.
- Reports: JSON keys and summary count; report column, table, truncation note.
- Manual: `ocx-validate validate rules` on `ocx-render/example-models/iter0.3docx`
  — finding counts for TOP-010/011/012, PROP-005/006 unchanged (156/6/6/160/312);
  record unchecked totals.

## Docs

- `packages/ocx-rules/CHANGELOG.md` and `packages/ocx-model-validator/CHANGELOG.md`
  (Unreleased → Added).
- `README.md`: one sentence defining "unchecked" in the rule-validation section.

## Delivery

Branch `feat/unchecked-elements` from `master` (after PR #15).
