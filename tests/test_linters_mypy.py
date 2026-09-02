"""Tests for MyPy linter."""

from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.mypy import MyPyLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.mypy.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> MyPyLinter:
    """MyPy linter instance."""
    return MyPyLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code, first_line, first_severity",
    [
        # Standard error matching
        (
            "test.py:1:5: error: Incompatible types [assignment]\n",
            1,
            "assignment",
            1,
            "error",
        ),
        # Multiple errors
        (
            "file1.py:10:1: error: Error 1 [err1]\n"
            "file1.py:20:5: error: Error 2 [err2]\n",
            2,
            "err1",
            10,
            "error",
        ),
        # Warning severity matches
        (
            "file.py:3:1: warning: X [warn-code]\n",
            1,
            "warn-code",
            3,
            "warning",
        ),
        # Note severity matches
        ("file.py:4:1: note: X [note-code]\n", 1, "note-code", 4, "note"),
        # Empty output
        ("", 0, None, None, None),
        # Noise and summary lines (unmatched)
        (
            "Success: no issues found\n"
            "Some random noise\n"
            "test.py:1:1: error: Real error [code]\n",
            1,
            "code",
            1,
            "error",
        ),
        # Missing error code does not match the regex
        (
            "test.py:1:1: error: Something without code\n",
            0,
            None,
            None,
            None,
        ),
        # Blank and whitespace-only lines are skipped before matching
        (
            "\n   \n\ttest.py:2:1: error: Indented error [E]\n\n"
            "test.py:3:1: error: Another [F]\n",
            2,
            "E",
            2,
            "error",
        ),
    ],
)
@pytest.mark.asyncio
async def test_mypy_scenarios(
    mocker,
    linter,
    stdout,
    expected_count,
    first_error_code,
    first_line,
    first_severity,
) -> None:
    """Test various MyPy parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=1)
    mocker.patch.object(MyPyLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].line_start == first_line
        assert results[0].raw_severity == first_severity
        assert results[0].snippet_context == "snippet"


@pytest.mark.asyncio
async def test_mypy_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a MyPy diagnostic."""
    stdout = (
        "src/mod.py:12:7: error: Incompatible types in assignment "
        "[assignment]\n"
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=1)
    mocker.patch.object(MyPyLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("src/mod.py")
    assert result.line_start == 12
    assert result.line_end == 12
    assert result.col_start == 7
    assert result.col_end is None
    assert result.error_code == "assignment"
    assert result.raw_severity == "error"
    assert "Incompatible types" in result.message


@pytest.mark.asyncio
async def test_mypy_ignores_stderr(mocker, linter) -> None:
    """Test that diagnostics on stderr are not parsed."""
    mock_result = AsyncCompletedProcess(
        stdout="", stderr="file.py:1:1: error: X [code]\n", returncode=1
    )
    mocker.patch.object(MyPyLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert results == []


@pytest.mark.asyncio
async def test_mypy_reuses_content_per_file(mocker, linter, tmp_path) -> None:
    """MyPy reuses one read of file content across multiple findings."""
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8")

    stdout = (
        f"{mod}:1:1: error: Error 1 [err1]\n{mod}:2:1: error: Error 2 [err2]\n"
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=1)
    mocker.patch.object(MyPyLinter, "_run_command", return_value=mock_result)
    context_calls = []

    def _capture_content(**kwargs):
        context_calls.append(kwargs.get("content"))
        return ("snippet", 1, "context")

    mocker.patch(
        "sanopy.linters.mypy.get_linter_context",
        side_effect=_capture_content,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert context_calls == ["x = 1\n", "x = 1\n"]


def test_mypy_build_command(tmp_path) -> None:
    """Test the MyPy command construction."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    assert MyPyLinter().build_command(target) == [
        "mypy",
        "--show-column-numbers",
        "--show-error-codes",
        "--no-error-summary",
        str(target.absolute()),
    ]
