# ocx-diagnose: rule-based advice — design

## Goal
Help inexperienced users understand *why* a surface meshes badly and *what to do*:
add evidence-based findings (root cause, steps to improve meshing, steps to improve
the OCX source NURBS) to the diagnose HTML report and JSON. Deterministic, offline,
rule-based (no LLM).

## Placement
- Panel tab: ranked "Findings" box at the top.
- Each worst-plate section: "Diagnosis" box (cause, *Improve meshing* steps, *Improve OCX source* steps).
- Front-page summary table: finding count per panel (by severity).
- JSON: `findings` list per panel and per plate.

## Components
- `ocx_diagnose/probes.py` — cheap source-NURBS probes per panel, bbox-prefiltered
  so a 2884-member panel stays fast:
  - coincident/duplicate members (surface samples at ~zero mutual distance),
  - degenerate members (tiny area, collapsed edges),
  - seam gaps between adjacent members (chart boundary edges after stitch),
  - open or self-touching trim contours.
  Each returns evidence: member ids, counts, distances.
- `ocx_diagnose/advice.py` — `Finding(id, severity, scope, status, evidence, cause,
  mesh_steps, source_steps)`; `status` is `likely` (metrics only) or `confirmed`
  (probe proved it). A registry of pure rule functions over plate/panel results and
  probe output. Every finding cites the metric values that triggered it.
  Initial rules: duplicate surfaces (high overlap_faces + coincident members);
  trim does not close/snap too large; flipped faces / high scale spread;
  deviation above tolerance (lower `--tolerance`); non-manifold/boundary edges
  (seam mismatch/T-junction); degenerate members.
- `report.py` — renders the boxes; `analyse.py` — runs probes once per panel (timed,
  DEBUG log), attaches findings to results.

## Data flow
render + sink -> existing metrics -> probes -> rules -> findings -> HTML/JSON.

## Error handling
A failing probe or rule is logged and skipped; it never breaks the report.

## Testing
- Unit tests per rule with synthetic metrics/probe inputs.
- Probe tests on small synthetic members (duplicate plane, degenerate patch).
- Report test: boxes present in HTML, `findings` in JSON.
- Real-model check on cadhu: total runtime stays near the current ~110 s.

## Out of scope
LLM narrative, automatic repair of the OCX source.
