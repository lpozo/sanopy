"""Tests for scan preflight: config, linter availability, filters."""
# pylint: disable=redefined-outer-name

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from sanopy.cli.cli import main
from sanopy.linters import LINTER_MAP


@pytest.fixture(autouse=True)
def _use_mock_scan_config(mock_scan_config):
    """Apply the shared scan-config mocks to every test in this module."""


def _patch_scan_env(
    mocker,
    *,
    exists: bool = True,
    load_error: Exception | None = None,
    unavailable: tuple[str, ...] = (),
) -> None:
    """Override the autouse scan fixture for one preflight scenario."""
    mocker.patch("sanopy.cli.scan_handler.Config.exists", return_value=exists)
    if load_error is not None:
        mocker.patch(
            "sanopy.cli.scan_handler.Config.load", side_effect=load_error
        )
    for name in unavailable:
        mocker.patch.object(
            LINTER_MAP[name], "is_available", return_value=False
        )


PREFLIGHT_FAILURES = [
    pytest.param(
        [],
        {"exists": False},
        ["No .sanopy.toml found", "sanopy init"],
        [],
        id="missing-config",
    ),
    pytest.param(
        [],
        {"load_error": ValueError("Invalid configuration at .sanopy.toml.")},
        ["Invalid configuration"],
        [],
        id="invalid-config",
    ),
    pytest.param(
        [],
        {"load_error": FileNotFoundError("Configuration file not found")},
        ["Configuration file not found"],
        [],
        id="config-vanished-after-exists-check",
    ),
    pytest.param(
        ["--only", "ruff"],
        {"unavailable": ("ruff",)},
        ["Missing linters", "ruff", "pip install 'sanopy[ruff]'"],
        [],
        id="one-linter-missing",
    ),
    pytest.param(
        ["--only", "ruff,mypy"],
        {"unavailable": ("ruff", "mypy")},
        ["Missing linters", "pip install 'sanopy[mypy,ruff]'"],
        [],
        id="two-linters-missing-hint-is-combined",
    ),
    pytest.param(
        ["--only", "rufff"],
        {},
        ["No linters selected", "Unknown linter name(s): rufff"],
        [],
        id="typo-in-only",
    ),
    pytest.param(
        ["--only", "ruff", "--skip", "ruff"],
        {},
        ["No linters selected"],
        ["Unknown linter name"],
        id="only-and-skip-cancel-out",
    ),
    pytest.param(
        ["--skip", ",".join(LINTER_MAP)],
        {},
        ["No linters selected"],
        ["Unknown linter name"],
        id="everything-skipped",
    ),
]


@pytest.mark.parametrize(
    "extra_args, patches, must_contain, must_not_contain",
    PREFLIGHT_FAILURES,
)
@pytest.mark.parametrize("output_mode", ["machine", "human"])
def test_scan_preflight_failures(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mocker,
    tmp_path,
    output_mode: str,
    extra_args: list[str],
    patches: dict[str, Any],
    must_contain: list[str],
    must_not_contain: list[str],
) -> None:
    """Every preflight failure exits 2, on stderr, leaving stdout clean.

    stdout must stay empty in *both* modes: it carries the JSON document
    in machine mode, and preflight runs before any per-target output.
    """
    runner = CliRunner()
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")
    _patch_scan_env(mocker, **patches)

    result = runner.invoke(
        main,
        ["scan", str(target), "--output-mode", output_mode, *extra_args],
    )

    assert result.exit_code == 2
    for fragment in must_contain:
        assert fragment in result.stderr
    for fragment in must_not_contain:
        assert fragment not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("target_count", [1, 2, 3, 5])
@pytest.mark.parametrize(
    "patches, message",
    [
        pytest.param({"exists": False}, "No .sanopy.toml found", id="config"),
        pytest.param(
            {"load_error": ValueError("Invalid configuration")},
            "Invalid configuration",
            id="invalid",
        ),
    ],
)
def test_scan_preflight_reports_once_per_run(
    mocker,
    tmp_path,
    target_count: int,
    patches: dict[str, Any],
    message: str,
) -> None:
    """Preflight is per-run, so N targets still produce one message."""
    runner = CliRunner()
    targets = []
    for index in range(target_count):
        path = tmp_path / f"f{index}.py"
        path.write_text("x = 1\n", encoding="utf-8")
        targets.append(str(path))
    _patch_scan_env(mocker, **patches)

    result = runner.invoke(main, ["scan", *targets])

    assert result.exit_code == 2
    assert result.stderr.count(message) == 1


@pytest.mark.parametrize(
    "args, expected_active",
    [
        pytest.param([], list(LINTER_MAP), id="all-by-default"),
        pytest.param(["--only", "ruff"], ["ruff"], id="only-one"),
        pytest.param(
            ["--only", "ruff,mypy"],
            [n for n in LINTER_MAP if n in {"ruff", "mypy"}],
            id="only-two",
        ),
        pytest.param(
            ["--skip", "ruff"],
            [n for n in LINTER_MAP if n != "ruff"],
            id="skip-one",
        ),
        pytest.param(["--only", "RUFF"], ["ruff"], id="case-insensitive"),
        pytest.param(
            ["--only", " ruff , mypy "],
            [n for n in LINTER_MAP if n in {"ruff", "mypy"}],
            id="whitespace-tolerant",
        ),
        # Blank filters mean "no filter", not "match nothing".
        pytest.param(["--only", "  "], list(LINTER_MAP), id="blank-only"),
        pytest.param(["--skip", ","], list(LINTER_MAP), id="comma-only-skip"),
    ],
)
def test_scan_reports_the_linters_it_ran(
    mocker, tmp_path, args: list[str], expected_active: list[str]
) -> None:
    """The JSON envelope names exactly the linters preflight selected."""

    runner = CliRunner()
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")
    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        return_value=[],
    )

    result = runner.invoke(main, ["scan", str(target), *args])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["run"]["active_linters"] == expected_active


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(RuntimeError("engine exploded"), id="runtime-error"),
        pytest.param(OSError("disk gone"), id="os-error"),
        pytest.param(ValueError("bad parse"), id="value-error"),
    ],
)
def test_scan_failure_is_reported_on_stderr(
    mocker, tmp_path, error: Exception
) -> None:
    """A crashing scan reports the cause instead of exiting 2 silently."""
    runner = CliRunner()
    target = tmp_path / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")
    mocker.patch(
        "sanopy.cli.scan_handler.Engine.run_all",
        new_callable=AsyncMock,
        side_effect=error,
    )

    result = runner.invoke(main, ["scan", str(target)])

    assert result.exit_code == 2
    assert str(error) in result.stderr
