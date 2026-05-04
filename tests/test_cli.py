"""Tests for the LintAIder CLI interface."""
# pylint: disable=redefined-outer-name

from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from lintaider.cli import main
from lintaider.config import Config
from lintaider.linters.result import LinterResult


@pytest.fixture(autouse=True)
def _mock_scan_config(mocker):
    """Fixture to mock scan config loading with defaults."""
    return mocker.patch(
        "lintaider.cli.scan_handler.Config.load", return_value=Config()
    )


def test_cli_scan_no_issues(mocker, tmp_path) -> None:
    """Test scanning a file with no issues."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    mocker.patch(
        "lintaider.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    result = runner.invoke(main, ["scan", str(test_file)])
    assert result.exit_code == 0
    assert "No issues found" in result.output


def test_cli_scan_with_issues(mocker, tmp_path) -> None:
    """Test scanning a file with issues saves results to a JSON file."""
    import json

    runner = CliRunner()
    test_file = tmp_path / "error.py"
    test_file.write_text("import bad\n", encoding="utf-8")

    fake_result = LinterResult(
        file_path=test_file,
        line_start=1,
        line_end=1,
        col_start=1,
        col_end=10,
        linter_name="TestLinter",
        error_code="E1",
        message="A test error",
        snippet_context="import bad",
    )

    mocker.patch(
        "lintaider.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    output_file = tmp_path / "scan-result.json"
    result = runner.invoke(
        main, ["scan", str(test_file), "--output", str(output_file)]
    )

    assert result.exit_code == 0
    assert "Findings Summary" in result.output
    assert "Results saved to" in result.output
    assert output_file.exists()
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["linter_name"] == "TestLinter"
    assert data[0]["error_code"] == "E1"


def test_cli_scan_human_readable_generates_markdown(mocker, tmp_path) -> None:
    """Test that --human-readable generates markdown and JSON output."""
    import json
    from pathlib import Path

    runner = CliRunner()
    test_file = tmp_path / "error.py"
    test_file.write_text("import bad\n", encoding="utf-8")

    fake_result = LinterResult(
        file_path=test_file,
        line_start=1,
        line_end=1,
        col_start=1,
        col_end=10,
        linter_name="TestLinter",
        error_code="E1",
        message="A test error",
        snippet_context="import bad",
    )

    mocker.patch(
        "lintaider.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    output_file = tmp_path / "scan-result.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main,
            [
                "scan",
                str(test_file),
                "--output",
                str(output_file),
                "--human-readable",
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["linter_name"] == "TestLinter"

        report_file = Path("linting-report.md")
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "# Linting Report" in content
        assert "TestLinter" in content
        assert "A test error" in content


def test_cli_scan_human_readable_short_flag(mocker, tmp_path) -> None:
    """Test that -r also generates linting-report.md."""
    from pathlib import Path

    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    mocker.patch(
        "lintaider.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    output_file = tmp_path / "scan-result.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main, ["scan", str(test_file), "--output", str(output_file), "-r"]
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert Path("linting-report.md").exists()


def test_cli_scan_verbose(mocker, tmp_path) -> None:
    """Test that --verbose prints per-issue panels."""
    runner = CliRunner()
    test_file = tmp_path / "error.py"
    test_file.write_text("import bad\n", encoding="utf-8")

    fake_result = LinterResult(
        file_path=test_file,
        line_start=3,
        line_end=3,
        col_start=5,
        col_end=10,
        linter_name="TestLinter",
        error_code="E1",
        message="A test error",
        snippet_context="import bad",
    )

    mocker.patch(
        "lintaider.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    output_file = tmp_path / "scan-result.json"
    result = runner.invoke(
        main,
        ["scan", str(test_file), "--output", str(output_file), "--verbose"],
    )

    assert result.exit_code == 0
    assert "Issue 1/1" in result.output
    assert "E1" in result.output
    assert "A test error" in result.output
    assert "import bad" in result.output


def test_cli_scan_only_filter(mocker, tmp_path) -> None:
    """Test the --only flag for filtering linters."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("print(1)\n", encoding="utf-8")

    mock_engine = mocker.patch("lintaider.cli.scan_handler.Engine")

    runner.invoke(main, ["scan", str(test_file), "--only", "ruff"])

    args, kwargs = mock_engine.call_args
    linters = kwargs.get("linters", []) or (args[0] if args else [])
    assert len(linters) == 1
    assert linters[0].__class__.__name__ == "RuffLinter"


