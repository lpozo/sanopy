"""Abstract base class for all linters."""

from __future__ import annotations

import abc
import asyncio
import importlib.util
import logging
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sanopy.config import DEFAULT_LINTER_CONFIGS
from sanopy.linters.config_discovery import (
    find_nearest_local_config,
    is_test_path,
    materialize_linter_config,
)
from sanopy.linters.result import LinterResult

if TYPE_CHECKING:
    from sanopy.config import Config

logger = logging.getLogger(__name__)


@dataclass  # pylint: disable=too-few-public-methods
class AsyncCompletedProcess:
    """Mock-like class for asyncio.subprocess results."""

    stdout: str
    stderr: str
    returncode: int


@dataclass  # pylint: disable=too-few-public-methods
class InstallResult:
    """Outcome of an attempt to install a linter package."""

    succeeded: bool
    output: str


class LinterNotAvailableError(RuntimeError):
    """Raised when a linter cannot be resolved in any environment."""


class BaseLinter(abc.ABC):
    """Abstract base class for all linters."""

    name: str

    #: PyPI distribution name, which is also the console-script name.
    package_name: str

    #: Importable module usable as ``python -m <module_name>``. ``None``
    #: when the package has no runnable module and must be invoked
    #: through its console script (e.g. Semgrep rejects ``python -m``).
    module_name: str | None = None

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the linter.

        Args:
            config: The active configuration, used to resolve bundled
                linter settings. Defaults to ``None``.
        """
        self.config = config

    @classmethod
    def from_config(cls, config: Config | None = None) -> BaseLinter:
        """Instantiate the linter from the active configuration.

        The base implementation passes ``config`` straight through. A
        subclass that needs config-derived settings beyond the shared
        ``config`` attribute overrides this to forward them.

        Args:
            config: The active configuration, or ``None`` for defaults.

        Returns:
            A configured linter instance.
        """
        return cls(config=config)

    @classmethod
    def resolve_command(cls, args: list[str]) -> list[str] | None:
        """Resolve the argv used to invoke this linter, if it is installed.

        Three invocation strategies are tried, in order:

        1. The console script, when it is on ``PATH``.
        2. The console script sitting beside the running interpreter.
           This reaches Sanopy's own environment when its ``bin``
           directory is not exported on ``PATH`` — a non-activated
           virtualenv, or a ``pipx`` / ``uv tool`` install. It is the
           only rung that can find a script-only linter there.
        3. ``python -m <module_name>`` in that same interpreter.

        ``is_available`` is defined in terms of this method so that the
        availability check can never disagree with the invocation.

        Args:
            args: Arguments to append after the resolved executable.

        Returns:
            The full argv, or ``None`` when the linter is not installed.
        """
        binary = shutil.which(cls.package_name)
        if binary:
            return [binary, *args]

        sibling = shutil.which(
            cls.package_name, path=str(Path(sys.executable).parent)
        )
        if sibling:
            return [sibling, *args]

        if cls.module_name and importlib.util.find_spec(cls.module_name):
            return [sys.executable, "-m", cls.module_name, *args]
        return None

    @classmethod
    def is_available(cls) -> bool:
        """Check whether the linter can be invoked from this environment.

        Returns:
            ``True`` if the linter resolves to a runnable command.
        """
        return cls.resolve_command([]) is not None

    @classmethod
    def install(cls) -> InstallResult:
        """Install the linter package into the environment Sanopy runs from.

        Both branches target ``sys.executable`` explicitly so that the
        package lands in the same environment ``resolve_command`` probes.
        ``uv`` is preferred when present because it is markedly faster.

        Returns:
            An ``InstallResult`` carrying the outcome and, on failure,
            the combined installer output for diagnostics.
        """
        cmd: list[str]
        if shutil.which("uv"):
            cmd = [
                "uv",
                "pip",
                "install",
                "--python",
                sys.executable,
                cls.package_name,
            ]
        else:
            cmd = [sys.executable, "-m", "pip", "install", cls.package_name]
        result = subprocess.run(  # nosec B603
            cmd, capture_output=True, text=True, check=False
        )
        return InstallResult(
            succeeded=result.returncode == 0,
            output=(result.stderr or result.stdout).strip(),
        )

    @abc.abstractmethod
    def build_command(self, target: Path) -> list[str]:
        """Build the command used to invoke the linter.

        Args:
            target: The file or directory to lint.

        Returns:
            A list of command arguments to pass to the subprocess.
        """

    @abc.abstractmethod
    def parse_output(
        self,
        process_result: AsyncCompletedProcess,
        target: Path,
    ) -> list[LinterResult]:
        """Parse process output into standardized linter results.

        Args:
            process_result: The completed process with stdout, stderr,
                and return code.
            target: The file or directory that was linted.

        Returns:
            A list of standardized LinterResult objects.
        """

    async def run(self, target: Path) -> list[LinterResult]:
        """Run the linter on the target path asynchronously.

        Args:
            target: The file or directory to lint.

        Returns:
            A list of standardized linter results.

        Raises:
            LinterNotAvailableError: If the linter is not installed.
        """
        # build_command() puts the linter's own name first; resolve_command
        # supplies the real executable, so that element is dropped.
        cmd = self.build_command(target)
        full_cmd = self.resolve_command(cmd[1:])
        if full_cmd is None:
            raise LinterNotAvailableError(
                f"{self.name} is not installed in this environment "
                f"(install it with: pip install 'sanopy[{self.package_name}]')"
            )

        process_result = await self._run_command(full_cmd, Path.cwd())
        results = self.parse_output(process_result, target)

        # A non-zero exit code is usually the linter signalling that it
        # found issues — which is normal. But when it exits non-zero and
        # yields no findings at all, it likely crashed or failed to run;
        # surface that or the scan would look spuriously clean.
        if process_result.returncode != 0 and not results:
            logger.warning(
                "Linter %s exited with code %s and reported no findings; "
                "it may have failed. stderr: %s",
                self.name,
                process_result.returncode,
                process_result.stderr.strip(),
            )

        return results

    def _get_effective_config_path(
        self, target: Path, candidate_filenames: list[str]
    ) -> Path | None:
        """Find the best configuration file for the target.

        Args:
            target: The file or directory being scanned.
            candidate_filenames: Filename candidates for local discovery.

        Returns:
            The path to the effective config file, or None.
        """
        # 1. Check for nearest local config
        local_config = find_nearest_local_config(
            target, candidate_filenames, self.name
        )
        if local_config:
            return local_config

        # 2. Fallback to bundled settings, from the config when available
        #    or the built-in defaults otherwise.
        category = "test" if is_test_path(target) else "default"
        linter_config = None
        if self.config:
            linter_config = self.config.linter_configs.get(self.name.lower())
        if linter_config is None:
            linter_config = DEFAULT_LINTER_CONFIGS.get(self.name.lower())
        if linter_config is not None:
            return materialize_linter_config(
                self.name.lower(), category, linter_config
            )
        return None

    async def _run_command(
        self, cmd: list[str], cwd: Path
    ) -> AsyncCompletedProcess:
        """Helper to run a shell command asynchronously and capture output.

        Args:
            cmd: A list of command arguments.
            cwd: The working directory for the command.

        Returns:
            The completed process instance with output and return code.
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return AsyncCompletedProcess(
            stdout=stdout.decode(encoding="utf-8"),
            stderr=stderr.decode(encoding="utf-8"),
            returncode=process.returncode or 0,
        )
