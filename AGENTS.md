# AGENTS.md

Sanopy is a Python 3.12 CLI that runs many linters concurrently and emits findings as versioned JSON. Built with `uv`; managed with `hatchling`. The repo dogfoods itself: `sanopy scan src tests` must report **0 findings**.

**Scope.** Linter orchestration and reporting only — there is no AI provider, model, or auto-fix pipeline, and the only commands are `init` and `scan`. A `fix` command and AI/provider settings were deliberately removed; do not reintroduce them or anything equivalent unless explicitly asked.

## Commands

All commands run through `uv run`. CI only runs `ruff check`, `ruff format --check`, and `pytest` — mypy/pyright/radon/self-scan are local-only and must be run manually.

```bash
uv run pytest                                # full suite
uv run pytest tests/test_config.py -q        # single file
uv run ruff check .
uv run ruff format --check .                 # fix with: uv run ruff format .
uv run mypy src tests                        # strict (tests relaxed via pyproject overrides)
uv run pyright src tests
uv run radon cc -n C src tests -s            # no function may rank C or above
uv run sanopy scan src tests                 # self-scan; must exit 0 with 0 findings
```

Linter dependencies are optional extras (`[project.optional-dependencies]`).
The base install only includes `click` and `rich`. For the self-scan and
full test suite, install with all extras:

```bash
uv sync --dev --extra all
```

After changing code, run the full set: tests → ruff → mypy → pyright → radon → self-scan. Verify, don't assume — the self-scan is the check most likely to catch a regression the others miss.

## Git Flow

This repo follows Git Flow. The rule that matters above all: **`main` only ever receives release branches, so it always equals the latest released code — all non-release work goes through `develop`.**

Feature branches branch off `develop` and PR into `develop`, never `main`:

```bash
# Feature work — branch off develop, PR into develop
git checkout -b feat/<name> develop
git push -u origin feat/<name>
gh pr create --base develop
```

Releases are the only exception. Cut a release branch off `develop`, bump the version there, and PR it into `main`:

```bash
# Release — branch off develop, bump version, PR into main
git checkout -b release/vX.Y.Z develop
# bump version in pyproject.toml, sync uv.lock, move CHANGELOG [Unreleased] entries under [X.Y.Z]
git push -u origin release/vX.Y.Z
gh pr create --base main
```

Because `publish.yml` fires on every PR merged into `main`, anything merged to `main` ships — keep non-release work off it. After each release, merge `main` back into `develop` so the version bump lands there too.

`gh pr create` and the GitHub web UI default to the repository's default branch, so pass `--base` explicitly to point a PR at the right base.

## Architecture

