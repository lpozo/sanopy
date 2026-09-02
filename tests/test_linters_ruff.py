"""Tests for Ruff linter."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.context import get_linter_context
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
        # Null results
        ("null", 0, None),
        # Malformed JSON
        ("Internal Error", 0, None),
        # Missing location fields fall back to defaults
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


@pytest.mark.asyncio
async def test_ruff_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Ruff finding."""
    stdout = json.dumps(
        [
            {
                "code": "E501",
                "message": "Line too long (101 > 88)",
                "filename": "src/mod.py",
                "location": {"row": 15, "column": 1},
                "end_location": {"row": 15, "column": 101},
            }
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RuffLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("src/mod.py")
    assert result.line_start == 15
    assert result.line_end == 15
    assert result.col_start == 1
    assert result.col_end == 101
    assert result.error_code == "E501"
    assert result.raw_severity is None
    assert result.message == "Line too long (101 > 88)"


@pytest.mark.asyncio
async def test_ruff_reuses_content_per_file(mocker, linter, tmp_path) -> None:
    """Ruff passes the same content to get_linter_context for one file.

    Multiple findings in the same file must reuse one read of the file
    content rather than re-reading it once per finding.
    """
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8")

    stdout = json.dumps(
        [
            {
                "code": "E501",
                "message": "msg1",
                "filename": str(mod),
                "location": {"row": 1, "column": 1},
            },
            {
                "code": "E501",
                "message": "msg2",
                "filename": str(mod),
                "location": {"row": 1, "column": 1},
            },
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RuffLinter, "_run_command", return_value=mock_result)
    context_calls = []

    def _capture_content(**kwargs):
        context_calls.append(kwargs.get("content"))
        return ("snippet", 1, "context")

    mocker.patch(
        "sanopy.linters.ruff.get_linter_context",
        side_effect=_capture_content,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert len(context_calls) == 2
    assert context_calls == ["x = 1\n", "x = 1\n"]


@pytest.mark.asyncio
async def test_ruff_unreadable_finding_file_is_graceful(
    mocker, linter, tmp_path
) -> None:
    """Findings pointing at an unreadable file do not crash parsing."""
    binary = tmp_path / "target"
    binary.mkdir()
    mod = binary / "mod.bin"
    mod.write_bytes(b"\xff\xfe\xfd")

    stdout = json.dumps(
        [
            {
                "code": "E501",
                "message": "odd",
                "filename": str(mod),
                "location": {"row": 1, "column": 1},
            }
        ]
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RuffLinter, "_run_command", return_value=mock_result)
    mocker.patch(
        "sanopy.linters.ruff.get_linter_context",
        side_effect=get_linter_context,
    )

    results = await linter.run(binary)

    assert len(results) == 1
    assert results[0].snippet_context == ""


@pytest.mark.parametrize("config_present", [False, True])
def test_ruff_build_command(mocker, tmp_path, config_present: bool) -> None:
    """Test that the Ruff command includes --config when available."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    config_path = Path("/cfg/ruff.toml") if config_present else None
    mock_config = mocker.patch.object(
        RuffLinter, "_get_effective_config_path", return_value=config_path
    )

    cmd = RuffLinter().build_command(target)

    expected = ["ruff", "check", "--output-format=json"]
    if config_present:
        expected += ["--config", "/cfg/ruff.toml"]

    assert cmd == expected + [str(target.absolute())]
    mock_config.assert_called_once_with(
        target, ["pyproject.toml", "ruff.toml", ".ruff.toml"]
    )
