# Copilot Workspace Instructions for Sanopy

## Overview
**Sanopy** is a linting orchestrator for Python projects.

Scope in this repository:
- Linter orchestration and reporting only.
- No AI provider, model, or auto-fix pipeline.
- CLI commands are `scan` and `init`.

## Build & Test Commands
```bash
uv sync                        # Install dependencies
uv run sanopy init             # Interactive linter defaults setup
uv run sanopy scan src/        # Run linters and collect issues
uv run sanopy scan src/ -r     # Also generate linting-report.md output
uv run pytest                  # Run test suite
```

## Project Structure
```
src/sanopy/
  cli/            # CLI entry point and handlers (main.py, scan_handler.py, init_handler.py)
  linters/        # Linter integrations: bandit, mypy, pylint, pyright, radon, ruff, safety, semgrep, vulture
                  #   engine.py = async orchestration, base.py = abstract base, result.py = normalized findings
                  #   context.py = snippet/context extraction for lint reports
  config.py       # Config: only_linters, skip_linters; normalized on load/save
```

## Key Conventions
- **Async orchestration**: Linters run concurrently via `Engine.run_all()` using `asyncio`.
- **Linter contract**: Each linter subclass implements `build_command()` and `parse_output()` from `BaseLinter`.
- **Config normalization**: `Config` lowercases and deduplicates linter lists on load/save.
- **Filtering behavior**: `--only` is applied before `--skip`.
- **Scan outputs**: `scan` writes JSON, with optional markdown output via `-r/--human-readable`.
- **Runner strategy**: Base linter execution prefers `uv run`, then falls back to `python -m`.

## Potential Pitfalls
- **Python 3.12+ required** — check `pyproject.toml` before changing syntax.
- **Radon is a linter too** — it's in `linters/` alongside static analysis tools; include it when iterating all linters.
- **Config discovery is layered** — local config files are preferred; bundled defaults in `linters/configs/` are used when local config is absent.
- **Async tests** should use `@pytest.mark.asyncio` when testing async logic directly.
- **Do not reintroduce removed features** — no `fix` command or AI/provider settings should be added unless explicitly requested.

## Documentation
- See [README.md](../README.md) for usage, CLI examples, and supported linters.
- See [pyproject.toml](../pyproject.toml) for lint/type/test tool settings.
- See [CHANGELOG.md](../CHANGELOG.md) for notable behavior changes.
