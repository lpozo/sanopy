"""Main entry point for the Sanopy CLI package."""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, cast

import click
from click.exceptions import Exit
from rich.markup import escape

from sanopy.cli.init_handler import handle_init
from sanopy.cli.scan_handler import handle_scan, preflight
from sanopy.cli.ui import console, err_console


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
@click.option(
    "--no-install",
    is_flag=True,
    default=False,
    help="Write the config only; never install missing linter packages.",
)
def init(  # vulture: ignore
    only: str | None = None,
    skip: str | None = None,
    no_install: bool = False,
) -> None:
    """Initialize linter defaults for Sanopy.

    Offers to install any selected linter that is not yet available.
    Exits 2 if an installation fails.
    """
    handle_init(only=only, skip=skip, no_install=no_install)


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

    Requires a .sanopy.toml in the current directory; run 'sanopy init'
    first. Findings go to stdout as JSON, diagnostics to stderr.

    Exit codes: 0 no findings, 1 findings reported, 2 could not run
    (missing or invalid config, a linter is not installed, or the
    filters select no linters).
    """

    selected_output_mode = cast(
        Literal["machine", "human"], output_mode.lower()
    )

    def make_output_path(base: Path, target: Path, suffix: str) -> Path:
        # Use the stem for files and name for directories.
        name = target.stem if target.is_file() else target.name
        return base.parent / f"{base.stem}-{name}{suffix}"

    # Validate config and linter availability once for the whole run, so a
    # multi-target scan reports a problem once instead of once per target.
    config, active_linters = preflight(only, skip)

    async def run_all_scans() -> list[tuple[int, str | None]]:
        return await asyncio.gather(
            *[
                handle_scan(
                    target,
                    config,
                    active_linters,
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
        scan_outputs = asyncio.run(run_all_scans())
    except Exception as err:  # pylint: disable=broad-exception-caught
        # Report the cause on stderr; exiting 2 silently makes scan
        # failures indistinguishable from a clean run in automation.
        err_console.print(f"[red]Scan failed:[/red] {escape(str(err))}")
        raise Exit(2) from err

    _write_stdout_payloads([doc for _, doc in scan_outputs if doc is not None])

    if sum(count for count, _ in scan_outputs) > 0:
        raise Exit(1)


def _write_stdout_payloads(stdout_docs: list[str]) -> None:
    """Write machine-mode JSON to stdout as a single valid document.

    With a single target the original per-target envelope is emitted
    unchanged. With several targets the envelopes are merged into one
    document so the output remains valid JSON.
    """
    if not stdout_docs:
        return

    if len(stdout_docs) == 1:
        console.file.write(stdout_docs[0] + "\n")
        return

    payloads = [json.loads(doc) for doc in stdout_docs]
    console.file.write(json.dumps(_merge_payloads(payloads), indent=2) + "\n")


def _merge_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-target scan payloads into a single JSON document."""
    first_run = payloads[0]["run"]
    return {
        "schema_version": payloads[0]["schema_version"],
        "run": {
            "target": [p["run"]["target"] for p in payloads],
            "generated_at": first_run["generated_at"],
            "active_linters": first_run["active_linters"],
            "finding_count": sum(p["run"]["finding_count"] for p in payloads),
        },
        "findings": [
            finding for payload in payloads for finding in payload["findings"]
        ],
    }
