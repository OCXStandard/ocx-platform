# ocx-mcp Carve-out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the `ocx-mcp` MCP server out of `ocx-model-validator` into a new public repository `OCXStandard/ocx-mcp`, released alongside platform v0.7.0.

**Architecture:** The platform drops the `ocx_model_validator.mcp` package, its script and the `mcp` dependency, and promotes the private compartment helper to the public `ocx_model_validator.compartments` module. The new `ocx-mcp` repo is a single uv package that consumes `ocx-model-core` and `ocx-model-validator` through uv git sources pinned to the v0.7.0 commit (same pattern as `ocx-render`).

**Tech Stack:** Python ≥ 3.12, uv (workspace + git sources), hatchling, FastMCP (`mcp>=1.0,<2`), pytest, ruff, pre-commit, GitHub CLI (`gh`).

**Spec:** `docs/superpowers/specs/2026-11-16-ocx-mcp-carve-out-design.md`

---

## Conventions for the executor

- Windows + PowerShell. Use backslash paths in shell commands; `&&` only chains native commands; use `;` otherwise.
- Always use `uv` (never pip directly). Run all platform commands from `C:\PythonDev\ocx-platform`, all new-repo commands from `C:\PythonDev\ocx-mcp`.
- The platform working tree contains **untracked files that are not yours** (`NAPA_VLCC.md`, `docs/*.docx`, `examples/`, several `models/...` files). Never `git add -A` / `git add .`; stage explicit paths or use `git add -u`.
- Running `ocx-mcp` server processes (started by other Copilot sessions) lock `C:\PythonDev\ocx-platform\.venv\Scripts\ocx-mcp.exe`, which makes `uv sync` fail. If `uv sync` reports *"The process cannot access the file … ocx-mcp.exe"*, ask the user to close those sessions; do not kill processes yourself. As a fallback for running tests, use `uv run --no-sync pytest` after `uv pip install --no-deps -e packages/<pkg>` for each changed package.
- Commit trailer on every commit: `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`

## File map

**Platform (`C:\PythonDev\ocx-platform`)**

| File | Change |
|---|---|
| `tests/test_package_pins.py` | Create — guards inter-package pins against current versions |
| `packages/ocx-geometry/pyproject.toml` | core pin → `>=0.6,<0.7`; version 0.3.1 |
| `packages/ocx-rules/pyproject.toml` | core pin → `>=0.6,<0.7` |
| `packages/ocx-integrity/pyproject.toml` | core pin → `>=0.6,<0.7`; version 0.2.1 |
| `packages/ocx-model-validator/pyproject.toml` | core pin; drop `mcp` dep + `ocx-mcp` script; description; version 0.7.0 |
| `packages/ocx-model-validator/src/ocx_model_validator/__init__.py` | `__version__ = "0.7.0"` |
| `packages/ocx-model-validator/src/ocx_model_validator/compartments.py` | Create (git mv from `reporting/generators/_compartment_data.py`) |
| `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/compartments.py` | Import from new module |
| `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/model_extent.py` | Import from new module |
| `tests/test_compartments_module.py` | Create — public import path |
| `packages/ocx-model-validator/src/ocx_model_validator/mcp/` | Delete |
| `tests/test_mcp_server.py` | Delete |
| `packaging/validator.spec` | Drop `ocx_model_validator.mcp` exclude |
| `README.md`, `packages/ocx-model-validator/README.md`, `.github/copilot-instructions.md` | Remove MCP server docs, point to new repo |
| `CHANGELOG.md`, `packages/*/CHANGELOG.md` | 0.7.0 entries |
| `uv.lock` | Regenerated |

**New repo (`C:\PythonDev\ocx-mcp`)**

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, git sources, ruff/pytest config |
| `src/ocx_mcp/__init__.py` | Package docstring + `__version__` |
| `src/ocx_mcp/state.py` | Process-wide loaded vessel |
| `src/ocx_mcp/server.py` | FastMCP server, 5 tools, `main()` |
| `tests/__init__.py` | Makes `tests.fixtures` importable |
| `tests/fixtures.py` | Synthetic vessel + writeback model/report builders |
| `tests/test_server.py` | Tool-level tests |
| `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.gitignore` | Tooling |
| `README.md`, `CHANGELOG.md` | Docs |

**Local config (outside both repos)**

| File | Change |
|---|---|
| `C:\Users\oca\.copilot\installed-plugins\_direct\hull-weight-optimizer\mcp.json` | `ocx` server → new repo |

---

## Part A — Platform v0.7.0

### Task 1: Feature branch

- [ ] **Step 1: Create the branch from an up-to-date master**

```powershell
git fetch -q origin; git switch master; git pull --ff-only; git switch -c feature/carve-out-mcp
```

Expected: `Switched to a new branch 'feature/carve-out-mcp'`.

- [ ] **Step 2: Baseline test run**

```powershell
uv run pytest -q -p no:cacheprovider 2>&1 | Select-Object -Last 2
```

Expected: `1254 passed, 42 skipped, 93 deselected` (counts may differ slightly if master moved; must be 0 failed).

---

### Task 2: Inter-package version pins

**Files:**
- Create: `tests/test_package_pins.py`
- Modify: `packages/ocx-geometry/pyproject.toml`, `packages/ocx-rules/pyproject.toml`, `packages/ocx-integrity/pyproject.toml`, `packages/ocx-model-validator/pyproject.toml` (the `ocx-model-core>=0.5,<0.6` line in each)

- [ ] **Step 1: Write the failing test**

Create `tests/test_package_pins.py`:

```python
"""Inter-package pins must admit the current version of each workspace member."""
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

PACKAGES = Path(__file__).resolve().parents[1] / "packages"


def _projects() -> dict[str, dict]:
    return {
        p.parent.name: tomllib.loads(p.read_text(encoding="utf-8"))["project"]
        for p in sorted(PACKAGES.glob("*/pyproject.toml"))
    }


def _pins():
    projects = _projects()
    versions = {proj["name"]: proj["version"] for proj in projects.values()}
    for proj in projects.values():
        for dep in proj.get("dependencies", []):
            req = Requirement(dep)
            if req.name in versions:
                yield proj["name"], req, versions[req.name]


@pytest.mark.parametrize("owner,req,current", list(_pins()),
                         ids=lambda v: str(v) if isinstance(v, str) else None)
def test_workspace_pin_admits_current_version(owner, req, current):
    assert req.specifier.contains(current, prereleases=True), (
        f"{owner} pins {req} but {req.name} is {current}")
```