def test_cli_scan_skip_filter(mocker, tmp_path) -> None:
    """Test the --skip flag for filtering linters."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("print(1)\n", encoding="utf-8")

    mock_engine = mocker.patch("lintaider.cli.scan_handler.Engine")

    runner.invoke(
        main,
        [
            "scan",
            str(test_file),
            "--skip",
            "ruff,pylint,bandit,mypy,pyright,semgrep",
        ],
    )

    args, kwargs = mock_engine.call_args
    linters = kwargs.get("linters", []) or (args[0] if args else [])
    assert len(linters) == 3
    remaining_names = [linter.__class__.__name__ for linter in linters]
    assert "VultureLinter" in remaining_names
    assert "RadonLinter" in remaining_names
    assert "SafetyLinter" in remaining_names


def test_cli_init_command(mocker) -> None:
    """Test linter-only init command flow."""
    from lintaider.cli.init_handler import ConfigBuilder

    runner = CliRunner()
    config = Config()

    mocker.patch("lintaider.cli.init_handler.Config.load", return_value=config)
    mocker.patch.object(Config, "save")
    mocker.patch(
        "lintaider.cli.init_handler.click.prompt",
        side_effect=["ruff", "mypy"],
    )
    mocker.patch("lintaider.cli.init_handler.click.confirm", return_value=True)

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    assert "Configuration Saved" in result.output
    assert config.skip_linters == ["ruff"]
    assert config.only_linters == ["mypy"]
    assert isinstance(ConfigBuilder(config), ConfigBuilder)


def test_init_helper_select_linter_preferences(mocker) -> None:
    """Test linter preference selection with validation."""
    from lintaider.cli.init_handler import ConfigBuilder

    config = Config(skip_linters=["ruff"], only_linters=[])
    builder = ConfigBuilder(config)

    mocker.patch(
        "lintaider.cli.init_handler.click.prompt",
        side_effect=["pylint", "bandit"],
    )

    skip, only = builder.select_linter_preferences()
    assert "pylint" in skip
    assert "bandit" in only
    assert "ruff" not in skip


def test_init_helper_select_linter_preferences_invalid(mocker) -> None:
    """Test that invalid linter names are handled gracefully via public API."""
    from lintaider.cli.init_handler import ConfigBuilder

    config = Config()
    builder = ConfigBuilder(config)

    mocker.patch(
        "lintaider.cli.init_handler.click.prompt",
        side_effect=["ruff,invalid_linter", ""],
    )

    skip, _ = builder.select_linter_preferences()
    assert "ruff" in skip
    assert "invalid_linter" not in skip


def test_init_helper_select_linter_preferences_overlap(mocker) -> None:
    """Test overlap removal between skip and only linters."""
    from lintaider.cli.init_handler import ConfigBuilder

    config = Config()
    builder = ConfigBuilder(config)

    mocker.patch(
        "lintaider.cli.init_handler.click.prompt",
        side_effect=["ruff,pylint", "pylint,bandit"],
    )

    skip, only = builder.select_linter_preferences()
    assert "pylint" not in skip
    assert "pylint" in only


@pytest.fixture
def fake_result(tmp_path) -> LinterResult:
    """A single LinterResult for use in ScanReporter tests."""
    return LinterResult(
        file_path=tmp_path / "sample.py",
        line_start=5,
        line_end=5,
        col_start=1,
        col_end=10,
        linter_name="TestLinter",
        error_code="T001",
        message="Something wrong",
        snippet_context="bad_code()",
    )


def test_scan_reporter_write_json_report(tmp_path, fake_result) -> None:
    """write_json_report saves results as valid JSON to the output path."""
    import json

    from lintaider.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output)
    reporter.write_json_report()

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["linter_name"] == "TestLinter"


def test_scan_reporter_write_human_readable_report(
    tmp_path, fake_result
) -> None:
    """write_human_readable_report writes a markdown file in the cwd."""
    import os
    from pathlib import Path

    from lintaider.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output)

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        reporter.write_human_readable_report()
    finally:
        os.chdir(old_cwd)

    report = tmp_path / "linting-report.md"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "# Linting Report" in content
    assert "TestLinter" in content
    assert "Something wrong" in content
    assert "bad_code()" in content


def test_scan_reporter_write_summary_report(tmp_path, fake_result) -> None:
    """write_summary_report prints the findings table."""
    from lintaider.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output)

    reporter.write_summary_report()
