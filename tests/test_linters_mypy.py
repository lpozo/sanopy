"""Tests for MyPy linter using parametrization."""

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
    "stdout, expected_count, first_error_code",
    [
        # Standard error matching
        (
            "test.py:1:5: error: Incompatible types [assignment]\n",
            1,
            "assignment",
        ),
        # Multiple errors
        (
            "file1.py:10:1: error: Error 1 [err1]\n"
            "file1.py:20:5: error: Error 2 [err2]\n",
            2,
            "err1",
        ),
        # Empty output
        ("", 0, None),
        # Noise and summary lines (unmatched)
        (
            "Success: no issues found\n"
            "Some random noise\n"
            "test.py:1:1: error: Real error [code]\n",
            1,
            "code",
        ),
        # Missing error code in output (should not match current regex)
        ("test.py:1:1: error: Something without code\n", 0, None),
    ],
)
@pytest.mark.asyncio
async def test_mypy_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various MyPy parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=1)
    mocker.patch.object(MyPyLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].snippet_context == "snippet"
