# Best-Practice Rule Wiki Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write one markdown documentation page per rule (36 rules) of the ocx-rules best-practice pack into `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\`, plus an index, so the rule logic can be reviewed.

**Architecture:** Pure documentation authoring — no source-code changes. Six category batches (one per TOML catalogue), each independently authorable, followed by an index page and a consolidation/verification pass. Pseudo code and flow diagrams are derived from the *actual* check implementations in `checks/*.py` and `primitives/`.

**Tech Stack:** Markdown + mermaid. Sources: TOML rule catalogues, Python check modules, `.3docx` XML stubs. Verification via PowerShell text checks.

**Spec:** `docs/superpowers/specs/2026-10-25-rule-wiki-pages-design.md`

---

## Shared conventions (read before any task)

**Source roots** (all under `C:\PythonDev\ocx-platform`):
- TOMLs: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\`
- Checks: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\`
- Primitives: `packages\ocx-rules\src\ocx_rules\primitives\` (`content.py`, `references.py`, `geometry.py`)
- Geometry context (for topology/curves rules): `packages\ocx-rules\src\ocx_rules\geometry_context.py`
- Stubs: `tests\data\ocx_320_stubs\*.3docx` and `tests\data\unitsml_stubs\*.xml`

**Output root:** `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\` — flat, one `<RULE-ID>.md` per rule.

**Page template** (every rule page MUST contain exactly these sections, in this order):

```markdown
# <RULE-ID> — <Title>

| Field | Value |
|---|---|
| Rule ID | <id> |
| Title | <title from TOML> |
| Category | <category> |
| Severity | <severity> |
| Rule type | primitive: `<name>` — or — custom check |
| Source wiki page | <source, as relative link: [<source>](../<source>/original.md)> |
| Requires | <requires list from TOML> |
| Implementation | `<checks module>.py:<function>` or `primitives/<module>.py:<function>` |

## Description

<Verbal description: the TOML description expanded with intent. If the source
wiki page exists under C:\PythonDev\ocx-wiki\out\wiki-writer\<source>\original.md,
read it and incorporate the intent; keep to 3–8 sentences.>

## Check logic (pseudo code)

<Implementation-faithful pseudo code in a fenced ``` block. Derive from the
actual Python function. Include concrete TOML params (xpath, key, normalize,
tolerances) as literals. For geometry-backed checks, pseudo-code at the
check-function level and name the GeometryContext services called.>

## Flow

```mermaid
flowchart TD
    <nodes/edges describing the algorithm: inputs, iteration, decision points,
     finding emission, PASS/FAIL outcomes>
```

<Optional extra visual where helpful (e.g. a second mermaid graph showing
entity/reference relationships for REF and TOP rules).>

## Example

### Compliant

```xml
<!-- Source: tests/data/ocx_320_stubs/<file>.3docx (trimmed) -->
<fragment with XML comments pointing at the attributes/elements the rule inspects>
```

### Violating

```xml
<same fragment with ONE deliberate defect>
<!-- VIOLATION: <one-line explanation of why this fails the rule> -->
```
```

**Hard rules for every page:**
- Pseudo code describes the real algorithm — read the Python before writing. Never invent behavior.
- Mermaid flowchart on **every** page. Node labels must not contain unescaped `"`, `(`/`)` inside `[]` brackets (use `["..."]` quoting) — keep labels simple so mermaid parses.
- Stub fragments are trimmed to the minimal relevant XML; keep original attribute values. No `xmlns` additions needed (stubs are namespace-free by design; keep `ocx:` prefixes as they appear in the stub files).
- If a check function cannot be located or no suitable stub exists: still write the page and add `> ⚠ note: <gap>` in the affected section. Never fabricate.
- Deferred rules (OCX-TOP-006/007 in `geometry_stubs.py`) get a line directly under the H1: `**Status: deferred — stub implementation**` and the pseudo code documents the stub behavior (always returns NOT_APPLICABLE/skip) plus the *intended* logic from the TOML description, clearly separated under a sub-heading `### Intended logic (not yet implemented)`.

**Per-task verification command** (run after writing a batch; `$ids` = the batch's rule IDs):

```powershell
$dir='C:\PythonDev\ocx-wiki\out\wiki-writer\rules'
foreach ($id in $ids) {
  $p = Join-Path $dir "$id.md"
  if (!(Test-Path $p)) { "MISSING $id"; continue }
  $t = Get-Content $p -Raw
  foreach ($h in '## Description','## Check logic (pseudo code)','## Flow','## Example','### Compliant','### Violating','```mermaid') {
    if ($t -notlike "*$h*") { "FAIL ${id}: missing $h" } }
}
'done'
```
Expected output: just `done` (no MISSING/FAIL lines).

---

### Task 1: Create output folder and template file

**Files:**
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\` (directory)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\_template.md`

