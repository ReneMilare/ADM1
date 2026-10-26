# Repository Guidelines

## Project Overview
ADM1 Workbench is a Python platform for designing and validating anaerobic digestion reactors with IWA ADM1-based simulations. It combines a numerical simulator, a simulator MCP server, and a Streamlit web interface. The main reader is a developer or technical user learning anaerobic digestion, so keep domain math explicit, well typed, and locally testable.

The public repository intentionally excludes the old internal RAG, private note vaults, reference PDFs, user data, generated simulation runs, and local machine paths.

## Project Structure
- `simulator/`: ADM1 engine, reactor models, validation workflows, design pipeline, scenario persistence, and simulator MCP server.
- `simulator/core/`: shared Pydantic models, defaults, kinetics, and PyADM1 backend adapter.
- `simulator/full_model/`: native full-model implementation, extensions, catalogs, governance checks, and solvers.
- `simulator/reactor_models/`: reactor strategy implementations such as CSTR, UASB, plug-flow, TPAD, two-phase, and batch.
- `simulator/tests/`: pytest regression suite.
- `webapp/`: Streamlit application.
- `webapp/pages/`: numbered Streamlit pages; keep filenames numbered to preserve navigation order.
- `webapp/services/`: UI-facing service layer around simulator, validation, reporting, preferences, and scenarios.
- `scripts/`: setup, environment check, webapp startup, and release bundle helpers. Each exists as PowerShell (`.ps1`, Windows) and Bash (`.sh`, Linux/macOS); keep both in sync when changing one.
- `vendor/PyADM1/`: vendored PyADM1 git submodule.

Treat `dist/`, `simulator/runs/`, `simulator/*_runs/`, `simulator/.pyadm1_runtime/`, `webapp/user_data/`, private notes, and reference PDFs as local/generated artifacts, not source.

## Commands
Create the environment with:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

On Linux/macOS:

```bash
./scripts/setup_local.sh   # creates .venv, inits vendor/PyADM1, installs requirements
source .venv/bin/activate
```

Common commands (Windows paths shown; on Linux/macOS use `./scripts/<name>.sh`):

```powershell
.\scripts\setup_local.ps1
.\scripts\check_env.ps1
.\scripts\run_webapp.ps1
python -m pytest simulator/tests -q
python -m simulator.benchmark
python -m simulator.validation
python -m simulator.design_pipeline --substrate "Lodo de Esgoto" --goal balanced --backend auto
python simulator/mcp_server.py
streamlit run webapp/app.py
```

Run a focused test with:

```powershell
python -m pytest simulator/tests/test_kinetics.py -q
python -m pytest simulator/tests/test_simulator.py::ADM1SimulationServiceTest::test_simulation_returns_profiles -q
```

`mcp` is pinned to `<2`: `simulator/mcp_server.py` uses `FastMCP`, which mcp 2.x renamed. Migrating to mcp 2.x is a separate task. `webapp/testing/test_phase_indicators_removed.py` needs `playwright` (dev extra) and a webapp running on port 8501; it is skipped when playwright is missing.

No linter or formatter is configured. There is no `ruff`, `mypy`, or `black` quality gate in this repository.

## Architecture
The simulator has two main backends:

- `pyadm1`: default high-fidelity backend via `vendor/PyADM1/`. It writes temporary CSVs, runs PyADM1 as a subprocess, and parses outputs. It is the preferred backend for CSTR reference fidelity.
- `reduced`: native Python 11-state simplified model in `simulator/core/kinetics.py`. It is always available, faster, and useful as fallback or exploratory backend.

Backend resolution lives in `simulator/service.py`. The `auto` setting currently selects PyADM1 for CSTR-oriented reference work and uses explicit fallback behavior where needed. Every `SimulationResult` records `backend_requested`, `backend_used`, and fallback information in metadata.

Reactor behavior follows a strategy pattern. `simulator/reactor_models/base.py` defines `ReactorBase`, and concrete reactors override hydrodynamic, washout, gas capture, and segment behavior. New reactor types should subclass `ReactorBase` and be registered in `simulator/reactor_models/__init__.py`.

The reduced model state vector is defined in `simulator/core/models.py` as `STATE_NAMES`: `particulate_cod`, `soluble_cod`, `acetate`, `propionate`, `hydrogen`, biomass populations, `inorganic_nitrogen`, and `alkalinity`. Kinetics, inhibition functions, and stoichiometric splits live in `simulator/core/kinetics.py`. COD balance is covered by tests; maintain `splits + yield = 1.0` per pathway when changing stoichiometry.

Typical data flow:

1. CLI, MCP, or webapp assembles Pydantic configs.
2. `ADM1SimulationService.simulate()` resolves and dispatches the backend.
3. Backend returns time series and profiles.
4. The service computes summary metrics such as methane, biogas, VFA, pH, effluent COD, and stability index.
5. `ScenarioStore` persists JSON results under `simulator/runs/` when persistence is enabled.

## Module Boundaries
- `simulator/` should remain usable without Streamlit.
- `webapp/` consumes simulator capabilities through service modules and shared contracts.
- Report and validation exports should write to generated project artifacts or `webapp/user_data/`, not private external folders.
- The simulator MCP server should expose validated, JSON-serializable, read/write-safe tools through Pydantic input models.

## Coding Style
Use Python 3.11+ with `from __future__ import annotations` in Python modules. Prefer 4-space indentation, type hints, `snake_case` for functions and variables, and `PascalCase` for classes and Pydantic models.

All domain models should follow the existing strict Pydantic pattern with assignment validation and `extra="forbid"`. Default configs should stay centralized in `simulator/core/defaults.py`.

Follow local patterns before adding abstractions. Add comments only where math, stoichiometry, numerical behavior, or workflow intent is not obvious from the code.

## Testing
Tests use `pytest` and live under `simulator/tests/` with `test_*.py` names. Add or update regression tests whenever kinetics, backend selection, persistence, full-model governance, or user-facing workflows change.

Before opening a PR, run:

```powershell
python -m pytest simulator/tests -q
```

For webapp-specific service checks, also run:

```powershell
python -m pytest webapp/testing -q
```

Include any manual checks such as `streamlit run webapp/app.py` in PR notes when UI behavior changes.

## Security And Publication
Do not commit `.venv/`, `webapp/user_data/`, runtime caches, private vaults, reference PDFs, `.env*`, Streamlit secrets, tokens, keys, generated bundles, or local absolute paths.

Public-facing output should not display local paths such as user home directories, workspace roots, junction targets, or private documentation paths. Prefer project-relative paths in metadata and UI messages.

Release bundles should include only source code, public configuration, and required vendored/submodule code. Keep private references and local documentation outside the public repository.

## Commit And PR Notes
Recent history uses short imperative subjects such as `Adjust GitHub publishing constraints`. Keep commits focused. PRs should summarize behavior changes, commands run, data/config impacts, and screenshots for `webapp/` UI changes.