- [ ] **Step 2: Run it to verify it fails**

```powershell
uv run pytest tests/test_package_pins.py -q -p no:cacheprovider 2>&1 | Select-Object -Last 8
```

Expected: 4 FAILED (`ocx-geometry`, `ocx-rules`, `ocx-integrity`, `ocx-model-validator` each with `pins ocx-model-core<0.6,>=0.5 but ocx-model-core is 0.6.0`), the rest passed.

- [ ] **Step 3: Fix the pins**

In each of the four `pyproject.toml` files replace the line

```toml
    "ocx-model-core>=0.5,<0.6",
```

with

```toml
    "ocx-model-core>=0.6,<0.7",
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
uv run pytest tests/test_package_pins.py -q -p no:cacheprovider 2>&1 | Select-Object -Last 2
```

Expected: all passed, 0 failed.

- [ ] **Step 5: Relock and commit**

```powershell
uv lock -q; uv lock --check
git add tests/test_package_pins.py packages/ocx-geometry/pyproject.toml packages/ocx-rules/pyproject.toml packages/ocx-integrity/pyproject.toml packages/ocx-model-validator/pyproject.toml uv.lock
git commit -q -m "fix: pin ocx-model-core >=0.6,<0.7 across workspace packages

Adds a test that every inter-package pin admits the member's current version.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Public `ocx_model_validator.compartments` module

**Files:**
- Create: `tests/test_compartments_module.py`
- Move: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/_compartment_data.py` → `packages/ocx-model-validator/src/ocx_model_validator/compartments.py`
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/compartments.py:19`
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/model_extent.py:13`

- [ ] **Step 1: Write the failing test**

Create `tests/test_compartments_module.py`:

```python
"""build_compartments_block is public API (consumed by the external ocx-mcp server)."""
from ocx_model_validator.compartments import build_compartments_block

from tests.section_fixtures import make_synthetic_vessel


def test_build_compartments_block_rows_and_warnings():
    rows, warnings = build_compartments_block(make_synthetic_vessel())
    assert isinstance(warnings, list)
    by_name = {r["name"]: r for r in rows}
    assert {"Ballast Tank", "Unclassified Space"} <= set(by_name)
```

- [ ] **Step 2: Run it to verify it fails**

```powershell
uv run pytest tests/test_compartments_module.py -q -p no:cacheprovider 2>&1 | Select-Object -Last 4
```

Expected: ERROR — `ModuleNotFoundError: No module named 'ocx_model_validator.compartments'`.

- [ ] **Step 3: Move the module and update the two importers**

```powershell
git mv packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/_compartment_data.py packages/ocx-model-validator/src/ocx_model_validator/compartments.py
```

In `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/compartments.py` replace

```python
from ocx_model_validator.reporting.generators._compartment_data import build_compartments_block
```

with

```python
from ocx_model_validator.compartments import build_compartments_block
```

In `packages/ocx-model-validator/src/ocx_model_validator/reporting/generators/model_extent.py` replace

```python
from ocx_model_validator.reporting.generators._compartment_data import _curve_points_mm
```

with

```python
from ocx_model_validator.compartments import _curve_points_mm
```

(The MCP server still imports the old path; it is deleted in Task 4, so do not update it.)

- [ ] **Step 4: Run the new test and the report tests**

```powershell
uv run pytest tests/test_compartments_module.py tests/test_reporting_compartment_cargo.py tests/test_model_extent.py -q -p no:cacheprovider 2>&1 | Select-Object -Last 3
```

Expected: 0 failed. (Rows carry keys `id, name, tank_type, cog_mm, volume_m3, extent_mm, …`; the synthetic vessel yields `Ballast Tank` and `Unclassified Space`.)

- [ ] **Step 5: Commit**

```powershell
git add -u; git add tests/test_compartments_module.py
git commit -q -m "refactor(validator): make compartment data a public module

reporting.generators._compartment_data -> ocx_model_validator.compartments.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Remove the MCP server from the platform

**Files:**
- Delete: `packages/ocx-model-validator/src/ocx_model_validator/mcp/` (`__init__.py`, `server.py`, `state.py`)
- Delete: `tests/test_mcp_server.py`
- Modify: `packages/ocx-model-validator/pyproject.toml`
- Modify: `packaging/validator.spec:36`

- [ ] **Step 1: Save a copy of the server files for Part B**

```powershell
$keep = "$env:TEMP\ocx-mcp-src"; New-Item -ItemType Directory -Force $keep | Out-Null
Copy-Item packages\ocx-model-validator\src\ocx_model_validator\mcp\server.py, packages\ocx-model-validator\src\ocx_model_validator\mcp\state.py, tests\test_mcp_server.py $keep
git rev-parse HEAD | Set-Content "$keep\SOURCE_SHA"
Get-ChildItem $keep | Select-Object Name
```

Expected: `server.py`, `state.py`, `test_mcp_server.py`, `SOURCE_SHA`. (Part B contains the full file contents anyway; this copy is a cross-check.)

- [ ] **Step 2: Delete code and test**

```powershell
git rm -q -r packages/ocx-model-validator/src/ocx_model_validator/mcp tests/test_mcp_server.py
```

- [ ] **Step 3: Edit `packages/ocx-model-validator/pyproject.toml`**

Replace

```toml
description = "Validate OCX .3docx ship model files — schema validation, model reports, CLI and MCP server"
```

with

```toml
description = "Validate OCX .3docx ship model files — schema validation, model reports and CLI"
```

Delete the dependency line

```toml
    "mcp>=1.0,<2",
```

Delete the script line

```toml
ocx-mcp = "ocx_model_validator.mcp.server:main"
```

- [ ] **Step 4: Edit `packaging/validator.spec`**

Replace

```python
    excludes=["ocx_model_validator.mcp"],
```

with

```python
    excludes=[],
