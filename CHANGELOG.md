# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project structure with async linter orchestration.
- Support for Ruff, Pylint, Bandit, MyPy, Pyright, Semgrep, Vulture, Radon, and Safety.
- Interactive onboarding wizard (`sanopy init`) for default linter selection.
- Standardized `LinterResult` model for unified issue representation.
- Semantic context extraction (function/class boundaries) for richer scan output.
- `--human-readable` (`-r`) flag for `sanopy scan` to generate a Markdown report.
- GitHub Actions CI/CD with PyPI Trusted Publishing support.
- Zero-config operation: bundled best-practice configurations for Ruff, Pylint, and Bandit are applied automatically when no local config is found.
- Context-aware configuration: production and test code receive separate rule sets automatically based on the target path.
- Linter command execution abstracted to support both `uv` and system Python environments.
- CLI modularized into dedicated command handlers (`scan_handler`, `init_handler`).
- Configuration management backed by TOML and environment variables, with `sanopy init` for interactive setup.
- Improved CLI help text for all commands and options.
- Google-style docstrings across the entire codebase.
- `Attributes:` sections in all dataclass docstrings.
- Configuration discovery validates `[tool.<linter>]` sections in `pyproject.toml` to correctly detect local configs.
- Ruff test glob set to `tests/**/*.py` for broader rule matching in test files.
