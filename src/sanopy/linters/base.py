"""Abstract base class for all linters."""

from __future__ import annotations

import abc
import asyncio
import shutil
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


@dataclass  # pylint: disable=too-few-public-methods
class AsyncCompletedProcess:
    """Mock-like class for asyncio.subprocess results."""

    stdout: str
    stderr: str
    returncode: int


class BaseLinter(abc.ABC):
    """Abstract base class for all linters."""

    name: str

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the linter.

        Args:
            config: The active configuration, used to resolve bundled
                linter settings. Defaults to ``None``.
        """
        self.config = config

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
        """
        cmd = self.build_command(target)
        prefix = self._get_command_prefix()
        full_cmd = prefix + cmd

        process_result = await self._run_command(full_cmd, Path.cwd())
        return self.parse_output(process_result, target)

    def _get_command_prefix(self) -> list[str]:
        """Check for 'uv' or fall back to the current python executable.

        Returns:
            ["uv", "run"] if uv is present, otherwise [sys.executable, "-m"].
        """
        if shutil.which("uv"):
            return ["uv", "run"]
        return [sys.executable, "-m"]

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
