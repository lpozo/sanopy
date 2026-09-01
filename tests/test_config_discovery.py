"""Tests for linter config discovery and materialization."""

# pylint: disable=protected-access  # tests exercise the private helper

from pathlib import Path

from sanopy.config import Config, LinterConfig
from sanopy.linters.config_discovery import (
    find_nearest_local_config,
    materialize_linter_config,
)
from sanopy.linters.ruff import RuffLinter


def _write_pyproject(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_pyproject_tool_section_is_detected(tmp_path: Path) -> None:
    path = _write_pyproject(
        tmp_path, "[project]\nname = 'x'\n\n[tool.ruff]\nline-length = 79\n"
    )
    found = find_nearest_local_config(tmp_path, ["pyproject.toml"], "ruff")
    assert found == path


def test_pyproject_section_in_comment_is_not_detected(tmp_path: Path) -> None:
    _write_pyproject(
        tmp_path,
        "[project]\nname = 'x'\n# [tool.ruff]\n[tool.pylint]\n",
    )
    assert (
        find_nearest_local_config(tmp_path, ["pyproject.toml"], "ruff") is None
    )


def test_pyproject_section_in_string_is_not_detected(tmp_path: Path) -> None:
    _write_pyproject(
        tmp_path, "[project]\ndescription = 'see [tool.ruff] docs'\n"
    )
    assert (
        find_nearest_local_config(tmp_path, ["pyproject.toml"], "ruff") is None
    )


def test_pyproject_without_tool_table_is_not_detected(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "[project]\nname = 'x'\n")
    assert (
        find_nearest_local_config(tmp_path, ["pyproject.toml"], "ruff") is None
    )


def test_materialize_pylint_config() -> None:
    path = materialize_linter_config(
        "pylint",
        "default",
        LinterConfig(settings={"disable": ["C0415", "W0621"]}),
    )
    assert path is not None
    assert path.read_text(encoding="utf-8") == (
        "[MESSAGES CONTROL]\ndisable=C0415,W0621\n"
    )


def test_materialize_bandit_config_applies_test_overrides() -> None:
    path = materialize_linter_config(
        "bandit",
        "test",
        LinterConfig(settings={"skips": []}, test={"skips": ["B101"]}),
    )
    assert path is not None
    assert path.read_text(encoding="utf-8") == "skips: ['B101']\n"


def test_materialize_ruff_config_renders_valid_toml() -> None:
    path = materialize_linter_config(
        "ruff",
        "default",
        LinterConfig(settings={"select": ["E", "F"], "ignore": ["S101"]}),
    )
    assert path is not None
    assert path.read_text(encoding="utf-8") == (
        '[lint]\nselect = ["E", "F"]\nignore = ["S101"]\n'
    )


def test_materialize_unknown_linter_returns_none() -> None:
    assert materialize_linter_config("mypy", "default", LinterConfig()) is None


def test_get_effective_config_prefers_local_config(tmp_path: Path) -> None:
    local = tmp_path / "ruff.toml"
    local.write_text("local", encoding="utf-8")
    config = Config(
        linter_configs={"ruff": LinterConfig(settings={"select": ["E"]})}
    )
    linter = RuffLinter(config=config)
    target = tmp_path / "app.py"
    assert linter._get_effective_config_path(target, ["ruff.toml"]) == local


def test_get_effective_config_materializes_from_config(
    tmp_path: Path,
) -> None:
    config = Config(
        linter_configs={
            "ruff": LinterConfig(
                settings={"select": ["E", "F"], "ignore": ["S101"]}
            )
        }
    )
    linter = RuffLinter(config=config)
    target = tmp_path / "app.py"
    path = linter._get_effective_config_path(target, ["ruff.toml"])
    assert path is not None and path.exists()
    assert 'select = ["E", "F"]' in path.read_text(encoding="utf-8")


def test_get_effective_config_uses_defaults_without_config(
    tmp_path: Path,
) -> None:
    linter = RuffLinter()
    target = tmp_path / "app.py"
    path = linter._get_effective_config_path(target, ["ruff.toml"])
    assert path is not None and path.exists()