```

- [ ] **Step 5: Verify nothing references the server**

```powershell
git --no-pager grep -n -E "ocx_model_validator\.mcp|_compartment_data|from mcp|import mcp" -- "*.py" "*.toml" "*.spec"
```

Expected: no output.

- [ ] **Step 6: Relock and confirm `mcp` left the validator's tree**

```powershell
uv lock -q; uv tree --package ocx-model-validator --depth 1 2>&1 | Select-String -Pattern "^\S|mcp"
```

Expected: the root line `ocx-model-validator v0.6.0` and no line containing `mcp`.

- [ ] **Step 7: Full suite**

```powershell
uv sync -q --dev; uv run pytest -q -p no:cacheprovider 2>&1 | Select-Object -Last 2
```

Expected: 0 failed (7 fewer tests than baseline from the deleted file, plus the new pin/compartment tests). If `uv sync` fails on the locked `ocx-mcp.exe`, see *Conventions*.

- [ ] **Step 8: Commit**

```powershell
git add -u
git commit -q -m "refactor!: move the ocx-mcp server out of ocx-model-validator

The MCP server now lives in OCXStandard/ocx-mcp. Removes the
ocx_model_validator.mcp package, the ocx-mcp script and the mcp dependency.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md` (lines ~24-25, ~98-125, ~176, ~184-186, ~335)
- Modify: `packages/ocx-model-validator/README.md:5`
- Modify: `.github/copilot-instructions.md` (lines ~72, ~78, ~86)

- [ ] **Step 1: Root `README.md` — feature bullet**

Replace

```markdown
- **MCP server** `ocx-mcp` exposing model loading, info, frame table,
  compartments and scantling write-back to LLM clients
