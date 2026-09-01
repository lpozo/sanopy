"""Tests for BaseLinter's invocation-resolution and install ladders."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sanopy.cli.scan_handler import _build_linter
from sanopy.config import Config
from sanopy.linters import LINTER_MAP, BaseLinter
from sanopy.linters.base import (
    AsyncCompletedProcess,
    InstallResult,
    LinterNotAvailableError,
    LinterTimeoutError,
)
from sanopy.linters.result import LinterResult

WHICH = "sanopy.linters.base.shutil.which"
FIND_SPEC = "sanopy.linters.base.importlib.util.find_spec"
RUN = "sanopy.linters.base.subprocess.run"
EXECUTABLE = "sanopy.linters.base.sys.executable"


class SampleLinter(BaseLinter):
    """Minimal concrete linter for exercising the base-class ladders."""

    name = "Sample"
    package_name = "mock-linter"
    module_name: str | None = "mock_linter"

    def build_command(self, target: Path) -> list[str]:
        return ["mock-linter", "--check", str(target)]

    def parse_output(
        self, process_result: AsyncCompletedProcess, target: Path
    ) -> list[LinterResult]:
        return []


class ScriptOnlyLinter(SampleLinter):
    """Linter that rejects ``python -m``, the way Semgrep does."""

    module_name: str | None = None


# ── resolve_command: the invocation ladder ───────────────────────────


ON_PATH = "/usr/bin/mock-linter"
SIBLING = "/venv/bin/mock-linter"


def _which(on_path: str | None, sibling: str | None):
    """Fake shutil.which distinguishing a PATH lookup from a scoped one.

    resolve_command's second rung passes ``path=<dir of sys.executable>``,
    so the two lookups are told apart by that keyword.
    """

    def which(cmd: str, path: str | None = None) -> str | None:
        del cmd
        return sibling if path else on_path

    return which


@pytest.mark.parametrize(
    "cls, on_path, sibling, spec_found, args, expected",
    [
        # 1. Console script on PATH outranks everything else.
        pytest.param(
            SampleLinter,
            ON_PATH,
            SIBLING,
            True,
            [],
            [ON_PATH],
            id="path-wins-over-sibling-and-module",
        ),
        pytest.param(
            SampleLinter,
            ON_PATH,
            None,
            False,
            [],
            [ON_PATH],
            id="path-only",
        ),
        pytest.param(
            ScriptOnlyLinter,
            ON_PATH,
            None,
            None,
            [],
            [ON_PATH],
            id="script-only-linter-on-path",
        ),
        # 2. Script beside our interpreter: a non-activated venv, pipx or
        #    uv tool install. The only rung that reaches a script-only
        #    linter there, which is why Semgrep needs it.
        pytest.param(
            SampleLinter,
            None,
            SIBLING,
            True,
            [],
            [SIBLING],
            id="sibling-wins-over-module",
        ),
        pytest.param(
            ScriptOnlyLinter,
            None,
            SIBLING,
            None,
            [],
            [SIBLING],
            id="sibling-reaches-script-only-linter",
        ),
        # 3. python -m in our own interpreter.
        pytest.param(
            SampleLinter,
            None,
            None,
            True,
            [],
            ["/venv/bin/python", "-m", "mock_linter"],
            id="module-fallback",
        ),
        # Nothing resolves.
        pytest.param(
            SampleLinter, None, None, False, [], None, id="not-installed"
        ),
        pytest.param(
            ScriptOnlyLinter,
            None,
            None,
            None,
            [],
            None,
            id="script-only-nowhere",
        ),
        # Argument passthrough on every rung.
        pytest.param(
            SampleLinter,
            ON_PATH,
            None,
            True,
            ["--check", "a.py"],
            [ON_PATH, "--check", "a.py"],
            id="args-via-path",
        ),
        pytest.param(
            SampleLinter,
            None,
            SIBLING,
            True,
            ["--check", "a.py"],
            [SIBLING, "--check", "a.py"],
            id="args-via-sibling",
        ),
        pytest.param(
            SampleLinter,
            None,
            None,
            True,
            ["--check", "a.py"],
            ["/venv/bin/python", "-m", "mock_linter", "--check", "a.py"],
            id="args-via-module",
        ),
        # Arguments that look like flags, or are empty, survive intact.
        pytest.param(
            SampleLinter,
            ON_PATH,
            None,
            True,
            ["--config", "", "-"],
            [ON_PATH, "--config", "", "-"],
            id="args-empty-and-dash",
        ),
    ],
)
def test_resolve_command(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    cls: type[BaseLinter],
    on_path: str | None,
    sibling: str | None,
    spec_found: bool | None,
    args: list[str],
    expected: list[str] | None,
) -> None:
    """resolve_command walks PATH, then our own bin/, then `python -m`."""
    spec = MagicMock() if spec_found else None
    with (
        patch(WHICH, side_effect=_which(on_path, sibling)),
        patch(FIND_SPEC, return_value=spec),
        patch(EXECUTABLE, "/venv/bin/python"),
    ):
        assert cls.resolve_command(args) == expected


def test_resolve_command_skips_find_spec_without_module_name() -> None:
    """module_name=None must not even probe for an importable module."""
    find_spec = MagicMock()
    with (
        patch(WHICH, side_effect=_which(None, None)),
        patch(FIND_SPEC, find_spec),
    ):
        assert ScriptOnlyLinter.resolve_command([]) is None

    find_spec.assert_not_called()


def test_resolve_command_scopes_the_sibling_lookup_to_our_own_bin() -> None:
    """The second rung must search only beside the running interpreter."""
    which = MagicMock(return_value=None)
    with (
        patch(WHICH, which),
        patch(FIND_SPEC, return_value=None),
        patch(EXECUTABLE, "/venv/bin/python"),
    ):
        SampleLinter.resolve_command([])

    assert which.call_args_list[1].kwargs == {"path": "/venv/bin"}


def test_resolve_command_does_not_mutate_the_args_list() -> None:
    """Callers pass a slice of build_command output; it must survive."""
    args = ["--check", "a.py"]
    with patch(WHICH, side_effect=_which(ON_PATH, None)):
        SampleLinter.resolve_command(args)

    assert args == ["--check", "a.py"]


# ── is_available: must never disagree with resolve_command ───────────


@pytest.mark.parametrize(
    "resolved, expected",
    [
        pytest.param(["/usr/bin/x"], True, id="resolved"),
        pytest.param(["/usr/bin/x", "-m", "y"], True, id="resolved-multi"),
        pytest.param(None, False, id="unresolved"),
    ],
)
def test_is_available_follows_resolve_command(
    resolved: list[str] | None, expected: bool
) -> None:
    """is_available is defined by resolve_command, so they cannot drift."""
    with patch.object(SampleLinter, "resolve_command", return_value=resolved):
        assert SampleLinter.is_available() is expected


@pytest.mark.parametrize(
    "cls, on_path, sibling, spec_found, expected",
    [
        pytest.param(SampleLinter, ON_PATH, None, False, True, id="on-path"),
        # The regressions this ladder exists for: installed in Sanopy's own
        # environment, whose bin/ is not exported on PATH. Neither may read
        # as missing.
        pytest.param(
            SampleLinter, None, None, True, True, id="importable-off-path"
        ),
        pytest.param(
            ScriptOnlyLinter,
            None,
            SIBLING,
            None,
            True,
            id="script-only-in-our-own-bin",
        ),
        pytest.param(
            SampleLinter, None, None, False, False, id="genuinely-absent"
        ),
        pytest.param(
            ScriptOnlyLinter,
            None,
            None,
            None,
            False,
            id="script-only-genuinely-absent",
        ),
    ],
)
def test_is_available_end_to_end(
    cls: type[BaseLinter],
    on_path: str | None,
    sibling: str | None,
    spec_found: bool | None,
    expected: bool,
) -> None:
    """Availability reflects any invocation strategy succeeding."""
    spec = MagicMock() if spec_found else None
    with (
        patch(WHICH, side_effect=_which(on_path, sibling)),
        patch(FIND_SPEC, return_value=spec),
    ):
        assert cls.is_available() is expected


@pytest.mark.asyncio
async def test_run_raises_when_linter_not_installed() -> None:
    """run() raises a clear error rather than spawning a missing binary."""
    linter = SampleLinter()
    with (
        patch.object(SampleLinter, "resolve_command", return_value=None),
        pytest.raises(LinterNotAvailableError, match="not installed"),
    ):
        await linter.run(Path("a.py"))


@pytest.mark.asyncio
async def test_run_replaces_only_the_leading_command_name() -> None:
    """run() drops build_command()[0] and keeps every remaining argument."""
    linter = SampleLinter()
    captured: list[list[str]] = []

    async def fake_run_command(self, cmd, cwd):  # noqa: ARG001
        captured.append(cmd)
        return AsyncCompletedProcess(stdout="", stderr="", returncode=0)

    with (
        patch(WHICH, side_effect=_which(ON_PATH, None)),
        patch.object(SampleLinter, "_run_command", fake_run_command),
    ):
        await linter.run(Path("a.py"))

    assert captured == [[ON_PATH, "--check", "a.py"]]


class FindingLinter(SampleLinter):
    """SampleLinter whose parse_output returns a single finding."""

    def parse_output(
        self, process_result: AsyncCompletedProcess, target: Path
    ) -> list[LinterResult]:
        return [
            LinterResult(
                Path("a.py"), 1, None, None, None, self.name, "E1", "msg", ""
            )
        ]


@pytest.mark.parametrize(
    "linter_cls, returncode, warn",
    [
        # Clean run: exit 0, no findings -> no warning.
        pytest.param(SampleLinter, 0, False, id="clean"),
        # Non-zero exit with findings is the normal "issues found" signal.
        pytest.param(FindingLinter, 1, False, id="issues-found"),
        # Non-zero exit with NO findings suggests a crash or failure to run.
        pytest.param(SampleLinter, 1, True, id="crashed"),
        pytest.param(SampleLinter, 127, True, id="command-not-found"),
    ],
)
@pytest.mark.asyncio
async def test_run_warns_on_nonzero_exit_without_findings(
    linter_cls, returncode, warn, caplog
) -> None:
    """run() warns when a linter exits non-zero but reports no findings."""
    linter = linter_cls()

    async def fake_run_command(self, cmd, cwd):  # noqa: ARG001
        return AsyncCompletedProcess(
            stdout="", stderr="boom output", returncode=returncode
        )

    with (
        patch.object(linter_cls, "resolve_command", return_value=["mock"]),
        patch.object(linter_cls, "_run_command", fake_run_command),
    ):
        await linter.run(Path("a.py"))

    messages = [m for m in caplog.messages if "exited with code" in m]
    if warn:
        assert any(
            f"exited with code {returncode}" in m and "boom output" in m
            for m in messages
        )
    else:
        assert not messages


@pytest.mark.asyncio
async def test_run_times_out() -> None:
    """run() raises LinterTimeoutError when a linter hangs past its timeout."""
    linter = SampleLinter(command_timeout=0.2)

    with (
        patch.object(
            SampleLinter,
            "resolve_command",
            return_value=[
                sys.executable,
                "-c",
                "import time; time.sleep(5)",
            ],
        ),
        pytest.raises(LinterTimeoutError, match="0.2s timeout"),
    ):
        await linter.run(Path("a.py"))


# ── install ──────────────────────────────────────────────────────────

UV_CMD = [
    "uv",
    "pip",
    "install",
    "--python",
    "/venv/bin/python",
    "mock-linter",
]
PIP_CMD = ["/venv/bin/python", "-m", "pip", "install", "mock-linter"]


@pytest.mark.parametrize(
    "uv_present, returncode, stdout, stderr, expected_cmd, ok, output",
    [
        # uv is preferred, and pinned to Sanopy's own interpreter so the
        # package lands where resolve_command will find it.
        pytest.param(True, 0, "", "", UV_CMD, True, "", id="uv-success"),
        pytest.param(False, 0, "", "", PIP_CMD, True, "", id="pip-success"),
        # Failure surfaces the installer's own output.
        pytest.param(
            True,
            1,
            "",
            "error: No virtual environment",
            UV_CMD,
            False,
            "error: No virtual environment",
            id="uv-failure-stderr",
        ),
        pytest.param(
            False,
            1,
            "",
            "No module named pip",
            PIP_CMD,
            False,
            "No module named pip",
            id="pip-failure-stderr",
        ),
        # stderr wins when both streams have content...
        pytest.param(
            True,
            1,
            "on stdout",
            "on stderr",
            UV_CMD,
            False,
            "on stderr",
            id="stderr-preferred",
        ),
        # ...but stdout is used when stderr is empty, since some
        # installers report errors there.
        pytest.param(
            True,
            1,
            "on stdout",
            "",
            UV_CMD,
            False,
            "on stdout",
            id="stdout-fallback",
        ),
        # Surrounding whitespace is trimmed.
        pytest.param(
            True,
            1,
            "",
            "  padded  \n",
            UV_CMD,
            False,
            "padded",
            id="output-stripped",
        ),
        # A silent failure still reports as a failure.
        pytest.param(
            True, 1, "", "", UV_CMD, False, "", id="failure-no-output"
        ),
        # Any non-zero code is a failure, not just 1.
        pytest.param(True, 2, "", "boom", UV_CMD, False, "boom", id="exit-2"),
        pytest.param(
            True, -9, "", "killed", UV_CMD, False, "killed", id="signal"
        ),
        # Success with chatter on stdout is still a success.
        pytest.param(
            True,
            0,
            "Installed 1 package",
            "",
            UV_CMD,
            True,
            "Installed 1 package",
            id="success-with-output",
        ),
    ],
)
def test_install(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    uv_present: bool,
    returncode: int,
    stdout: str,
    stderr: str,
    expected_cmd: list[str],
    ok: bool,
    output: str,
) -> None:
    """install() picks uv or pip and reports the outcome plus diagnostics."""
    mock_run = MagicMock(
        return_value=MagicMock(
            returncode=returncode, stdout=stdout, stderr=stderr
        )
    )

    def which(cmd):
        return "/usr/bin/uv" if cmd == "uv" and uv_present else None

    with (
        patch(WHICH, side_effect=which),
        patch(RUN, mock_run),
        patch(EXECUTABLE, "/venv/bin/python"),
    ):
        result = SampleLinter.install()

    assert result == InstallResult(succeeded=ok, output=output)
    mock_run.assert_called_once_with(
        expected_cmd, capture_output=True, text=True, check=False
    )


def test_install_never_uses_a_shell() -> None:
    """The package name reaches the installer as an argv element."""
    mock_run = MagicMock(
        return_value=MagicMock(returncode=0, stdout="", stderr="")
    )
    with patch(WHICH, return_value=None), patch(RUN, mock_run):
        SampleLinter.install()

    _, kwargs = mock_run.call_args
    assert "shell" not in kwargs
    assert isinstance(mock_run.call_args[0][0], list)


# ── Invariants across every registered linter ────────────────────────


@pytest.mark.parametrize("name", sorted(LINTER_MAP))
def test_linter_declares_a_usable_package_name(name: str) -> None:
    """package_name is the PyPI name and the console-script name."""
    package_name = LINTER_MAP[name].package_name

    assert package_name
    assert package_name == package_name.strip()
    assert " " not in package_name


@pytest.mark.parametrize("name", sorted(LINTER_MAP))
def test_linter_module_name_is_importable_or_none(name: str) -> None:
    """A declared module_name must really be importable.

    ``pip-audit`` is the trap here: the distribution is hyphenated but the
    module is ``pip_audit``, so ``python -m pip-audit`` never worked.
    """
    module_name = LINTER_MAP[name].module_name
    if module_name is None:
        pytest.skip(f"{name} is console-script only")

    assert "-" not in module_name
    assert module_name.isidentifier()
    assert importlib.util.find_spec(module_name) is not None


@pytest.mark.parametrize("name", sorted(LINTER_MAP))
def test_build_command_leads_with_package_name(name: str) -> None:
    """build_command()[0] must be package_name.

    run() drops the first element and lets resolve_command supply the real
    executable. If a linter led with something else, that argument would be
    silently swallowed instead of reaching the tool.
    """
    linter = _build_linter(name, Config())
    command = linter.build_command(Path("a.py"))

    assert command
    assert command[0] == linter.package_name


@pytest.mark.parametrize("name", sorted(LINTER_MAP))
def test_from_config_returns_configured_linter(name: str) -> None:
    """from_config builds a linter carrying the active config."""
    config = Config()
    linter = LINTER_MAP[name].from_config(config)

    assert isinstance(linter, BaseLinter)
    assert linter.config is config


def test_from_config_base_forwards_config_only() -> None:
    """The generic from_config just passes config to __init__."""
    config = Config()
    linter = SampleLinter.from_config(config)

    assert isinstance(linter, SampleLinter)
    assert linter.config is config


@pytest.mark.parametrize("name", sorted(LINTER_MAP))
def test_registered_linter_resolves_in_this_environment(name: str) -> None:
    """Every linter resolves when its extra is installed (as in CI)."""
    cls = LINTER_MAP[name]
    resolved = cls.resolve_command(["--version"])

    assert resolved is not None, f"{name} did not resolve"
    assert resolved[-1] == "--version"
    assert cls.is_available() is True
