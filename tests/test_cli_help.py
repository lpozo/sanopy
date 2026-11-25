"""CLI help-surface tests."""

import pytest
from click.testing import CliRunner

from sanopy.cli.cli import main


@pytest.mark.parametrize(
    "command, expected_options",
    [
        pytest.param(
            "scan",
            ["--only", "--skip", "--output", "--human-readable"],
            id="scan-help",
        ),
        pytest.param(
            "init",
            ["--only", "--skip", "--no-install"],
            id="init-help",
        ),
    ],
)
def test_cli_command_help(command: str, expected_options: list[str]) -> None:
    """scan and init expose their options via --help."""
    runner = CliRunner()

    result = runner.invoke(main, [command, "--help"])

    assert result.exit_code == 0
    for option in expected_options:
        assert option in result.output


@pytest.mark.parametrize(
    "command",
    ["scan", "init"],
)
def test_cli_group_help_lists_commands(command: str) -> None:
    """The top-level help lists both subcommands."""
    runner = CliRunner()

    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert command in result.output
