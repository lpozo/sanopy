"""Engine to orchestrate multiple linters."""

import asyncio
import logging
import traceback
from collections.abc import Callable
from pathlib import Path

from sanopy.linters.base import BaseLinter
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
        self, target: Path, progress_callback: Callable[[], None] | None = None
    ) -> list[LinterResult]:
        """Run all configured linters on the target in parallel using asyncio.

        Args:
            target: The file or directory to scan.
            progress_callback: Optional callable called when a linter finishes.

        Returns:
            A combined list of all linter results.
        """
        all_results: list[LinterResult] = []

        tasks = [
            (linter, asyncio.create_task(linter.run(target)))
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

        return all_results
