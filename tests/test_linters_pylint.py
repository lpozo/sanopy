"""Tests for Pylint linter using parametrization."""

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
        # Malformed JSON
        ("Crashed", 0, None),
        # Missing optional fields
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
            "W0611",  # Placeholder code
            # PylintLinter.parse_output fallback:
            # error_code = error.get("message-id", ... "Unknown")
        ),
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
        # Note: fix expectation for the missing message-id case
        if "message-id" not in stdout and "symbol" in stdout:
            expected_code = "some-error"
        else:
            expected_code = first_error_code

        assert results[0].error_code == expected_code
        assert results[0].snippet_context == "snippet"
