# Sanopy

<div align="center">

[![CI](https://github.com/lpozo/sanopy/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/lpozo/sanopy/actions/workflows/pr-checks.yml)
[![PyPI - Version](https://img.shields.io/pypi/v/sanopy)](https://pypi.org/project/sanopy/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/sanopy)](https://pypi.org/project/sanopy/)
[![Ruff](https://img.shields.io/badge/linting-ruff-D7FF64?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
[![Mypy](https://img.shields.io/badge/typing-mypy-2a6db2)](https://github.com/python/mypy)
[![Pyright](https://img.shields.io/badge/typing-pyright-2a6db2)](https://github.com/microsoft/pyright)
[![License](https://img.shields.io/github/license/lpozo/sanopy)](https://github.com/lpozo/sanopy/blob/main/LICENSE)

</div>

Sanopy is a CLI tool for improving Python code quality. It runs multiple linters concurrently and emits findings as JSON to stdout.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — optional. Sanopy uses it to
  install linters when present, and falls back to `pip` otherwise.

## Installation

```bash
# Core only (click + rich); linters installed later by `sanopy init`
pip install sanopy

# Or pull in every linter up front
pip install 'sanopy[all]'

# Or pick just the ones you want
pip install 'sanopy[ruff,mypy]'

# Optional with uv
uv venv .venv
uv pip install 'sanopy[all]'
```

Each linter is an optional extra, so the base install stays small. Extra
names match the linter names: `ruff`, `pylint`, `bandit`, `mypy`,
`pyright`, `semgrep`, `vulture`, `radon`, `safety`, `pip-audit`, plus
`all`.

## Quick Start

### 1. Initialize

Sanopy requires a `.sanopy.toml` configuration file in your project.
Run `init` to create it and install the linters you need:

```bash
# Interactive (manual) — prompts before installing anything
sanopy init

# Non-interactive (CI/automation) — installs missing linters directly
sanopy init --only ruff,mypy --skip bandit

# Write the config only, never touch the environment
sanopy init --only ruff,mypy --no-install
```

`init` installs any selected linter that is not already available, into
the same environment Sanopy runs from. The interactive flow asks first;
the non-interactive flow just does it, so pass `--no-install` if your
pipeline manages dependencies itself. `init` exits `2` if an install
fails, so a following `scan` will not run against a half-built
environment.

If you run `sanopy scan` before initializing, Sanopy will tell you to
run `sanopy init` first and exit `2`.

### 2. Scan a Codebase

```bash
sanopy scan src/
```

By default, machine-readable JSON is printed to stdout in a versioned
envelope:

```json
{
  "schema_version": "1.0.0",
  "run": {
    "target": "src",
    "generated_at": "2026-08-09T00:00:00+00:00",
    "active_linters": ["ruff", "pylint", "mypy"],
    "finding_count": 0
  },
  "findings": []
}
```

Use human output mode for terminal-friendly progress and summaries:

```bash
sanopy scan src/ --output-mode human
```

You can scan multiple directories or files at once:

```bash
sanopy scan src/ tests/
```

When scanning multiple targets, the results are merged into a single JSON
document, and `run.target` becomes an array of the scanned paths.

Generate a human-readable Markdown report:

```bash
sanopy scan src/ --human-readable
```

The report is saved as `linting-report-<target>.md` (e.g.,
`linting-report-src.md`).

Save results to a custom file:

```bash
sanopy scan src/ -o my-scan.json
```

## Exit Codes

`sanopy scan` distinguishes "clean" from "could not check", so a failed
run never looks like a passing one:

| Code | Meaning |
| --- | --- |
| `0` | Scan completed, no findings |
| `1` | Scan completed, findings reported |
| `2` | Scan could not run, or crashed |

Exit `2` covers a missing or unreadable `.sanopy.toml`, a selected linter
that is not installed, filters that select no linters at all, and an
unexpected error during the scan. Every case prints its reason to
**stderr**, so stdout stays a valid JSON document.

`sanopy init` exits `0` on success and `2` if a linter installation
fails, so `sanopy init && sanopy scan src/` will not scan against a
half-built environment.

## Linter Filtering

Run only selected linters:

```bash
sanopy scan . --only ruff,mypy
```

Skip selected linters:

```bash
sanopy scan . --skip safety
```

Names are case-insensitive and surrounding whitespace is ignored, so
`--only " Ruff , MyPy "` works.

You can also set default `only_linters` and `skip_linters` values in
`.sanopy.toml` via `sanopy init`.

**Precedence.** Each CLI flag replaces its own counterpart in
`.sanopy.toml`, but not the other one. Given `skip_linters = ["ruff"]` in
the config, `--only ruff,mypy` runs only `mypy`: the CLI `--only`
replaced `only_linters`, while the config's `skip_linters` still applies.
Pass `--skip` explicitly to override it. `--only` is applied before
`--skip`, so a linter named in both is skipped.

**Selecting nothing is an error.** If the filters leave no linters to
run, Sanopy exits `2` instead of reporting a clean scan, and names any
unrecognised linter:

```console
$ sanopy scan src/ --only rufff
No linters selected.
Unknown linter name(s): rufff
Available: bandit, mypy, pip-audit, pylint, pyright, radon, ruff, safety, semgrep, vulture
```

## How Sanopy Finds Linters

Linters run as subprocesses, never as imports. For each one, Sanopy tries
in order:

1. The console script on `PATH` (e.g. `ruff`).
2. The console script next to the running Python interpreter — this
   reaches Sanopy's own environment even when its `bin/` directory is not
   on `PATH`, as with a non-activated virtualenv, `pipx`, or `uv tool`.
3. `python -m <module>` in that same interpreter, for linters that
   support it.

A linter is reported as missing only when all three fail, and `scan`
then exits `2` rather than silently skipping it.

## Supported Linters

The `Name` column is what you pass to `--only`/`--skip`; the `Extra`
column is what you pass to `pip install 'sanopy[...]'`.

| Linter | Name | Extra | Category | Detects |
| --- | --- | --- | --- | --- |
| [Ruff](https://github.com/astral-sh/ruff) | `ruff` | `ruff` | Style | PEP 8, imports, code smells |
| [Pylint](https://github.com/pylint-dev/pylint) | `pylint` | `pylint` | Style | Code quality, conventions |
| [Bandit](https://github.com/PyCQA/bandit) | `bandit` | `bandit` | Security | Common security vulnerabilities |
| [MyPy](https://github.com/python/mypy) | `mypy` | `mypy` | Typing | Static type checking |
| [Pyright](https://github.com/microsoft/pyright) | `pyright` | `pyright` | Typing | Advanced type inference |
| [Semgrep](https://github.com/semgrep/semgrep) | `semgrep` | `semgrep` | Semantic | Pattern-based analysis |
| [Vulture](https://github.com/jendrikseipp/vulture) | `vulture` | `vulture` | Dead code | Unused variables, functions |
| [Radon](https://github.com/rubik/radon) | `radon` | `radon` | Complexity | Cyclomatic complexity |
| [Safety](https://github.com/pyupio/safety) | `safety` | `safety` | Dependencies | Known vulnerabilities |
| [pip-audit](https://github.com/pypa/pip-audit) | `pip-audit` | `pip-audit` | Dependencies | Known vulnerabilities in dependency tree |

Semgrep is the one linter that cannot be run as `python -m semgrep`, so
it must be reachable as a console script (step 1 or 2 above).

## Configuration File

The `.sanopy.toml` file controls linter defaults for the current project.

- Manual workflow: run `sanopy init` and answer prompts.
- CI/AI workflow: run `sanopy init --only ... --skip ...` in scripts.
- The file is required — `sanopy scan` exits `2` if it is missing.
- Diagnostics (missing config, missing linters, scan failures) go to
  stderr, so stdout stays a valid JSON document in machine mode.

```toml
[linters]
only_linters = []
skip_linters = []

[linters.pylint]
disable = ["duplicate-code", "too-many-locals"]

[linters.bandit]
skips = []

[linters.ruff]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "SIM", "PTH"]
ignore = []

[safety]
ignore_cves = ["CVE-2026-0994"]

[pip-audit]
ignore_vulns = ["PYSEC-2026-3482"]
```

The `[safety]` section lists CVE IDs that the Safety linter should
suppress. By default a small set of known-unresolvable CVEs is ignored;
set `ignore_cves = []` to disable all suppressions.

The `[pip-audit]` section lists vulnerability IDs (or aliases) that the
pip-audit linter should suppress, matched by primary ID or alias.

Both suppression lists **replace** the built-in defaults rather than
adding to them, so whatever you write is exactly what gets suppressed.
`sanopy init` seeds the file with the defaults so you can see and edit
them.

The optional `[linters.<name>]` sections provide the configuration that
Sanopy passes to linters shipping bundled defaults (`pylint`, `bandit`,
and `ruff`). A nested `[linters.<name>.test]` table overrides the
settings used for test code. Sections and keys you omit fall back to the
bundled defaults; a freshly generated `.sanopy.toml` materializes all of
them so they are visible and editable.

Example CI step:

```yaml
steps:
  - name: Configure Sanopy
    run: sanopy init --only ruff,mypy --skip bandit
  - name: Run scan
    run: sanopy scan src/ tests/
```

## Troubleshooting

**`No .sanopy.toml found.`** — Run `sanopy init` in the project root.
`scan` never creates the file for you.

**`Missing linters: ...`** — The named linters are not installed in the
environment Sanopy runs from. Install them with the suggested command
(`pip install 'sanopy[ruff,mypy]'`), or re-run `sanopy init`, which
offers to install whatever is missing.

**`No linters selected.`** — Your `--only`/`--skip` flags, or the
`only_linters`/`skip_linters` values in `.sanopy.toml`, cancel out or name
a linter that does not exist. The message lists the valid names.

**A linter is killed after running for 120 seconds** — a linter subprocess
that hangs (or runs longer than the 120s timeout) is killed so the scan can
finish, and the failure is reported on stderr. The other linters' results
are unaffected.

**Empty or malformed JSON on stdout** — Sanopy writes only the JSON
document to stdout; everything else goes to stderr. If you are capturing
output, redirect the two separately: `sanopy scan src/ > out.json`.

## Development

Clone the repo and install dependencies, including every linter extra:

```bash
git clone https://github.com/lpozo/sanopy.git
cd sanopy
uv sync --dev --extra all
```

The linters are optional extras, so a plain `uv sync` leaves them out and
the self-scan below will not run.

Run the checks:

```bash
uv run pytest                        # test suite
uv run ruff check .                  # lint
uv run ruff format --check .         # formatting
uv run mypy src tests                # type check
uv run pyright src tests             # type check
uv run radon cc -n C src tests -s    # complexity
uv run sanopy scan src tests         # dogfood: must report 0 findings
```

See [AGENTS.md](AGENTS.md) for architecture notes and repo conventions.