```

with

```markdown
- **MCP server**: `ocx-mcp` (model loading, info, frame table, compartments,
  scantling write-back for LLM clients) lives in its own repository,
  [OCXStandard/ocx-mcp](https://github.com/OCXStandard/ocx-mcp).
```

- [ ] **Step 2: Root `README.md` — remove the "MCP server" section**

Delete everything from the line `### MCP server` up to and including the last tools-table row

```markdown
| `apply_scantlings` | Apply an `nh-optimisation/1` report to a `.3docx`: plate thicknesses plus stiffener `BarSection`s, written to a new file |
```

and the blank line after it, leaving the following `---` / `## Project structure` intact.

- [ ] **Step 3: Root `README.md` — layout tree and pipeline diagram**

Replace

```text
│   └── ocx-model-validator/       ← validation, reports, CLI, MCP server
```

with

```text
│   └── ocx-model-validator/       ← validation, reports, CLI
```

Replace this block (7 lines)

```text
│           ├── reporting/
│           │   ├── model.py       ← Report, ReportSection, ReportTable
│           │   ├── generators/    ← frame table, compartments, catalogues, BOM, …
│           │   └── renderers/     ← rich, markdown and html renderers
│           └── mcp/
│               ├── state.py       ← session state (loaded vessel)
│               └── server.py      ← FastMCP "ocx-mcp" server (5 tools)
```

with

```text
│           ├── compartments.py    ← compartment rows (tank type, COG, volume, extent)
│           └── reporting/
│               ├── model.py       ← Report, ReportSection, ReportTable
│               ├── generators/    ← frame table, compartments, catalogues, BOM, …
│               └── renderers/     ← rich, markdown and html renderers
```

Replace

```text
validator CLI / ocx-mcp MCP server
```

with

```text
validator CLI
```

- [ ] **Step 4: `packages/ocx-model-validator/README.md`**

Replace

```markdown
BOM), the `validator` / `ocx-validate` CLI and the `ocx-mcp` MCP server.
```

with

```markdown
BOM) and the `validator` / `ocx-validate` CLI. The `ocx-mcp` MCP server
lives in [OCXStandard/ocx-mcp](https://github.com/OCXStandard/ocx-mcp).
```

- [ ] **Step 5: `.github/copilot-instructions.md`**

Replace `│   └── ocx-model-validator/    ← reports, CLI, MCP server` with
`│   └── ocx-model-validator/    ← reports, CLI`.

Replace

```text
│           ├── reporting/       ← generators/ + renderers/ (rich, md, html)
│           └── mcp/             ← FastMCP "ocx-mcp" server + session state
```

with

```text
│           ├── compartments.py  ← compartment rows (public; used by ocx-mcp)
│           └── reporting/       ← generators/ + renderers/ (rich, md, html)
```

Replace `` `ocx_model_core.*`; reporting/CLI/MCP code under `ocx_model_validator.*`; `` with
`` `ocx_model_core.*`; reporting/CLI code under `ocx_model_validator.*`; ``.

At the end of that same "Import rule" paragraph, after
`No tessellation or rendering code belongs in this repo.`, append:
` The MCP server lives in OCXStandard/ocx-mcp and must not be added back here.`

Also in the "Project layout" intro, after the sentence ending
`must not be added back here.` add:
`The ocx-mcp MCP server likewise lives in OCXStandard/ocx-mcp.`

- [ ] **Step 6: Verify**

```powershell
git --no-pager grep -n -i -E "mcp" -- README.md packages/ocx-model-validator/README.md .github/copilot-instructions.md
```

Expected: only lines pointing to `OCXStandard/ocx-mcp`.

- [ ] **Step 7: Commit**

```powershell
git add README.md packages/ocx-model-validator/README.md .github/copilot-instructions.md
git commit -q -m "docs: point MCP server docs to OCXStandard/ocx-mcp

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 6: Versions and changelogs

**Files:**
- Modify: `packages/ocx-model-validator/pyproject.toml` (`version = "0.6.0"` → `"0.7.0"`)
- Modify: `packages/ocx-model-validator/src/ocx_model_validator/__init__.py:19`
- Modify: `packages/ocx-geometry/pyproject.toml` (`0.3.0` → `0.3.1`)
- Modify: `packages/ocx-integrity/pyproject.toml` (`0.2.0` → `0.2.1`)
- Modify: `CHANGELOG.md`, `packages/ocx-model-validator/CHANGELOG.md`, `packages/ocx-geometry/CHANGELOG.md`, `packages/ocx-integrity/CHANGELOG.md`, `packages/ocx-rules/CHANGELOG.md`

`ocx-model-core` (no change) and `ocx-rules` (has unreleased feature work; stays 0.1.0) are not bumped.

- [ ] **Step 1: Bump versions**

```powershell
@'
import pathlib as P
def sub(path, old, new):
    p = P.Path(path); t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (path, old)
    p.write_text(t.replace(old, new), encoding="utf-8")
sub("packages/ocx-model-validator/pyproject.toml", 'version = "0.6.0"', 'version = "0.7.0"')
sub("packages/ocx-model-validator/src/ocx_model_validator/__init__.py", '__version__ = "0.6.0"', '__version__ = "0.7.0"')
sub("packages/ocx-geometry/pyproject.toml", 'version = "0.3.0"', 'version = "0.3.1"')
sub("packages/ocx-integrity/pyproject.toml", 'version = "0.2.0"', 'version = "0.2.1"')
'@ | uv run --no-sync python -
```

Expected: no output, exit 0.

- [ ] **Step 2: Validator changelog** — insert directly below `# Changelog — ocx-model-validator` (above `## 0.6.0 — 2026-11-16`):

```markdown
## 0.7.0 — 2026-11-16

### Removed (breaking)

- The `ocx-mcp` MCP server (`ocx_model_validator.mcp`, the `ocx-mcp`
  script and the `mcp` dependency). It now lives in
  [OCXStandard/ocx-mcp](https://github.com/OCXStandard/ocx-mcp) with the
  same five tools.

### Changed

- Compartment data extraction is public:
  `ocx_model_validator.compartments.build_compartments_block` (was the
  private `reporting.generators._compartment_data`; no alias).
- Requires `ocx-model-core>=0.6,<0.7`.

```

- [ ] **Step 3: Geometry and integrity changelogs** — insert below each title line:

`packages/ocx-geometry/CHANGELOG.md`:

```markdown
## 0.3.1 — 2026-11-16

### Changed

- Requires `ocx-model-core>=0.6,<0.7` (metadata only).

```

`packages/ocx-integrity/CHANGELOG.md`:

```markdown
## 0.2.1 — 2026-11-16

- Requires `ocx-model-core>=0.6,<0.7` (metadata only).

```

- [ ] **Step 4: Rules changelog** — in `packages/ocx-rules/CHANGELOG.md`, directly below `## Unreleased`, insert:

```markdown

### Changed

- Requires `ocx-model-core>=0.6,<0.7`.
```

- [ ] **Step 5: Workspace changelog** — insert directly above `## 0.6.0 — 2026-11-16` in `CHANGELOG.md`:

```markdown
## 0.7.0 — 2026-11-16

### Removed (breaking)

- `ocx-model-validator`: the `ocx-mcp` MCP server moved to its own
  repository, [OCXStandard/ocx-mcp](https://github.com/OCXStandard/ocx-mcp).
  MCP client configs must launch it from that repository.

### Changed

- `ocx-model-validator`: `ocx_model_validator.compartments` is public.
- All packages require `ocx-model-core>=0.6,<0.7` (stale `<0.6` pins
  fixed); a test now guards inter-package pins.

```

- [ ] **Step 6: Relock, full suite, lint**

```powershell
uv lock -q; uv lock --check; uv sync -q --dev; uv run pytest -q -p no:cacheprovider 2>&1 | Select-Object -Last 2; uvx pre-commit run --all-files 2>&1 | Select-Object -Last 6
```

Expected: lock check clean, 0 failed, pre-commit all `Passed`. (`uv sync` lock-file problem → see *Conventions*.)

- [ ] **Step 7: Commit**

```powershell
git add -u
git commit -q -m "Release 0.7.0: ocx-mcp moved to its own repository

ocx-model-validator 0.7.0, ocx-geometry 0.3.1, ocx-integrity 0.2.1.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 7: Merge, tag, push

- [ ] **Step 1: Merge into master**

```powershell
git switch master; git pull --ff-only; git merge --no-ff feature/carve-out-mcp -m "Merge branch 'feature/carve-out-mcp': ocx-mcp moved to its own repository (0.7.0)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

- [ ] **Step 2: Re-run the suite on master**

```powershell
uv run pytest -q -p no:cacheprovider 2>&1 | Select-Object -Last 2
```

Expected: 0 failed.

- [ ] **Step 3: Tag and push**

```powershell
git tag -a v0.7.0 -m "v0.7.0: ocx-mcp moved to OCXStandard/ocx-mcp"; git push origin master v0.7.0; git branch -d feature/carve-out-mcp
git rev-parse "v0.7.0^{commit}"
```

Record the printed SHA — it is `<PLATFORM_SHA>` in Part B. (The `Publish to PyPI` workflow also runs on the tag; it already failed for v0.6.0 and is out of scope — don't investigate it.)

---

## Part B — New repository `OCXStandard/ocx-mcp`

All commands run in `C:\PythonDev\ocx-mcp` unless stated otherwise. Replace `<PLATFORM_SHA>` everywhere with the SHA from Task 7 Step 3.

### Task 8: Create and scaffold the repository

**Files:** Create `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`, `src/ocx_mcp/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create the GitHub repo and clone it**

```powershell
gh repo create OCXStandard/ocx-mcp --public --description "MCP server exposing OCX .3docx ship models (load, info, frame table, compartments, scantling write-back) to LLM clients"
git clone https://github.com/OCXStandard/ocx-mcp.git C:\PythonDev\ocx-mcp
```

Expected: `✓ Created repository OCXStandard/ocx-mcp on GitHub` and a clone of an empty repo (git warns *"You appear to have cloned an empty repository"* — that's fine).

- [ ] **Step 2: `pyproject.toml`**

```toml
[project]
name = "ocx-mcp"
version = "0.1.0"
description = "MCP server exposing OCX .3docx ship models to LLM clients"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0,<2",
    "loguru>=0.7",
    "ocx-model-core>=0.6,<0.7",
    "ocx-model-validator>=0.7,<0.8",
]

[project.scripts]
ocx-mcp = "ocx_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ocx_mcp"]

