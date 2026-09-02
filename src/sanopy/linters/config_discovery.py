"""Logic for discovering linter configurations (local and bundled defaults)."""

from __future__ import annotations

import json
import tempfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sanopy.config import LinterConfig

BUNDLED_FILENAME_MAP = {
    "pylint": ".pylintrc",
    "bandit": "bandit.yaml",
    "ruff": "ruff.toml",
}

_materialized_config_dirs: set[Path] = set()


def is_test_path(path: Path) -> bool:
    """Determine if a path belongs to test code.

    A path is test code when its filename follows a ``test_*`` /
    ``*_test.py`` pattern, or when a directory literally named ``tests``
    sits between the path and the project root (CWD). Matching is done on
    exact path components so a project merely *living under* a directory
    named ``tests`` is not misclassified.

    Args:
        path: The file or directory path.

    Returns:
        True if the path is likely test code, False otherwise.
    """
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True

    current = path.absolute()
    stop_at = Path.cwd().absolute()
    while True:
        if current.name == "tests":
            return True
        if current in (stop_at, current.parent):
            break
        current = current.parent
    return False


def materialize_linter_config(
    linter_name: str,
    category: str,
    linter_config: LinterConfig,
) -> Path | None:
    """Render and write a linter's native config from structured settings.

    Each call writes to a fresh, unique temporary directory so concurrent
    scans can never race on a shared path. The created directory is
    tracked and can be removed with ``cleanup_materialized_configs``.

    Args:
        linter_name: The lowercase linter name (e.g., 'pylint', 'ruff').
        category: The code category ('default' or 'test').
        linter_config: The configured settings to render.

    Returns:
        The path to the written config file, or None when the linter has
        no bundled config format.
    """
    if linter_name not in BUNDLED_FILENAME_MAP:
        return None

    content = render_native_config(
        linter_name, linter_config.effective(category)
    )
    if content is None:
        return None

    config_dir = Path(tempfile.mkdtemp(prefix=f"sanopy-{category}-"))
    path = config_dir / BUNDLED_FILENAME_MAP[linter_name]
    path.write_text(content, encoding="utf-8")
    _materialized_config_dirs.add(config_dir)
    return path


def cleanup_materialized_configs() -> int:
    """Remove every temporary directory created during materialization.

    Safe to call repeatedly: directories already removed are ignored.

    Returns:
        The number of directories removed.
    """
    removed = 0
    while _materialized_config_dirs:
        config_dir = _materialized_config_dirs.pop()
        try:
            config_dir.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError:
            try:
                for child in config_dir.iterdir():
                    child.unlink()
                config_dir.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


def render_native_config(
    linter_name: str, settings: dict[str, list[str]]
) -> str | None:
    """Render native config file content for a linter.

    Args:
        linter_name: The lowercase linter name (e.g., 'pylint', 'ruff').
        settings: The effective settings for the category.

    Returns:
        The config file content, or None for unsupported linters.
    """
    if linter_name == "pylint":
        disable = settings.get("disable") or []
        return f"[MESSAGES CONTROL]\ndisable={','.join(disable)}\n"
    if linter_name == "bandit":
        skips = settings.get("skips") or []
        return f"skips: {skips!r}\n"
    if linter_name == "ruff":
        lines = ["[lint]"]
        for key in ("select", "ignore"):
            if key in settings:
                lines.append(f"{key} = {json.dumps(settings[key])}")
        return "\n".join(lines) + "\n"
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
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return False
    return linter_name.lower() in tool
