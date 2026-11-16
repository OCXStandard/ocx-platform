# ocx-mcp carve-out — design

Date: 2026-11-16
Status: approved

## Goal

Move the `ocx-mcp` MCP server out of `ocx-model-validator` into a new
public repository, `OCXStandard/ocx-mcp`, so it has its own repo and release
cadence and the platform stays a pure library + CLI.

Success criteria:

- `ocx-platform` no longer contains the `ocx_model_validator.mcp` package,
  the `ocx-mcp` script or the `mcp` dependency.
- `OCXStandard/ocx-mcp` exposes the same server (`FastMCP("ocx-mcp")`) with
  the same 5 tools — `load_model`, `get_model_info`, `get_frame_table`,
  `get_compartments`, `apply_scantlings` — and identical result shapes.
- `ocx-mcp` resolves the platform packages from git (outside the workspace)
  and its tests pass.
- The `hull-weight-optimizer` plugin launches the server from the new repo.

## Decisions

| Topic | Decision |
|---|---|
| Driver | Decoupling (own repo and release cadence) |
| Repo | `OCXStandard/ocx-mcp`, public, local clone `C:\PythonDev\ocx-mcp` |
| History | Fresh initial commit; provenance (platform commit SHA) in the commit message and README |
| Platform removal | Remove outright — breaking change, `ocx-model-validator` 0.7.0; no deprecation release |
| Dependencies | Approach A: `ocx-mcp` depends on `ocx-model-core` + `ocx-model-validator`, git-pinned like `ocx-render` |

Rejected: moving `frame_table` and compartment data into `ocx-model-core`
(larger refactor; not parse/IR concerns) and copying the helpers into
`ocx-mcp` (duplicated logic that drifts from the reports).

## Current state

- `packages/ocx-model-validator/src/ocx_model_validator/mcp/` — `server.py`
  (5 tools, ~120 lines) and `state.py` (process-wide loaded vessel).
- The server imports `ocx_model_core` (parser, builder factory, writeback),
  `ocx_model_validator.frame_table`, and
  `ocx_model_validator.reporting.generators._compartment_data.build_compartments_block`
  (a private module).
- `tests/test_mcp_server.py` uses `tests.section_fixtures.make_synthetic_vessel`
  and `make_model` / `make_report` / `plate_row` from `tests/test_writeback.py`.
- Every platform package still pins `ocx-model-core>=0.5,<0.6` although core
  is 0.6.0. The pins are only satisfied inside the uv workspace (workspace
  sources override them); a git-pinned consumer cannot resolve them.

## Section 1 — Platform changes (release v0.7.0)

1. **Inter-package pins.** Update every `pyproject.toml` under `packages/`
   so pins match current versions: `ocx-model-core>=0.6,<0.7` everywhere;
   the validator's `ocx-geometry` and `ocx-rules` pins match their (bumped)
   versions.
2. **Public compartments module.** Move
   `reporting/generators/_compartment_data.py` to
   `ocx_model_validator/compartments.py` (same contents, including
   `build_compartments_block` and `_curve_points_mm`). Update the imports in
   `reporting/generators/compartments.py` and `model_extent.py`. No alias for
   the old private path.
3. **Remove the server.** Delete `ocx_model_validator/mcp/`, the `ocx-mcp`
   entry in `[project.scripts]`, the `mcp` dependency and
   `tests/test_mcp_server.py`; drop the `ocx_model_validator.mcp` exclude in
   `packaging/validator.spec`; remove "MCP server" from the validator
   package description and README.
4. **Docs.** Root README: replace the MCP feature bullet and "MCP server"
   section with a pointer to `OCXStandard/ocx-mcp`; remove `mcp/` from both
   layout trees. `.github/copilot-instructions.md`: remove `mcp/` from the
   tree. Changelogs: validator entry under "Removed (breaking)"; workspace
   changelog entry; patch entries for packages whose pins changed.
5. **Versions.** `ocx-model-validator` 0.7.0 (pyproject + `__version__`);
   `ocx-geometry`, `ocx-rules`, `ocx-integrity` patch bumps (pin metadata
   only; `ocx_rules.__version__` follows its pyproject). `uv lock`. Tag
   `v0.7.0`.

## Section 2 — The `ocx-mcp` repository

Single package (no workspace):

```
ocx-mcp/
├── pyproject.toml
├── src/ocx_mcp/
│   ├── __init__.py
│   ├── server.py
│   └── state.py
├── tests/
│   ├── fixtures.py        ← synthetic vessel + writeback model/report builders
│   └── test_server.py
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── .gitignore
├── README.md
└── CHANGELOG.md
```

- `pyproject.toml`: `name = "ocx-mcp"`, `version = "0.1.0"`,
  `requires-python = ">=3.12"`, hatchling build, script
  `ocx-mcp = "ocx_mcp.server:main"`. Dependencies: `mcp>=1.0,<2`,
  `loguru>=0.7`, `ocx-model-core>=0.6,<0.7`, `ocx-model-validator>=0.7,<0.8`.
  `[tool.uv.sources]` pins both to
  `git = "https://github.com/OCXStandard/ocx-platform"` with
  `subdirectory = "packages/<name>"` and `rev = <v0.7.0 commit SHA>`.
  Dev group, ruff and pytest settings copied from the platform root.
- `server.py` / `state.py` are copied unchanged except imports:
  `from ocx_mcp import state` and
  `from ocx_model_validator.compartments import build_compartments_block`.
- `tests/test_server.py` is the platform's `test_mcp_server.py` with imports
  pointing at `ocx_mcp` and `tests.fixtures`. `tests/fixtures.py` holds
  copies of `make_synthetic_vessel` and `make_model` / `make_report` /
  `plate_row` (test-only copies; the platform keeps its own).
- CI mirrors the platform `ci.yml` (pre-commit lint job + `uv sync --dev` /
  `uv run pytest`). No publish workflow.
- README: purpose, install (`uv sync`), run (`uv run ocx-mcp`), MCP client
  config, the tools table moved from the platform README, how to upgrade the
  platform pin (edit `rev`, `uv lock`), and a provenance line.
- No LICENSE file (the platform has none).

## Section 3 — Cutover and verification

1. **Platform**: implement Section 1 on a branch; `uv run pytest` green;
   `uv lock --check` clean; `uv tree --package ocx-model-validator` shows no
   `mcp`. Merge to `master`, tag `v0.7.0`, push.
2. **ocx-mcp**: `gh repo create OCXStandard/ocx-mcp --public`, build the
   repo per Section 2 pinned to the `v0.7.0` SHA. `uv lock` succeeding
   proves the platform resolves outside its workspace. `uv run pytest`
   green. Stdio smoke test: start the server, `list_tools` returns exactly
   the 5 tools, `load_model` succeeds on a real model from
   `ocx-platform/models/`. Push.
3. **Client config**: point
   `~/.copilot/installed-plugins/_direct/hull-weight-optimizer/mcp.json`
   `ocx` server at
   `["run", "--directory", "C:\\PythonDev\\ocx-mcp", "ocx-mcp"]`
   (local config, outside both repos).
4. **Local venv**: running `ocx-mcp` processes lock
   `.venv\Scripts\ocx-mcp.exe`; stop the sessions that run them before
   `uv sync --dev` in the platform.

## Out of scope

- The failing `Publish to PyPI` workflow (failed on `v0.6.0`).
- New MCP tools or behaviour changes.
- Publishing `ocx-mcp` to PyPI.
