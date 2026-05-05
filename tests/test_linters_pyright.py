"""Tests for Pyright linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.pyright import PyrightLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.pyright.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> PyrightLinter:
    """Pyright linter instance."""
    return PyrightLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard success
        (
            json.dumps(
                {
                    "generalDiagnostics": [
                        {
                            "file": "test.py",
                            "severity": "error",
                            "message": "Type error",
                            "rule": "reportGeneralTypeIssues",
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 0, "character": 5},
                            },
                        }
                    ]
                }
            ),
            1,
            "reportGeneralTypeIssues",
        ),
        # Empty results
        (json.dumps({"generalDiagnostics": []}), 0, None),
        # Malformed JSON
        ("Error", 0, None),
        # Missing fields
        (
            json.dumps({"generalDiagnostics": [{"message": "No fields"}]}),
            1,
            "Unknown",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pyright_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various Pyright parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        PyrightLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].snippet_context == "snippet"
