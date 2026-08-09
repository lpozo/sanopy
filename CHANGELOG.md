# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project structure with async linter orchestration.
- Support for Ruff, Pylint, Bandit, MyPy, Pyright, Semgrep, Vulture, Radon, and Safety.
- Support for pip-audit, a dependency vulnerability scanner for Python environments.
- Configurable pip-audit suppressions via the `[pip-audit] ignore_vulns` setting in `.sanopy.toml`.
- Bundled linter defaults (pylint, bandit, ruff) moved to `[linters.<name>]` sections in `.sanopy.toml`; suppression and linter defaults materialize at init/reset.
- Interactive onboarding wizard (`sanopy init`) for default linter selection.
- Standardized `LinterResult` model for unified issue representation.
- Semantic context extraction (function/class boundaries) for richer scan output.
- `--human-readable` (`-r`) flag for `sanopy scan` to generate a Markdown report.
- GitHub Actions CI/CD with PyPI Trusted Publishing support.
- Zero-config operation: bundled best-practice configurations for Ruff, Pylint, and Bandit are applied automatically when no local config is found.
- Context-aware configuration: production and test code receive separate rule sets automatically based on the target path.
- Linter command execution abstracted to support both `uv` and system Python environments.
- CLI modularized into dedicated command handlers (`scan_handler`, `init_handler`).
- Configuration management backed by TOML, with `sanopy init` for interactive setup.
- Improved CLI help text for all commands and options.
- Google-style docstrings across the entire codebase.
- `Attributes:` sections in all dataclass docstrings.
- Configuration discovery validates `[tool.<linter>]` sections in `pyproject.toml` to correctly detect local configs.
- Ruff test glob set to `tests/**/*.py` for broader rule matching in test files.
- Multi-target `scan` runs now emit a single valid JSON document, merging per-target results.
- Comprehensive parametrized test suite covering linter output parsing for all supported linters.

### Changed

- Configurable Safety CVE suppressions via the `[safety] ignore_cves` setting in `.sanopy.toml`, replacing the hardcoded suppression in the Safety linter.
- Upgraded transitive dependencies (`cryptography`, `joserfc`, `nltk`) to clear Safety CVE findings.
- Added CI, version, tooling, and license badges to the README.

### Fixed

- Config status messages now use rich output on stderr, keeping machine JSON output on stdout clean.
- Hardened linter result parsing against null or malformed JSON lists.
- Pyright `reportUnsupportedDunderAll` warning for the dynamic `__all__` export in the linters package.
- Removed the leftover `sanopy.toml` file left behind by the app rename.
- Corrected the `-r`/`--human-readable` help text to match the actual report filename (`linting-report-<target>.md`).
- Translated leftover non-English CLI docstrings and comments to English.