# ocx-platform packages, pinned to one commit. To upgrade, change both rev
# values and run `uv lock`.
[tool.uv.sources]
ocx-model-core = { git = "https://github.com/OCXStandard/ocx-platform", subdirectory = "packages/ocx-model-core", rev = "<PLATFORM_SHA>" }
ocx-model-validator = { git = "https://github.com/OCXStandard/ocx-platform", subdirectory = "packages/ocx-model-validator", rev = "<PLATFORM_SHA>" }

[dependency-groups]
dev = [
    "pytest>=9.0",
    "pytest-cov>=7.0",
    "pre-commit>=4.0",
    "ruff>=0.14",
]

[tool.ruff]
line-length = 100
# ocx_mcp (src/) and tests (.) are first-party for import sorting
src = ["src", "."]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F", "I"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"
pythonpath = ["."]
```

- [ ] **Step 3: `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
.python-version
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.idea/
.vscode/
.DS_Store
*.log
.env
.env.*
```

- [ ] **Step 4: `.pre-commit-config.yaml`** (same hooks as the platform)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-added-large-files
        args: [--maxkb=2048]
      - id: check-merge-conflict
      - id: check-toml
      - id: check-yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.3
    hooks:
      - id: ruff-check
```

- [ ] **Step 5: Package and test package markers**

`src/ocx_mcp/__init__.py`:

```python
"""ocx-mcp: MCP server exposing OCX .3docx ship models to LLM clients."""

__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

- [ ] **Step 6: Resolve dependencies from git**

```powershell
uv lock; uv sync --dev
```

Expected: `uv lock` resolves `ocx-model-core v0.6.0`, `ocx-model-validator v0.7.0`, `ocx-geometry v0.3.1`, `ocx-rules v0.1.0` from `git+https://github.com/OCXStandard/ocx-platform…#<PLATFORM_SHA>`. This proves the platform resolves outside its workspace. Confirm:

```powershell
Select-String -Path uv.lock -Pattern '^name = "ocx' | ForEach-Object Line
uv run python -c "from ocx_model_validator.compartments import build_compartments_block; print('ok')"
```

Expected: the four `ocx-*` names plus `ocx` and `ocx-mcp`; then `ok`.

---

### Task 9: Test fixtures and failing server tests

**Files:** Create `tests/fixtures.py`, `tests/test_server.py`

- [ ] **Step 1: `tests/fixtures.py`** — test-only copies of the platform fixtures

