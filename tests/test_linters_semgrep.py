"""Tests for Semgrep linter."""

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
        # Standard finding
        (
            json.dumps(
                {
                    "results": [
                        {
                            "path": "src/app.py",
                            "start": {"line": 42, "col": 5},
                            "end": {"line": 42, "col": 20},
                            "check_id": "python.lang.security.eval.eval-used",
                            "extra": {
                                "severity": "ERROR",
                                "message": "Avoid using eval",
                            },
                        }
                    ]
                }
            ),
            1,
            "python.lang.security.eval.eval-used",
        ),
        # Empty results
        (json.dumps({"results": []}), 0, None),
        # Missing results key
        (json.dumps({"other": []}), 0, None),
        # Null results
        (json.dumps({"results": None}), 0, None),
        # Malformed JSON
        ("semgrep crashed", 0, None),
        # Missing optional fields fall back to defaults
        (
            json.dumps({"results": [{"check_id": "rule.id.missing-fields"}]}),
            1,
            "rule.id.missing-fields",
        ),
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


@pytest.mark.asyncio
async def test_semgrep_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Semgrep finding."""
    stdout = json.dumps(
        {
            "results": [
                {
                    "path": "src/auth.py",
                    "start": {"line": 10, "col": 4},
                    "end": {"line": 12, "col": 8},
                    "check_id": "python.lang.security.audit.sql-injection",
                    "extra": {
                        "severity": "WARNING",
                        "message": "Possible SQL injection",
                    },
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        SemgrepLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("src/auth.py")
    assert result.line_start == 10
    assert result.line_end == 12
    assert result.col_start == 4
    assert result.col_end == 8
    assert result.error_code == "python.lang.security.audit.sql-injection"
    assert result.raw_severity == "warning"
    assert result.message == "[WARNING] Possible SQL injection"


@pytest.mark.asyncio
async def test_semgrep_lowercase_severity_uppercased(mocker, linter) -> None:
    """Test that lowercase severities are normalized to uppercase."""
    stdout = json.dumps(
        {
            "results": [
                {
                    "path": "a.py",
                    "start": {"line": 1, "col": 1},
                    "check_id": "rule.id",
                    "extra": {"severity": "error", "message": "Msg"},
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        SemgrepLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    assert results[0].message == "[ERROR] Msg"


def test_semgrep_build_command(tmp_path) -> None:
    """Test the Semgrep command construction."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    assert SemgrepLinter().build_command(target) == [
        "semgrep",
        "scan",
        "--config",
        "auto",
        "--json",
        str(target.absolute()),
    ]
