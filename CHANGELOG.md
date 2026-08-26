# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Linter dependencies are now optional extras (`pip install 'sanopy[ruff]'`, `'sanopy[all]'`, etc.) — core install is lightweight, linters are installed on-demand via `sanopy init`.
- `sanopy init` installs any selected linter that is not yet available, into the environment Sanopy runs from. The interactive flow prompts first; the non-interactive flow installs directly. Exits `2` if an installation fails, and reports the installer's own output so failures are diagnosable.
- `sanopy init --no-install` writes the configuration without touching the environment, for pipelines that manage dependencies themselves.
- `sanopy scan` exits with code 2 and an extras-based install hint when a required linter is not installed.
- `sanopy scan` exits with code 2 when the `--only`/`--skip` filters select no linters at all, naming any unrecognised linter names. Previously a typo like `--only rufff` ran nothing, printed "No issues found" and exited 0.
- `sanopy scan` without a `.sanopy.toml` config exits with code 2 and tells the user to run `sanopy init` first.
- `Config.defaults()` is now public, replacing the private `_defaults_with_materialized_sections()`.
- README sections documenting the exit-code contract, how Sanopy locates linters, `--only`/`--skip` precedence, and troubleshooting for each error message.
- `sanopy scan --help` now states the exit codes and that diagnostics go to stderr.

### Changed

- `sanopy scan` no longer auto-creates `.sanopy.toml` or redirects to the init wizard — the user must run `sanopy init` explicitly.
- Linter availability is now determined by how the linter is actually invoked: the console script on `PATH`, else the console script beside Sanopy's own interpreter, else `python -m <module>` in that interpreter. A linter installed in a non-activated virtualenv, or via `pipx`/`uv tool`, is no longer misreported as missing — including console-script-only linters such as Semgrep.
- Linters are invoked directly rather than through `uv run`, so the version that runs is the one Sanopy resolved.
- All diagnostics (missing config, missing linters, linter crashes, scan failures) now go to **stderr**. Previously they were written to stdout, which corrupted the JSON document in the default machine output mode.
- Config and linter checks run once per invocation instead of once per target, so a multi-target scan no longer repeats the same error message.
- A failing scan now reports the underlying error instead of exiting `2` silently.

### Fixed

- `sanopy init` no longer silently discards an invalid `.sanopy.toml`; it warns before overwriting it.
- Blank or separator-only `--only`/`--skip` values (`--only "  "`, `--only ,`) are treated as absent rather than parsed into an empty linter name, which had silently selected no linters.
- `DEFAULT_IGNORED_CVES` no longer carries suppressions specific to Sanopy's own environment. Because `init` seeds these defaults into every user's `.sanopy.toml`, they had been hiding those CVEs from unrelated projects.

## [0.1.0] - 2026-08-25

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
