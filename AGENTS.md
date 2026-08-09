# AGENTS.md

Sanopy is a Python 3.12 CLI that runs many linters concurrently and emits findings as versioned JSON. Built with `uv`; managed with `hatchling`. The repo dogfoods itself: `sanopy scan src tests` must report **0 findings**.

## Commands

All commands run through `uv run`. CI only runs `ruff check`, `ruff format --check`, and `pytest` — mypy/pyright/radon/self-scan are local-only and must be run manually.

```bash
uv run pytest                                # full suite
uv run pytest tests/test_config.py -q        # single file
uv run ruff check .
uv run ruff format --check .                 # fix with: uv run ruff format .
uv run mypy src tests                        # strict (tests relaxed via pyproject overrides)
uv run pyright src
uv run radon cc -n C src tests -s            # no function may rank C or above
uv run sanopy scan src tests                 # self-scan; must exit 0 with 0 findings
```

After changing code, run the full set: tests → ruff → mypy → pyright → radon → self-scan.

## Architecture

- `src/sanopy/cli/cli.py` — click entrypoint (`sanopy` / `python -m sanopy`). Two commands: `init`, `scan`. `scan` exits `1` when findings exist, `2` on exception.
- `src/sanopy/cli/scan_handler.py` — scan orchestration: `Config.load()` → filter linters → `Engine` → `ScanReporter`. `_build_linter` passes config-dependent settings; **safety and pip-audit are special-cased** (`ignored_cves=` / `ignore_vulns=` kwargs), everything else gets `config=config`.
- `src/sanopy/cli/init_handler.py` — `init` flow (interactive prompts + CLI options).
- `src/sanopy/config.py` — `Config` dataclass, load/save of `.sanopy.toml`, `LinterConfig`, `DEFAULT_LINTER_CONFIGS` (pylint/bandit/ruff), `DEFAULT_IGNORED_CVES` / `DEFAULT_IGNORED_VULNS`. Values are normalized (strip, dedupe; CVEs/vulns uppercased).
- `src/sanopy/linters/<name>.py` — one module per linter, each a `BaseLinter` subclass with `name`, `build_command`, `parse_output`.
- `src/sanopy/linters/base.py` — `BaseLinter` (holds `config`; `_get_effective_config_path` resolves native config), `AsyncCompletedProcess`.
- `src/sanopy/linters/engine.py` — runs linters concurrently via asyncio.
- `src/sanopy/linters/config_discovery.py` — `is_test_path`, `materialize_linter_config`, `render_native_config`, `find_nearest_local_config`.
- `src/sanopy/linters/__init__.py` — **linters are discovered dynamically** (`LINTER_MAP` built by scanning the package). Adding a linter module in this directory auto-registers it; keep the import guarded with `# nosemgrep` as existing modules do.

## Non-obvious behavior

- `.sanopy.toml` is **tracked in git** and regenerated automatically: missing file → created with all defaults materialized; **invalid TOML → reset to defaults**. Don't commit scan-induced churn in it.
- Config resolution for ruff/pylint/bandit: nearest local config (searching upward from target to CWD, `pyproject.toml` only honored if it has `[tool.<name>]`) wins; otherwise bundled defaults are materialized from `[linters.<name>]` sections (falling back to `DEFAULT_LINTER_CONFIGS`) into `$TMPDIR/sanopy/configs/<category>/` and passed via `--config`.
- `[linters.<name>.test]` tables override the `test` category only; `is_test_path` decides the category (paths under `tests/` or `test_*`/`*_test.py`).
- `BaseLinter.__init__(config=None)` — any subclass defining its own `__init__` must call `super().__init__()` or the self-scan flags pylint W0231.
- Test linters by mocking `_run_command` and feeding canned `AsyncCompletedProcess(stdout=..., stderr="", returncode=0)` output (see `tests/test_linters_ruff.py`); mock `get_linter_context` when a linter calls it.
- Strict line-length 79; ruff format uses double quotes.

## Conventions

- Conventional commit messages (`feat:`, `fix:`, `docs:`, `chore:`, often scoped, e.g. `feat(config):`), feature branch per change, PR merged into `main`.
- Python 3.12 (`requires-python = ">=3.12"`); new code should keep 100% coverage of src type-checked under strict mypy.
- Running linters (ruff, pylint, bandit, mypy, pyright, semgrep, vulture, radon, safety, pip-audit) are runtime dependencies of the package itself — they are run as subprocesses, not imported as tools.
- Lint findings are `LinterResult` dataclasses; output envelope `schema_version: "1.0.0"` is part of the public contract (tests assert on it).
