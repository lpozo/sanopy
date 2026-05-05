"""Tests for Bandit linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.bandit import BanditLinter
from sanopy.linters.base import AsyncCompletedProcess


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.bandit.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> BanditLinter:
    """Bandit linter instance."""
    return BanditLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code, first_severity",
    [
        # Success case with one error
        (
            json.dumps(
                {
                    "results": [
                        {
                            "filename": "test.py",
                            "issue_severity": "LOW",
                            "issue_text": "subprocess is bad",
                            "line_number": 1,
                            "line_range": [1],
                            "test_id": "B404",
                        }
                    ]
                }
            ),
            1,
            "B404",
            "[LOW]",
        ),
        # Empty results
        (json.dumps({"results": []}), 0, None, None),
        # Multiple vulnerabilities
        (
            json.dumps(
                {
                    "results": [
                        {
                            "test_id": "B001",
                            "line_number": 1,
                            "issue_severity": "HIGH",
                        },
                        {
                            "test_id": "B002",
                            "line_number": 2,
                            "issue_severity": "MEDIUM",
                        },
                    ]
                }
            ),
            2,
            "B001",
            "[HIGH]",
        ),
        # Malformed JSON
        ("Not JSON", 0, None, None),
        # Missing optional fields
        (
            json.dumps({"results": [{"test_id": "B999", "line_number": 5}]}),
            1,
            "B999",
            "[LOW]",  # Fallback severity
        ),
    ],
)
@pytest.mark.asyncio
async def test_bandit_scenarios(
    mocker, linter, stdout, expected_count, first_error_code, first_severity
) -> None:
    """Test various Bandit parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(BanditLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        if first_severity:
            assert first_severity in results[0].message
        assert results[0].snippet_context == "snippet"
