"""Main entry point for the Sanopy CLI package."""

import asyncio
from pathlib import Path

import click

from sanopy.cli.constants import HUMAN_READABLE_REPORT_FILE, SCAN_RESULT_FILE
from sanopy.cli.init_handler import handle_init
from sanopy.cli.scan_handler import handle_scan


@click.group()
def main() -> None:
    """Linting orchestrator for Python projects."""


@main.command()
@click.option(
    "--only", help="Comma-separated list of linters to run by default"
)
@click.option(
    "--skip", help="Comma-separated list of linters to skip by default"
)
def init(
    only: str | None = None, skip: str | None = None
) -> None:  # vulture: ignore
    """Initialize linter defaults for Sanopy."""
    handle_init(only=only, skip=skip)


@main.command()
@click.argument(
    "targets", nargs=-1, type=click.Path(exists=True, path_type=Path)
)
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
    targets: tuple[Path, ...],
    only: str | None,
    skip: str | None,
    output: Path | None,
    verbose: bool,
    human_readable: bool,
) -> None:
    """Scan one or more target files o directorios y guarda los resultados.

    TARGETS: Archivos o directorios a analizar.
    """

    def make_output_path(base: Path, target: Path, suffix: str) -> Path:
        # Use the stem for files, name for directories, fallback to str(target)
        name = target.stem if target.is_file() else target.name
        return base.parent / f"{base.stem}-{name}{suffix}"

    async def run_all_scans() -> None:
        await asyncio.gather(
            *[
                handle_scan(
                    target,
                    only,
                    skip,
                    make_output_path(
                        output or SCAN_RESULT_FILE, target, ".json"
                    ),
                    verbose,
                    human_readable,
                    # El human_readable se ajusta dentro de handle_scan
                )
                for target in targets
            ]
        )

    asyncio.run(run_all_scans())
