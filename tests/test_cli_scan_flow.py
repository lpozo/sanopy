"""CLI scan-flow tests: progress rendering and multi-target merging."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from sanopy.cli.cli import main
from sanopy.linters.result import LinterResult


@pytest.fixture(autouse=True)
def _use_mock_scan_config(mock_scan_config):
    """Apply the shared scan-config mocks to every test in this module."""


def test_cli_scan_human_mode_drives_progress_callback(
    mocker, tmp_path
) -> None:
    """Human mode calls the run_all progress callback to advance the bar."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    calls: list[int] = []

    async def _run_all_with_progress(
        target, progress_callback=None, semaphore=None
    ):
        if progress_callback:
            progress_callback()
            calls.append(1)
        return []

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        side_effect=_run_all_with_progress,
    )

    result = runner.invoke(
        main, ["scan", str(test_file), "--output-mode", "human"]
    )

    assert result.exit_code == 0
    assert calls == [1]
    assert "No issues found" in result.output


def test_cli_scan_multiple_targets_merges_per_target_findings(
    mocker, tmp_path
) -> None:
    """Multi-target merge sums per-target finding_count and concats findings.

    Each target returns a different number of findings so the merged
    finding_count is verified as a sum and the findings are concatenated
    rather than overwritten or counted from the first target only.
    """
    runner = CliRunner()
    first_file = tmp_path / "first.py"
    first_file.write_text("x = 1\n", encoding="utf-8")
    second_file = tmp_path / "second.py"
    second_file.write_text("y = 2\n", encoding="utf-8")

    def make_result(pos: int, path: Path) -> LinterResult:
        return LinterResult(
            file_path=path,
            line_start=pos + 1,
            line_end=pos + 1,
            col_start=1,
            col_end=2,
            linter_name="TestLinter",
            error_code=f"E{pos}",
            message=f"finding {pos}",
        )

    def _distinct_results(target, progress_callback=None, semaphore=None):
        if str(target) == str(first_file):
            return [make_result(1, first_file), make_result(2, first_file)]
        return [make_result(3, second_file)]

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        side_effect=_distinct_results,
    )

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main, ["scan", str(first_file), str(second_file)]
        )

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["run"]["finding_count"] == 3
        assert [f["message"] for f in payload["findings"]] == [
            "finding 1",
            "finding 2",
            "finding 3",
        ]
        assert payload["run"]["active_linters"]  # present in the merged run
