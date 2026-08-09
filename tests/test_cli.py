"""Tests for the Sanopy CLI interface."""
# pylint: disable=redefined-outer-name

from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from sanopy.cli.cli import main
from sanopy.config import Config
from sanopy.linters.result import LinterResult


@pytest.fixture(autouse=True)
def _mock_scan_config(mocker):
    """Fixture to mock scan config loading with defaults."""
    return mocker.patch(
        "sanopy.cli.scan_handler.Config.load", return_value=Config()
    )


def _assert_stdout_finding(finding: dict[str, object], test_file) -> None:
    """Assert the machine-readable shape of a stdout scan finding."""
    assert finding["id"]
    assert finding["message"] == "A test error"
    assert finding["linter"] == {
        "name": "TestLinter",
        "rule_id": "E1",
        "raw_severity": None,
        "normalized_severity": "error",
    }
    assert finding["location"] == {
        "path": str(test_file),
        "start": {"line": 1, "column": 1},
        "end": {"line": 1, "column": 10},
    }


def test_cli_scan_no_issues(mocker, tmp_path) -> None:
    """Test machine-mode scan emits schema envelope with no findings."""
    import json

    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    result = runner.invoke(main, ["scan", str(test_file)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.0.0"
    assert payload["findings"] == []


def test_cli_scan_with_issues(mocker, tmp_path) -> None:
    """Test human-mode scan with --output saves schema envelope JSON."""
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
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    output_file = tmp_path / "scan-result.json"
    result = runner.invoke(
        main,
        [
            "scan",
            str(test_file),
            "--output",
            str(output_file),
            "--output-mode",
            "human",
        ],
    )

    assert result.exit_code == 1
    assert "Findings Summary" in result.output
    assert "Results saved to" in result.output
    expected_output_file = tmp_path / "scan-result-error.json"
    assert expected_output_file.exists()
    payload = json.loads(expected_output_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["linter"]["name"] == "TestLinter"
    assert payload["findings"][0]["linter"]["rule_id"] == "E1"


def test_cli_scan_prints_json_to_stdout_by_default(mocker, tmp_path) -> None:
    """Test scanning emits JSON to stdout when no output path is provided."""
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
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["scan", str(test_file)])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["schema_version"] == "1.0.0"
        assert payload["run"]["finding_count"] == 1
        _assert_stdout_finding(payload["findings"][0], test_file)
        assert not (tmp_path / "scan-result-error.json").exists()


def test_cli_scan_human_mode_does_not_print_json_stdout(
    mocker, tmp_path
) -> None:
    """Test human output mode avoids machine JSON output on stdout."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    result = runner.invoke(
        main, ["scan", str(test_file), "--output-mode", "human"]
    )

    assert result.exit_code == 0
    assert "No issues found" in result.output
    assert '"schema_version"' not in result.output


def test_cli_scan_human_readable_generates_markdown(mocker, tmp_path) -> None:
    """Test that --human-readable generates markdown and JSON output."""
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
        "sanopy.cli.scan_handler.Engine.run_all",
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

        assert result.exit_code == 1
        expected_output_file = tmp_path / "scan-result-error.json"
        assert expected_output_file.exists()

        payload = json.loads(expected_output_file.read_text(encoding="utf-8"))
        assert len(payload["findings"]) == 1
        assert payload["findings"][0]["linter"]["name"] == "TestLinter"

        report_file = tmp_path / "linting-report-error.md"
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "# Linting Report" in content
        assert "TestLinter" in content
        assert "A test error" in content


def test_cli_scan_human_readable_short_flag(mocker, tmp_path) -> None:
    """Test that -r also generates linting-report.md."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("def ok():\n    return 1\n", encoding="utf-8")

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    output_file = tmp_path / "scan-result.json"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main, ["scan", str(test_file), "--output", str(output_file), "-r"]
        )

        assert result.exit_code == 0
        assert (tmp_path / "scan-result-valid.json").exists()
        assert (tmp_path / "linting-report-valid.md").exists()


def test_cli_scan_returns_exit_code_2_on_scan_failure(
    mocker, tmp_path
) -> None:
    """Test scan exits with code 2 when linter execution fails."""
    runner = CliRunner()
    test_file = tmp_path / "broken.py"
    test_file.write_text("print('x')\n", encoding="utf-8")

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        side_effect=RuntimeError("engine failure"),
    )

    result = runner.invoke(main, ["scan", str(test_file)])

    assert result.exit_code == 2


