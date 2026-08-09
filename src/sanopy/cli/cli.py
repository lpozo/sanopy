"""Main entry point for the Sanopy CLI package."""

import asyncio
from pathlib import Path
from typing import Literal, cast

import click
from click.exceptions import Exit

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
    help=(
        "Optional path for JSON results file. "
        "If omitted, JSON is printed to stdout."
    ),
)
@click.option(
    "-r",
    "--human-readable",
    is_flag=True,
    default=False,
    help=(
        "Generate a markdown report for humans "
        "(default: linting-report-<target>.md)."
    ),
)
@click.option(
    "--output-mode",
    type=click.Choice(["machine", "human"], case_sensitive=False),
    default="machine",
    show_default=True,
    help="Choose machine JSON-only output or human terminal output.",
)
# pylint: disable=too-many-arguments,too-many-positional-arguments
def scan(  # vulture: ignore
    targets: tuple[Path, ...],
    only: str | None,
    skip: str | None,
    output: Path | None,
    output_mode: str,
    human_readable: bool,
) -> None:
    """Scan one or more target files or directories.

    TARGETS: Files or directories to analyze.
    """

    selected_output_mode = cast(
        Literal["machine", "human"], output_mode.lower()
    )

    def make_output_path(base: Path, target: Path, suffix: str) -> Path:
        # Use the stem for files and name for directories.
        name = target.stem if target.is_file() else target.name
        return base.parent / f"{base.stem}-{name}{suffix}"

    async def run_all_scans() -> list[int]:
        return await asyncio.gather(
            *[
                handle_scan(
                    target,
                    only,
                    skip,
                    make_output_path(output, target, ".json")
                    if output
                    else None,
                    selected_output_mode,
                    human_readable,
                )
                for target in targets
            ]
        )

    try:
        finding_counts = asyncio.run(run_all_scans())
    except Exception as err:  # pylint: disable=broad-exception-caught
        raise Exit(2) from err

    if sum(finding_counts) > 0:
        raise Exit(1)
