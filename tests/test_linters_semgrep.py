"""Tests for Semgrep linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.semgrep import SemgrepLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.semgrep.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> SemgrepLinter:
    """Semgrep linter instance."""
    return SemgrepLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code",
    [
        # Standard success
        (
            json.dumps(
                {
                    "results": [
                        {
                            "check_id": "rules.unsafe",
                            "path": "test.py",
                            "start": {"line": 1, "col": 1},
                            "extra": {
                                "message": "Unsafe",
                                "severity": "WARNING",
                            },
                        }
                    ]
                }
            ),
            1,
            "rules.unsafe",
        ),
        # Empty results
        (json.dumps({"results": []}), 0, None),
        # Malformed JSON
        ("Failed", 0, None),
        # Missing fields
        (json.dumps({"results": [{"check_id": "minimal"}]}), 1, "minimal"),
    ],
)
@pytest.mark.asyncio
async def test_semgrep_scenarios(
    mocker, linter, stdout, expected_count, first_error_code
) -> None:
    """Test various Semgrep parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        SemgrepLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert results[0].snippet_context == "snippet"