- [ ] **Step 1: Create the directory**

```powershell
New-Item -ItemType Directory -Force 'C:\PythonDev\ocx-wiki\out\wiki-writer\rules' | Out-Null
Test-Path 'C:\PythonDev\ocx-wiki\out\wiki-writer\rules'
```
Expected: `True`

- [ ] **Step 2: Write `_template.md`** containing the page-template markdown block from "Shared conventions" above, verbatim (the content between the outer ``` fences). This is the working reference for all batches; it is deleted in Task 9.

- [ ] **Step 3: Verify**

```powershell
Get-Content 'C:\PythonDev\ocx-wiki\out\wiki-writer\rules\_template.md' | Select-Object -First 3
```
Expected: the `# <RULE-ID> — <Title>` heading line appears.

---

### Task 2: Identity rule pages (5 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\identity.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\identity.py`
- Read: `packages\ocx-rules\src\ocx_rules\primitives\content.py` (the `unique` primitive)
- Read: `C:\PythonDev\ocx-wiki\out\wiki-writer\guidsidsandnames\original.md` (source intent)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-ID-001.md` … `OCX-ID-005.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-ID-001 | Structural objects carry GUIDRef and id | error | custom `identity.py:entitybase_has_guid_and_id` | `panel.3docx` |
| OCX-ID-002 | GUIDs are unique | error | primitive `unique` (xpath `//*[@ocx:GUIDRef and not(@ocx:refType) and not(@localRef)]`, key `@ocx:GUIDRef`, normalize `guid`, exclude_tag_suffix `Ref`) | `panel.3docx`, `vessel.3docx` |
| OCX-ID-003 | Local ids are unique | error | primitive `unique` (xpath `//*[@id]`, key `@id`) | `panel.3docx` |
| OCX-ID-004 | Geometry objects carry a local id | error | custom `identity.py:idbase_has_id` | `nurbs3d.3docx`, `line3d.3docx` |
| OCX-ID-005 | Names are not identifiers | info | custom `identity.py:names_not_identifiers` | `panel.3docx` |

- [ ] **Step 1: Read all source files listed above** (TOML, checks module incl. helper `_tagged_elements`, `unique` primitive, source wiki page, suggested stubs).
- [ ] **Step 2: Write the five pages** following `_template.md`, honoring every Hard rule. For the two `unique` primitive rules, the pseudo code documents the primitive algorithm *with the rule's concrete TOML parameters inlined*.
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-ID-001','OCX-ID-002','OCX-ID-003','OCX-ID-004','OCX-ID-005'`. Expected: `done` only.

---

### Task 3: Document rule pages (5 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\document.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\document.py`
- Read: source wiki pages per TOML `source` field (under `C:\PythonDev\ocx-wiki\out\wiki-writer\<source>\original.md`; e.g. `schema_root_element`, `units`)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-DOC-001.md` … `OCX-DOC-005.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-DOC-001 | schemaLocation names the namespace/XSD tuple | error | custom `document.py:schema_location_tuple` | `ocxxml.3docx` |
| OCX-DOC-002 | Root declarations present | error | custom `document.py:root_declarations` | `ocxxml.3docx`, `header.3docx` |
| OCX-DOC-003 | Units fully declared | error | custom `document.py:unit_definitions` | `tests\data\unitsml_stubs\unitsml.xml`, `unit.xml` |
| OCX-DOC-004 | Unit and dimension references resolve | error | custom `document.py:unit_refs_resolve` | `unitsml_stubs\unit.xml`, `dimension.xml` |
| OCX-DOC-005 | Enumerated root units preferred | warning | custom `document.py:enumerated_root_units` | `unitsml_stubs\enumeratedrootunit.xml`, `rootunits.xml` |

- [ ] **Step 1: Read all source files listed above** (incl. helper `_units`).
- [ ] **Step 2: Write the five pages** per `_template.md` and the Hard rules. For DOC-003/004/005 the examples are UnitsML fragments — state clearly in the example caption that they come from `tests/data/unitsml_stubs/`.
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-DOC-001','OCX-DOC-002','OCX-DOC-003','OCX-DOC-004','OCX-DOC-005'`. Expected: `done` only.

---

### Task 4: Reference rule pages (8 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\references.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\references.py`
- Read: `packages\ocx-rules\src\ocx_rules\primitives\references.py` (`ref_resolves`) and `primitives\content.py` (`cardinality`)
- Read: `packages\ocx-rules\src\ocx_rules\xml_index.py` (reference resolution underpinning `ref_resolves`)
- Read: source wiki pages per TOML `source` field (e.g. `structural_connectivity`, `slots`, `end_cuts`)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-REF-001.md` … `OCX-REF-008.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-REF-001 | All references resolve | error | primitive `ref_resolves` | `plateref.3docx`, `materialref.3docx` |
| OCX-REF-002 | Panel contains at least one plate | error | primitive `cardinality` | `panel.3docx`, `composedof.3docx` |
| OCX-REF-003 | Stiffener has one end configuration per end | error | custom `references.py:stiffener_end_configurations` | `stiffener.3docx`, `endcutend1.3docx`, `endcutend2.3docx` |
| OCX-REF-004 | Slot carries at most two LugPlateRef | error | custom `references.py:slot_lug_plate_refs` | `slotparameters.3docx`, `lugplateref.3docx` |
| OCX-REF-005 | Connectivity is explicit | error | custom `references.py:explicit_connectivity` | `cutby.3docx`, `splitby.3docx`, `penetration.3docx` |
| OCX-REF-006 | Exactly one root coordinate system | error | primitive `cardinality` | `coordinatesystem.3docx`, `vessel.3docx` |
| OCX-REF-007 | Panel represented as OccurrenceGroup | error | custom `references.py:panel_as_occurrence_group` | `occurrencegroup.3docx`, `occurrence.3docx` |
| OCX-REF-008 | Single hole representation | warning | custom `references.py:hole_single_representation` | `holeref.3docx`, `hole2d.3docx`, `rectangularhole.3docx` |

- [ ] **Step 1: Read all source files listed above.** For the two primitive rules, read the exact TOML params (xpath/cardinality bounds) and inline them in the pseudo code.
- [ ] **Step 2: Write the eight pages** per `_template.md` and the Hard rules. For REF rules, add the optional second mermaid diagram (entity/reference graph) where it clarifies the relationship being checked (recommended for REF-001, REF-005, REF-007).
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-REF-001','OCX-REF-002','OCX-REF-003','OCX-REF-004','OCX-REF-005','OCX-REF-006','OCX-REF-007','OCX-REF-008'`. Expected: `done` only.

---

### Task 5: Property rule pages (4 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\properties.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\properties.py`
- Read: `packages\ocx-rules\src\ocx_rules\geometry_context.py` (services used by weight/CoG checks)
- Read: source wiki pages per TOML `source` field (e.g. `physical_properties_weight`, `renewal_thickness`)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-PROP-001.md` … `OCX-PROP-004.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-PROP-001 | Plate weight consistent | warning | custom `properties.py:plate_weight_consistent` | `plate.3docx`, `massproperties.3docx`, `thickness.3docx` |
| OCX-PROP-002 | Panel weight/CoG consistent | warning | custom `properties.py:panel_weight_cog_consistent` | `panel.3docx`, `massproperties.3docx`, `centerofgravity.3docx` |
| OCX-PROP-003 | Profile parameters close | error | custom `properties.py:profile_closed_section` | `tbar.3docx`, `sectionoutershape.3docx`, `barsection.3docx` |
| OCX-PROP-004 | Renewal thickness on instance | error | custom `properties.py:renewal_thickness_on_instance` | `occurrence.3docx`, `thickness.3docx` |

- [ ] **Step 1: Read all source files listed above** (incl. helpers `_declared_weight_kg`, `_declared_cog`, `_cog_m`, `_open_uv`, `_any_instance_renewal`). Note each tolerance/threshold constant used and reproduce it literally in the pseudo code.
- [ ] **Step 2: Write the four pages** per `_template.md` and the Hard rules. PROP-001/002 are geometry-backed: name the GeometryContext services called.
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-PROP-001','OCX-PROP-002','OCX-PROP-003','OCX-PROP-004'`. Expected: `done` only.

---

### Task 6: Topology rule pages (9 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\topology.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\topology.py`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\geometry_stubs.py` (OCX-TOP-006/007)
- Read: `packages\ocx-rules\src\ocx_rules\geometry_context.py`
- Read: source wiki pages per TOML `source` field (e.g. `topology`, `seamsandopenings`, `surfacecollectionnormals`, `inclination`)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-TOP-001.md` … `OCX-TOP-009.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-TOP-001 | Panel LimitedBy closes | error | custom `topology.py:panel_limited_by_closed` | `panel.3docx`, `limitedby.3docx` |
| OCX-TOP-002 | Composite curves continuous | error | custom `topology.py:composite_curve_continuous` | `compositecurve3d.3docx` |
| OCX-TOP-003 | Hole contours closed | error | custom `topology.py:hole_contours_closed` | `hole2dcontour.3docx`, `outercontour.3docx` |
| OCX-TOP-004 | Holes do not split plates | error | custom `topology.py:hole_not_splitting_plate` | `hole2d.3docx`, `holeref.3docx`, `plate.3docx` |
| OCX-TOP-005 | Seam topology valid | error | custom `topology.py:seam_topology` | `seam.3docx`, `seamref.3docx` |
| OCX-TOP-006 | Compartment boundaries closed | error | **deferred stub** `geometry_stubs.py` (`compartment_closure`) | `compartment.3docx`, `compartmentface.3docx` |
| OCX-TOP-007 | Compartments disjoint | warning | **deferred stub** `geometry_stubs.py` (`compartments_disjoint`) | `compartment.3docx`, `physicalspace.3docx` |
| OCX-TOP-008 | Surface normals and boundaries consistent | error | custom `topology.py:surface_normals_and_boundaries` | `nurbssurface.3docx`, `surfacecollection.3docx`, `normal.3docx` |
| OCX-TOP-009 | Stiffener inclinations consistent | error | custom `topology.py:stiffener_inclinations` | `stiffener.3docx`, `inclination.3docx` |

- [ ] **Step 1: Read all source files listed above**, including the module-private helpers (`_panel_boundary_samples`, `_composite_curves`, `_resolve_catalogue_hole`, `_open_ring`, `_placed_hole_outlines`, `_normal_at`, `_probe_into`, `_inclination_positions`, `_direction_flip`) — the pseudo code must reflect what they actually do, including tolerance values.
- [ ] **Step 2: Write the nine pages** per `_template.md` and the Hard rules. TOP-006/007 follow the deferred-rule convention (Status line + `### Intended logic (not yet implemented)` sub-heading). Geometry-backed checks name the GeometryContext services used. Add the optional relationship diagram where it helps (recommended for TOP-001, TOP-005).
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-TOP-001','OCX-TOP-002','OCX-TOP-003','OCX-TOP-004','OCX-TOP-005','OCX-TOP-006','OCX-TOP-007','OCX-TOP-008','OCX-TOP-009'`. Expected: `done` only.

---

### Task 7: Curves & surfaces rule pages (5 pages)

**Files:**
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\rules\curves_surfaces.toml`
- Read: `packages\ocx-rules\src\ocx_rules\packs\best_practice\checks\curves.py`
- Read: source wiki pages per TOML `source` field (e.g. `nurbs`, `pararmetricholesandholeshapecatalogue`)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\OCX-GEO-001.md` … `OCX-GEO-005.md`

| Rule | Title | Severity | Type / Implementation | Suggested stubs |
|---|---|---|---|---|
| OCX-GEO-001 | NURBS control-point count | error | custom `curves.py:nurbs_control_points` | `nurbs3d.3docx`, `controlptlist.3docx`, `nurbsproperties.3docx` |
| OCX-GEO-002 | NURBS knots non-decreasing | error | custom `curves.py:nurbs_knots_non_decreasing` | `knotvector.3docx`, `nurbs3d.3docx` |
| OCX-GEO-003 | NURBS knot multiplicity | error | custom `curves.py:nurbs_knot_multiplicity` | `nurbs3d.3docx`, `uknotvector.3docx`, `vknotvector.3docx` |
| OCX-GEO-004 | Closed polylines well-formed | error | custom `curves.py:polyline_closed` | `polyline3d.3docx` |
| OCX-GEO-005 | Catalogue hole contours planar and centered | warning | custom `curves.py:catalogue_holes_planar` | `holeshapecatalogue.3docx`, `hole2dcontour.3docx` |

- [ ] **Step 1: Read all source files listed above**, including helpers (`_int_of`, `_floats_of`, `_unit_scales_mm`, `_nurbs_nodes`, `_knot_vectors`). Reproduce the NURBS validity relations (e.g. control-point/knot/degree count equation) exactly as implemented.
- [ ] **Step 2: Write the five pages** per `_template.md` and the Hard rules.
- [ ] **Step 3: Run the per-task verification command** with `$ids = 'OCX-GEO-001','OCX-GEO-002','OCX-GEO-003','OCX-GEO-004','OCX-GEO-005'`. Expected: `done` only.

---

### Task 8: Index page

**Files:**
- Read: all six TOMLs (for authoritative id/title/severity/type per rule)
- Create: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\README.md`

- [ ] **Step 1: Write `README.md`** with:
  1. H1 `# OCX best-practice rule catalogue` and a short header (3–5 sentences): what the pack is, where it lives in ocx-platform (`packages/ocx-rules/src/ocx_rules/packs/best_practice/`), and that each rule links to a detail page.
  2. One `## <Category>` section per category in this order: Identity, Document, References, Properties, Topology, Curves & surfaces. Each contains a table:

```markdown
| Rule ID | Title | Severity | Rule type | Status |
|---|---|---|---|---|
| [OCX-ID-001](OCX-ID-001.md) | Structural objects carry GUIDRef and id | error | custom | implemented |
```

  Status is `implemented` for all rules except OCX-TOP-006 and OCX-TOP-007, which are `deferred`.
  3. A closing `## Sources` section linking the source wiki topic folders used by the pack, as relative links of the form `[guidsidsandnames](../guidsidsandnames/original.md)` (one per distinct TOML `source` value).

- [ ] **Step 2: Verify link integrity**

```powershell
$dir='C:\PythonDev\ocx-wiki\out\wiki-writer\rules'
$links = Select-String -Path (Join-Path $dir 'README.md') -Pattern '\]\(([^)]+\.md)\)' -AllMatches |
  ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
foreach ($l in $links) {
  $p = Join-Path $dir $l
  if (!(Test-Path $p)) { "BROKEN: $l" } }
'links ok'
```
Expected: `links ok` only.

---

### Task 9: Consolidation and final verification

**Files:**
- Delete: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\_template.md`
- Read/verify: all 36 pages + `README.md`

- [ ] **Step 1: Delete the working template**

```powershell
Remove-Item 'C:\PythonDev\ocx-wiki\out\wiki-writer\rules\_template.md'
```

- [ ] **Step 2: Count check** — 36 rule pages + README = 37 files:

```powershell
(Get-ChildItem 'C:\PythonDev\ocx-wiki\out\wiki-writer\rules' -Filter *.md).Count
```
Expected: `37`

- [ ] **Step 3: Full section/mermaid/example check across all pages**

```powershell
$dir='C:\PythonDev\ocx-wiki\out\wiki-writer\rules'
Get-ChildItem $dir -Filter 'OCX-*.md' | ForEach-Object {
  $t = Get-Content $_.FullName -Raw
  foreach ($h in '## Description','## Check logic (pseudo code)','## Flow','## Example','### Compliant','### Violating','```mermaid','VIOLATION') {
    if ($t -notlike "*$h*") { "FAIL $($_.Name): missing $h" } } }
'all pages ok'
```
Expected: `all pages ok` only.

- [ ] **Step 4: Mermaid syntax validation.** If `mmdc` (mermaid-cli) is available (`Get-Command mmdc`), extract each ```mermaid block to a temp `.mmd` file and run `mmdc -i <file> -o NUL`; report any parse failures. If `mmdc` is unavailable, visually spot-check the mermaid blocks of 5 pages (one per category) for balanced brackets and valid `flowchart TD` syntax, and note in the task report that CLI validation was skipped.

- [ ] **Step 5: Faithfulness spot-check.** Pick 4 rules at random — one primitive-based (e.g. OCX-ID-002) and three custom (e.g. OCX-REF-003, OCX-TOP-002, OCX-GEO-001) — and re-read the Python implementation side-by-side with the page's pseudo code. Fix any divergence (missing early-exit, wrong tolerance, wrong xpath) directly in the page.

- [ ] **Step 6: Gap report.** List every `⚠ note` emitted across pages in the final summary to the user — these are review findings for the rule-revision round.

**Note on commits:** the output lives outside the ocx-platform repository. If `C:\PythonDev\ocx-wiki` is itself a git repository, commit the new `rules/` folder there with message `docs: add best-practice rule pages (36 rules + index)`; otherwise no commit is required.