def test_cli_scan_multiple_targets_emits_single_json(mocker, tmp_path) -> None:
    """Test that multi-target stdout scans produce one valid JSON document."""
    import json

    runner = CliRunner()
    first_file = tmp_path / "first.py"
    first_file.write_text("x = 1\n", encoding="utf-8")
    second_file = tmp_path / "second.py"
    second_file.write_text("y = 2\n", encoding="utf-8")

    fake_result = LinterResult(
        file_path=first_file,
        line_start=1,
        line_end=1,
        col_start=1,
        col_end=2,
        linter_name="TestLinter",
        error_code="E1",
        message="A test error",
    )

    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[fake_result],
    )

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            main, ["scan", str(first_file), str(second_file)]
        )

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["schema_version"] == "1.0.0"
        assert payload["run"]["target"] == [
            str(first_file),
            str(second_file),
        ]
        assert payload["run"]["finding_count"] == 2
        assert len(payload["findings"]) == 2
        assert all(
            finding["linter"]["name"] == "TestLinter"
            for finding in payload["findings"]
        )


def test_cli_scan_verbose_option_not_available(tmp_path) -> None:
    """Test that --verbose is not a supported scan option."""
    runner = CliRunner()
    test_file = tmp_path / "error.py"
    test_file.write_text("import bad\n", encoding="utf-8")

    result = runner.invoke(main, ["scan", str(test_file), "--verbose"])

    assert result.exit_code != 0
    assert "No such option: --verbose" in result.output


