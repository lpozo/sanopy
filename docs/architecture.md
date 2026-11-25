# Architecture

Sanopy is a Python 3.12 CLI that runs external linters as subprocesses and
emits one versioned JSON document on stdout. This file is the quick map for
contributors and coding agents. `AGENTS.md` holds the binding rules and the
full list of non-obvious invariants.

## Start here

| Question | File |
| --- | --- |
| How does a CLI invocation begin? | `src/sanopy/cli/cli.py` |
| Where are run-level guards applied? | `src/sanopy/cli/scan_handler.py` (`preflight`) |
| Which linters are active? | `src/sanopy/cli/selection.py` |
| How are linters invoked? | `src/sanopy/linters/base.py` (`resolve_command`) |
| How does a finding get its snippet and context? | `src/sanopy/linters/context.py` |
| How are linters discovered? | `src/sanopy/linters/__init__.py` |

## Data flow

1. `cli.py` parses `init` or `scan`. Diagnostics go to stderr; stdout is
   reserved for the JSON payload.
2. `scan_handler.preflight()` runs once per invocation: config guard →
   `Config.load()` → resolve active linters → non-empty guard → availability
   check. Any failure exits `2`.
3. `Engine.run_all()` runs the active linters concurrently. A shared
   `asyncio.Semaphore` caps subprocess concurrency for multi-target scans.
4. Each linter's `parse_output()` converts tool output into `LinterResult`
   objects. Context-using linters create one `ContentCache` per parse and
   pass it to `get_linter_context(..., cache=cache)`.
5. `ScanReporter` normalizes severities, merges targets, and writes the
   `schema_version: "1.0.0"` envelope to stdout. Exit is `0` for clean,
   `1` for findings, `2` for "could not run".

## Module map

| Path | Responsibility |
| --- | --- |
| `src/sanopy/cli/cli.py` | Click entrypoint; logging to stderr; exit codes |
| `src/sanopy/cli/init_handler.py` | Interactive/non-interactive `init` flow |
| `src/sanopy/cli/scan_handler.py` | `preflight()` and per-target scan orchestration |
| `src/sanopy/cli/selection.py` | The single owner of linter selection |
| `src/sanopy/cli/reporter.py` | Severity bucketing and JSON envelope |
| `src/sanopy/cli/ui.py` | `console` (stdout) and `err_console` (stderr) |
| `src/sanopy/config.py` | Read-only load, atomic save, defaults, normalization |
| `src/sanopy/linters/base.py` | `BaseLinter`, command resolution, install, timeout |
| `src/sanopy/linters/engine.py` | Async execution and per-instance temp cleanup |
| `src/sanopy/linters/config_discovery.py` | Local config discovery and materialization |
| `src/sanopy/linters/<name>.py` | One adapter per linter; auto-registered |
| `src/sanopy/linters/context.py` | File reads, AST/block cache, snippet extraction |
| `src/sanopy/render.py` | Terminal rendering of the JSON report |

## Contracts and invariants

- `resolve_command()` is the only source of truth for linter invocation.
  `is_available()` is defined in terms of it, so they can never disagree.
- `build_command()[0]` must equal `package_name`; `run()` drops that element
  and lets `resolve_command()` supply the executable.
- A linter subclass with its own `__init__` must call `super().__init__()`.
- Adding a linter module under `src/sanopy/linters/` auto-registers it in
  `LINTER_MAP`. Also add its own extra and its name in the `all` extra.
- stdout carries the JSON document only. Use `err_console` or `logging` for
  everything else, and escape interpolated text with `rich.markup.escape`.
- An empty active linter set is an error, not a clean scan.
- `Config.load()` never writes. Missing, invalid, and unreadable configs are
  distinct cases.

## Performance model

- Linter subprocess startup dominates a normal scan. The in-process work is
  kept linear in findings with constant-time lookups per finding.
- `ContentCache` is created once per `parse_output()` call. It caches file
  reads, failed reads, the parsed AST, and a line-to-semantic-block index.
- `get_linter_context(..., cache=content_cache)` is the preferred path. The
  older `content=` argument remains for callers that only have pre-read
  text. Do not reintroduce an `ast.walk()` per finding.
- A local 600-finding Ruff parse dropped from ~2.25s to ~0.007s after the
  block index was introduced. Config discovery measured ~0.0035s for 100
  calls and is not a bottleneck.

## Adding a linter

1. Create `src/sanopy/linters/<name>.py` with a `BaseLinter` subclass.
2. Set `name`, `package_name`, `module_name`, and `build_command()`.
3. Implement `parse_output()` and populate `raw_severity` when the tool
   reports one.
4. Add `<name>` and `<name>` inside `all` to
   `[project.optional-dependencies]` in `pyproject.toml`.
5. Add tests that mock `_run_command` with canned
   `AsyncCompletedProcess(stdout=..., stderr="", returncode=0)` output.
6. Update `README.md`, `AGENTS.md`, and `CHANGELOG.md`.

## Verification

Run all checks after changing code:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pyright src tests
uv run radon cc -n C src tests -s
uv run sanopy scan src tests
```

The full self-scan includes dependency-audit linters and may report findings
from the project's own environment. For code-only regressions, restrict the
scan to source linters with `--only`.