- `src/sanopy/cli/cli.py` — click entrypoint (`sanopy` / `python -m sanopy`). Two commands: `init`, `scan`. `scan` exits `0` clean, `1` when findings exist, and `2` when it could not run at all: missing or invalid config, a missing linter, filters selecting no linters, or an unexpected error. `init` exits `2` if an install fails.
- `src/sanopy/cli/scan_handler.py` — `preflight()` runs **once per invocation** from `cli.scan` (config guard → load → resolve linters → non-empty guard → availability check) and returns `(config, active_linters)`; `handle_scan` receives both and only scans. Keep new run-level guards in `preflight`, not `handle_scan`, or a multi-target scan reports them once per target. Both guards exit `2`.
- `src/sanopy/cli/selection.py` — `parse_linter_names`, `resolve_active_linters`, `format_install_hint`. The single owner of "which linters are active".
- `src/sanopy/cli/ui.py` — `console` (stdout, JSON payload only) and `err_console` (stderr, everything else).
- `src/sanopy/cli/init_handler.py` — `init` flow (interactive prompts + CLI options). Catches `FileNotFoundError` / `ValueError` from `Config.load()` and falls back to `Config.defaults()` in memory, warning on the invalid-file case because saving overwrites it. Saves once after user confirms, then installs missing linters (prompted when interactive, automatic otherwise, never with `--no-install`) and exits `2` if any install fails.
- `src/sanopy/config.py` — `Config` dataclass, `load()` (read-only, raises on missing/invalid), `save()` (write-only), `exists()`, `defaults()`, `LinterConfig`, `DEFAULT_LINTER_CONFIGS` (pylint/bandit/ruff), `DEFAULT_IGNORED_CVES` / `DEFAULT_IGNORED_VULNS`. Values are normalized (strip, dedupe; CVEs/vulns uppercased).
- `src/sanopy/linters/<name>.py` — one module per linter (radon and pip-audit are linters too; include them when iterating over all of them), each a `BaseLinter` subclass with `name`, `package_name`, `module_name`, `build_command`, `parse_output` (populating `raw_severity` from the linter's native severity when it reports one).
- `src/sanopy/linters/base.py` — `BaseLinter` (holds `config`; `from_config()` instantiates it from the active config; `resolve_command()` is the single source of truth for how a linter is invoked, `is_available()` is defined in terms of it, `install()` runs pip/uv against `sys.executable`; `command_timeout` — default 120s — kills a hung subprocess, surfacing `LinterTimeoutError`), `AsyncCompletedProcess`, `InstallResult`, `LinterNotAvailableError`.
- `src/sanopy/linters/engine.py` — runs linters concurrently via asyncio.
- `src/sanopy/linters/config_discovery.py` — `is_test_path`, `materialize_linter_config`, `cleanup_materialized_configs`, `render_native_config`, `find_nearest_local_config`.
- `src/sanopy/linters/__init__.py` — **linters are discovered dynamically** (`LINTER_MAP` built by scanning the package). Adding a linter module in this directory auto-registers it; keep the import guarded with `# nosemgrep` as existing modules do.

## Non-obvious behavior

- `.sanopy.toml` is **tracked in git** and required — `sanopy scan` exits `2` when it is missing, telling the user to run `sanopy init`. Don't commit scan-induced churn in it.
- `DEFAULT_IGNORED_CVES` / `DEFAULT_IGNORED_VULNS` are **seeded into every user's** `.sanopy.toml` by `init`, and a file's `[safety]`/`[pip-audit]` section *replaces* them rather than extending. Suppressions for Sanopy's own environment go in this repo's `.sanopy.toml` only — never in the shipped defaults.
- `Config.load()` is **read-only** — it never creates or modifies files. Missing file → `FileNotFoundError`. Invalid TOML → `ValueError`. The `init_handler` catches both and creates defaults in memory; the scan handler exits `2`.
- Config resolution for ruff/pylint/bandit: nearest local config (searching upward from target to CWD, `pyproject.toml` only honored if it has `[tool.<name>]`) wins; otherwise bundled defaults are materialized from `[linters.<name>]` sections (falling back to `DEFAULT_LINTER_CONFIGS`) into a fresh, unique temp directory per call and passed via `--config`, then removed when the scan run ends (`Engine.run_all` calls `cleanup_materialized_configs`).
- `[linters.<name>.test]` tables override the `test` category only; `is_test_path` decides the category (a directory component named `tests` between the path and CWD, or a `test_*`/`*_test.py` filename).
- `BaseLinter.__init__(config=None, command_timeout=None)` — any subclass defining its own `__init__` must call `super().__init__()` or the self-scan flags pylint W0231.
- `BaseLinter.resolve_command()` tries three rungs in order: console script on `PATH`, console script beside `sys.executable` (reaches Sanopy's own env when its `bin/` is not on `PATH` — the only rung that finds a script-only linter there), then `python -m module_name`. `is_available()` is `resolve_command(...) is not None`, so the availability check can never disagree with the invocation — change them together. Set `module_name = None` for a package that rejects `python -m` (Semgrep does). `build_command()[0]` **must** equal `package_name`: `run()` drops that element and lets `resolve_command` supply the executable, so a mismatch silently swallows an argument. In tests, mock `is_available` on linter classes since linter binaries may not be installed.
- Diagnostics go to stderr, never `console` (stdout) — machine mode writes the JSON document to stdout, so anything else there corrupts it. The CLI layer prints via `err_console`; the linters layer logs via the `logging` module, wired to stderr by `logging.basicConfig(stream=sys.stderr)` in `cli.py`, so it never depends on the CLI. Escape interpolated dynamic text with `rich.markup.escape`, or Rich eats `[extras]` brackets and `[...]`-shaped paths.
- Findings carry the linter's native `raw_severity` when one is reported; `ScanReporter._normalize_severity` buckets it via `_RAW_TO_SEVERITY_BUCKET` (fatal/critical/high→error, medium→warning, low/note/hint/convention/refactor→info). A recognized `raw_severity` wins; otherwise the bucket falls back to the linter name (security/type linters → error) and then the code prefix (E/F/B → error, W/C/R → warning, else info). Linters with no severity concept (Ruff, Vulture, pip-audit, Radon) leave `raw_severity` as `None`.
- The active linter set is resolved **only** through `sanopy.cli.selection.resolve_active_linters`; `init` and `scan` must not keep private copies. Blank/separator-only filters (`--only "  "`, `--only ,`) mean "no filter", never "match nothing".
- An empty active set is an **error** (exit `2`), not an empty run. `--only rufff` or `--only x --skip x` would otherwise print "No issues found" and exit 0 — a green CI run that checked nothing.
- Tests live in flat modules under `tests/`. `tests/conftest.py` holds the shared `mock_scan_config` fixture, deliberately **not** autouse: patching `is_available` globally would hide real resolution behavior from `tests/test_linters_base.py`, which exercises it. CLI modules opt in with a one-line module-level autouse wrapper.
- pylint caps a module at 1000 lines (C0302) and the self-scan enforces it, so split large test modules instead of suppressing. `test_cli.py` is already near the cap; new CLI tests belong in `test_cli_scan_preflight.py`, `test_cli_init.py`, or a new module.
- Prefer `@pytest.mark.parametrize` with `pytest.param(..., id=...)` over near-duplicate test functions, and cover the edge cases (blank/whitespace/separator-only input, unknown names, both filters cancelling, non-zero exit codes, empty installer output).
- Async logic tested directly needs `@pytest.mark.asyncio`.
- Test linters by mocking `_run_command` and feeding canned `AsyncCompletedProcess(stdout=..., stderr="", returncode=0)` output (see `tests/test_linters_ruff.py`); mock `get_linter_context` when a linter calls it.
- Strict line-length 79; ruff format uses double quotes.

## Conventions

- Conventional commit messages (`feat:`, `fix:`, `docs:`, `chore:`, often scoped, e.g. `feat(config):`), feature branch per change, PR merged into `develop`.
- **Keep docs in step with behavior.** If a change alters the CLI contract (exit codes, output streams, config handling, how linters are located), update this file, `README.md`, and `CHANGELOG.md` in the same change. Skipping this is what let `.github/copilot-instructions.md` drift into describing a linter-invocation strategy that had already been replaced.
- Releases are **automated** by `.github/workflows/publish.yml`: merging a release PR into `main` builds, publishes to PyPI (Trusted Publishing), then pushes a `v<version>` tag and creates the GitHub Release. The only manual step is cutting the release branch and bumping the version there — see **Git Flow** above. Never publish by hand — it collides with Trusted Publishing and leaves the release untagged.
- Adding a linter means adding **two** entries to `[project.optional-dependencies]`: its own extra and its name inside the `all` extra. The module auto-registers in `LINTER_MAP` either way, so a missing `all` entry would silently ship an `sanopy[all]` that cannot run the full set (`tests/test_cli_selection.py` enforces both).
- Python 3.12 (`requires-python = ">=3.12"`); new code should keep 100% coverage of src type-checked under strict mypy.
- Running linters (ruff, pylint, bandit, mypy, pyright, semgrep, vulture, radon, safety, pip-audit) are **optional extras**, not runtime dependencies — the base install is `click` + `rich` only. They are run as subprocesses, never imported as tools. CI uses `uv sync --dev --extra all`.
- Lint findings are `LinterResult` dataclasses carrying `raw_severity` and a normalized `error`/`warning`/`info` bucket; output envelope `schema_version: "1.0.0"` is part of the public contract (tests assert on it).
- Tests should cover the **public API only** — `Config` (`exists`/`load`/`save`/`defaults`), `InitHandler`, `ConfigUpdater`, `Engine`, `BaseLinter` (`resolve_command`/`is_available`/`install`), `sanopy.cli.selection`, CLI commands via `CliRunner`. Do not test private (`_`-prefixed) functions directly, and do not patch them out either — drive the behaviour through the public surface (e.g. mock `is_available` rather than the install helpers).

## Documentation

- `README.md` — the user-facing manual: installation, CLI usage, exit codes, linter filtering and precedence, how linters are located, supported linters, configuration, troubleshooting.
- `CHANGELOG.md` — notable behavior changes, Keep a Changelog format. New work goes under `[Unreleased]`.
- `pyproject.toml` — lint/type/test tool settings and the linter extras.
- `.github/copilot-instructions.md` — a pointer to this file, nothing more. Guidance belongs here; that file only signposts it.
