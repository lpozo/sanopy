"""Tests for Pylint linter."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.pylint import PylintLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.pylint.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> PylintLinter:
    """Pylint linter instance."""
    return PylintLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard success
        (
            json.dumps(
                [
                    {
                        "line": 1,
                        "column": 0,
                        "path": "test.py",
                        "symbol": "unused-import",
                        "message": "Unused import os",
                        "message-id": "W0611",
                    }
                ]
            ),
            1,
            "W0611",
        ),
        # Empty results
        ("[]", 0, None),
        # Null results
        ("null", 0, None),
        # Malformed JSON
        ("Crashed", 0, None),
        # Missing message-id falls back to the symbol
        (
            json.dumps(
                [
                    {
                        "line": 10,
                        "symbol": "some-error",
                        "message": "Something happened",
                    }
                ]
            ),
            1,
            "some-error",
        ),
        # Missing all optional fields falls back to Unknown
        (json.dumps([{"line": 3, "message": "Bare message"}]), 1, "Unknown"),
    ],
)
@pytest.mark.asyncio
async def test_pylint_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various Pylint parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(PylintLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].snippet_context == "snippet"


@pytest.mark.asyncio
async def test_pylint_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Pylint message."""
    stdout = json.dumps(
        [
            {
                "line": 8,
                "column": 4,
                "endLine": 12,
                "endColumn": 9,
                "path": "src/mod.py",
                "symbol": "too-many-args",
                "message": "Too many arguments",
                "message-id": "R0913",
            }
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(PylintLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("src/mod.py")
    assert result.line_start == 8
    assert result.line_end == 12
    assert result.col_start == 4
    assert result.col_end == 9
    assert result.error_code == "R0913"
    assert result.raw_severity == "refactor"
    assert result.message == "Too many arguments"


@pytest.mark.asyncio
async def test_pylint_reuses_content_per_file(
    mocker, linter, tmp_path
) -> None:
    """Pylint reuses one read of file content across multiple findings."""
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8")

    stdout = json.dumps(
        [
            {
                "line": 1,
                "column": 1,
                "path": str(mod),
                "message": "msg 1",
                "message-id": "E0001",
            },
            {
                "line": 2,
                "column": 1,
                "path": str(mod),
                "message": "msg 2",
                "message-id": "E0001",
            },
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(PylintLinter, "_run_command", return_value=mock_result)
    context_calls = []

    def _capture_content(**kwargs):
        context_calls.append(kwargs.get("content"))
        return ("snippet", 1, "context")

    mocker.patch(
        "sanopy.linters.pylint.get_linter_context",
        side_effect=_capture_content,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert context_calls == ["x = 1\n", "x = 1\n"]


@pytest.mark.parametrize("config_present", [False, True])
def test_pylint_build_command(mocker, tmp_path, config_present: bool) -> None:
    """Test that the Pylint command includes the rcfile when available."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    config_path = Path("/cfg/.pylintrc") if config_present else None
    mock_config = mocker.patch.object(
        PylintLinter, "_get_effective_config_path", return_value=config_path
    )

    cmd = PylintLinter().build_command(target)

    expected = ["pylint", "--output-format=json"]
    if config_present:
        expected += ["--rcfile=/cfg/.pylintrc"]

    assert cmd == expected + [str(target.absolute())]
    mock_config.assert_called_once_with(
        target, [".pylintrc", "pylintrc", "pyproject.toml"]
    )
