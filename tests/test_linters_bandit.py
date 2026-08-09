"""Tests for Bandit linter."""

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
        # Missing results key
        (json.dumps({"other": []}), 0, None, None),
        # Null results
        (json.dumps({"results": None}), 0, None, None),
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
        # Missing optional fields fall back to defaults
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


@pytest.mark.asyncio
async def test_bandit_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Bandit finding."""
    stdout = json.dumps(
        {
            "results": [
                {
                    "test_id": "B603",
                    "line_number": 7,
                    "line_range": [7, 8],
                    "issue_severity": "MEDIUM",
                    "issue_text": "shell injection",
                    "filename": "/abs/svc.py",
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(BanditLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("/abs/svc.py")
    assert result.line_start == 7
    assert result.line_end == 8
    assert result.col_start is None
    assert result.error_code == "B603"
    assert "[MEDIUM]" in result.message
    assert "shell injection" in result.message


@pytest.mark.parametrize(
    "is_dir, config_present",
    [
        (True, False),
        (True, True),
        (False, False),
        (False, True),
    ],
)
def test_bandit_build_command(
    mocker, tmp_path, is_dir: bool, config_present: bool
) -> None:
    """Test that the Bandit command reflects target kind and config."""
    target = tmp_path / ("pkg" if is_dir else "file.py")
    if is_dir:
        target.mkdir()
    else:
        target.write_text("x = 1\n", encoding="utf-8")

    config_path = Path("/cfg/bandit.yaml") if config_present else None
    mock_config = mocker.patch.object(
        BanditLinter, "_get_effective_config_path", return_value=config_path
    )

    cmd = BanditLinter().build_command(target)

    target_str = str(target.absolute())
    expected = ["bandit", "-f", "json"]
    if config_present:
        expected += ["-c", "/cfg/bandit.yaml"]
    expected += ["-r", target_str] if is_dir else [target_str]

    assert cmd == expected
    mock_config.assert_called_once_with(
        target, ["bandit.yaml", ".bandit", "pyproject.toml"]
    )