```python
"""Test fixtures copied from ocx-platform (tests/section_fixtures.py, tests/test_writeback.py)."""
from __future__ import annotations

from ocx_model_core.model.ir.arrangement import IrCompartment
from ocx_model_core.model.ir.base import (
    IrCog,
    IrMassProperties,
    ParentKind,
    ParentRef,
    Quantity,
    Ref,
)
from ocx_model_core.model.ir.catalogues import IrMaterial
from ocx_model_core.model.ir.geometry import (
    IrCoordinateSystem,
    IrLine3D,
    IrPoint3D,
    IrPolyLine3D,
    IrRefPlane,
)
from ocx_model_core.model.ir.sections import IrBulbFlatSection
from ocx_model_core.model.ir.structural import IrPanel, IrPlate, IrStiffener, IrVessel

NS = "https://3docx.org/fileadmin//ocx_schema//V300//OCX_Schema.xsd"


def q(value: float, unit: str) -> Quantity:
    return Quantity(value, unit)


def p(x: float, y: float, z: float, unit: str = "Um") -> IrPoint3D:
    return IrPoint3D(x=x, y=y, z=z, unit=unit)


def line(y: float, z: float, start_x: float = 0.0, end_x: float = 10.0) -> IrLine3D:
    return IrLine3D(curve_length=None, start=p(start_x, y, z), end=p(end_x, y, z))


def rectangle(y1: float, y2: float, z: float) -> IrPolyLine3D:
    return IrPolyLine3D(
        curve_length=None,
        vertices=[p(4.0, y1, z), p(6.0, y1, z), p(6.0, y2, z), p(4.0, y2, z)],
        is_closed=True,
    )


def parent(panel_id: str) -> ParentRef:
    return ParentRef(ParentKind.PANEL, panel_id)


def make_synthetic_vessel() -> IrVessel:
    vessel = IrVessel(id="vessel-1")
    vessel.coordinate_systems["global"] = IrCoordinateSystem(
        id="global",
        is_global=True,
        x_ref_plane_ids=["fr0", "fr5", "fr10"],
    )
    vessel.ref_planes["fr0"] = IrRefPlane(id="fr0", name="X0", location=q(0.0, "Um"))
    vessel.ref_planes["fr5"] = IrRefPlane(id="fr5", name="X5", location=q(5.0, "Um"))
    vessel.ref_planes["fr10"] = IrRefPlane(id="fr10", name="X10", location=q(10.0, "Um"))
    vessel.materials["mat315"] = IrMaterial(
        id="mat315", name="NV-NS", yield_stress=q(315e6, "UPa"))
    vessel.sections["hp300"] = IrBulbFlatSection(
        id="hp300", name="HP 300x11",
        height=q(300.0, "Umm"), web_thickness=q(11.0, "Umm"))
    vessel.panels["panel-a"] = IrPanel(
        id="panel-a", name="Panel A", guidref="panel-a-guid",
        plate_ids=["plate-a1", "plate-a2"],
        stiffener_ids=["stiff-a1", "stiff-a2", "stiff-a-no-cross"],
    )
    vessel.panels["panel-b"] = IrPanel(id="panel-b", name="Panel B", stiffener_ids=["stiff-b1"])
    vessel.plates["plate-a1"] = IrPlate(
        id="plate-a1", parent_ref=parent("panel-a"), name="Plate A1",
        guidref="plate-a1-guid", material_ref=Ref("mat315"), thickness=q(12.5, "Umm"),
        mass_properties=IrMassProperties(moulded_cog=IrCog(5.0, 0.25, 0.0, "Um")),
        outer_contour=rectangle(0.0, 2.0, 0.0),
    )
    vessel.plates["plate-a2"] = IrPlate(
        id="plate-a2", parent_ref=parent("panel-a"), name="Plate A2",
        material_ref=Ref("mat315"), thickness=q(10.0, "Umm"),
        mass_properties=IrMassProperties(moulded_cog=IrCog(5.0, 1.75, 1.0, "Um")),
        outer_contour=rectangle(0.0, 2.0, 1.0),
    )
    vessel.stiffeners["stiff-a1"] = IrStiffener(
        id="stiff-a1", parent_ref=parent("panel-a"), name="A bulb",
        guidref="stiff-a1-guid", material_ref=Ref("mat315"),
        section_ref=Ref("hp300"), trace=line(0.4, 0.1),
    )
    vessel.stiffeners["stiff-a2"] = IrStiffener(
        id="stiff-a2", parent_ref=parent("panel-a"), name="A missing profile",
        material_ref=Ref("mat315"), trace=line(1.2, 0.1),
    )
    vessel.stiffeners["stiff-a-no-cross"] = IrStiffener(
        id="stiff-a-no-cross", parent_ref=parent("panel-a"), name="A no cross",
        trace=line(9.0, 9.0, start_x=0.0, end_x=4.0),
    )
    vessel.stiffeners["stiff-b1"] = IrStiffener(
        id="stiff-b1", parent_ref=parent("panel-b"), name="B alone",
        material_ref=Ref("mat315"), section_ref=Ref("hp300"), trace=line(3.0, 0.2),
    )
    vessel.compartments["ballast"] = IrCompartment(
        id="ballast", name="Ballast Tank", compartment_purpose="ballast water",
        volume=q(123.456, "Um3"), face_refs=[Ref("panel-a")],
        cog=IrCog(5.0, 1.0, 0.5, "Um"),
    )
    vessel.compartments["empty"] = IrCompartment(
        id="empty", name="Unclassified Space", face_refs=[Ref("missing-panel")])
    return vessel


def make_model(tmp_path):
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ocx:ocxXML xmlns:ocx="{NS}" schemaVersion="3.0.0">
  <ocx:Vessel>
    <ocx:Panel>
      <ocx:ComposedOf>
        <ocx:Plate id="pl1" name="P:P50/DECK" ocx:GUIDRef="guid-p1">
          <ocx:PlateMaterial>
            <ocx:Thickness numericvalue="0.03" unit="Um"/>
          </ocx:PlateMaterial>
        </ocx:Plate>
        <ocx:Stiffener id="st1" name="S:1/DECK" ocx:GUIDRef="guid-s1">
          <ocx:SectionRef localRef="sec1" ocx:GUIDRef="guid-sec1"
                          name="L450x150x11x14"/>
        </ocx:Stiffener>
      </ocx:ComposedOf>
    </ocx:Panel>
  </ocx:Vessel>
  <ocx:ClassCatalogue>
    <ocx:XSectionCatalogue>
      <ocx:BarSection id="sec1" name="L450x150x11x14"
                      ocx:GUIDRef="guid-sec1">
        <ocx:LBar>
          <ocx:Height numericvalue="0.45" unit="Um"/>
          <ocx:Width numericvalue="0.15" unit="Um"/>
          <ocx:WebThickness numericvalue="0.011" unit="Um"/>
          <ocx:FlangeThickness numericvalue="0.014" unit="Um"/>
        </ocx:LBar>
      </ocx:BarSection>
    </ocx:XSectionCatalogue>
  </ocx:ClassCatalogue>
</ocx:ocxXML>"""
    path = tmp_path / "model.3docx"
    path.write_text(xml, encoding="utf-8")
    return path


def make_report(plates=(), stiffeners=()):
    return {"schema": "nh-optimisation/1", "source": {},
            "plates": list(plates), "stiffeners": list(stiffeners),
            "totals": {}}


def plate_row(**over):
    row = {"name": "P:P50/DECK_EPP1", "guidref": None,
           "offered_mm": 30.0, "optimised_mm": 20.0, "status": "optimised",
           "saving_kg_per_m": 66.7, "iterations": 2}
    row.update(over)
    return row
```

- [ ] **Step 2: `tests/test_server.py`** — the platform's `test_mcp_server.py` retargeted

```python
"""ocx-mcp server tools (unit level, synthetic vessel via monkeypatched loader)."""
import asyncio
import json

import pytest

from ocx_mcp import server, state
from tests.fixtures import make_model, make_report, make_synthetic_vessel, plate_row


@pytest.fixture(autouse=True)
def clean_state():
    state.reset()
    yield
    state.reset()


def test_five_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == {
        "load_model",
        "get_model_info",
        "get_frame_table",
        "get_compartments",
        "apply_scantlings",
    }


def test_server_name_is_ocx_mcp():
    assert server.mcp.name == "ocx-mcp"


def test_all_tools_have_descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    for tool in tools:
        assert tool.description and tool.description.strip(), tool.name


def test_tools_require_loaded_model():
    for fn in (server.get_model_info, server.get_frame_table, server.get_compartments):
        out = fn()
        assert out["ok"] is False and "load_model" in out["error"]


def test_load_model_missing_file():
    out = server.load_model(r"C:\nope\missing.ocx")
    assert out["ok"] is False


def test_pipeline_with_synthetic_model(monkeypatch):
    monkeypatch.setattr(server, "_load_vessel", lambda path: make_synthetic_vessel())
    assert server.load_model("fake.ocx")["ok"] is True
    info = server.get_model_info()
    assert info["ok"] and info["counts"]["stiffeners"] >= 1
    ft = server.get_frame_table()
    assert ft["ok"] and ft["frame_table"]["positions"]
    comp = server.get_compartments()
    assert comp["ok"]


def test_apply_scantlings_ok(tmp_path):
    model = make_model(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(make_report(plates=[plate_row()])), encoding="utf-8")
    out = tmp_path / "patched.3docx"
    result = server.apply_scantlings(str(model), str(report_path), str(out))
    assert result["ok"] is True
    assert result["plates_updated"] == 1
    assert out.exists()


def test_apply_scantlings_error_dict():
    result = server.apply_scantlings("no-such.3docx", "no-such.json", "out.3docx")
    assert result["ok"] is False
    assert "error" in result
```

- [ ] **Step 3: Run the tests to verify they fail**

```powershell
uv run pytest -q 2>&1 | Select-Object -Last 4
```

