"""Engine to orchestrate multiple linters."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from sanopy.linters.base import BaseLinter
from sanopy.linters.result import LinterResult


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
            asyncio.create_task(linter.run(target)) for linter in self.linters
        ]

        for coro in asyncio.as_completed(tasks):
            try:
                results = await coro
                all_results.extend(results)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                # Log the error but keep results from other linters
                print(f"Linter task failed: {exc}")
            finally:
                if progress_callback:
                    progress_callback()

        return all_results
