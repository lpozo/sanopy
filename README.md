# Sanopy

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

By default, machine-readable JSON is printed to stdout.

You can now scan multiple directories or files at once:

```bash
sanopy scan src/ tests/
```

Generate a human-readable Markdown report:

```bash
sanopy scan src/ --human-readable
```

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
