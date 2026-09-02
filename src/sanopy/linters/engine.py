"""Engine to orchestrate multiple linters."""

import asyncio
import logging
import traceback
from collections.abc import Callable
from pathlib import Path

from sanopy.linters.base import BaseLinter
from sanopy.linters.config_discovery import cleanup_materialized_configs
from sanopy.linters.result import LinterResult

logger = logging.getLogger(__name__)


class Engine:
    """Orchestrator to run multiple linters."""

    # pylint: disable=too-few-public-methods

    def __init__(self, linters: list[BaseLinter]) -> None:
        """Initialise the engine with a list of linters.

        Args:
            linters: A list of linter instances to execute.
        """
        self.linters = linters

    async def run_all(
        self,
        target: Path,
        progress_callback: Callable[[], None] | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> list[LinterResult]:
        """Run all configured linters on the target in parallel using asyncio.

        Args:
            target: The file or directory to scan.
            progress_callback: Optional callable called when a linter finishes.
            semaphore: Optional shared semaphore to cap total concurrency
                across targets. When given, a linter acquires it before
                launching its subprocess, so a multi-target scan cannot
                spawn unbounded concurrent subprocesses.

        Returns:
            A combined list of all linter results.
        """
        all_results: list[LinterResult] = []

        async def run_one(linter: BaseLinter) -> list[LinterResult]:
            if semaphore is None:
                return await linter.run(target)
            async with semaphore:
                return await linter.run(target)

        tasks = [
            (linter, asyncio.create_task(run_one(linter)))
            for linter in self.linters
        ]

        for linter, task in tasks:
            try:
                results = await task
                all_results.extend(results)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                # Log the error with the linter's identity and a traceback
                # so failures are debuggable, but keep results from other
                # linters. Diagnostics go to a logger (wired to stderr),
                # never stdout, so they cannot corrupt the JSON document
                # machine mode writes.
                logger.error(
                    "Linter %s failed with %s:\n%s",
                    linter.name,
                    type(exc).__name__,
                    traceback.format_exc(),
                )
            finally:
                if progress_callback:
                    progress_callback()

        # The temp config files each linter materialized in build_command
        # were consumed by the subprocesses above; now they can be removed.
        cleanup_materialized_configs()

        return all_results
