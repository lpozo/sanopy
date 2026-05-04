"""Main entry point for the LintAIder CLI package."""

import asyncio
from pathlib import Path

import click

from lintaider.cli.init_handler import handle_init
from lintaider.cli.scan_handler import handle_scan
from lintaider.cli.ui import HUMAN_READABLE_REPORT_FILE, SCAN_RESULT_FILE


@click.group()
def main() -> None:
    """Linting orchestrator for Python projects."""


@main.command()
def init() -> None:  # vulture: ignore
    """Initialize linter defaults for LintAIder."""
    handle_init()


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--only", help="Comma-separated list of linters to run")
@click.option("--skip", help="Comma-separated list of linters to skip")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Path for the JSON results file (default: {SCAN_RESULT_FILE})",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Print a detailed report of every issue found.",
)
@click.option(
    "-r",
    "--human-readable",
    is_flag=True,
    default=False,
    help=(
        "Generate a markdown report for humans "
        f"(default: {HUMAN_READABLE_REPORT_FILE})."
    ),
)
# pylint: disable=too-many-arguments,too-many-positional-arguments
def scan(  # vulture: ignore
    target: Path,
    only: str | None,
    skip: str | None,
    output: Path | None,
    verbose: bool,
    human_readable: bool,
) -> None:
    """Scan a target file or directory and save results.

    TARGET: The file or directory you want to analyze.
    """
    asyncio.run(
        handle_scan(
            target,
            only,
            skip,
            output or SCAN_RESULT_FILE,
            verbose,
            human_readable,
        ),
    )


if __name__ == "__main__":
    main()
