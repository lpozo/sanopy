"""Tests for the `init` command's install flow."""
# pylint: disable=redefined-outer-name

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from sanopy.cli.cli import main
from sanopy.config import Config
from sanopy.linters import LINTER_MAP
from sanopy.linters.base import InstallResult


@pytest.fixture(autouse=True)
def _use_mock_scan_config(mock_scan_config):
    """Apply the shared scan-config mocks to every test in this module."""


def _patch_init_env(
    mocker,
    *,
    missing: tuple[str, ...] = (),
    outcomes: dict[str, InstallResult] | None = None,
    load_error: Exception | None = None,
) -> dict[str, MagicMock]:
    """Set up an init scenario and return the per-linter install mocks."""
    if load_error is None:
        mocker.patch(
            "sanopy.cli.init_handler.Config.load", return_value=Config()
        )
    else:
        mocker.patch(
            "sanopy.cli.init_handler.Config.load", side_effect=load_error
        )
    mocker.patch.object(Config, "save")

    installs: dict[str, MagicMock] = {}
    for name in missing:
        cls = LINTER_MAP[name]
        mocker.patch.object(cls, "is_available", return_value=False)
        result = (outcomes or {}).get(name, InstallResult(True, ""))
        installs[name] = mocker.patch.object(
            cls, "install", return_value=result
        )
    return installs


@pytest.mark.parametrize(
    "missing, outcomes, expect_exit, out_bits, err_bits",
    [
        pytest.param((), {}, 0, [], [], id="nothing-missing"),
        pytest.param(
            ("ruff",), {}, 0, ["ruff installed"], [], id="one-success"
        ),
        pytest.param(
            ("ruff", "mypy"),
            {},
            0,
            ["ruff installed", "mypy installed"],
            [],
            id="two-successes",
        ),
        pytest.param(
            ("ruff",),
            {"ruff": InstallResult(False, "error: no venv")},
            2,
            [],
            ["Failed to install ruff", "error: no venv", "1 linter(s)"],
            id="one-failure",
        ),
        pytest.param(
            ("ruff", "mypy"),
            {
                "ruff": InstallResult(False, "boom-ruff"),
                "mypy": InstallResult(False, "boom-mypy"),
            },
            2,
            [],
            ["boom-ruff", "boom-mypy", "2 linter(s)"],
            id="two-failures",
        ),
        pytest.param(
            ("ruff", "mypy"),
            {"mypy": InstallResult(False, "boom-mypy")},
            2,
            ["ruff installed"],
            ["boom-mypy", "1 linter(s)"],
            id="partial-failure-still-exits-2",
        ),
        pytest.param(
            ("ruff",),
            {"ruff": InstallResult(False, "")},
            2,
            [],
            ["Failed to install ruff", "1 linter(s)"],
            id="failure-without-output",
        ),
    ],
)
def test_init_non_interactive_install(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker,
    missing: tuple[str, ...],
    outcomes: dict[str, InstallResult],
    expect_exit: int,
    out_bits: list[str],
    err_bits: list[str],
) -> None:
    """init installs what is missing and exits 2 if any install fails."""
    runner = CliRunner()
    installs = _patch_init_env(mocker, missing=missing, outcomes=outcomes)

    result = runner.invoke(main, ["init", "--only", "ruff,mypy"])

    assert result.exit_code == expect_exit
    for mock in installs.values():
        mock.assert_called_once_with()
    for fragment in out_bits:
        assert fragment in result.stdout
    for fragment in err_bits:
        assert fragment in result.stderr
    # The config is written regardless, so a retry keeps the selection.
    assert "Configuration Saved" in result.stdout


@pytest.mark.parametrize(
    "outcomes",
    [
        pytest.param({}, id="would-have-succeeded"),
        pytest.param(
            {"ruff": InstallResult(False, "boom")}, id="would-have-failed"
        ),
    ],
)
def test_init_no_install_never_touches_the_environment(
    mocker, outcomes: dict[str, InstallResult]
) -> None:
    """--no-install writes the config and exits 0 without installing."""
    runner = CliRunner()
    installs = _patch_init_env(mocker, missing=("ruff",), outcomes=outcomes)

    result = runner.invoke(main, ["init", "--only", "ruff", "--no-install"])

    assert result.exit_code == 0
    installs["ruff"].assert_not_called()
    assert "Configuration Saved" in result.stdout


@pytest.mark.parametrize(
    "accept, expect_install, expect_exit, expect_output",
    [
        pytest.param(True, True, 0, "ruff installed", id="accepted"),
        pytest.param(
            False, False, 0, "pip install 'sanopy[ruff]'", id="declined"
        ),
    ],
)
def test_init_interactive_install_prompt(
    mocker,
    accept: bool,
    expect_install: bool,
    expect_exit: int,
    expect_output: str,
) -> None:
    """The wizard asks before installing, and hints when declined."""
    runner = CliRunner()
    installs = _patch_init_env(mocker, missing=("ruff",))
    mocker.patch(
        "sanopy.cli.init_handler.click.prompt", side_effect=["", "ruff"]
    )
    # Confirm the save, then answer the install prompt.
    mocker.patch(
        "sanopy.cli.init_handler.click.confirm", side_effect=[True, accept]
    )

    result = runner.invoke(main, ["init"])

    assert result.exit_code == expect_exit
    assert installs["ruff"].called is expect_install
    assert expect_output in result.output


def test_init_interactive_install_failure_exits_2(mocker) -> None:
    """A failed install in the wizard also exits 2."""
    runner = CliRunner()
    _patch_init_env(
        mocker,
        missing=("ruff",),
        outcomes={"ruff": InstallResult(False, "boom")},
    )
    mocker.patch(
        "sanopy.cli.init_handler.click.prompt", side_effect=["", "ruff"]
    )
    mocker.patch(
        "sanopy.cli.init_handler.click.confirm", side_effect=[True, True]
    )

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 2
    assert "boom" in result.stderr


def test_init_cancelled_wizard_installs_nothing(mocker) -> None:
    """Declining the save aborts before any install is attempted."""
    runner = CliRunner()
    installs = _patch_init_env(mocker, missing=("ruff",))
    mocker.patch(
        "sanopy.cli.init_handler.click.prompt", side_effect=["", "ruff"]
    )
    mocker.patch("sanopy.cli.init_handler.click.confirm", return_value=False)

    result = runner.invoke(main, ["init"])

    assert result.exit_code == 0
    installs["ruff"].assert_not_called()
    assert "Setup cancelled" in result.output
    assert "Configuration Saved" not in result.output


@pytest.mark.parametrize(
    "load_error, expect_warning",
    [
        pytest.param(
            FileNotFoundError("not found"), False, id="missing-is-normal"
        ),
        pytest.param(
            ValueError("Invalid configuration at .sanopy.toml."),
            True,
            id="invalid-is-warned",
        ),
    ],
)
def test_init_config_load_failures(
    mocker, load_error: Exception, expect_warning: bool
) -> None:
    """A missing config is routine; an unreadable one must be flagged.

    Saving replaces the file, so silently discarding it would lose the
    user's settings without a word.
    """
    runner = CliRunner()
    _patch_init_env(mocker, load_error=load_error)

    result = runner.invoke(main, ["init", "--only", "ruff"])

    assert result.exit_code == 0
    assert ("overwrite" in result.stderr) is expect_warning
    assert ("Invalid configuration" in result.stderr) is expect_warning
