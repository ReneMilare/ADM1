# Repository Guidelines

## Project Structure & Module Organization
`simulator/` contains the ADM1 engine, reactor models, validation pipeline, and pytest suite in `simulator/tests/`. `rag/` holds PDF extraction, chunking, indexing, and MCP endpoints. `webapp/` is the Streamlit UI; numbered files in `webapp/pages/` map to app screens. `vaultObsidian/` stores project notes, plans, and code review context. `documentation/` contains reference PDFs. Treat `dist/`, `rag/db/`, `rag/extracted/`, `simulator/runs/`, and `simulator/*_runs/` as generated artifacts, not source.

## Build, Test, and Development Commands
Create the environment with `python -m venv .venv` and `.\.venv\Scripts\activate`, then install dependencies with `pip install -r requirements.txt`.

- `.\scripts\setup_local.ps1`: bootstrap local dev setup and optional RAG tooling.
- `.\scripts\check_env.ps1`: verify Python, Ollama, embedding model, and local index status.
- `.\scripts\run_webapp.ps1` or `streamlit run webapp/app.py`: start the local UI.
- `python -m pytest simulator/tests -q`: run the simulator regression suite.
- `python rag/extract_pdfs.py` and `python rag/index_documents.py`: rebuild extracted documents and the Chroma index.
- `python -m simulator.validation` or `python -m simulator.design_pipeline --substrate "Lodo de Esgoto" --goal balanced --backend auto`: run validation and design workflows.

## Coding Style & Naming Conventions
Use Python 3.11+ style with 4-space indentation, type hints, and small, testable functions. Prefer `snake_case` for modules, functions, and variables; use `PascalCase` for classes and Pydantic models. Keep Streamlit page filenames numbered (`01_...`, `02_...`) to preserve navigation order. Follow existing patterns before introducing abstractions; add comments only when the math, stoichiometry, or workflow is not obvious.

## Testing Guidelines
Tests use `pytest` and live under `simulator/tests/` with `test_*.py` names. Add or update regression tests whenever kinetics, backend selection, persistence, or RAG scoring changes. Before opening a PR, run `python -m pytest simulator/tests -q` and note any manual checks such as `streamlit run webapp/app.py` or RAG indexing.

## Commit & Pull Request Guidelines
Recent history uses short, imperative subjects such as `Adjust GitHub publishing constraints` and `Initial ADM1 local test bundle`. Keep commits focused and descriptive. PRs should summarize behavior changes, list commands run, call out data or config impacts, and include screenshots for `webapp/` UI changes. Link the relevant issue, plan note, or code review note from `vaultObsidian/` when applicable.

## Security & Configuration Tips
Do not commit `.venv/`, `webapp/user_data/`, runtime caches, or generated indexes. Large reference files may exceed GitHub limits; keep them in local bundles or release assets when needed. RAG features depend on local Ollama configuration via `ADM1_OLLAMA_HOST` and `ADM1_EMBED_MODEL`.
