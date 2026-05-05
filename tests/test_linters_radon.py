"""Tests for Radon linter using parametrization."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.radon import RadonLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.radon.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> RadonLinter:
    """Radon linter instance."""
    return RadonLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_error_code, first_name_fragment",
    [
        # Single complex function
        (
            json.dumps(
                {
                    "src/cli.py": [
                        {
                            "type": "function",
                            "name": "_async_scan",
                            "classname": "",
                            "complexity": 18,
                            "rank": "C",
                            "lineno": 150,
                            "endline": 214,
                            "col_offset": 0,
                        }
                    ]
                }
            ),
            1,
            "CC-C",
            "_async_scan",
        ),
        # Method inside a class
        (
            json.dumps(
                {
                    "module.py": [
                        {
                            "type": "method",
                            "name": "process",
                            "classname": "Engine",
                            "complexity": 25,
                            "rank": "D",
                            "lineno": 10,
                            "endline": 50,
                            "col_offset": 4,
                        }
                    ]
                }
            ),
            1,
            "CC-D",
            "Engine.process",
        ),
        # Multiple files with issues
        (
            json.dumps(
                {
                    "a.py": [
                        {
                            "type": "function",
                            "name": "f1",
                            "complexity": 12,
                            "rank": "C",
                            "lineno": 1,
                            "endline": 10,
                        },
                    ],
                    "b.py": [
                        {
                            "type": "function",
                            "name": "f2",
                            "complexity": 30,
                            "rank": "F",
                            "lineno": 5,
                            "endline": 60,
                        },
                    ],
                }
            ),
            2,
            "CC-C",
            "f1",
        ),
        # Empty results (no complex code)
        ("{}", 0, None, None),
        # Malformed JSON
        ("not json", 0, None, None),
    ],
)
@pytest.mark.asyncio
async def test_radon_scenarios(
    mocker,
    linter,
    stdout,
    expected_count,
    first_error_code,
    first_name_fragment,
) -> None:
    """Test various Radon parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RadonLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].error_code == first_error_code
        assert first_name_fragment in results[0].message
        assert results[0].snippet_context == "snippet"
