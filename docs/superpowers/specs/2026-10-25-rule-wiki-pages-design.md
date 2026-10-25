# Rule wiki pages for the best-practice pack — design

**Date:** 2026-10-25
**Status:** approved

## Goal

Produce one markdown documentation page per rule in the `ocx-rules` best-practice
pack, stored in the local ocx-wiki markdown store, to give a full overview of the
rule logic ahead of a review/revision round of the rule set.

## Sources

- Rule catalogues: `packages/ocx-rules/src/ocx_rules/packs/best_practice/rules/*.toml`
  (6 files: `identity`, `references`, `properties`, `topology`, `document`,
  `curves_surfaces`) — 36 rules total.
- Check implementations: `packages/ocx-rules/src/ocx_rules/packs/best_practice/checks/`
  (`identity.py`, `references.py`, `properties.py`, `topology.py`, `document.py`,
  `curves.py`, `geometry_stubs.py`) and the shared `ocx_rules/primitives/` package.
- XML examples: `tests/data/ocx_320_stubs/*.3docx` (OCX 3.2.0 entity stubs).

## Output

- Target folder: `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\`
- **Flat layout:** one file per rule, `rules/<RULE-ID>.md` (e.g. `OCX-ID-002.md`).
- **Index:** `rules/README.md` with one table per category — columns: Rule ID
  (link), Title, Severity, Rule type, Status (implemented / deferred) — plus a
  short header describing the pack and relative links back to the source wiki
  topic folders (e.g. `../guidsidsandnames/original.md`).
- Nothing else in the ocx-wiki store or the ocx-platform repo is modified.

## Page template

Every rule page follows this fixed structure:

```markdown
# <RULE-ID> — <Title>

| Field | Value |
|---|---|
| Rule ID | <id> |
| Title | <title> |
| Category | <category> |
| Severity | <severity> |
| Rule type | primitive: <name> — or — custom check |
| Source wiki page | <source> |
| Requires | <requires list> |
| Implementation | <module/function or primitive module> |

## Description
Verbal description: the TOML description expanded with intent from the
source wiki page.

## Check logic (pseudo code)
Implementation-faithful pseudo code derived from the actual check function
or primitive, including TOML parameters (xpath, key, normalize, ...).

## Flow
Mermaid flowchart of the check algorithm (every rule page gets one).
Optional extra visual where helpful — e.g. a mermaid ER/graph diagram for
reference and topology rules.

## Example
### Compliant
Annotated .3docx XML fragment taken from tests/data/ocx_320_stubs, trimmed
to the minimal relevant fragment, with XML comments pointing at the
attributes/elements the rule inspects.
### Violating
Hand-crafted variant of the same fragment with one deliberate defect,
marked with an `<!-- VIOLATION: ... -->` comment.
```

## Authoring approach

Category-parallel authoring: six batches, one per TOML catalogue, each run as
an independent subagent. Each batch receives:

- its TOML file,
- the matching `checks/*.py` module (plus `geometry_stubs.py` where referenced),
- the shared `primitives/` package (read-only reference),
- the relevant `ocx_320_stubs/*.3docx` files,
- the page template above.

Pseudo-code fidelity: describe the real algorithm as implemented. For geometry
rules whose checks delegate to `ocx-geometry` services, write pseudo code at
the check-function level and name the geometry services called.

Deferred rules: OCX-TOP-006 and OCX-TOP-007 (compartment rules, stub
implementations in `geometry_stubs.py`) get pages too, marked
**Status: deferred — stub implementation**.

Stub selection: pick the stub whose root entity matches the rule target
(e.g. identity rules → `panel.3docx` / vessel-level stubs).

## Error handling

If a check function cannot be located, or no suitable 3.2.0 stub exists for the
rule's target entity, the page is still written with an explicit `> ⚠ note`
naming the gap — never invented content. These notes double as review findings
for the upcoming rule-revision round.

## Verification

After all batches complete, a consolidation pass checks:

1. Page count equals rule count in the TOMLs (36 pages + `README.md`).
2. Every page contains all template sections, at least one mermaid block, and
   both example variants (or an explicit gap note).
3. Mermaid syntax validates (via `mermaid-cli` if available, else spot-check).
4. All index links resolve to existing files.
5. Pseudo code spot-checked for faithfulness against 3–4 randomly chosen check
   functions.

## Boundaries

- Writes only to `C:\PythonDev\ocx-wiki\out\wiki-writer\rules\`.
- No changes to ocx-platform source, tests, or existing wiki topic folders.
- The ocx-wiki store is outside this git repository; only this design document
  is committed to ocx-platform.
