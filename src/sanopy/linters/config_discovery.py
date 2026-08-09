"""Logic for discovering linter configurations (local and bundled defaults)."""

# Python 3.7 compatibility rule is irrelevant: sanopy requires >=3.12.
from importlib import resources  # nosemgrep: python37-compatibility-importlib2
from pathlib import Path


def is_test_path(path: Path) -> bool:
    """Determine if a path belongs to test code.

    Args:
        path: The file or directory path.

    Returns:
        True if the path is likely test code, False otherwise.
    """
    path_str = str(path.absolute())
    # Common test directory and filename patterns
    return (
        "tests/" in path_str
        or "/tests" in path_str
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def get_bundled_config_path(linter_name: str, category: str) -> Path | None:
    """Retrieve the path to a bundled configuration file.

    Args:
        linter_name: The name of the linter (e.g., 'pylint', 'bandit', 'ruff').
        category: The code category ('default' or 'test').

    Returns:
        A Path to the bundled config file, or None if not found.
    """
    filename_map = {
        "pylint": ".pylintrc",
        "bandit": "bandit.yaml",
        "ruff": "ruff.toml",
    }
    filename = filename_map.get(linter_name.lower())
    if not filename:
        return None

    try:
        # Construct resource package path
        resource_pkg = f"sanopy.linters.configs.{category}"
        # When installed as a regular package, we can get the path directly.
        # importlib.resources.files() is the modern way.
        resource_path = resources.files(resource_pkg).joinpath(filename)
        # We need an actual file path.
        # If it's a real file (not in zip), .resolve() gives
        # us the absolute path.
        if resource_path.is_file():
            # In local development and most installations, it's a real file.
            return Path(str(resource_path))

        return None
    except (ImportError, FileNotFoundError, TypeError):
        return None


def find_nearest_local_config(
    target: Path, filenames: list[str], linter_name: str | None = None
) -> Path | None:
    """Search upward for the nearest local config file up to the project root.

    Args:
        target: The file or directory to scan.
        filenames: Candidate filenames to look for.
        linter_name: Optional linter name to verify sections in pyproject.toml.

    Returns:
        The path to the nearest config file, or None.
    """
    curr = target.absolute()
    if not curr.is_dir():
        curr = curr.parent

    # We stop at the project root (assumed to be CWD)
    stop_at = Path.cwd().absolute()

    while True:
        for filename in filenames:
            candidate = curr / filename
            if candidate.exists():
                # Special check for pyproject.toml: it must contain
                # the linter section
                if filename == "pyproject.toml" and linter_name:
                    if _has_linter_section(candidate, linter_name):
                        return candidate
                    continue  # Skip this pyproject.toml and look for others
                return candidate

        if curr in (stop_at, curr.parent):
            break
        curr = curr.parent

    return None


def _has_linter_section(path: Path, linter_name: str) -> bool:
    """Check if a pyproject.toml file has a section for the given linter.

    Args:
        path: Path to the ``pyproject.toml`` file.
        linter_name: The linter name to look for (e.g., ``"ruff"``).

    Returns:
        True if a ``[tool.<linter_name>]`` section exists, False otherwise.
    """
    try:
        content = path.read_text(encoding="utf-8")
        # Crude check to avoid full TOML parsing dependency if possible,
        # but reliable enough for [tool.<linter>]
        section = f"[tool.{linter_name.lower()}]"
        return section in content
    except OSError:
        return False
