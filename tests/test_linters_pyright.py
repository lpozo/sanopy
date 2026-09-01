"""Tests for Pyright linter."""

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
        # Empty diagnostics
        (json.dumps({"generalDiagnostics": []}), 0, None),
        # Missing diagnostics key
        (json.dumps({"other": []}), 0, None),
        # Null diagnostics
        (json.dumps({"generalDiagnostics": None}), 0, None),
        # Malformed JSON
        ("Error", 0, None),
        # Missing fields fall back to Unknown and defaults
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


@pytest.mark.asyncio
async def test_pyright_parses_fields(mocker, linter) -> None:
    """Test that Pyright's 0-indexed ranges normalize to 1-indexed."""
    stdout = json.dumps(
        {
            "generalDiagnostics": [
                {
                    "file": "src/mod.py",
                    "severity": "warning",
                    "message": "Type is partially unknown",
                    "rule": "reportUnknownVariableType",
                    "range": {
                        "start": {"line": 4, "character": 2},
                        "end": {"line": 6, "character": 8},
                    },
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        PyrightLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("src/mod.py")
    assert result.line_start == 5
    assert result.line_end == 7
    assert result.col_start == 3
    assert result.col_end == 9
    assert result.error_code == "reportUnknownVariableType"
    assert result.raw_severity == "warning"
    assert "[WARNING]" in result.message


def test_pyright_build_command(tmp_path) -> None:
    """Test the Pyright command construction."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    assert PyrightLinter().build_command(target) == [
        "pyright",
        "--outputjson",
        str(target.absolute()),
    ]
