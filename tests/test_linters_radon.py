"""Tests for Radon linter."""

import json
from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.radon import MIN_COMPLEXITY_RANK, RadonLinter


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
        # A file with null blocks
        (
            json.dumps({"a.py": None}),
            0,
            None,
            None,
        ),
        # Missing rank falls back to A
        (
            json.dumps(
                {
                    "a.py": [
                        {
                            "type": "function",
                            "name": "f1",
                            "complexity": 5,
                            "lineno": 1,
                        }
                    ]
                }
            ),
            1,
            "CC-A",
            "f1",
        ),
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


@pytest.mark.asyncio
async def test_radon_parses_fields(mocker, linter) -> None:
    """Test full field mapping from a Radon block."""
    stdout = json.dumps(
        {
            "mod.py": [
                {
                    "type": "function",
                    "name": "process",
                    "classname": "Engine",
                    "complexity": 21,
                    "rank": "C",
                    "lineno": 30,
                    "endline": 55,
                }
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RadonLinter, "_run_command", return_value=mock_result)

    results = await linter.run(Path("target.py"))

    assert len(results) == 1
    result = results[0]
    assert result.file_path == Path("mod.py")
    assert result.line_start == 30
    assert result.line_end == 55
    assert result.col_start is None
    assert result.error_code == "CC-C"
    assert "Function 'Engine.process'" in result.message
    assert "complexity 21" in result.message


@pytest.mark.asyncio
async def test_radon_reuses_content_per_file(mocker, linter, tmp_path) -> None:
    """Radon reuses one read of file content across multiple blocks."""
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8")

    stdout = json.dumps(
        {
            str(mod): [
                {
                    "type": "function",
                    "name": "f1",
                    "complexity": 12,
                    "rank": "C",
                    "lineno": 1,
                    "endline": 2,
                },
                {
                    "type": "function",
                    "name": "f2",
                    "complexity": 12,
                    "rank": "C",
                    "lineno": 3,
                    "endline": 4,
                },
            ]
        }
    )
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(RadonLinter, "_run_command", return_value=mock_result)
    context_calls = []

    def _capture_content(**kwargs):
        context_calls.append(kwargs.get("content"))
        return ("snippet", 1, "context")

    mocker.patch(
        "sanopy.linters.radon.get_linter_context",
        side_effect=_capture_content,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert context_calls == ["x = 1\n", "x = 1\n"]


def test_radon_build_command(tmp_path) -> None:
    """Test the Radon command construction."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    assert RadonLinter().build_command(target) == [
        "radon",
        "cc",
        "-j",
        "-n",
        MIN_COMPLEXITY_RANK,
        str(target.absolute()),
    ]