Expected: collection ERROR — `ImportError: cannot import name 'server' from 'ocx_mcp'`.

---

### Task 10: Server implementation

**Files:** Create `src/ocx_mcp/state.py`, `src/ocx_mcp/server.py`

- [ ] **Step 1: `src/ocx_mcp/state.py`**

```python
"""Process-wide model state for the ocx-mcp server."""
from __future__ import annotations

from ocx_model_core.model.ir.structural import IrVessel

vessel: IrVessel | None = None
source_file: str | None = None


def set_model(v: IrVessel, path: str) -> None:
    global vessel, source_file
    vessel, source_file = v, path


def reset() -> None:
    global vessel, source_file
    vessel = source_file = None
```

- [ ] **Step 2: `src/ocx_mcp/server.py`** — unchanged from the platform except the two `ocx_mcp` / `compartments` imports

```python
"""FastMCP server exposing OCX model tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from ocx_model_core import writeback
from ocx_model_core.builders.factory import get_builder
from ocx_model_core.model.ir.structural import IrVessel
from ocx_model_core.parsers.parser import OcxParser
from ocx_model_validator.compartments import build_compartments_block
from ocx_model_validator.frame_table import build_frame_table, frame_table_block

from ocx_mcp import state

mcp = FastMCP("ocx-mcp")


def _counts(vessel: IrVessel) -> dict[str, int]:
    return {
        "panels": len(vessel.panels),
        "plates": len(vessel.plates),
        "stiffeners": len(vessel.stiffeners),
        "compartments": len(vessel.compartments),
        "ref_planes": len(vessel.ref_planes),
        "materials": len(vessel.materials),
        "sections": len(vessel.sections),
    }


def _load_vessel(path: str) -> IrVessel:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Model file not found: {path}")
    root = OcxParser().parse(source)
    schema_version = getattr(root, "schema_version", "unknown")
    return get_builder(schema_version).build(root)


def _require_model() -> IrVessel:
    if state.vessel is None:
        raise RuntimeError("No model loaded; call load_model first")
    return state.vessel


def _frame_table_dict(vessel: IrVessel) -> tuple[dict[str, Any], list[str]]:
    frame_table = build_frame_table(vessel)
    return (
        frame_table_block(frame_table),
        list(frame_table.warnings),
    )


@mcp.tool()
def load_model(path: str) -> dict[str, Any]:
    """Load and parse an OCX 3D ship model file. Must be called before any other tool."""
    try:
        vessel = _load_vessel(path)
        state.set_model(vessel, path)
        return {"ok": True, "vessel_id": vessel.id, "counts": _counts(vessel)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_model_info() -> dict[str, Any]:
    """Retrieve model ID, name, and entity counts (panels, plates, stiffeners, compartments, ref planes, materials, sections)."""
    try:
        vessel = _require_model()
        return {
            "ok": True,
            "vessel_id": vessel.id,
            "vessel_name": vessel.name,
            "counts": _counts(vessel),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_frame_table() -> dict[str, Any]:
    """Retrieve frame table with labels, positions and spacings in mm derived from X reference planes. Requires load_model."""
    try:
        vessel = _require_model()
        frame_table, warnings = _frame_table_dict(vessel)
        return {"ok": True, "frame_table": frame_table, "warnings": warnings}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_compartments() -> dict[str, Any]:
    """Retrieve compartment list with tank type, center-of-gravity (mm), volume (m³), and extent (mm). Requires load_model."""
    try:
        vessel = _require_model()
        compartments, warnings = build_compartments_block(vessel)
        return {"ok": True, "compartments": compartments, "warnings": warnings}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def apply_scantlings(model_path: str, report_path: str,
                     output_path: str) -> dict[str, Any]:
    """Apply an nh-optimisation/1 scantling report to an OCX .3docx model.
    Patches plate thicknesses (max over each plate's EPP strips) and
    repoints stiffener SectionRefs to new BarSections with the optimised
    dimensions. Writes the patched model to output_path (must differ from
    model_path); never modifies the input. Returns counts of updated items
    and any unmatched report rows."""
    try:
        report = json.loads(
            Path(report_path).read_text(encoding="utf-8"))
        result = writeback.apply_report(model_path, report, output_path)
        return {"ok": True, **result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> None:
    mcp.run()
```

Cross-check against the saved original (only the import lines may differ):

```powershell
git diff --no-index --stat "$env:TEMP\ocx-mcp-src\server.py" src\ocx_mcp\server.py
```

- [ ] **Step 3: Run tests and lint**

```powershell
uv sync -q --dev; uv run pytest -q 2>&1 | Select-Object -Last 2; uv run ruff check .
```

Expected: `8 passed`; `All checks passed!`. If ruff reports `E501` on the long docstrings it is not selected (`E4,E7,E9,F,I` only) — any `I001` import-order finding: run `uv run ruff check --fix .` and re-run.

- [ ] **Step 4: Stdio smoke test against a real model** (not committed)

```powershell
@'
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = r"C:\PythonDev\ocx-platform\models\D-VLCC_1-HOLD-OCX-simple_v3.3docx"

async def main():
    params = StdioServerParameters(command="uv", args=["run", "--directory", r"C:\PythonDev\ocx-mcp", "ocx-mcp"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            print("tools:", names)
            res = await s.call_tool("load_model", {"path": MODEL})
            print("load_model:", res.content[0].text[:200])
            res = await s.call_tool("get_model_info", {})
            print("get_model_info:", res.content[0].text[:200])

asyncio.run(main())
'@ | uv run python -
```

Expected: `tools: ['apply_scantlings', 'get_compartments', 'get_frame_table', 'get_model_info', 'load_model']`, then `load_model` and `get_model_info` JSON containing `"ok": true` and non-zero `panels`.

---

### Task 11: CI, docs, initial commit, push

**Files:** Create `.github/workflows/ci.yml`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - name: Run pre-commit hooks
        run: uvx pre-commit run --all-files --show-diff-on-failure

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --dev
      - name: Run tests
        run: uv run pytest
