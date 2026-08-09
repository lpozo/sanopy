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
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
pip install sanopy

# Optional with uv
uv venv .venv
uv pip install sanopy
```

## Quick Start

### 1. Configure

Sanopy always uses a local `.sanopy.toml` in the current project.

- If `.sanopy.toml` does not exist, Sanopy creates it automatically with defaults.
- Use `init` to customize settings manually or in automation.

```bash
# Interactive (manual)
sanopy init

# Non-interactive (CI/automation)
sanopy init --only ruff,mypy --skip bandit
```

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

## Linter Filtering

Run only selected linters:

```bash
sanopy scan . --only ruff,mypy
```

Skip selected linters:

```bash
sanopy scan . --skip safety
```

You can also set default `only_linters` and `skip_linters` values in
`.sanopy.toml` via `sanopy init`.

## Supported Linters

| Linter | Category | Detects |
| --- | --- | --- |
| [Ruff](https://github.com/astral-sh/ruff) | Style | PEP 8, imports, code smells |
| [Pylint](https://github.com/pylint-dev/pylint) | Style | Code quality, conventions |
| [Bandit](https://github.com/PyCQA/bandit) | Security | Common security vulnerabilities |
| [MyPy](https://github.com/python/mypy) | Typing | Static type checking |
| [Pyright](https://github.com/microsoft/pyright) | Typing | Advanced type inference |
| [Semgrep](https://github.com/semgrep/semgrep) | Semantic | Pattern-based analysis |
| [Vulture](https://github.com/jendrikseipp/vulture) | Dead code | Unused variables, functions |
| [Radon](https://github.com/rubik/radon) | Complexity | Cyclomatic complexity |
| [Safety](https://github.com/pyupio/safety) | Dependencies | Known vulnerabilities |

## Configuration File

The `.sanopy.toml` file controls linter defaults for the current project.

- Manual workflow: run `sanopy init` and answer prompts.
- CI/AI workflow: run `sanopy init --only ... --skip ...` in scripts.
- If the file is missing, Sanopy creates `.sanopy.toml` with defaults.

```toml
[linters]
only_linters = []
skip_linters = []

[safety]
ignore_cves = ["CVE-2026-0994"]
```

The `[safety]` section lists CVE IDs that the Safety linter should
suppress. By default a small set of known-unresolvable CVEs is ignored;
set `ignore_cves = []` to disable all suppressions.

Example CI step:

```yaml
steps:
  - name: Configure Sanopy
    run: sanopy init --only ruff,mypy --skip bandit
  - name: Run scan
    run: sanopy scan src/ tests/
```

## Development

Clone the repo and install dependencies:

```bash
git clone https://github.com/lpozo/sanopy.git
cd sanopy
uv sync
```

Run tests:

```bash
uv run pytest
```
