# LintAIder

LintAIder is a CLI tool for improving Python code quality. It runs multiple linters concurrently and aggregates findings into a single JSON report.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
uv venv .venv
uv add lintaider
```

## Quick Start

### 1. Initialize

```bash
uv run lintaider init
```

### 2. Scan a Codebase

```bash
uv run lintaider scan src/
```

Verbose output that prints every finding with code context:

```bash
uv run lintaider scan src/ -v
```

Generate a human-readable Markdown report:

```bash
uv run lintaider scan src/ --human-readable
```

Save results to a custom file:

```bash
uv run lintaider scan src/ -o my-scan.json
```

## Linter Filtering

Run only selected linters:

```bash
uv run lintaider scan . --only ruff,mypy
```

Skip selected linters:

```bash
uv run lintaider scan . --skip safety
```

You can also set default `only_linters` and `skip_linters` values in
`lintaider.toml` via `uv run lintaider init`.

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

The `lintaider.toml` file (created by `lintaider init`) controls linter defaults.

## Development

Clone the repo and install dependencies:

```bash
git clone https://github.com/lpozo/lintaider.git
cd lintaider
uv sync
```

Run tests:

```bash
uv run pytest
```
