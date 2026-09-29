# Repository Guidelines

## Project Structure & Module Organization

The project has a Python 3.11+ FastAPI backend in `api/` and a Vue 3 + TypeScript frontend in `ui/`. `api/main.py` defines the JSON API; `api/sources/` contains video discovery and playback adapters; `api/filtering/` handles deterministic rules and local LLM classification; and `api/media/` contains playback and thumbnail helpers. The frontend is a Vite application. Editable hard-filter rules live in `config/rules.yaml`. Tests are in `tests/`. Keep local secrets in `.env` and use `.env.example` for documented defaults; do not commit generated databases or credentials.

## Build, Test, and Development Commands

- `python3 -m venv .venv && source .venv/bin/activate` creates and activates an isolated environment.
- `pip install -r requirements.txt` installs the application and test dependencies.
- `uvicorn api.main:app --reload` starts the local API at `http://127.0.0.1:8000`.
- `cd ui && npm run dev` starts the frontend at `http://localhost:5173`.
- `PYTHONPATH=. pytest -q` runs the test suite. Ollama is needed for live local classification, but rule tests should remain deterministic and self-contained.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, `snake_case` for modules, functions, and variables, and `PascalCase` for classes. Keep source-specific behavior in its adapter and filtering behavior in `api/filtering/`. Use descriptive test names such as `test_rejects_blocked_title`. Preserve the existing YAML structure and indentation when changing `config/rules.yaml`; keep configuration examples synchronized with settings added to `api/config.py`.

## Testing Guidelines

Tests use pytest and are named `test_*.py`; test functions use the `test_*` prefix. Add focused tests for rule changes and behavior changes, including boundary cases where applicable. Run `PYTHONPATH=. pytest -q` from the repository root before submitting. Do not rely on external video services or a running Ollama instance for unit tests.

## Commit & Pull Request Guidelines

The visible history uses short imperative summaries, for example `Update rules.yaml` and `include compilations`; continue with a concise action-oriented subject, ideally naming the affected area. A pull request should explain the user-visible or operational effect, list relevant configuration changes, link an issue when available, and include screenshots for UI changes. Mention test commands and results.

## Security & Configuration Tips

Never commit `.env`, API credentials, or personal data. Add safe, non-secret defaults to `.env.example`. Filtering rules are applied before LLM classification, so describe rule changes and their impact clearly in the pull request.
