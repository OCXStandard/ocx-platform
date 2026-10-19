# TOP-001 LimitedBy Contour Diagnostic — Design

Date: 2026-10-19
Status: approved

## Problem

OCX-TOP-001 ("Panel LimitedBy closes") reports only the worst gap per panel
(e.g. `tr05_tc14a_cadhu.3docx` panels `_hullgroup2_layer-02_0panel` /
`_1panel` with 4 939 mm and 2 663 mm gaps). To fix an exporter, the user
needs to *see* the unresolved contour: which segments exist, their order,
where the declared contour bounds are, and where the ring fails to close.

## Goal

A CLI command that renders, per failing panel, an interactive 3D plot of the
LimitedBy contour segments with per-segment colors, document-order sequence
labels, ContourBounds markers (Start/Mid/End), gap annotations, and the
optional Panel OuterContour as a reference curve.

## Decisions (user-confirmed)

- Command lives in the existing **`ocx-diagnose`** CLI (plotly + typer
  infrastructure already present).
- Output is **interactive plotly 3D HTML** only (no static images).
- Default scope is **failing panels**; a repeatable `--panel ID` option
  forces specific panels regardless of pass/fail.
- Sequence labels use the **document order** of the `LimitedBy` children
  (what the exporter author needs), not the chained closure order.
- **Gaps are highlighted**: red dashed connector between unmatched endpoints
  annotated with the distance in mm.
- **Unresolvable segments are still plotted** from their ContourBounds
  points (dashed grey Start→Mid→End polyline with markers and label).

## CLI

```
ocx-diagnose top-001 MODEL.3docx
    [--panel ID]...        # repeatable; force specific panels
    [--tolerance MM]       # closure tolerance, default 1.0 (rule default)
    [--report PATH]        # default: <model>.top001.html
    [--log-level LEVEL]
```

Behavior:
1. Parse/build the model (reuse `_load_vessel` as the existing `diagnose`
   command does).
2. Evaluate closure per panel with the same primitives as the rule:
   `GeometryContext.boundary_curves(panel)` → `sample` →
   `chain_polylines` (from `ocx_geometry.measure`).
3. Select panels: those whose worst gap exceeds the tolerance, or whose
   LimitedBy has unresolvable refs; `--panel` overrides selection.
4. Write one self-contained HTML report: a summary table (panel id, segment
   count, unresolved count, worst gap in mm) followed by one 3D figure per
   panel.

Exit codes: `0` report written, all plotted panels close within tolerance;
`1` report written, at least one panel does not close; `2` cannot
parse/build the model; `3` cannot write the output file.

## Core IR additions (`ocx-model-core`)

Both OCX 3.1.0 and 3.2.0 define `ContourBounds` (`ContourStart`,
`ContourEnd`, optional `ContourMidPoint`) on LimitedBy reference elements;
the builder already reads `contour_bounds.contour_mid_point`.

- `IrLimitedByRef`: add `contour_start: IrPoint3D | None = None` and
  `contour_end: IrPoint3D | None = None`, populated in `OcxV3Builder`
  beside the existing `contour_mid_point` extraction (same `getattr`
  chain; degrades to `None`).
- `IrPanel`: add `outer_contours: list[IrCurve3D] = []` — the schema
  allows `OuterContour` 0..unbounded on `Panel_T`; build each entry with
  the existing `_build_contour` helper.

No behavior change for existing consumers (frozen dataclasses, defaulted
fields, getattr-based raw access).

## Diagnosis assembly (`ocx_diagnose/top001.py`)

Per selected panel build a `PanelTop001Diagnosis`:

- `segments: list[SegmentDiag]` in **document order** of
  `panel.limited_by`, each with: 1-based `seq`, `ref_type`, target id
  (`local_ref`/`guidref`), sampled `(N, 3)` polyline in metres (or `None`
  when unresolvable), and the ContourBounds points (`start`, `mid`,
  `end`, each optional).
- `gaps: list[GapDiag]`: run `chain_polylines` over the resolvable
  samples; for each junction gap above tolerance record the two unmatched
  endpoint coordinates and the distance.
- `outer_contours: list[np.ndarray]`: sampled panel OuterContour
  polylines, when present.
- `worst_gap_m`, `unresolved_count` summary fields.

All per-segment sampling is wrapped lean (log at debug, mark the segment
unresolvable); a single bad curve never aborts the panel or the report.

## Figure (`ocx_diagnose/figures.py` addition)

One plotly 3D scene per panel, equal aspect (`aspectmode="data"`):

- Resolvable segment: solid `Scatter3d` line, distinct color from a cyclic
  qualitative palette, legend name `"{seq}: {ref_type} {target}"`, text
  annotation `{seq}` at the polyline midpoint.
- ContourBounds markers in the segment's color where provided:
  ContourStart ▲ (`diamond` fallback per plotly symbol set), ContourMidPoint
  ● (`circle`), ContourEnd ■ (`square`).
- Unresolvable segment: dashed grey line through Start→(Mid)→End with the
  same markers and sequence label.
- Panel OuterContour(s): black semi-transparent line, legend name
  "OuterContour".
- Gap: red dashed connector between the two unmatched endpoints with a
  text annotation `"gap {mm:.1f} mm"`.

Coordinates are plotted in metres (IR/geometry convention); only gap
annotations use mm, matching the rule's reporting.

## Testing

Shared `tests/` suite, run from the repo root:

- Builder tests: `contour_start`/`contour_end` and panel `outer_contours`
  built from inline stub objects (per `test_builders.py` convention),
  including absence → `None`/`[]`.
- Assembly tests on synthetic IR: document-order sequencing, gap detection
  above/below tolerance, unresolvable-segment handling, OuterContour
  sampling.
- Figure/report smoke test: build the HTML for a synthetic failing panel
  (plotly offline, no browser), assert the file is written and contains
  the expected trace names.

## Out of scope

- No changes to the OCX-TOP-001 rule itself or its findings.
- No static image export (PNG/SVG).
- No diagnostics for other TOP rules (the report layout should not preclude
  adding them later, but nothing is built for them now).
