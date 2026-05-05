"""Tests for Ruff linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.ruff import RuffLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.ruff.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> RuffLinter:
    """Ruff linter instance."""
    return RuffLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard success
        (
            json.dumps(
                [
                    {
                        "code": "F401",
                        "message": "'os' imported but unused",
                        "filename": "test.py",
                        "location": {"row": 1, "column": 1},
                        "end_location": {"row": 1, "column": 10},
                    }
                ]
            ),
            1,
            "F401",
        ),
        # Empty results
        ("[]", 0, None),
        # Malformed JSON
        ("Internal Error", 0, None),
        # Missing location fields
        (
            json.dumps(
                [
                    {
                        "code": "E999",
                        "message": "Minimal error",
                        "filename": "minimal.py",
                    }
                ]
            ),
            1,
            "E999",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ruff_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various Ruff parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RuffLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].snippet_context == "snippet"
