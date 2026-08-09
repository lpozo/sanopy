# Sanopy

Sanopy is distributed as a Python package and CLI tool for orchestrating multiple linters in Python projects.

## Publishing to PyPI

1. **Check version**: Update the `version` field in `pyproject.toml`.
2. **Build the package**:
   ```bash
   uv build
   ```
3. **Check the build** (optional):
   ```bash
   uvx twine check dist/*
   ```
4. **Publish**:
   ```bash
   uvx twine upload dist/*
   ```

## Notes
- The package is built with Hatchling; `README.md`, `LICENSE`, and `src/sanopy/py.typed` are included automatically.
- The CLI entry point is defined in `pyproject.toml` as `sanopy = "sanopy.__main__:main"`.
- Requires Python 3.12+.

## Post-publish smoke test

After publishing, validate the PyPI package in a clean environment:

```bash
python -m venv .venv-smoke
source .venv-smoke/bin/activate
pip install sanopy
sanopy --help
sanopy init --only ruff,mypy --skip bandit
sanopy scan src/
```

This confirms that the PyPI install works and `.sanopy.toml` is created/used correctly.

For more details, see the [PyPI packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
