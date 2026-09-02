"""Tests for Vulture linter using parametrization."""

from pathlib import Path

import pytest

from sanopy.linters.base import AsyncCompletedProcess
from sanopy.linters.vulture import VultureLinter


@pytest.fixture(autouse=True)
def _mock_get_context(mocker):
    """Mock get_linter_context to return dummy values."""
    return mocker.patch(
        "sanopy.linters.vulture.get_linter_context",
        return_value=("snippet", 1, "context"),
    )


@pytest.fixture
def linter() -> VultureLinter:
    """Vulture linter instance."""
    return VultureLinter()


@pytest.mark.parametrize(
    "stdout, expected_count, first_line",
    [
        # Standard success
        ("test.py:1: unused variable 'x' (60% confidence)\n", 1, 1),
        # Multiple issues
        (
            "file1.py:10: unused function 'foo'\n"
            "file1.py:20: unused class 'Bar'\n",
            2,
            10,
        ),
        # Empty output
        ("", 0, None),
        # Noise
        ("Some header\nfile.py:5: unused import 'os'\nFooter\n", 1, 5),
        # Blank and whitespace-only lines are skipped before matching
        ("\n   \nfile.py:3: unused function 'foo'\n\n", 1, 3),
    ],
)
@pytest.mark.asyncio
async def test_vulture_scenarios(
    mocker, linter, stdout, expected_count, first_line
) -> None:
    """Test various Vulture parsing scenarios."""
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        VultureLinter, "_run_command", return_value=mock_result
    )

    results = await linter.run(Path("target.py"))

    assert len(results) == expected_count
    if expected_count > 0:
        assert results[0].line_start == first_line
        assert results[0].snippet_context == "snippet"


@pytest.mark.parametrize(
    "target_name, is_dir",
    [
        pytest.param("app.py", False, id="single-file"),
        pytest.param("src", True, id="directory"),
    ],
)
def test_vulture_build_command(
    tmp_path, target_name: str, is_dir: bool
) -> None:
    """Vulture command is package name followed by the absolute target."""
    target = tmp_path / target_name
    if is_dir:
        target.mkdir()
    else:
        target.write_text("x = 1\n", encoding="utf-8")

    assert VultureLinter().build_command(target) == [
        "vulture",
        str(target.absolute()),
    ]


def test_vulture_build_command_starts_with_package_name(tmp_path) -> None:
    """build_command()[0] equals package_name so run() drops it correctly."""
    target = tmp_path / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")

    cmd = VultureLinter().build_command(target)

    assert cmd[0] == VultureLinter.package_name


@pytest.mark.asyncio
async def test_vulture_reuses_content_per_file(
    mocker, linter, tmp_path
) -> None:
    """Vulture reuses one read of file content across multiple findings."""
    src = tmp_path / "target"
    src.mkdir()
    mod = src / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8")

    stdout = f"{mod}:1: unused function 'foo'\n{mod}:2: unused class 'Bar'\n"
    mock_result = AsyncCompletedProcess(stdout=stdout, stderr="", returncode=0)
    mocker.patch.object(
        VultureLinter, "_run_command", return_value=mock_result
    )
    context_calls = []

    def _capture_content(**kwargs):
        context_calls.append(kwargs.get("content"))
        return ("snippet", 1, "context")

    mocker.patch(
        "sanopy.linters.vulture.get_linter_context",
        side_effect=_capture_content,
    )

    results = await linter.run(src)

    assert len(results) == 2
    assert context_calls == ["x = 1\n", "x = 1\n"]