def test_cli_scan_only_filter(mocker, tmp_path) -> None:
    """Test the --only flag for filtering linters."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("print(1)\n", encoding="utf-8")

    mock_engine = mocker.patch("sanopy.cli.scan_handler.Engine")

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

    mock_engine = mocker.patch("sanopy.cli.scan_handler.Engine")

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


def test_cli_scan_safety_receives_ignored_cves(mocker, tmp_path) -> None:
    """Safety linter is built with config-supplied ignored CVEs."""
    runner = CliRunner()
    test_file = tmp_path / "valid.py"
    test_file.write_text("print(1)\n", encoding="utf-8")

    mocker.patch(
        "sanopy.cli.scan_handler.Config.load",
        return_value=Config(ignored_cves=["CVE-2026-0994"]),
    )
    mock_engine = mocker.patch("sanopy.cli.scan_handler.Engine")

    runner.invoke(main, ["scan", str(test_file), "--only", "safety"])

    args, kwargs = mock_engine.call_args
    linters = kwargs.get("linters", []) or (args[0] if args else [])
    assert len(linters) == 1
    assert linters[0].ignored_cves == ["CVE-2026-0994"]


def test_cli_init_command(mocker) -> None:
    """Test linter-only init command flow."""
    from sanopy.cli.init_handler import ConfigUpdater

    runner = CliRunner()
    config = Config()

    mocker.patch("sanopy.cli.init_handler.Config.load", return_value=config)
    mocker.patch.object(Config, "save")
    mocker.patch(
        "sanopy.cli.init_handler.click.prompt",
        side_effect=["ruff", "mypy"],
    )
    mocker.patch("sanopy.cli.init_handler.click.confirm", return_value=True)

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    assert "Configuration Saved" in result.output
    assert config.skip_linters == ["ruff"]
    assert config.only_linters == ["mypy"]
    assert isinstance(ConfigUpdater(config), ConfigUpdater)


def test_init_handler_handles_cli_options(mocker) -> None:
    """InitHandler handles non-interactive CLI-provided options."""
    from sanopy.cli.init_handler import InitHandler

    config = Config()
    load_mock = mocker.patch(
        "sanopy.cli.init_handler.Config.load", return_value=config
    )
    save_mock = mocker.patch.object(Config, "save")
    apply_cli_config_mock = mocker.patch(
        "sanopy.cli.init_handler.ConfigUpdater.apply_cli_config"
    )
    print_saved_mock = mocker.patch(
        "sanopy.cli.init_handler.InitHandler.print_saved_summary"
    )

    handler = InitHandler()
    handler.handle_cli_options(only="ruff", skip="mypy")

    load_mock.assert_called_once_with()
    apply_cli_config_mock.assert_called_once_with(only="ruff", skip="mypy")
    save_mock.assert_called_once()
    print_saved_mock.assert_called_once_with()


def test_init_handler_handles_interactive_cancel(mocker) -> None:
    """InitHandler exits without saving when interactive flow is canceled."""
    from sanopy.cli.init_handler import InitHandler

    config = Config()
    load_mock = mocker.patch(
        "sanopy.cli.init_handler.Config.load", return_value=config
    )
    save_mock = mocker.patch.object(Config, "save")
    apply_interactive_mock = mocker.patch(
        "sanopy.cli.init_handler.ConfigUpdater.apply_interactive_config"
    )
    print_setup_mock = mocker.patch(
        "sanopy.cli.init_handler.InitHandler.print_setup_summary"
    )
    print_saved_mock = mocker.patch(
        "sanopy.cli.init_handler.InitHandler.print_saved_summary"
    )
    confirm_mock = mocker.patch(
        "sanopy.cli.init_handler.click.confirm", return_value=False
    )

    handler = InitHandler()
    handler.handle_interactive_options()

    load_mock.assert_called_once_with()
    apply_interactive_mock.assert_called_once_with()
    print_setup_mock.assert_called_once_with()
    confirm_mock.assert_called_once_with(
        "Save this configuration?", default=True
    )
    save_mock.assert_not_called()
    print_saved_mock.assert_not_called()


def test_init_helper_apply_interactive_config(mocker) -> None:
    """Test linter preference selection with validation."""
    from sanopy.cli.init_handler import ConfigUpdater

    config = Config(skip_linters=["ruff"], only_linters=[])
    updater = ConfigUpdater(config)

    mocker.patch(
        "sanopy.cli.init_handler.click.prompt",
        side_effect=["pylint", "bandit"],
    )

    updater.apply_interactive_config()
    assert "pylint" in config.skip_linters
    assert "bandit" in config.only_linters
    assert "ruff" not in config.skip_linters


def test_init_helper_apply_interactive_config_invalid(mocker) -> None:
    """Test that invalid linter names are handled gracefully via public API."""
    from sanopy.cli.init_handler import ConfigUpdater

    config = Config()
    updater = ConfigUpdater(config)

    mocker.patch(
        "sanopy.cli.init_handler.click.prompt",
        side_effect=["ruff,invalid_linter", ""],
    )

    updater.apply_interactive_config()
    assert "ruff" in config.skip_linters
    assert "invalid_linter" not in config.skip_linters


def test_init_helper_apply_interactive_config_overlap(mocker) -> None:
    """Test overlap removal between skip and only linters."""
    from sanopy.cli.init_handler import ConfigUpdater

    config = Config()
    updater = ConfigUpdater(config)

    mocker.patch(
        "sanopy.cli.init_handler.click.prompt",
        side_effect=["ruff,pylint", "pylint,bandit"],
    )

    updater.apply_interactive_config()
    assert "pylint" not in config.skip_linters
    assert "pylint" in config.only_linters


def test_config_updater_has_no_summary_rendering_method() -> None:
    """ConfigUpdater keeps preference logic only; rendering stays outside."""
    from sanopy.cli.init_handler import ConfigUpdater

    assert not hasattr(ConfigUpdater, "print_summary")


def test_config_summary_printer_renders_setup_and_saved(mocker) -> None:
    """Summary rendering is handled by InitHandler methods."""
    from sanopy.cli.init_handler import InitHandler

    config = Config(skip_linters=["ruff"], only_linters=["mypy"])
    load_mock = mocker.patch(
        "sanopy.cli.init_handler.Config.load", return_value=config
    )
    print_mock = mocker.patch("sanopy.cli.init_handler.console.print")

    handler = InitHandler()
    handler.print_setup_summary()
    handler.print_saved_summary()

    load_mock.assert_called_once_with()
    assert print_mock.call_count == 2
    assert print_mock.call_args_list[0].args[0].title == "Setup Summary"
    assert (
        print_mock.call_args_list[1].args[0].title
        == "Configuration Saved to .sanopy.toml"
    )


def test_init_handler_constructor_has_no_config_parameter() -> None:
    """InitHandler constructor should not expose config injection."""
    import inspect

    from sanopy.cli.init_handler import InitHandler

    signature = inspect.signature(InitHandler.__init__)
    assert "config" not in signature.parameters


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

    from sanopy.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output, ["testlinter"])
    reporter.write_json_report()

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["linter"]["name"] == "TestLinter"


def test_scan_reporter_write_human_readable_report(
    tmp_path, fake_result
) -> None:
    """write_human_readable_report writes a markdown file in the cwd."""
    import os
    from pathlib import Path

    from sanopy.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output, ["testlinter"])

    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        reporter.write_human_readable_report()
    finally:
        os.chdir(old_cwd)

    report = reporter.get_human_readable_path()
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "# Linting Report" in content
    assert "TestLinter" in content
    assert "Something wrong" in content
    assert "bad_code()" in content


def test_scan_reporter_write_summary_report(tmp_path, fake_result) -> None:
    """write_summary_report prints the findings table."""
    from sanopy.cli.scan_handler import ScanReporter

    output = tmp_path / "out.json"
    reporter = ScanReporter([fake_result], tmp_path, output, ["testlinter"])

    reporter.write_summary_report()
