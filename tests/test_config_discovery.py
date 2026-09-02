"""Tests for linter config discovery and materialization."""

# pylint: disable=protected-access  # tests exercise the private helper

from pathlib import Path

import pytest

from sanopy.config import Config, LinterConfig
from sanopy.linters.config_discovery import (
    cleanup_materialized_configs,
    find_nearest_local_config,
    is_test_path,
    materialize_linter_config,
)
from sanopy.linters.ruff import RuffLinter


@pytest.mark.parametrize(
    "rel_path, expected",
    [
        pytest.param("app.py", False, id="plain-file"),
        pytest.param("tests/test_app.py", True, id="file-under-tests-dir"),
        pytest.param("tests/shared.py", True, id="shared-file-under-tests"),
        pytest.param("tests/sub/test_x.py", True, id="nested-under-tests"),
        pytest.param("test_app.py", True, id="test-prefix"),
        pytest.param("helpers.py", False, id="non-test-module"),
    ],
)
def test_is_test_path_under_project(
    tmp_path: Path, monkeypatch, rel_path, expected
) -> None:
    """is_test_path classifies files relative to the project root (CWD)."""
    monkeypatch.chdir(tmp_path)
    project_file = tmp_path / rel_path
    project_file.parent.mkdir(parents=True, exist_ok=True)
    project_file.write_text("x = 1\n", encoding="utf-8")

    assert is_test_path(project_file) is expected


def test_is_test_path_project_under_tests_dir_is_not_test_code(
    tmp_path: Path, monkeypatch
) -> None:
    """A project living under a directory named 'tests' is not test code."""
    project = tmp_path / "tests" / "project"
    project.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(project)
    app = project / "app.py"
    app.write_text("x = 1\n", encoding="utf-8")

    assert is_test_path(app) is False


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


def test_materialized_config_paths_are_unique_per_call() -> None:
    """Repeated materialization must not race on a shared path.

    Two scans in the same category used to write to the same deterministic
    path under ``$TMPDIR``, so concurrent scans could clobber each other.
    Each call must produce a distinct file.
    """
    linter_config = LinterConfig(settings={"disable": ["C0415"]})
    path_a = materialize_linter_config("pylint", "default", linter_config)
    path_b = materialize_linter_config("pylint", "default", linter_config)
    try:
        assert path_a is not None and path_b is not None
        assert path_a != path_b
        assert path_a.read_text(encoding="utf-8") == (
            "[MESSAGES CONTROL]\ndisable=C0415\n"
        )
        assert path_b.read_text(encoding="utf-8") == (
            "[MESSAGES CONTROL]\ndisable=C0415\n"
        )
    finally:
        cleanup_materialized_configs()


def test_cleanup_materialized_configs_removes_created_files() -> None:
    """Cleanup removes every file created by materialize_linter_config."""
    paths = [
        materialize_linter_config(
            "pylint", "default", LinterConfig(settings={"disable": ["C0415"]})
        ),
        materialize_linter_config(
            "ruff", "default", LinterConfig(settings={"select": ["E"]})
        ),
    ]
    non_null = [p for p in paths if p is not None]
    assert len(non_null) == len(paths)
    assert all(p.exists() for p in non_null)

    removed = cleanup_materialized_configs()

    assert removed == len(paths)
    assert all(not p.exists() for p in non_null)


def test_cleanup_materialized_configs_is_idempotent() -> None:
    """Running cleanup again after an empty registry removes nothing."""
    materialize_linter_config(
        "pylint", "default", LinterConfig(settings={"disable": ["C0415"]})
    )
    cleanup_materialized_configs()
    assert cleanup_materialized_configs() == 0


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