```

- [ ] **Step 2: `README.md`**

````markdown
# ocx-mcp

[MCP](https://modelcontextprotocol.io) server that exposes OCX `.3docx` ship
models to LLM clients: load a model, read its info, frame table and
compartments, and write optimised scantlings back.

Built on the [ocx-platform](https://github.com/OCXStandard/ocx-platform)
packages `ocx-model-core` (parsing, IR, write-back) and `ocx-model-validator`
(frame table, compartment data).

## Install

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run

The server speaks MCP over stdio:

```bash
uv run ocx-mcp
```

MCP client configuration (e.g. `mcp.json`):

```json
{
  "mcpServers": {
    "ocx": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\PythonDev\\ocx-mcp", "ocx-mcp"]
    }
  }
}
```

## Tools

| Tool | Purpose |
|---|---|
| `load_model` | Parse a `.3docx` file and build the IR (kept in session state) |
| `get_model_info` | Vessel name, schema version and entity counts |
| `get_frame_table` | Frame 0 offset, spacing entries and frame positions (mm) |
| `get_compartments` | Compartment names, tank types, COGs, volumes and extents |
| `apply_scantlings` | Apply an `nh-optimisation/1` report to a `.3docx`: plate thicknesses plus stiffener `BarSection`s, written to a new file |

Every tool returns a dict with `"ok": true` and its data, or `"ok": false`
and an `"error"` message.

## Upgrading the platform

The platform packages are pinned to one ocx-platform commit in
`[tool.uv.sources]` of `pyproject.toml`. To upgrade, change both `rev`
values to the new commit and run `uv lock`.

## Development

```bash
uv sync --dev
uv run pytest
uvx pre-commit run --all-files
```

## Provenance

Moved out of `ocx-model-validator` (`ocx_model_validator.mcp`) at
ocx-platform commit `<PLATFORM_SHA>` (release v0.7.0).
````

- [ ] **Step 3: `CHANGELOG.md`**

```markdown
# Changelog — ocx-mcp

## 0.1.0 — 2026-11-16

- Initial release: the `ocx-mcp` server moved out of ocx-platform
  (`ocx_model_validator.mcp`, platform v0.7.0) with its five tools
  `load_model`, `get_model_info`, `get_frame_table`, `get_compartments`
  and `apply_scantlings`; behaviour and result shapes unchanged.
- Depends on `ocx-model-core` and `ocx-model-validator` via uv git sources
  pinned to ocx-platform `<PLATFORM_SHA>`.
```

- [ ] **Step 4: Lint everything, then commit and push**

```powershell
git add -A; uvx pre-commit run --all-files 2>&1 | Select-Object -Last 6
uv run pytest -q 2>&1 | Select-Object -Last 2
git branch -M main
git commit -q -m "Initial commit: ocx-mcp server moved out of ocx-platform

Source: OCXStandard/ocx-platform @ <PLATFORM_SHA> (v0.7.0),
packages/ocx-model-validator/src/ocx_model_validator/mcp.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push -u origin main
git tag -a v0.1.0 -m "v0.1.0: initial release"; git push origin v0.1.0
```

(`git add -A` is safe here: the new repo has only your files. Check `git status --short` before committing that `.venv/` and `uv.lock` behave as expected — `.venv/` ignored, `uv.lock` **committed**.)

Expected: pre-commit all `Passed`, `8 passed`, push succeeds.

- [ ] **Step 5: CI is green**

```powershell
gh run watch --repo OCXStandard/ocx-mcp --exit-status (gh run list --repo OCXStandard/ocx-mcp --limit 1 --json databaseId --jq ".[0].databaseId")
```

Expected: both `lint` and `test` jobs succeed.

---

## Part C — Cutover

### Task 12: Repoint the MCP client config

**Files:** Modify `C:\Users\oca\.copilot\installed-plugins\_direct\hull-weight-optimizer\mcp.json` (local, not in any repo)

- [ ] **Step 1: Back up and edit**

```powershell
$f = "$env:USERPROFILE\.copilot\installed-plugins\_direct\hull-weight-optimizer\mcp.json"; Copy-Item $f "$f.bak"
```

Replace the `ocx` server entry

```json
    "ocx": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "C:\\PythonDev\\ocx-platform",
               "--package", "ocx-model-validator", "ocx-mcp"]
    }
```

with

```json
    "ocx": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "C:\\PythonDev\\ocx-mcp", "ocx-mcp"]
    }
```

- [ ] **Step 2: Validate JSON and check other configs**

```powershell
Get-Content $f -Raw | ConvertFrom-Json | Out-Null; "json ok"
Select-String -Path "$env:USERPROFILE\.copilot\mcp-config.json" -Pattern "ocx-platform" -SimpleMatch
```

Expected: `json ok`. If `mcp-config.json` references `ocx-platform` for an `ocx-mcp` server, apply the same change there. If the hull-weight-optimizer plugin has a source repository, tell the user its `mcp.json` must get the same change upstream (the `_direct` copy is overwritten on plugin reinstall).

- [ ] **Step 3: Tell the user** to restart Copilot sessions that use the `ocx` MCP server, and — once those platform-launched `ocx-mcp` processes are gone — to run `uv sync --dev` in `C:\PythonDev\ocx-platform` (removes the stale `ocx-mcp.exe` and the `mcp` package from the platform venv).

- [ ] **Step 4: Clean up temp files**

```powershell
Remove-Item -Recurse -Force "$env:TEMP\ocx-mcp-src"
```

---

## Spec coverage

| Spec item | Task |
|---|---|
| §1.1 inter-package pins | 2 |
| §1.2 public compartments module | 3 |
| §1.3 remove server, script, dep, test, spec exclude, description | 4 |
| §1.4 docs (README ×2, copilot-instructions, changelogs) | 5, 6 |
| §1.5 versions, lock, tag v0.7.0 | 6, 7 |
| §2 repo layout, pyproject, git sources, server/state, tests, fixtures, CI, README (tools table, upgrade, provenance), no LICENSE, no publish | 8–11 |
| §3.1 platform verification (`pytest`, `uv lock --check`, `uv tree` without mcp) | 4, 6, 7 |
| §3.2 `gh repo create`, `uv lock` from git, tests, stdio smoke test, push | 8, 10, 11 |
| §3.3 client config | 12 |
| §3.4 local venv lock | Conventions, 12 |
